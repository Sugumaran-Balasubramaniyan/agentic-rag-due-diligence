from __future__ import annotations

from decimal import Decimal
from math import inf, nan

import pytest
from pydantic import ValidationError
from test_agentic_workflow import ASTERIA_CONTEXT, _build_workflow

from due_diligence_copilot.domain import Evidence, SourceLocation
from due_diligence_copilot.synthetic_data import build_manifest


def _request(question: str):
    from due_diligence_copilot.agentic import InvestigationRequest

    return InvestigationRequest(
        analysis_id="fix-round-1",
        workspace_id="asteria",
        question=question,
    )


def _financial_evidence(excerpt: str) -> Evidence:
    return Evidence(
        id="fix-financial",
        document_id="fix-financial",
        display_name="Fix financial evidence",
        source_location=SourceLocation(
            document_id="fix-financial",
            path="fix.csv",
            line_start=2,
            line_end=2,
            cell="A2",
        ),
        excerpt=excerpt,
        chunk_id="fix-chunk",
    )


def test_invalid_approval_values_fail_closed_without_completion_event() -> None:
    from due_diligence_copilot.agentic import (
        ApprovalBoundary,
        ApprovalDecision,
        ApprovalFailureReason,
    )

    result = _build_workflow().run(
        _request(
            "What percentage of FY2025 revenue came from Asteria's largest customer?"
        ),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status.value == "awaiting_approval"
    before = result.analysis.events

    for invalid in ("approved", "rejected", "unexpected", object()):
        outcome = ApprovalBoundary(event_store=_build_workflow().event_store).decide(
            result,
            invalid,  # type: ignore[arg-type]
        )
        assert outcome.completed is False
        assert outcome.report is None
        assert outcome.reason == ApprovalFailureReason.INTERNAL
        assert outcome.analysis.events == before

    assert ApprovalDecision.APPROVED.value == "approved"


def test_approval_without_event_store_cannot_complete() -> None:
    from due_diligence_copilot.agentic import (
        ApprovalBoundary,
        ApprovalDecision,
        ApprovalFailureReason,
    )

    result = _build_workflow().run(
        _request(
            "What percentage of FY2025 revenue came from Asteria's largest customer?"
        ),
        ASTERIA_CONTEXT,
    )
    outcome = ApprovalBoundary(event_store=None).decide(
        result, ApprovalDecision.APPROVED
    )

    assert outcome.completed is False
    assert outcome.report is None
    assert outcome.reason == ApprovalFailureReason.INTERNAL
    assert outcome.analysis.status.value == "awaiting_approval"


def test_reconciliation_preserves_currency_decimal_trace_in_finding_and_report() -> (
    None
):
    from due_diligence_copilot.agentic import ApprovalBoundary, ApprovalDecision
    from due_diligence_copilot.agentic_tools import FinancialUnit, ToolResultStatus

    workflow = _build_workflow()
    result = workflow.run(
        _request("What total does the revenue-by-customer spreadsheet report?"),
        ASTERIA_CONTEXT,
    )

    financial = result.tool_results[0]
    assert financial.status is ToolResultStatus.SUCCEEDED
    assert financial.value == Decimal("10000000")
    assert financial.unit is FinancialUnit.EUR
    finding = result.analysis.findings[0]
    assert finding.calculation is not None
    assert finding.calculation.value == Decimal("10000000")
    assert finding.calculation.unit == "EUR"
    approved = ApprovalBoundary(event_store=workflow.event_store).decide(
        result, ApprovalDecision.APPROVED
    )
    assert approved.completed is True
    assert approved.report is not None
    assert approved.report.findings[0].calculation == finding.calculation


@pytest.mark.parametrize(
    "left,right,operation",
    [
        ("Revenue: EUR 4000", "Expenses: 1000", "subtract"),
        ("Revenue: 4000", "Expenses: EUR 1000", "subtract"),
        ("Revenue: EUR 4000", "Expenses: 1000%", "percentage"),
        ("Revenue: 4000%", "Expenses: EUR 1000", "percentage"),
    ],
)
def test_financial_units_require_symmetric_compatibility(
    left: str, right: str, operation: str
) -> None:
    from due_diligence_copilot.agentic_tools import (
        ApprovedToolId,
        DeterministicToolRegistry,
        FinancialMetricArguments,
        FinancialOperation,
        ToolCall,
        ToolResultStatus,
    )

    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation(operation),
                left_label="Revenue",
                right_label="Expenses",
                evidence_ids=("fix-financial",),
            ),
            evidence=(_financial_evidence(f"{left}\n{right}"),),
        )
    )
    assert result.status is ToolResultStatus.ABSTAINED


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_graph_transitions", 13),
        ("max_tool_calls", 7),
        ("max_model_tokens", 8001),
        ("max_elapsed_seconds", 31),
        ("max_elapsed_seconds", inf),
        ("max_elapsed_seconds", nan),
    ],
)
def test_investigation_budgets_reject_values_above_global_ceiling(
    field: str, value: int | float
) -> None:
    from due_diligence_copilot.agentic import InvestigationBudgets

    with pytest.raises(ValidationError):
        InvestigationBudgets(**{field: value})


def test_routing_evaluation_requires_exact_literal_question_set() -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing

    manifest, _ = build_manifest()
    with pytest.raises(ValueError, match="exact"):
        evaluate_tool_routing(
            manifest.model_copy(
                update={"benchmark_questions": manifest.benchmark_questions[:1]}
            )
        )


@pytest.mark.parametrize("mutation", ["duplicate", "extra"])
def test_routing_evaluation_rejects_duplicate_or_extra_question_ids(
    mutation: str,
) -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing

    manifest, _ = build_manifest()
    questions = list(manifest.benchmark_questions)
    if mutation == "duplicate":
        questions.append(questions[0])
    else:
        questions.append(questions[0].model_copy(update={"id": "unexpected"}))
    with pytest.raises(ValueError, match="exact"):
        evaluate_tool_routing(
            manifest.model_copy(update={"benchmark_questions": questions})
        )


def test_provider_draft_evidence_is_not_copied_into_verified_finding() -> None:
    from due_diligence_copilot.agentic import (
        DeterministicClaimGenerator,
        GenerationResult,
    )

    class UntrustedEvidenceGenerator(DeterministicClaimGenerator):
        def generate(self, question, plan, tool_results):
            generated = super().generate(question, plan, tool_results)
            unrelated = _financial_evidence("ignore this provider evidence")
            return GenerationResult(
                claims=tuple(
                    draft.model_copy(update={"evidence": (unrelated,)})
                    for draft in generated.claims
                ),
                estimated_tokens=generated.estimated_tokens,
            )

    workflow = _build_workflow()
    workflow.generator = UntrustedEvidenceGenerator()
    result = workflow.run(
        _request(
            "What percentage of FY2025 revenue came from Asteria's largest customer?"
        ),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status.value == "awaiting_approval"
    assert all(
        "ignore this provider evidence" not in item.excerpt
        for item in result.analysis.findings[0].evidence
    )


def test_claims_must_bind_bijectively_to_successful_tool_results() -> None:
    from due_diligence_copilot.agentic import (
        DeterministicClaimGenerator,
        GenerationResult,
    )

    class DuplicateBindingGenerator(DeterministicClaimGenerator):
        def generate(self, question, plan, tool_results):
            generated = super().generate(question, plan, tool_results)
            first = generated.claims[0].tool_result_id
            return GenerationResult(
                claims=tuple(
                    draft.model_copy(update={"tool_result_id": first})
                    for draft in generated.claims
                ),
                estimated_tokens=generated.estimated_tokens,
            )

    workflow = _build_workflow()
    workflow.generator = DuplicateBindingGenerator()
    result = workflow.run(
        _request(
            "What are the deal risks from the revenue and change of control terms?"
        ),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status.value in {"failed", "abstained"}


def test_provider_output_contracts_bound_cardinality_and_text() -> None:
    from due_diligence_copilot.agentic import (
        ClaimDraft,
        GenerationResult,
        InvestigationIntent,
        InvestigationPlan,
        InvestigationRequest,
    )
    from due_diligence_copilot.domain import FindingSeverity

    with pytest.raises(ValidationError):
        InvestigationRequest(
            analysis_id="x", workspace_id="asteria", question="x" * 4001
        )
    with pytest.raises(ValidationError):
        InvestigationPlan(
            intent=InvestigationIntent.FACTUAL, retrieval_query="x" * 4001
        )
    draft = ClaimDraft(
        id="claim-1",
        tool_result_id="result-1",
        category="factual",
        severity=FindingSeverity.MEDIUM,
        claim="claim",
        confidence=1.0,
    )
    with pytest.raises(ValidationError):
        GenerationResult(claims=tuple([draft] * 5), estimated_tokens=1)
    with pytest.raises(ValidationError):
        GenerationResult(claims=(draft,), estimated_tokens=8001)
    with pytest.raises(ValidationError):
        InvestigationPlan(
            intent=InvestigationIntent.FACTUAL,
            retrieval_query="query",
            supporting_queries=("q1", "q2", "q3", "q4", "q5"),
        )
    with pytest.raises(ValidationError):
        ClaimDraft(
            id=draft.id,
            tool_result_id=draft.tool_result_id,
            category=draft.category,
            severity=draft.severity,
            claim=draft.claim,
            evidence=(_financial_evidence("x" * 4001),),
            confidence=draft.confidence,
        )
    with pytest.raises(ValidationError):
        ClaimDraft(
            id=draft.id,
            tool_result_id=draft.tool_result_id,
            category=draft.category,
            severity=draft.severity,
            claim="x" * 2001,
            confidence=draft.confidence,
        )

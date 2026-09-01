from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_agentic_workflow import ASTERIA_CONTEXT, _build_workflow

from due_diligence_copilot.agentic import (
    ClaimDraft,
    GenerationResult,
    InvestigationRequest,
    _provenance_token,
)
from due_diligence_copilot.agentic_tools import (
    ApprovedToolId,
    DeterministicToolRegistry,
    FinancialMetricArguments,
    FinancialMetricResult,
    FinancialOperation,
    FinancialUnit,
    ToolCall,
    ToolResultStatus,
)
from due_diligence_copilot.domain import (
    AgentEvent,
    AnalysisState,
    AnalysisStatus,
    ApprovalState,
    CalculationTrace,
    Evidence,
    Finding,
    FindingSeverity,
    Report,
    SourceLocation,
    VerificationStatus,
)

QUESTION = "What percentage of FY2025 revenue came from Asteria's largest customer?"
RISK_QUESTION = (
    "What deal risk combines customer concentration with change-of-control consent?"
)
PROVENANCE_KEY = b"task-5-fix-round-4-test-key"


def _request(question: str, analysis_id: str = "fix-round-4") -> InvestigationRequest:
    return InvestigationRequest(
        analysis_id=analysis_id, workspace_id="asteria", question=question
    )


def _signed(result):
    return result.model_copy(
        update={"provenance_token": _provenance_token(result, PROVENANCE_KEY)}
    )


def _approved_result(question: str = QUESTION, analysis_id: str = "fix-round-4"):
    workflow = _build_workflow()
    workflow.provenance_key = PROVENANCE_KEY
    result = workflow.run(_request(question, analysis_id), ASTERIA_CONTEXT)
    assert result.analysis.status is AnalysisStatus.AWAITING_APPROVAL
    return workflow, result


def _evidence() -> Evidence:
    return Evidence(
        id="evidence-round-4",
        document_id="document-round-4",
        display_name="Round 4 document",
        source_location=SourceLocation(
            document_id="document-round-4", path="round-4.md", line_start=1
        ),
        excerpt="Revenue: 1",
        chunk_id="chunk-round-4",
    )


def _tool_call(evidence: Evidence | None = None) -> ToolCall:
    item = evidence or _evidence()
    return ToolCall(
        tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
        arguments=FinancialMetricArguments(
            operation=FinancialOperation.REPORTED_VALUE,
            left_label="Revenue",
            evidence_ids=(item.id,),
        ),
        evidence=(item,),
    )


def _tool_result(evidence: Evidence | None = None) -> FinancialMetricResult:
    item = evidence or _evidence()
    return FinancialMetricResult(
        id="tool-result-1",
        status=ToolResultStatus.SUCCEEDED,
        value=Decimal("1"),
        unit=FinancialUnit.UNITLESS,
        claim="Revenue: 1",
        evidence=(item,),
        primary_evidence=(item,),
    )


def _finding(
    evidence: Evidence | None = None,
    *,
    finding_id: str = "finding-1",
    tool_result_id: str = "tool-result-1",
) -> Finding:
    item = evidence or _evidence()
    return Finding(
        id=finding_id,
        category="financial",
        severity=FindingSeverity.MEDIUM,
        claim="Revenue: 1",
        evidence=[item],
        confidence=1.0,
        verification_status=VerificationStatus.VERIFIED,
        tool_result_id=tool_result_id,
    )


def test_workflow_rejects_a_result_subclass_for_an_approved_tool_id() -> None:
    from due_diligence_copilot.agentic import FailureCode

    class DerivedFinancialMetricResult(FinancialMetricResult):
        pass

    class SubclassRegistry:
        def execute(self, call: ToolCall):
            result = DeterministicToolRegistry().execute(call)
            return DerivedFinancialMetricResult.model_validate(result.model_dump())

    workflow = _build_workflow()
    workflow.tools = SubclassRegistry()
    result = workflow.run(_request(QUESTION), ASTERIA_CONTEXT)

    assert result.analysis.status is AnalysisStatus.FAILED
    assert result.failure is not None
    assert result.failure.code is FailureCode.INTERNAL_INVARIANT
    assert result.tool_results == ()


def test_approval_rejects_same_id_citation_with_an_altered_fingerprint() -> None:
    from due_diligence_copilot.agentic import ApprovalBoundary, ApprovalDecision

    workflow, result = _approved_result(analysis_id="altered-citation")
    tool_result = result.tool_results[0]
    primary = tool_result.primary_evidence[0]
    altered = primary.model_copy(update={"excerpt": "Altered same-ID citation"})
    altered_result = tool_result.model_copy(update={"primary_evidence": (altered,)})
    altered_finding = result.analysis.findings[0].model_copy(
        update={"evidence": [altered]}
    )
    forged = result.model_copy(
        update={
            "tool_results": (altered_result,),
            "analysis": result.analysis.model_copy(
                update={"findings": (altered_finding,)}
            ),
        }
    )

    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(forged), ApprovalDecision.APPROVED)

    assert outcome.completed is False
    assert outcome.report is None


def test_approval_rejects_duplicate_tool_result_ids_independently() -> None:
    from due_diligence_copilot.agentic import ApprovalBoundary, ApprovalDecision

    workflow, result = _approved_result(RISK_QUESTION, "duplicate-results")
    first_result, second_result = result.tool_results
    duplicate_second = second_result.model_copy(update={"id": first_result.id})
    second_finding = result.analysis.findings[1].model_copy(
        update={"tool_result_id": first_result.id}
    )
    forged = result.model_copy(
        update={
            "tool_results": (first_result, duplicate_second),
            "analysis": result.analysis.model_copy(
                update={"findings": (second_finding,)}
            ),
        }
    )

    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(forged), ApprovalDecision.APPROVED)

    assert outcome.completed is False
    assert outcome.report is None


def test_approval_rejects_duplicate_finding_ids_independently() -> None:
    from due_diligence_copilot.agentic import ApprovalBoundary, ApprovalDecision

    workflow, result = _approved_result(RISK_QUESTION, "duplicate-findings")
    first_finding, second_finding = result.analysis.findings
    duplicate_second = second_finding.model_copy(update={"id": first_finding.id})
    forged = result.model_copy(
        update={
            "analysis": result.analysis.model_copy(
                update={"findings": (first_finding, duplicate_second)}
            )
        }
    )

    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(forged), ApprovalDecision.APPROVED)

    assert outcome.completed is False
    assert outcome.report is None


def test_approval_rejects_a_successful_result_without_a_lineage_finding() -> None:
    from due_diligence_copilot.agentic import ApprovalBoundary, ApprovalDecision

    workflow, result = _approved_result(RISK_QUESTION, "missing-lineage")
    first_result, second_result = result.tool_results
    unrepresented_first = first_result.model_copy(
        update={"status": ToolResultStatus.ABSTAINED}
    )
    forged = result.model_copy(
        update={
            "tool_results": (unrepresented_first, second_result),
            "analysis": result.analysis.model_copy(
                update={"findings": (result.analysis.findings[1],)}
            ),
        }
    )

    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(forged), ApprovalDecision.APPROVED)

    assert outcome.completed is False
    assert outcome.report is None


def test_routing_evaluation_ignores_mutation_of_public_expectations(
    monkeypatch,
) -> None:
    import due_diligence_copilot.agentic_evaluation as evaluation_module
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing
    from due_diligence_copilot.synthetic_data import build_manifest

    manifest, _ = build_manifest()
    monkeypatch.setitem(
        evaluation_module.LITERAL_TOOL_ROUTING, "revenue-concentration", ()
    )

    evaluation = evaluate_tool_routing(manifest)

    scenario = next(
        item
        for item in evaluation.scenarios
        if item.question_id == "revenue-concentration"
    )
    assert scenario.expected_tool_ids == (ApprovedToolId.CALCULATE_FINANCIAL_METRIC,)
    assert evaluation.correct_count == evaluation.scenario_count


def test_tool_and_finding_collections_have_explicit_cardinality_bounds() -> None:
    from due_diligence_copilot.agentic import InvestigationResult

    evidence = _evidence()
    call = _tool_call(evidence)
    result = _tool_result(evidence)
    finding = _finding(evidence)
    analysis = AnalysisState(
        analysis_id="analysis-round-4",
        workspace_id="asteria",
        question="question",
        status=AnalysisStatus.AWAITING_APPROVAL,
    )

    with pytest.raises(ValidationError):
        Finding.model_validate(
            {
                **finding.model_dump(),
                "evidence": [evidence] * 11,
            }
        )
    with pytest.raises(ValidationError):
        AnalysisState.model_validate(
            {
                **analysis.model_dump(),
                "findings": [finding] * 5,
            }
        )
    with pytest.raises(ValidationError):
        InvestigationResult(
            analysis=analysis,
            retrieved_chunk_ids=tuple(f"chunk-{index}" for index in range(51)),
            budget={"graph_transitions": 0, "tool_calls": 0, "model_tokens": 0},
        )
    with pytest.raises(ValidationError):
        InvestigationResult(
            analysis=analysis,
            tool_calls=(call,) * 5,
            budget={"graph_transitions": 0, "tool_calls": 0, "model_tokens": 0},
        )
    with pytest.raises(ValidationError):
        InvestigationResult(
            analysis=analysis,
            tool_results=(result,) * 5,
            budget={"graph_transitions": 0, "tool_calls": 0, "model_tokens": 0},
        )
    with pytest.raises(ValidationError):
        Report(
            id="report-round-4",
            workspace_id="asteria",
            title="Round 4",
            status=AnalysisStatus.COMPLETED,
            findings=[finding] * 5,
            approval_state=ApprovalState.APPROVED,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FinancialMetricArguments(
            operation=FinancialOperation.REPORTED_VALUE,
            left_label="Revenue",
            evidence_ids=("x" * 129,),
        ),
        lambda: Finding(
            id="x" * 129,
            category="financial",
            severity=FindingSeverity.MEDIUM,
            claim="claim",
            confidence=1.0,
            verification_status=VerificationStatus.VERIFIED,
        ),
        lambda: Finding(
            id="finding",
            category="x" * 65,
            severity=FindingSeverity.MEDIUM,
            claim="claim",
            confidence=1.0,
            verification_status=VerificationStatus.VERIFIED,
        ),
        lambda: Finding(
            id="finding",
            category="financial",
            severity=FindingSeverity.MEDIUM,
            claim="x" * 2001,
            confidence=1.0,
            verification_status=VerificationStatus.VERIFIED,
        ),
        lambda: CalculationTrace(
            operation="x" * 65,
            value=Decimal("1"),
            unit="unitless",
            tool_result_id="result",
        ),
        lambda: AgentEvent(
            sequence=1,
            node="x" * 65,
            status="completed",
            duration_ms=0,
            summary="summary",
        ),
        lambda: AgentEvent(
            sequence=1,
            node="node",
            status="completed",
            duration_ms=0,
            summary="x" * 257,
        ),
        lambda: AnalysisState(
            analysis_id="x" * 129,
            workspace_id="asteria",
            question="question",
            status=AnalysisStatus.AWAITING_APPROVAL,
        ),
        lambda: AnalysisState(
            analysis_id="analysis",
            workspace_id="asteria",
            question="x" * 4001,
            status=AnalysisStatus.AWAITING_APPROVAL,
        ),
        lambda: Report(
            id="report",
            workspace_id="asteria",
            title="title",
            status=AnalysisStatus.COMPLETED,
            unresolved_questions=["x" * 4001],
            approval_state=ApprovalState.APPROVED,
        ),
    ],
)
def test_nested_tool_and_finding_strings_are_bounded(factory) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_tool_result_primary_evidence_collection_is_bounded() -> None:
    evidence = _evidence()

    with pytest.raises(ValidationError):
        FinancialMetricResult(
            status=ToolResultStatus.SUCCEEDED,
            unit=FinancialUnit.UNITLESS,
            evidence=(evidence,),
            primary_evidence=(evidence,) * 11,
        )


def test_claim_generation_collection_is_bounded() -> None:
    draft = ClaimDraft(
        id="claim-1",
        tool_result_id="result-1",
        category="financial",
        severity=FindingSeverity.MEDIUM,
        claim="claim",
        confidence=1.0,
    )

    with pytest.raises(ValidationError):
        GenerationResult(claims=(draft,) * 5, estimated_tokens=1)

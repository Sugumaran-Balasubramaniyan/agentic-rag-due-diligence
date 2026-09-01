from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_agentic_workflow import ASTERIA_CONTEXT, _build_workflow

from due_diligence_copilot.domain import (
    AnalysisState,
    AnalysisStatus,
    Evidence,
    Finding,
    FindingSeverity,
    SourceLocation,
    VerificationStatus,
)
from due_diligence_copilot.synthetic_data import build_manifest


def _request(question: str):
    from due_diligence_copilot.agentic import InvestigationRequest

    return InvestigationRequest(
        analysis_id="fix-round-2", workspace_id="asteria", question=question
    )


def test_forged_awaiting_verified_state_cannot_be_approved() -> None:
    from due_diligence_copilot.adapters import InMemoryAnalysisEventStore
    from due_diligence_copilot.agentic import (
        ApprovalBoundary,
        ApprovalDecision,
        ApprovalFailureReason,
        BudgetUsage,
        InvestigationResult,
    )

    evidence = Evidence(
        id="forged-evidence",
        document_id="forged-document",
        display_name="Forged document",
        source_location=SourceLocation(
            document_id="forged-document", path="forged.md", line_start=1
        ),
        excerpt="Forged provider claim",
        chunk_id="forged-chunk",
    )
    analysis = AnalysisState(
        analysis_id="forged",
        workspace_id="asteria",
        question="forged question",
        status=AnalysisStatus.AWAITING_APPROVAL,
        findings=(
            Finding(
                id="finding-forged",
                category="factual",
                severity=FindingSeverity.HIGH,
                claim="Forged provider claim",
                evidence=[evidence],
                confidence=1.0,
                verification_status=VerificationStatus.VERIFIED,
            ),
        ),
    )
    result = InvestigationResult(analysis=analysis, budget=BudgetUsage())
    store = InMemoryAnalysisEventStore()
    outcome = ApprovalBoundary(event_store=store).decide(
        result, ApprovalDecision.APPROVED
    )

    assert outcome.completed is False
    assert outcome.report is None
    assert outcome.reason == ApprovalFailureReason.INTERNAL
    assert outcome.analysis.status is AnalysisStatus.AWAITING_APPROVAL
    assert store.list_events("asteria", "forged") == ()


@pytest.mark.parametrize("mixed", [False, True])
def test_provider_contradiction_category_cannot_bypass_independent_support(
    mixed: bool,
) -> None:
    from due_diligence_copilot.agentic import (
        DeterministicClaimGenerator,
        GenerationResult,
    )

    class ForgedContradictionGenerator(DeterministicClaimGenerator):
        def generate(self, question, plan, tool_results):
            generated = super().generate(question, plan, tool_results)
            claims = list(generated.claims)
            index = 1 if mixed else 0
            draft = claims[index]
            claims[index] = draft.model_copy(
                update={
                    "category": "contradiction",
                    "claim": (
                        "The cited evidence proves an unrelated fabricated "
                        "contradiction."
                    ),
                }
            )
            return GenerationResult(
                claims=tuple(claims), estimated_tokens=generated.estimated_tokens
            )

    workflow = _build_workflow()
    workflow.generator = ForgedContradictionGenerator()
    question = (
        "What are the deal risks from the revenue and change of control terms?"
        if mixed
        else "What percentage of FY2025 revenue came from Asteria's largest customer?"
    )
    result = workflow.run(_request(question), ASTERIA_CONTEXT)

    assert result.analysis.status is AnalysisStatus.ABSTAINED
    assert result.analysis.findings == ()


@pytest.mark.parametrize(
    "field,initial,mutated",
    [
        ("max_graph_transitions", 1, 99),
        ("max_tool_calls", 1, 99),
        ("max_model_tokens", 1, 99),
        ("max_elapsed_seconds", 0, 99),
    ],
)
def test_mutated_public_budgets_cannot_raise_execution_ceiling(
    field: str, initial: int | float, mutated: int | float
) -> None:
    from due_diligence_copilot.agentic import (
        BoundedInvestigationWorkflow,
        FailureCode,
        InvestigationBudgets,
    )

    base = _build_workflow()
    workflow = BoundedInvestigationWorkflow(
        base.retriever,
        base.documents,
        budgets=InvestigationBudgets(**{field: initial}),
    )
    workflow.budgets = workflow.budgets.model_copy(update={field: mutated})
    question = (
        "What deal risk combines customer concentration with change-of-control consent?"
        if field == "max_tool_calls"
        else "What percentage of FY2025 revenue came from Asteria's largest customer?"
    )
    result = workflow.run(_request(question), ASTERIA_CONTEXT)

    assert result.budget.graph_transitions <= 12
    assert result.budget.tool_calls <= 6
    assert result.budget.model_tokens <= 8000
    assert result.budget.elapsed_seconds <= 30
    assert result.failure is not None
    expected = {
        "max_graph_transitions": FailureCode.BUDGET_GRAPH_TRANSITIONS,
        "max_tool_calls": FailureCode.BUDGET_TOOL_CALLS,
        "max_model_tokens": FailureCode.BUDGET_MODEL_TOKENS,
    }
    if field in expected:
        assert result.failure.code is expected[field]


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: __import__(
            "due_diligence_copilot.agentic_tools", fromlist=["FinancialMetricArguments"]
        ).FinancialMetricArguments(
            operation="reported_value", left_label="x" * 1001, evidence_ids=("x",)
        ),
        lambda: __import__(
            "due_diligence_copilot.agentic", fromlist=["ContradictionPlanInput"]
        ).ContradictionPlanInput(subject="x" * 1001),
        lambda: __import__(
            "due_diligence_copilot.agentic", fromlist=["MissingDocumentPlanInput"]
        ).MissingDocumentPlanInput(document_name="x" * 1001),
    ],
)
def test_nested_provider_strings_are_bounded(constructor) -> None:
    with pytest.raises(ValidationError):
        constructor()


def test_tool_results_are_revalidated_before_stable_id_assignment() -> None:
    from due_diligence_copilot.agentic_tools import FinancialMetricResult

    result = FinancialMetricResult(
        status="succeeded", unit="unitless", value=Decimal("1"), claim="claim"
    ).model_copy(update={"claim": "x" * 4001})
    with pytest.raises(ValidationError):
        FinancialMetricResult.model_validate(result.model_dump())


def test_planner_usage_is_based_on_bounded_serialized_output_size() -> None:
    from due_diligence_copilot.agentic import InvestigationPlan

    class VerbosePlanner:
        def plan(self, question, classification):
            del question, classification
            return InvestigationPlan(
                intent="factual", retrieval_query="bounded output " + "x" * 1000
            )

    workflow = _build_workflow()
    workflow.planner = VerbosePlanner()
    result = workflow.run(
        _request("What was Asteria's FY2025 revenue?"), ASTERIA_CONTEXT
    )

    assert result.budget.model_tokens > 64
    assert result.budget.model_tokens <= 8000


@pytest.mark.parametrize("field", ["question", "category", "answer", "evidence"])
def test_routing_evaluation_rejects_canonical_manifest_mutation(field: str) -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing

    manifest, _ = build_manifest()
    question = manifest.benchmark_questions[0]
    if field == "question":
        changed = question.model_copy(
            update={"question": question.question + " altered"}
        )
    elif field == "category":
        changed = question.model_copy(update={"category": "unsupported"})
    elif field == "answer":
        answer = question.expected_answer.model_copy(update={"answer": "altered"})
        changed = question.model_copy(update={"expected_answer": answer})
    else:
        evidence = question.expected_evidence[0].model_copy(
            update={"literal": "altered"}
        )
        changed = question.model_copy(update={"expected_evidence": [evidence]})
    questions = [changed, *manifest.benchmark_questions[1:]]

    with pytest.raises(ValueError, match="canonical"):
        evaluate_tool_routing(
            manifest.model_copy(update={"benchmark_questions": questions})
        )

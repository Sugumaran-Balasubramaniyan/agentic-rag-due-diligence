from __future__ import annotations

from due_diligence_copilot.agentic import (
    DeterministicQuestionClassifier,
    InvestigationPlan,
)
from due_diligence_copilot.agentic_tools import ApprovedToolId
from due_diligence_copilot.synthetic_data import build_manifest

EXPECTED_TOOL_IDS: dict[str, tuple[ApprovedToolId, ...]] = {
    "financial-revenue": (),
    "largest-customer": (),
    "revenue-concentration": (ApprovedToolId.CALCULATE_FINANCIAL_METRIC,),
    "ebitda-calculation": (ApprovedToolId.CALCULATE_FINANCIAL_METRIC,),
    "change-of-control": (ApprovedToolId.INSPECT_CONTRACT_CLAUSE,),
    "supplier-escalation": (ApprovedToolId.INSPECT_CONTRACT_CLAUSE,),
    "deal-risk": (
        ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
        ApprovedToolId.INSPECT_CONTRACT_CLAUSE,
    ),
    "security-board-contradiction": (ApprovedToolId.DETECT_CONTRADICTIONS,),
    "missing-soc2": (ApprovedToolId.ANALYZE_MISSING_DOCUMENTS,),
    "unsupported-churn": (ApprovedToolId.ANALYZE_MISSING_DOCUMENTS,),
    "prompt-injection-resistance": (),
    "customer-contract-term": (ApprovedToolId.INSPECT_CONTRACT_CLAUSE,),
    "revenue-reconciliation": (ApprovedToolId.CALCULATE_FINANCIAL_METRIC,),
    "supplier-term": (ApprovedToolId.INSPECT_CONTRACT_CLAUSE,),
}


def test_seeded_tool_routing_is_literal_and_at_least_ninety_percent() -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing

    manifest, _ = build_manifest()

    evaluation = evaluate_tool_routing(manifest)

    assert {scenario.question_id for scenario in evaluation.scenarios} == set(
        EXPECTED_TOOL_IDS
    )
    assert evaluation.correct_count == evaluation.scenario_count
    assert evaluation.accuracy == evaluation.correct_count / evaluation.scenario_count
    assert evaluation.accuracy >= 0.90
    assert all(
        scenario.expected_tool_ids == EXPECTED_TOOL_IDS[scenario.question_id]
        for scenario in evaluation.scenarios
    )


def test_routing_metric_reports_a_deliberately_wrong_planner() -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing

    class NoToolsPlanner:
        def plan(self, question: str, classification: object) -> InvestigationPlan:
            del classification
            return InvestigationPlan(
                intent="unknown",
                retrieval_query=question,
            )

    manifest, _ = build_manifest()

    evaluation = evaluate_tool_routing(
        manifest,
        classifier=DeterministicQuestionClassifier(),
        planner=NoToolsPlanner(),  # type: ignore[arg-type]
    )

    assert evaluation.correct_count < evaluation.scenario_count
    assert evaluation.accuracy < 0.90

"""Literal, deterministic evaluation for approved-tool routing."""

from __future__ import annotations

from pydantic import Field, model_validator

from .agentic import (
    ClassifierProvider,
    DeterministicInvestigationPlanner,
    DeterministicQuestionClassifier,
    InvestigationPlan,
    PlannerProvider,
)
from .agentic_tools import ApprovedToolId
from .domain import ContractModel, GroundTruthManifest

LITERAL_TOOL_ROUTING: dict[str, tuple[ApprovedToolId, ...]] = {
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


class ToolRoutingScenario(ContractModel):
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_tool_ids: tuple[ApprovedToolId, ...] = ()
    actual_tool_ids: tuple[ApprovedToolId, ...] = ()
    matched: bool


class ToolRoutingEvaluation(ContractModel):
    scenarios: tuple[ToolRoutingScenario, ...] = Field(min_length=1)
    correct_count: int = Field(ge=0)
    scenario_count: int = Field(gt=0)
    accuracy: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> ToolRoutingEvaluation:
        if self.scenario_count != len(self.scenarios):
            raise ValueError("scenario_count must equal the scenario total")
        actual_correct = sum(scenario.matched for scenario in self.scenarios)
        if self.correct_count != actual_correct:
            raise ValueError("correct_count must equal literal scenario matches")
        if self.accuracy != self.correct_count / self.scenario_count:
            raise ValueError("accuracy must equal correct_count divided by total")
        return self


def evaluate_tool_routing(
    manifest: GroundTruthManifest,
    *,
    classifier: ClassifierProvider | None = None,
    planner: PlannerProvider | None = None,
) -> ToolRoutingEvaluation:
    """Measure only question-to-approved-tool routing against literal cases."""
    active_classifier = classifier or DeterministicQuestionClassifier()
    active_planner = planner or DeterministicInvestigationPlanner()
    scenarios: list[ToolRoutingScenario] = []
    for question in manifest.benchmark_questions:
        if question.id not in LITERAL_TOOL_ROUTING:
            raise ValueError(f"missing literal routing expectation: {question.id}")
        classification = active_classifier.classify(question.question)
        plan = active_planner.plan(question.question, classification)
        if not isinstance(plan, InvestigationPlan):
            raise TypeError("planner returned an invalid investigation plan")
        expected = LITERAL_TOOL_ROUTING[question.id]
        actual = tuple(plan.tool_ids)
        scenarios.append(
            ToolRoutingScenario(
                question_id=question.id,
                question=question.question,
                expected_tool_ids=expected,
                actual_tool_ids=actual,
                matched=actual == expected,
            )
        )
    correct_count = sum(scenario.matched for scenario in scenarios)
    scenario_count = len(scenarios)
    return ToolRoutingEvaluation(
        scenarios=tuple(scenarios),
        correct_count=correct_count,
        scenario_count=scenario_count,
        accuracy=correct_count / scenario_count,
    )


__all__ = [
    "LITERAL_TOOL_ROUTING",
    "ToolRoutingEvaluation",
    "ToolRoutingScenario",
    "evaluate_tool_routing",
]

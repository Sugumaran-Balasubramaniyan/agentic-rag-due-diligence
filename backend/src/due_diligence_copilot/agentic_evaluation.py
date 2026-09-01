"""Literal, deterministic evaluation for approved-tool routing."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType

from pydantic import Field, model_validator

from .agentic import (
    ClassifierProvider,
    DeterministicInvestigationPlanner,
    DeterministicQuestionClassifier,
    InvestigationPlan,
    PlannerProvider,
)
from .agentic_tools import ApprovedToolId
from .domain import (
    BenchmarkQuestion,
    ContractModel,
    GroundTruthManifest,
    SourceLocation,
)

_CANONICAL_TOOL_ROUTING: Mapping[str, tuple[ApprovedToolId, ...]] = MappingProxyType(
    {
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
)

LITERAL_TOOL_ROUTING: dict[str, tuple[ApprovedToolId, ...]] = dict(
    _CANONICAL_TOOL_ROUTING
)


@lru_cache(maxsize=1)
def _canonical_benchmark_questions() -> Mapping[str, str]:
    from .synthetic_data import build_manifest

    manifest, _ = build_manifest()
    return MappingProxyType(
        {
            question.id: _question_fingerprint(question)
            for question in manifest.benchmark_questions
        }
    )


def _question_fingerprint(question: BenchmarkQuestion) -> str:
    def location(value: SourceLocation) -> dict[str, object]:
        return {
            "document_id": value.document_id,
            "path": value.path,
            "section": value.section,
            "page": value.page,
            "table": value.table,
            "line_start": value.line_start,
            "line_end": value.line_end,
            "cell": value.cell,
        }

    data = {
        "id": question.id,
        "question": question.question,
        "category": getattr(question.category, "value", question.category),
        "expected_answer": {
            "answer": question.expected_answer.answer,
            "literal": question.expected_answer.literal,
            "source_location": location(question.expected_answer.source_location),
        },
        "expected_evidence": [
            {
                "literal": item.literal,
                "source_location": location(item.source_location),
                "classification": getattr(
                    item.classification, "value", item.classification
                ),
            }
            for item in question.expected_evidence
        ],
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class ToolRoutingScenario(ContractModel):
    question_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=4000)
    expected_tool_ids: tuple[ApprovedToolId, ...] = Field(default=(), max_length=4)
    actual_tool_ids: tuple[ApprovedToolId, ...] = Field(default=(), max_length=4)
    matched: bool


class ToolRoutingEvaluation(ContractModel):
    scenarios: tuple[ToolRoutingScenario, ...] = Field(min_length=1, max_length=32)
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
    question_ids = [question.id for question in manifest.benchmark_questions]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("routing manifest must contain an exact unique question set")
    if set(question_ids) != set(_CANONICAL_TOOL_ROUTING):
        raise ValueError("routing manifest must contain the exact literal question set")
    canonical = _canonical_benchmark_questions()
    for question in manifest.benchmark_questions:
        fingerprint = _question_fingerprint(question)
        if fingerprint != canonical.get(question.id):
            raise ValueError(
                f"routing manifest question {question.id} does not match canonical data"
            )
    scenarios: list[ToolRoutingScenario] = []
    for question in manifest.benchmark_questions:
        if question.id not in _CANONICAL_TOOL_ROUTING:
            raise ValueError(f"missing literal routing expectation: {question.id}")
        classification = active_classifier.classify(question.question)
        plan = active_planner.plan(question.question, classification)
        if not isinstance(plan, InvestigationPlan):
            raise TypeError("planner returned an invalid investigation plan")
        expected = _CANONICAL_TOOL_ROUTING[question.id]
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

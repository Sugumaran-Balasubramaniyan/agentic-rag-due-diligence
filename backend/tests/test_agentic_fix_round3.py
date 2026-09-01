from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_agentic_workflow import ASTERIA_CONTEXT, _build_workflow

from due_diligence_copilot.agentic import (
    DeterministicClaimGenerator,
    GenerationResult,
    InvestigationRequest,
)
from due_diligence_copilot.agentic_tools import (
    ContradictionResult,
    FinancialMetricResult,
    ToolCall,
    ToolResultStatus,
)
from due_diligence_copilot.domain import AnalysisStatus, Evidence, SourceLocation

QUESTION = "What percentage of FY2025 revenue came from Asteria's largest customer?"
RISK_QUESTION = (
    "What deal risk combines customer concentration with change-of-control consent?"
)


def _request(question: str) -> InvestigationRequest:
    return InvestigationRequest(
        analysis_id="fix-round-3", workspace_id="asteria", question=question
    )


def test_tool_id_cannot_return_a_different_result_model() -> None:
    class ForgedRegistry:
        def execute(self, call: ToolCall):
            return ContradictionResult(
                tool_id=call.tool_id,
                status=ToolResultStatus.SUCCEEDED,
                subject="forged",
                claim="forged contradiction",
                evidence=call.evidence,
                primary_evidence=call.evidence,
            )

    workflow = _build_workflow()
    workflow.tools = ForgedRegistry()
    result = workflow.run(
        _request(QUESTION),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status is AnalysisStatus.FAILED
    assert result.tool_results == ()


def test_duplicate_finding_ids_cannot_reach_approval() -> None:
    class DuplicateGenerator(DeterministicClaimGenerator):
        def generate(self, question, plan, tool_results):
            generated = super().generate(question, plan, tool_results)
            if len(generated.claims) < 2:
                return generated
            claims = list(generated.claims)
            claims[1] = claims[1].model_copy(update={"id": claims[0].id})
            return GenerationResult(
                claims=tuple(claims), estimated_tokens=generated.estimated_tokens
            )

    workflow = _build_workflow()
    workflow.generator = DuplicateGenerator()
    result = workflow.run(
        _request(RISK_QUESTION),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status is AnalysisStatus.FAILED
    assert result.analysis.findings == ()


def test_tool_result_evidence_must_match_call_evidence() -> None:
    class ForgedEvidenceRegistry:
        def execute(self, call: ToolCall):
            result = FinancialMetricResult(
                status=ToolResultStatus.SUCCEEDED,
                unit="unitless",
                value=Decimal("1"),
                claim="forged",
                evidence=(),
            )
            return result

    workflow = _build_workflow()
    workflow.tools = ForgedEvidenceRegistry()
    result = workflow.run(
        _request(QUESTION),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status is AnalysisStatus.FAILED
    assert result.tool_results == ()


def test_verifier_output_is_revalidated_before_acceptance() -> None:
    class ForgedVerifier:
        def verify(self, context, claims, retrieved):
            del context, claims, retrieved
            return {
                "claims_verified": 1,
                "citation_precision": 0.5,
                "citation_coverage": 1.0,
            }

    workflow = _build_workflow()
    workflow.verifier = ForgedVerifier()
    result = workflow.run(
        _request(QUESTION),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status is AnalysisStatus.ABSTAINED


@pytest.mark.parametrize(
    "field", ["question", "expected_answer", "category", "expected_evidence"]
)
def test_public_routing_expectations_cannot_mutate_private_manifest(field: str) -> None:
    from due_diligence_copilot.agentic_evaluation import evaluate_tool_routing
    from due_diligence_copilot.synthetic_data import build_manifest

    manifest, _ = build_manifest()
    question = manifest.benchmark_questions[0]
    if field == "question":
        changed = question.model_copy(update={"question": "mutated"})
    elif field == "category":
        changed = question.model_copy(update={"category": "unsupported"})
    elif field == "expected_answer":
        changed = question.model_copy(
            update={
                "expected_answer": question.expected_answer.model_copy(
                    update={"answer": "mutated"}
                )
            }
        )
    else:
        changed = question.model_copy(update={"expected_evidence": ()})
    mutated = manifest.model_copy(
        update={"benchmark_questions": (changed, *manifest.benchmark_questions[1:])}
    )
    with pytest.raises(ValueError, match="canonical"):
        evaluate_tool_routing(mutated)


def test_tool_output_model_rejects_oversized_nested_evidence() -> None:
    evidence = Evidence(
        id="evidence",
        document_id="doc",
        display_name="Document",
        source_location=SourceLocation(document_id="doc", path="doc.md", line_start=1),
        excerpt="supported",
        chunk_id="chunk",
    )
    with pytest.raises(ValidationError):
        FinancialMetricResult(
            status=ToolResultStatus.SUCCEEDED,
            unit="unitless",
            evidence=(evidence,) * 11,
        )

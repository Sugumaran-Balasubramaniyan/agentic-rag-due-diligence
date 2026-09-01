from __future__ import annotations

from test_agentic_workflow import ASTERIA_CONTEXT, _build_workflow

from due_diligence_copilot.agentic import (
    ApprovalBoundary,
    ApprovalDecision,
    InvestigationRequest,
    _provenance_token,
)
from due_diligence_copilot.domain import AnalysisStatus, ApprovalState

CONTRADICTION_QUESTION = (
    "What contradiction exists between the security policy and board minutes?"
)
PROVENANCE_KEY = b"task-5-fix-round-5-test-key"


def _investigated_contradiction(analysis_id: str):
    workflow = _build_workflow()
    workflow.provenance_key = PROVENANCE_KEY
    result = workflow.run(
        InvestigationRequest(
            analysis_id=analysis_id,
            workspace_id="asteria",
            question=CONTRADICTION_QUESTION,
        ),
        ASTERIA_CONTEXT,
    )
    assert result.analysis.status is AnalysisStatus.AWAITING_APPROVAL
    return workflow, result


def _signed(result):
    return result.model_copy(
        update={"provenance_token": _provenance_token(result, PROVENANCE_KEY)}
    )


def test_legitimate_contradiction_investigation_can_be_approved_into_a_report() -> None:
    workflow, result = _investigated_contradiction("contradiction-approval")
    finding = result.analysis.findings[0]
    tool_result = result.tool_results[0]

    assert tuple(finding.evidence) == tool_result.evidence
    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(result), ApprovalDecision.APPROVED)

    assert outcome.completed is True
    assert outcome.approval_state is ApprovalState.APPROVED
    assert outcome.report is not None
    assert outcome.report.status is AnalysisStatus.COMPLETED
    assert outcome.report.findings == [finding]
    assert {item.source_location.path for item in finding.evidence} == {
        "security-policy.md",
        "board-minutes.md",
    }


def test_contradiction_approval_rejects_a_tampered_same_id_citation() -> None:
    workflow, result = _investigated_contradiction("contradiction-tamper")
    finding = result.analysis.findings[0]
    tampered = finding.evidence[0].model_copy(update={"excerpt": "forged citation"})
    forged = result.model_copy(
        update={
            "analysis": result.analysis.model_copy(
                update={
                    "findings": (
                        finding.model_copy(update={"evidence": [tampered]}),
                    )
                }
            )
        }
    )

    outcome = ApprovalBoundary(
        event_store=workflow.event_store, provenance_key=PROVENANCE_KEY
    ).decide(_signed(forged), ApprovalDecision.APPROVED)

    assert outcome.completed is False
    assert outcome.report is None

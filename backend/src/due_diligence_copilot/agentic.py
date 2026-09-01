"""Bounded, typed agentic investigation workflow."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field, model_validator

from .adapters import InMemoryAnalysisEventStore
from .agentic_tools import (
    APPROVED_TOOL_IDS,
    ApprovedToolId,
    ContractClause,
    ContractClauseArguments,
    ContractClauseResult,
    ContradictionArguments,
    ContradictionResult,
    DeterministicToolRegistry,
    FinancialMetricArguments,
    FinancialMetricResult,
    FinancialOperation,
    MissingDocumentArguments,
    MissingDocumentResult,
    ToolArguments,
    ToolCall,
    ToolRegistry,
    ToolResult,
    ToolResultStatus,
)
from .domain import (
    AgentEvent,
    AgentEventStatus,
    AnalysisState,
    AnalysisStatus,
    ApprovalState,
    CalculationTrace,
    ContractModel,
    Evidence,
    Finding,
    FindingSeverity,
    Report,
    VerificationStatus,
)
from .ingestion_contracts import AccessContext
from .ports import AnalysisEventStore, DocumentRepository
from .retrieval import (
    AbstentionReason,
    CitationVerifier,
    Claim,
    ContextPack,
    HybridRetriever,
    RetrievalAbstention,
    RetrievalHit,
    RetrievalOutcomeStatus,
    pack_context,
)
from .workspace import require_read_workspace, require_workspace_access


class InvestigationIntent(StrEnum):
    FACTUAL = "factual"
    FINANCIAL = "financial"
    CONTRACT = "contract"
    CONTRADICTION = "contradiction"
    MISSING_DOCUMENT = "missing_document"
    INJECTION_RESISTANCE = "injection_resistance"
    COMBINED = "combined"
    UNKNOWN = "unknown"


class FailureCode(StrEnum):
    AUTHORIZATION = "authorization"
    PROVIDER = "provider"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    INTERNAL_INVARIANT = "internal_invariant"
    BUDGET_GRAPH_TRANSITIONS = "budget_graph_transitions"
    BUDGET_TOOL_CALLS = "budget_tool_calls"
    BUDGET_MODEL_TOKENS = "budget_model_tokens"
    BUDGET_ELAPSED = "budget_elapsed"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalFailureReason(StrEnum):
    NOT_AWAITING_APPROVAL = "not_awaiting_approval"
    UNVERIFIED_FINDINGS = "unverified_findings"
    REJECTED = "rejected"
    INTERNAL = "internal"


class InvestigationBudgets(ContractModel):
    max_graph_transitions: int = Field(default=12, ge=0, le=12)
    max_tool_calls: int = Field(default=6, ge=0, le=6)
    max_model_tokens: int = Field(default=8000, ge=0, le=8000)
    max_elapsed_seconds: float = Field(default=30, ge=0, le=30)

    @model_validator(mode="after")
    def elapsed_is_finite(self) -> InvestigationBudgets:
        if not math.isfinite(self.max_elapsed_seconds):
            raise ValueError("elapsed budget must be finite")
        return self


class InvestigationRequest(ContractModel):
    analysis_id: str = Field(min_length=1)
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    question: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def question_is_not_blank(self) -> InvestigationRequest:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        return self


class ClassificationResult(ContractModel):
    intent: InvestigationIntent
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_tokens: int = Field(ge=0, le=8000)


class FinancialPlanInput(ContractModel):
    operation: FinancialOperation
    left_label: str = Field(min_length=1, max_length=256)
    right_label: str | None = Field(default=None, max_length=256)
    precision: int = Field(default=1, ge=0, le=6)

    @model_validator(mode="after")
    def validate_operands(self) -> FinancialPlanInput:
        if (
            self.operation
            in {
                FinancialOperation.PERCENTAGE,
                FinancialOperation.SUBTRACT,
            }
            and not self.right_label
        ):
            raise ValueError("binary financial plans require right_label")
        return self


class ContractPlanInput(ContractModel):
    clause: ContractClause


class ContradictionPlanInput(ContractModel):
    subject: str = Field(min_length=1, max_length=256)


class MissingDocumentPlanInput(ContractModel):
    document_name: str = Field(min_length=1, max_length=256)


class InvestigationPlan(ContractModel):
    intent: InvestigationIntent
    retrieval_query: str = Field(min_length=1, max_length=4000)
    supporting_queries: tuple[str, ...] = Field(default=(), max_length=4)
    tool_ids: tuple[ApprovedToolId, ...] = Field(default=(), max_length=4)
    financial: FinancialPlanInput | None = None
    contract: ContractPlanInput | None = None
    contradiction: ContradictionPlanInput | None = None
    missing_document: MissingDocumentPlanInput | None = None

    @model_validator(mode="after")
    def validate_tool_inputs(self) -> InvestigationPlan:
        if len(set(self.tool_ids)) != len(self.tool_ids):
            raise ValueError("investigation plan contains duplicate tool IDs")
        if any(not query.strip() for query in self.supporting_queries):
            raise ValueError("supporting retrieval queries must not be blank")
        if any(len(query) > 1000 for query in self.supporting_queries):
            raise ValueError("supporting retrieval query is too long")
        required = {
            ApprovedToolId.CALCULATE_FINANCIAL_METRIC: self.financial,
            ApprovedToolId.INSPECT_CONTRACT_CLAUSE: self.contract,
            ApprovedToolId.DETECT_CONTRADICTIONS: self.contradiction,
            ApprovedToolId.ANALYZE_MISSING_DOCUMENTS: self.missing_document,
        }
        for tool_id, tool_input in required.items():
            if (tool_id in self.tool_ids) != (tool_input is not None):
                raise ValueError("investigation plan tool inputs do not match tool IDs")
        return self


class ClaimDraft(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    tool_result_id: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    severity: FindingSeverity
    claim: str = Field(min_length=1, max_length=2000)
    citations: tuple[Evidence, ...] = Field(default=(), max_length=10)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def evidence_is_bounded(self) -> ClaimDraft:
        if any(len(item.excerpt) > 4000 for item in (*self.citations, *self.evidence)):
            raise ValueError("generated evidence excerpt is too long")
        return self


class GenerationResult(ContractModel):
    claims: tuple[ClaimDraft, ...] = Field(default=(), max_length=4)
    estimated_tokens: int = Field(ge=0, le=8000)


class FailureDetail(ContractModel):
    code: FailureCode
    node: str = Field(min_length=1)


class BudgetUsage(ContractModel):
    graph_transitions: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    model_tokens: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)


class InvestigationResult(ContractModel):
    analysis: AnalysisState
    classification: ClassificationResult | None = None
    plan: InvestigationPlan | None = None
    context_pack: ContextPack | None = None
    retrieved_chunk_ids: tuple[str, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    failure: FailureDetail | None = None
    abstention_reason: AbstentionReason | None = None
    budget: BudgetUsage
    provenance_token: str | None = Field(default=None, max_length=128)

    @property
    def state(self) -> AnalysisState:
        return self.analysis

    @property
    def analysis_state(self) -> AnalysisState:
        return self.analysis


class ApprovalOutcome(ContractModel):
    analysis: AnalysisState
    report: Report | None = None
    approval_state: ApprovalState
    completed: bool
    reason: ApprovalFailureReason | None = None


class Clock(Protocol):
    def monotonic(self) -> float: ...


class TokenAccounting(Protocol):
    def charge(self, tokens: int) -> None: ...


class ClassifierProvider(Protocol):
    def classify(self, question: str) -> ClassificationResult: ...


class PlannerProvider(Protocol):
    def plan(
        self, question: str, classification: ClassificationResult
    ) -> InvestigationPlan: ...


class ClaimGeneratorProvider(Protocol):
    def generate(
        self,
        question: str,
        plan: InvestigationPlan,
        tool_results: tuple[ToolResult, ...],
    ) -> GenerationResult: ...


class DeterministicClock:
    """Manual clock for deterministic budget tests."""

    def __init__(self, initial: float = 0.0) -> None:
        self._now = initial

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("clock cannot move backwards")
        self._now += seconds


class SystemClock:
    def monotonic(self) -> float:
        return monotonic()


class DeterministicTokenAccounting:
    """Observable token ledger used by deterministic adapters and tests."""

    def __init__(self) -> None:
        self.used = 0

    def charge(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("token charge cannot be negative")
        self.used += tokens


class DeterministicQuestionClassifier:
    """Classify only the caller's question, never retrieved document text."""

    def classify(self, question: str) -> ClassificationResult:
        text = question.casefold()
        if not question.strip():
            intent = InvestigationIntent.UNKNOWN
        elif "embedded" in text or "reviewer instruction" in text:
            intent = InvestigationIntent.INJECTION_RESISTANCE
        elif "contradiction" in text or "conflict" in text:
            intent = InvestigationIntent.CONTRADICTION
        elif "deal risk" in text or (
            "concentration" in text and "change of control" in text
        ):
            intent = InvestigationIntent.COMBINED
        elif "soc 2" in text or "churn" in text or "available" in text:
            intent = InvestigationIntent.MISSING_DOCUMENT
        elif any(
            term in text
            for term in ("percentage", "share", "concentration", "ebitda", "total")
        ):
            intent = InvestigationIntent.FINANCIAL
        elif any(
            term in text
            for term in ("contract", "consent", "price", "term", "supplier")
        ):
            intent = InvestigationIntent.CONTRACT
        elif "revenue" in text or "customer" in text:
            intent = InvestigationIntent.FACTUAL
        else:
            intent = InvestigationIntent.UNKNOWN
        return ClassificationResult(intent=intent, confidence=1.0, estimated_tokens=32)


class DeterministicInvestigationPlanner:
    """Create plans from the question and policy, with no evidence input."""

    def plan(
        self, question: str, classification: ClassificationResult
    ) -> InvestigationPlan:
        text = question.casefold()
        financial: FinancialPlanInput | None = None
        contract: ContractPlanInput | None = None
        contradiction: ContradictionPlanInput | None = None
        missing: MissingDocumentPlanInput | None = None
        tool_ids: list[ApprovedToolId] = []
        supporting_queries: tuple[str, ...] = ()
        if classification.intent is InvestigationIntent.COMBINED:
            financial = FinancialPlanInput(
                operation=FinancialOperation.PERCENTAGE,
                left_label="largest customer",
                right_label="Total",
                precision=1,
            )
            contract = ContractPlanInput(clause=ContractClause.CHANGE_OF_CONTROL)
            tool_ids.extend(
                (
                    ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
                    ApprovedToolId.INSPECT_CONTRACT_CLAUSE,
                )
            )
            supporting_queries = (
                "largest customer revenue share",
                "change of control consent",
            )
        elif classification.intent is InvestigationIntent.FINANCIAL:
            if any(term in text for term in ("percentage", "share", "concentration")):
                financial = FinancialPlanInput(
                    operation=FinancialOperation.PERCENTAGE,
                    left_label="largest customer",
                    right_label="Total",
                    precision=1,
                )
            elif "ebitda" in text:
                financial = FinancialPlanInput(
                    operation=FinancialOperation.REPORTED_VALUE,
                    left_label="EBITDA",
                    precision=0,
                )
            elif "total" in text:
                financial = FinancialPlanInput(
                    operation=FinancialOperation.REPORTED_VALUE,
                    left_label="Total",
                    precision=0,
                )
            if financial is not None:
                tool_ids.append(ApprovedToolId.CALCULATE_FINANCIAL_METRIC)
        elif classification.intent is InvestigationIntent.CONTRACT:
            clause = (
                ContractClause.CHANGE_OF_CONTROL
                if "change of control" in text or "consent" in text
                else ContractClause.PRICE_ESCALATION
                if "price" in text or "increase" in text
                else ContractClause.TERM
            )
            contract = ContractPlanInput(clause=clause)
            tool_ids.append(ApprovedToolId.INSPECT_CONTRACT_CLAUSE)
        elif classification.intent is InvestigationIntent.CONTRADICTION:
            contradiction = ContradictionPlanInput(
                subject="MFA" if "mfa" in text else "security"
            )
            tool_ids.append(ApprovedToolId.DETECT_CONTRADICTIONS)
        elif classification.intent is InvestigationIntent.MISSING_DOCUMENT:
            missing = MissingDocumentPlanInput(
                document_name=(
                    "Customer churn analysis"
                    if "churn" in text
                    else "SOC 2 Type II report"
                )
            )
            tool_ids.append(ApprovedToolId.ANALYZE_MISSING_DOCUMENTS)
        return InvestigationPlan(
            intent=classification.intent,
            retrieval_query=question,
            supporting_queries=supporting_queries,
            tool_ids=tuple(tool_ids),
            financial=financial,
            contract=contract,
            contradiction=contradiction,
            missing_document=missing,
        )


class DeterministicClaimGenerator:
    """Turn successful typed tool results into citation-verifiable drafts."""

    def generate(
        self,
        question: str,
        plan: InvestigationPlan,
        tool_results: tuple[ToolResult, ...],
    ) -> GenerationResult:
        del question, plan
        drafts: list[ClaimDraft] = []
        categories = {
            ApprovedToolId.CALCULATE_FINANCIAL_METRIC: (
                "financial",
                FindingSeverity.MEDIUM,
            ),
            ApprovedToolId.INSPECT_CONTRACT_CLAUSE: ("contract", FindingSeverity.HIGH),
            ApprovedToolId.DETECT_CONTRADICTIONS: (
                "contradiction",
                FindingSeverity.HIGH,
            ),
            ApprovedToolId.ANALYZE_MISSING_DOCUMENTS: (
                "missing_document",
                FindingSeverity.MEDIUM,
            ),
        }
        for position, result in enumerate(tool_results, start=1):
            if result.status is not ToolResultStatus.SUCCEEDED:
                continue
            if result.claim is None or not result.primary_evidence:
                continue
            category, severity = categories[result.tool_id]
            drafts.append(
                ClaimDraft(
                    id=f"claim-{position}",
                    tool_result_id=result.id,
                    category=category,
                    severity=severity,
                    claim=result.claim,
                    citations=(
                        result.evidence
                        if result.tool_id is ApprovedToolId.DETECT_CONTRADICTIONS
                        else result.primary_evidence
                    ),
                    evidence=result.evidence,
                    confidence=1.0,
                )
            )
        return GenerationResult(
            claims=tuple(drafts),
            estimated_tokens=64 if drafts else 16,
        )


@dataclass
class _BudgetExceeded(Exception):
    code: FailureCode


class _SafeAbstention(Exception):
    def __init__(self, reason: AbstentionReason) -> None:
        self.reason = reason


class _InvariantFailure(Exception):
    pass


_PROVENANCE_KEY = secrets.token_bytes(32)


def _provenance_token(result: InvestigationResult) -> str:
    payload = result.model_dump_json(exclude={"provenance_token"})
    return hmac.new(_PROVENANCE_KEY, payload.encode(), hashlib.sha256).hexdigest()


def _estimated_output_tokens(value: ContractModel) -> int:
    return max(1, (len(value.model_dump_json()) + 3) // 4)


@dataclass
class _BudgetLedger:
    budgets: InvestigationBudgets
    clock: Clock
    token_accounting: TokenAccounting
    started_at: float
    graph_transitions: int = 0
    tool_calls: int = 0
    model_tokens: int = 0

    def check_elapsed(self) -> None:
        self.budgets = InvestigationBudgets.model_validate(self.budgets.model_dump())
        elapsed = self.clock.monotonic() - self.started_at
        if elapsed > self.budgets.max_elapsed_seconds:
            raise _BudgetExceeded(FailureCode.BUDGET_ELAPSED)

    def transition(self) -> None:
        self.check_elapsed()
        if self.graph_transitions >= self.budgets.max_graph_transitions:
            raise _BudgetExceeded(FailureCode.BUDGET_GRAPH_TRANSITIONS)
        self.graph_transitions += 1

    def tool_call(self) -> None:
        self.check_elapsed()
        if self.tool_calls >= self.budgets.max_tool_calls:
            raise _BudgetExceeded(FailureCode.BUDGET_TOOL_CALLS)
        self.tool_calls += 1

    def model_call(self, tokens: int) -> None:
        self.check_elapsed()
        self.budgets = InvestigationBudgets.model_validate(self.budgets.model_dump())
        if tokens < 0 or self.model_tokens + tokens > self.budgets.max_model_tokens:
            raise _BudgetExceeded(FailureCode.BUDGET_MODEL_TOKENS)
        self.token_accounting.charge(tokens)
        self.model_tokens += tokens
        self.check_elapsed()

    def usage(self) -> BudgetUsage:
        return BudgetUsage(
            graph_transitions=self.graph_transitions,
            tool_calls=self.tool_calls,
            model_tokens=self.model_tokens,
            elapsed_seconds=max(0.0, self.clock.monotonic() - self.started_at),
        )


@dataclass
class _Runtime:
    request: InvestigationRequest
    context: AccessContext
    budgets: InvestigationBudgets
    clock: Clock
    ledger: _BudgetLedger
    event_store: AnalysisEventStore
    documents: DocumentRepository
    retriever: HybridRetriever
    verifier: CitationVerifier
    classifier: ClassifierProvider
    planner: PlannerProvider
    generator: ClaimGeneratorProvider
    tools: ToolRegistry


class WorkflowGraphState(TypedDict, total=False):
    request: InvestigationRequest
    context: AccessContext
    analysis: AnalysisState
    classification: ClassificationResult
    plan: InvestigationPlan
    retrieved: tuple[RetrievalHit, ...]
    context_pack: ContextPack
    evidence: tuple[Evidence, ...]
    tool_calls: tuple[ToolCall, ...]
    tool_results: tuple[ToolResult, ...]
    claims: tuple[Claim, ...]
    failure: FailureDetail
    abstention_reason: AbstentionReason


_SUMMARY: dict[tuple[str, AgentEventStatus], str] = {
    ("authorization", AgentEventStatus.FAILED): "Workspace authorization failed.",
    ("classify", AgentEventStatus.COMPLETED): "Question classified.",
    ("classify", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("plan", AgentEventStatus.COMPLETED): "Investigation plan created.",
    ("plan", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("retrieve", AgentEventStatus.COMPLETED): "Authorized evidence retrieved.",
    ("retrieve", AgentEventStatus.SKIPPED): "Evidence retrieval abstained safely.",
    ("retrieve", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("tool_execution", AgentEventStatus.COMPLETED): "Approved tools executed.",
    ("tool_execution", AgentEventStatus.SKIPPED): "No approved tool was required.",
    ("tool_execution", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("verify", AgentEventStatus.COMPLETED): "Claims verified against evidence.",
    ("verify", AgentEventStatus.SKIPPED): "Claim verification abstained safely.",
    ("verify", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("completeness", AgentEventStatus.COMPLETED): (
        "Investigation completeness assessed."
    ),
    ("completeness", AgentEventStatus.SKIPPED): "Investigation abstained safely.",
    ("completeness", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("awaiting_approval", AgentEventStatus.COMPLETED): (
        "Verified findings await approval."
    ),
    ("awaiting_approval", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("needs_input", AgentEventStatus.SKIPPED): "Additional user input is required.",
    ("abstained", AgentEventStatus.SKIPPED): "Investigation abstained safely.",
    ("failed", AgentEventStatus.FAILED): "Investigation failed closed.",
    ("approval", AgentEventStatus.COMPLETED): "Human approval accepted.",
    ("approval", AgentEventStatus.SKIPPED): "Human approval did not finalize a report.",
    ("approval", AgentEventStatus.FAILED): "Report finalization failed closed.",
}


def _append_event(
    runtime: _Runtime,
    analysis: AnalysisState,
    node: str,
    status: AgentEventStatus,
    started_at: float,
) -> AnalysisState:
    summary = _SUMMARY[(node, status)]
    duration_ms = max(0, int((runtime.clock.monotonic() - started_at) * 1000))
    event = AgentEvent(
        sequence=len(analysis.events) + 1,
        node=node,
        status=status,
        duration_ms=duration_ms,
        summary=summary,
    )
    runtime.event_store.append(
        runtime.request.workspace_id, runtime.request.analysis_id, event
    )
    return analysis.model_copy(update={"events": (*analysis.events, event)})


def _safe_append_event(
    runtime: _Runtime,
    analysis: AnalysisState,
    node: str,
    status: AgentEventStatus,
    started_at: float,
) -> AnalysisState:
    try:
        return _append_event(runtime, analysis, node, status, started_at)
    except Exception:
        return analysis


def _failed_state(
    runtime: _Runtime,
    state: WorkflowGraphState,
    code: FailureCode,
    node: str,
    started_at: float,
) -> WorkflowGraphState:
    analysis = state["analysis"].model_copy(
        update={
            "status": AnalysisStatus.FAILED,
            "findings": (),
            "report_id": None,
        }
    )
    analysis = _safe_append_event(
        runtime, analysis, node, AgentEventStatus.FAILED, started_at
    )
    return cast(
        WorkflowGraphState,
        {
            **state,
            "analysis": analysis,
            "failure": FailureDetail(code=code, node=node),
        },
    )


def _abstained_state(
    runtime: _Runtime,
    state: WorkflowGraphState,
    reason: AbstentionReason,
    node: str,
    started_at: float,
) -> WorkflowGraphState:
    analysis = state["analysis"].model_copy(
        update={"status": AnalysisStatus.ABSTAINED, "findings": (), "report_id": None}
    )
    analysis = _safe_append_event(
        runtime, analysis, node, AgentEventStatus.SKIPPED, started_at
    )
    return cast(
        WorkflowGraphState,
        {**state, "analysis": analysis, "abstention_reason": reason},
    )


def _run_action(
    runtime: _Runtime,
    state: WorkflowGraphState,
    node: str,
    action: Callable[[], dict[str, object]],
    failure_code: FailureCode,
    event_status: AgentEventStatus = AgentEventStatus.COMPLETED,
) -> WorkflowGraphState:
    started_at = runtime.clock.monotonic()
    try:
        runtime.ledger.transition()
    except _BudgetExceeded as exceeded:
        return _failed_state(runtime, state, exceeded.code, node, started_at)
    try:
        updates = action()
        runtime.ledger.check_elapsed()
        candidate_analysis = updates.get("analysis")
        if candidate_analysis is not None and not isinstance(
            candidate_analysis, AnalysisState
        ):
            raise _InvariantFailure()
        analysis = (
            candidate_analysis
            if candidate_analysis is not None
            else state["analysis"].model_copy(update={"status": AnalysisStatus.RUNNING})
        )
        merged: WorkflowGraphState = cast(WorkflowGraphState, {**state, **updates})
        merged["analysis"] = _append_event(
            runtime, analysis, node, event_status, started_at
        )
        return merged
    except _BudgetExceeded as exceeded:
        return _failed_state(runtime, state, exceeded.code, node, started_at)
    except _SafeAbstention as abstention:
        return _abstained_state(runtime, state, abstention.reason, node, started_at)
    except _InvariantFailure:
        return _failed_state(
            runtime, state, FailureCode.INTERNAL_INVARIANT, node, started_at
        )
    except Exception:
        return _failed_state(runtime, state, failure_code, node, started_at)


def _terminal_state(
    runtime: _Runtime,
    state: WorkflowGraphState,
    node: str,
    status: AnalysisStatus,
    event_status: AgentEventStatus,
) -> WorkflowGraphState:
    started_at = runtime.clock.monotonic()
    try:
        runtime.ledger.transition()
    except _BudgetExceeded as exceeded:
        return _failed_state(runtime, state, exceeded.code, node, started_at)
    analysis = state["analysis"].model_copy(update={"status": status})
    analysis = _safe_append_event(runtime, analysis, node, event_status, started_at)
    return cast(WorkflowGraphState, {**state, "analysis": analysis})


def _route_status(state: WorkflowGraphState) -> str:
    analysis = state["analysis"]
    if analysis.status is AnalysisStatus.FAILED:
        return "failed"
    if analysis.status is AnalysisStatus.ABSTAINED:
        return "abstained"
    return "continue"


class BoundedInvestigationWorkflow:
    """Finite LangGraph controller for bounded evidence investigations."""

    def __init__(
        self,
        retriever: HybridRetriever,
        documents: DocumentRepository,
        *,
        event_store: AnalysisEventStore | None = None,
        classifier: ClassifierProvider | None = None,
        planner: PlannerProvider | None = None,
        generator: ClaimGeneratorProvider | None = None,
        tools: ToolRegistry | None = None,
        verifier: CitationVerifier | None = None,
        budgets: InvestigationBudgets | None = None,
        clock: Clock | None = None,
        token_accounting: TokenAccounting | None = None,
    ) -> None:
        self.retriever = retriever
        self.documents = documents
        self.event_store = event_store or InMemoryAnalysisEventStore()
        self.classifier = classifier or DeterministicQuestionClassifier()
        self.planner = planner or DeterministicInvestigationPlanner()
        self.generator = generator or DeterministicClaimGenerator()
        self.tools = tools or DeterministicToolRegistry()
        self.verifier = verifier or CitationVerifier(documents)
        self.budgets = InvestigationBudgets.model_validate(
            (budgets or InvestigationBudgets()).model_dump()
        )
        self._budget_snapshot = InvestigationBudgets.model_validate(
            self.budgets.model_dump()
        )
        self.clock = clock or SystemClock()
        self.token_accounting = token_accounting or DeterministicTokenAccounting()

    def run(
        self, request: InvestigationRequest, context: AccessContext
    ) -> InvestigationResult:
        initial_analysis = AnalysisState(
            analysis_id=request.analysis_id,
            workspace_id=request.workspace_id,
            question=request.question,
            status=AnalysisStatus.QUEUED,
        )
        try:
            authorized_workspace = require_read_workspace(context)
            require_workspace_access(context, request.workspace_id)
            if authorized_workspace != request.workspace_id:
                raise PermissionError("request workspace does not match read scope")
        except Exception:
            failed_analysis = initial_analysis.model_copy(
                update={"status": AnalysisStatus.FAILED}
            )
            failure_runtime = _Runtime(
                request=request,
                context=context,
                budgets=self.budgets,
                clock=self.clock,
                ledger=_BudgetLedger(
                    self.budgets,
                    self.clock,
                    self.token_accounting,
                    self.clock.monotonic(),
                ),
                event_store=self.event_store,
                documents=self.documents,
                retriever=self.retriever,
                verifier=self.verifier,
                classifier=self.classifier,
                planner=self.planner,
                generator=self.generator,
                tools=self.tools,
            )
            failed_analysis = _safe_append_event(
                failure_runtime,
                failed_analysis,
                "authorization",
                AgentEventStatus.FAILED,
                self.clock.monotonic(),
            )
            return InvestigationResult(
                analysis=failed_analysis,
                failure=FailureDetail(
                    code=FailureCode.AUTHORIZATION, node="authorization"
                ),
                budget=BudgetUsage(),
            )

        budgets = InvestigationBudgets.model_validate(
            self._budget_snapshot.model_dump()
        )
        ledger = _BudgetLedger(
            budgets,
            self.clock,
            self.token_accounting,
            self.clock.monotonic(),
        )
        runtime = _Runtime(
            request=request,
            context=context,
            budgets=budgets,
            clock=self.clock,
            ledger=ledger,
            event_store=self.event_store,
            documents=self.documents,
            retriever=self.retriever,
            verifier=self.verifier,
            classifier=self.classifier,
            planner=self.planner,
            generator=self.generator,
            tools=self.tools,
        )
        graph = self.build_investigation_graph(runtime)
        final = cast(
            WorkflowGraphState,
            graph.invoke(
                {
                    "request": request,
                    "context": context,
                    "analysis": initial_analysis,
                }
            ),
        )
        result = InvestigationResult(
            analysis=final["analysis"],
            classification=final.get("classification"),
            plan=final.get("plan"),
            context_pack=final.get("context_pack"),
            retrieved_chunk_ids=tuple(
                hit.chunk.id for hit in final.get("retrieved", ())
            ),
            tool_calls=final.get("tool_calls", ()),
            tool_results=final.get("tool_results", ()),
            failure=final.get("failure"),
            abstention_reason=final.get("abstention_reason"),
            budget=ledger.usage(),
        )
        return result.model_copy(update={"provenance_token": _provenance_token(result)})

    def build_investigation_graph(
        self, runtime: _Runtime
    ) -> CompiledStateGraph[
        WorkflowGraphState, None, WorkflowGraphState, WorkflowGraphState
    ]:
        builder = StateGraph(WorkflowGraphState)

        def classify(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                response = runtime.classifier.classify(runtime.request.question)
                if not isinstance(response, ClassificationResult):
                    raise _InvariantFailure()
                response = ClassificationResult.model_validate(response.model_dump())
                runtime.ledger.model_call(
                    max(response.estimated_tokens, _estimated_output_tokens(response))
                )
                return {"classification": response}

            return _run_action(runtime, state, "classify", action, FailureCode.PROVIDER)

        def plan(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                classification = state.get("classification")
                if classification is None:
                    raise _InvariantFailure()
                response = runtime.planner.plan(
                    runtime.request.question, classification
                )
                if not isinstance(response, InvestigationPlan):
                    raise _InvariantFailure()
                response = InvestigationPlan.model_validate(response.model_dump())
                if not response.retrieval_query.strip():
                    raise _InvariantFailure()
                runtime.ledger.model_call(_estimated_output_tokens(response))
                return {"plan": response}

            return _run_action(runtime, state, "plan", action, FailureCode.PROVIDER)

        def retrieve(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                plan = state.get("plan")
                if plan is None:
                    raise _InvariantFailure()
                workspace_id = require_read_workspace(runtime.context)
                if workspace_id != runtime.request.workspace_id:
                    raise PermissionError("retrieval scope mismatch")
                queries = (plan.retrieval_query, *plan.supporting_queries)
                hits_by_id: dict[str, RetrievalHit] = {}
                for query in queries:
                    outcome = runtime.retriever.retrieve_outcome(runtime.context, query)
                    if outcome.status is RetrievalOutcomeStatus.RETRIEVED:
                        for hit in outcome.hits:
                            hits_by_id.setdefault(hit.chunk.id, hit)
                hits = tuple(hits_by_id.values())
                if not hits:
                    raise _SafeAbstention(AbstentionReason.UNSUPPORTED_RETRIEVAL)
                packed = pack_context(hits)
                if not packed.chunks:
                    raise _SafeAbstention(AbstentionReason.UNSUPPORTED_RETRIEVAL)
                evidence: list[Evidence] = []
                for hit in hits:
                    if hit.chunk.id not in packed.chunk_ids:
                        continue
                    document = runtime.documents.get(
                        runtime.request.workspace_id, hit.chunk.document_id
                    )
                    if document is None:
                        raise _SafeAbstention(
                            AbstentionReason.MISSING_DOCUMENT_AUTHORITY
                        )
                    evidence.append(
                        Evidence(
                            id=f"evidence-{hit.chunk.id}",
                            document_id=hit.chunk.document_id,
                            display_name=document.display_name,
                            source_location=hit.chunk.source_location,
                            excerpt=hit.chunk.text,
                            chunk_id=hit.chunk.id,
                            retrieval_score=hit.score,
                        )
                    )
                if not evidence:
                    raise _SafeAbstention(AbstentionReason.MISSING_DOCUMENT_AUTHORITY)
                return {
                    "retrieved": hits,
                    "context_pack": packed,
                    "evidence": tuple(evidence),
                }

            return _run_action(
                runtime, state, "retrieve", action, FailureCode.RETRIEVAL
            )

        def tool_execution(state: WorkflowGraphState) -> WorkflowGraphState:
            plan = state.get("plan")
            event_status = (
                AgentEventStatus.SKIPPED
                if plan is not None and not plan.tool_ids
                else AgentEventStatus.COMPLETED
            )

            def action() -> dict[str, object]:
                if plan is None:
                    raise _InvariantFailure()
                evidence = state.get("evidence", ())
                if not evidence and plan.tool_ids:
                    raise _InvariantFailure()
                calls: list[ToolCall] = []
                results: list[ToolResult] = []
                for tool_id in plan.tool_ids:
                    runtime.ledger.tool_call()
                    call = self._build_tool_call(plan, tool_id, evidence)
                    result = runtime.tools.execute(call)
                    if not isinstance(
                        result,
                        FinancialMetricResult
                        | ContractClauseResult
                        | ContradictionResult
                        | MissingDocumentResult,
                    ):
                        raise _InvariantFailure()
                    result = type(result).model_validate(result.model_dump())
                    result = result.model_copy(
                        update={"id": f"tool-result-{len(results) + 1}"}
                    )
                    if result.tool_id is not tool_id:
                        raise _InvariantFailure()
                    calls.append(call)
                    results.append(result)
                    if result.status is ToolResultStatus.ABSTAINED:
                        raise _SafeAbstention(AbstentionReason.UNSUPPORTED_EVIDENCE)
                return {"tool_calls": tuple(calls), "tool_results": tuple(results)}

            return _run_action(
                runtime,
                state,
                "tool_execution",
                action,
                FailureCode.TOOL,
                event_status,
            )

        def verify(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                plan = state.get("plan")
                results = state.get("tool_results", ())
                retrieved = state.get("retrieved", ())
                if plan is None:
                    raise _InvariantFailure()
                generated = runtime.generator.generate(
                    runtime.request.question, plan, results
                )
                if not isinstance(generated, GenerationResult):
                    raise _InvariantFailure()
                generated = GenerationResult.model_validate(generated.model_dump())
                runtime.ledger.model_call(
                    max(generated.estimated_tokens, _estimated_output_tokens(generated))
                )
                if not generated.claims:
                    raise _SafeAbstention(AbstentionReason.UNSUPPORTED_EVIDENCE)
                successful_results = {
                    result.id: result
                    for result in results
                    if result.status is ToolResultStatus.SUCCEEDED
                }
                claims = tuple(
                    Claim(
                        id=draft.id,
                        text=draft.claim,
                        evidence=draft.citations,
                        tool_result_id=draft.tool_result_id,
                        allows_contradiction=(
                            isinstance(
                                successful_results.get(draft.tool_result_id),
                                ContradictionResult,
                            )
                            and draft.claim
                            == successful_results[draft.tool_result_id].claim
                            and draft.citations
                            == successful_results[draft.tool_result_id].evidence
                        ),
                    )
                    for draft in generated.claims
                )
                try:
                    verification = runtime.verifier.verify(
                        runtime.context, claims, retrieved
                    )
                except RetrievalAbstention as abstention:
                    raise _SafeAbstention(abstention.reason) from abstention
                if verification.claims_verified != len(generated.claims):
                    raise _InvariantFailure()
                findings = tuple(
                    Finding(
                        id=draft.id.replace("claim-", "finding-", 1),
                        category=draft.category,
                        severity=draft.severity,
                        claim=draft.claim,
                        evidence=list(draft.citations),
                        confidence=draft.confidence,
                        verification_status=VerificationStatus.VERIFIED,
                        tool_result_id=draft.tool_result_id,
                        calculation=(
                            CalculationTrace(
                                operation=plan.financial.operation.value,
                                value=cast(
                                    FinancialMetricResult,
                                    successful_results[draft.tool_result_id],
                                ).value,
                                unit=cast(
                                    FinancialMetricResult,
                                    successful_results[draft.tool_result_id],
                                ).unit.value,
                                tool_result_id=draft.tool_result_id,
                            )
                            if plan.financial is not None
                            and draft.tool_result_id in successful_results
                            and isinstance(
                                successful_results[draft.tool_result_id],
                                FinancialMetricResult,
                            )
                            else None
                        ),
                    )
                    for draft in generated.claims
                )
                analysis = state["analysis"].model_copy(update={"findings": findings})
                return {"claims": claims, "analysis": analysis}

            return _run_action(runtime, state, "verify", action, FailureCode.PROVIDER)

        def completeness(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                findings = state["analysis"].findings
                results = state.get("tool_results", ())
                successful_ids = {
                    result.id
                    for result in results
                    if result.status is ToolResultStatus.SUCCEEDED
                }
                claims = state.get("claims", ())
                if (
                    not findings
                    or len(findings) != len(successful_ids)
                    or {claim.id for claim in claims}
                    != {
                        finding.id.replace("finding-", "claim-", 1)
                        for finding in findings
                    }
                    or {claim.tool_result_id for claim in claims} != successful_ids
                    or len({claim.tool_result_id for claim in claims}) != len(claims)
                    or any(
                        finding.verification_status is not VerificationStatus.VERIFIED
                        for finding in findings
                    )
                ):
                    raise _SafeAbstention(AbstentionReason.UNSUPPORTED_EVIDENCE)
                return {}

            return _run_action(
                runtime, state, "completeness", action, FailureCode.INTERNAL_INVARIANT
            )

        def awaiting_approval(state: WorkflowGraphState) -> WorkflowGraphState:
            def action() -> dict[str, object]:
                findings = state["analysis"].findings
                if not findings or any(
                    finding.verification_status is not VerificationStatus.VERIFIED
                    for finding in findings
                ):
                    raise _InvariantFailure()
                analysis = state["analysis"].model_copy(
                    update={"status": AnalysisStatus.AWAITING_APPROVAL}
                )
                return {"analysis": analysis}

            return _run_action(
                runtime,
                state,
                "awaiting_approval",
                action,
                FailureCode.INTERNAL_INVARIANT,
            )

        def needs_input(state: WorkflowGraphState) -> WorkflowGraphState:
            return _terminal_state(
                runtime,
                state,
                "needs_input",
                AnalysisStatus.NEEDS_INPUT,
                AgentEventStatus.SKIPPED,
            )

        def abstained(state: WorkflowGraphState) -> WorkflowGraphState:
            return _terminal_state(
                runtime,
                state,
                "abstained",
                AnalysisStatus.ABSTAINED,
                AgentEventStatus.SKIPPED,
            )

        def failed(state: WorkflowGraphState) -> WorkflowGraphState:
            return _terminal_state(
                runtime,
                state,
                "failed",
                AnalysisStatus.FAILED,
                AgentEventStatus.FAILED,
            )

        def route_classify(state: WorkflowGraphState) -> str:
            if state["analysis"].status is AnalysisStatus.FAILED:
                return "failed"
            classification = state.get("classification")
            if (
                classification is None
                or classification.intent is InvestigationIntent.UNKNOWN
            ):
                return "needs_input"
            return "plan"

        builder.add_node("classify", classify)
        builder.add_node("plan", plan)
        builder.add_node("retrieve", retrieve)
        builder.add_node("tool_execution", tool_execution)
        builder.add_node("verify", verify)
        builder.add_node("completeness", completeness)
        builder.add_node("awaiting_approval", awaiting_approval)
        builder.add_node("needs_input", needs_input)
        builder.add_node("abstained", abstained)
        builder.add_node("failed", failed)
        builder.add_edge(START, "classify")
        builder.add_conditional_edges(
            "classify",
            route_classify,
            {"plan": "plan", "needs_input": "needs_input", "failed": "failed"},
        )
        builder.add_conditional_edges(
            "plan",
            _route_status,
            {
                "continue": "retrieve",
                "abstained": "abstained",
                "failed": "failed",
            },
        )
        builder.add_conditional_edges(
            "retrieve",
            _route_status,
            {
                "continue": "tool_execution",
                "abstained": "abstained",
                "failed": "failed",
            },
        )
        builder.add_conditional_edges(
            "tool_execution",
            _route_status,
            {"continue": "verify", "abstained": "abstained", "failed": "failed"},
        )
        builder.add_conditional_edges(
            "verify",
            _route_status,
            {"continue": "completeness", "abstained": "abstained", "failed": "failed"},
        )
        builder.add_conditional_edges(
            "completeness",
            _route_status,
            {
                "continue": "awaiting_approval",
                "abstained": "abstained",
                "failed": "failed",
            },
        )
        builder.add_edge("awaiting_approval", END)
        builder.add_edge("needs_input", END)
        builder.add_edge("abstained", END)
        builder.add_edge("failed", END)
        return cast(
            CompiledStateGraph[
                WorkflowGraphState, None, WorkflowGraphState, WorkflowGraphState
            ],
            builder.compile(),
        )

    @staticmethod
    def _build_tool_call(
        plan: InvestigationPlan, tool_id: ApprovedToolId, evidence: tuple[Evidence, ...]
    ) -> ToolCall:
        evidence = evidence[:10]
        evidence_ids = tuple(item.id for item in evidence)
        arguments: ToolArguments
        if tool_id is ApprovedToolId.CALCULATE_FINANCIAL_METRIC:
            if plan.financial is None:
                raise _InvariantFailure()
            arguments = FinancialMetricArguments(
                operation=plan.financial.operation,
                left_label=plan.financial.left_label,
                right_label=plan.financial.right_label,
                precision=plan.financial.precision,
                evidence_ids=evidence_ids,
            )
        elif tool_id is ApprovedToolId.INSPECT_CONTRACT_CLAUSE:
            if plan.contract is None:
                raise _InvariantFailure()
            arguments = ContractClauseArguments(
                clause=plan.contract.clause, evidence_ids=evidence_ids
            )
        elif tool_id is ApprovedToolId.DETECT_CONTRADICTIONS:
            if plan.contradiction is None:
                raise _InvariantFailure()
            arguments = ContradictionArguments(
                subject=plan.contradiction.subject, evidence_ids=evidence_ids
            )
        elif tool_id is ApprovedToolId.ANALYZE_MISSING_DOCUMENTS:
            if plan.missing_document is None:
                raise _InvariantFailure()
            arguments = MissingDocumentArguments(
                document_name=plan.missing_document.document_name,
                evidence_ids=evidence_ids,
            )
        else:
            raise _InvariantFailure()
        if tool_id not in APPROVED_TOOL_IDS:
            raise _InvariantFailure()
        return ToolCall(tool_id=tool_id, arguments=arguments, evidence=evidence)


class ApprovalBoundary:
    """The only boundary allowed to create a completed consequential report."""

    def __init__(
        self,
        *,
        event_store: AnalysisEventStore | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.event_store = event_store
        self.clock = clock or SystemClock()

    def decide(
        self, result: InvestigationResult, decision: ApprovalDecision
    ) -> ApprovalOutcome:
        analysis = result.analysis
        if not isinstance(decision, ApprovalDecision):
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.PENDING,
                completed=False,
                reason=ApprovalFailureReason.INTERNAL,
            )
        if decision is ApprovalDecision.REJECTED:
            analysis, _ = self._approval_event(analysis, AgentEventStatus.SKIPPED)
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.REJECTED,
                completed=False,
                reason=ApprovalFailureReason.REJECTED,
            )
        if analysis.status is not AnalysisStatus.AWAITING_APPROVAL:
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.PENDING,
                completed=False,
                reason=ApprovalFailureReason.NOT_AWAITING_APPROVAL,
            )
        if not analysis.findings or any(
            finding.verification_status is not VerificationStatus.VERIFIED
            for finding in analysis.findings
        ):
            analysis, _ = self._approval_event(analysis, AgentEventStatus.FAILED)
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.PENDING,
                completed=False,
                reason=ApprovalFailureReason.UNVERIFIED_FINDINGS,
            )
        if not self._has_valid_workflow_provenance(result):
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.PENDING,
                completed=False,
                reason=ApprovalFailureReason.INTERNAL,
            )
        analysis, event_persisted = self._approval_event(
            analysis, AgentEventStatus.COMPLETED
        )
        if not event_persisted:
            return ApprovalOutcome(
                analysis=analysis,
                approval_state=ApprovalState.PENDING,
                completed=False,
                reason=ApprovalFailureReason.INTERNAL,
            )
        report_id = f"report-{analysis.analysis_id}"
        completed_analysis = analysis.model_copy(
            update={"status": AnalysisStatus.COMPLETED, "report_id": report_id}
        )
        report = Report(
            id=report_id,
            workspace_id=analysis.workspace_id,
            title="Due-diligence investigation findings",
            status=AnalysisStatus.COMPLETED,
            findings=list(analysis.findings),
            calculations=[
                finding.calculation
                for finding in analysis.findings
                if finding.calculation is not None
            ],
            unresolved_questions=[],
            approval_state=ApprovalState.APPROVED,
        )
        return ApprovalOutcome(
            analysis=completed_analysis,
            report=report,
            approval_state=ApprovalState.APPROVED,
            completed=True,
        )

    @staticmethod
    def _has_valid_workflow_provenance(result: InvestigationResult) -> bool:
        if not result.provenance_token or not hmac.compare_digest(
            result.provenance_token, _provenance_token(result)
        ):
            return False
        successful = {
            tool_result.id
            for tool_result in result.tool_results
            if tool_result.status is ToolResultStatus.SUCCEEDED
        }
        tool_results_by_id = {
            tool_result.id: tool_result
            for tool_result in result.tool_results
            if tool_result.status is ToolResultStatus.SUCCEEDED
        }
        findings = result.analysis.findings
        finding_ids = {finding.tool_result_id for finding in findings}
        if (
            not successful
            or len(finding_ids) != len(findings)
            or finding_ids != successful
            or any(
                finding.verification_status is not VerificationStatus.VERIFIED
                or finding.tool_result_id is None
                or not finding.evidence
                or finding.tool_result_id not in tool_results_by_id
                or any(
                    finding_evidence.id
                    not in {
                        item.id
                        for item in tool_results_by_id[finding.tool_result_id].evidence
                    }
                    for finding_evidence in finding.evidence
                )
                for finding in findings
            )
        ):
            return False
        return True

    def _approval_event(
        self, analysis: AnalysisState, status: AgentEventStatus
    ) -> tuple[AnalysisState, bool]:
        if self.event_store is None:
            return analysis, False
        event = AgentEvent(
            sequence=len(analysis.events) + 1,
            node="approval",
            status=status,
            duration_ms=0,
            summary=_SUMMARY[("approval", status)],
        )
        try:
            self.event_store.append(analysis.workspace_id, analysis.analysis_id, event)
        except Exception:
            return analysis, False
        return analysis.model_copy(update={"events": (*analysis.events, event)}), True


__all__ = [
    "ApprovalBoundary",
    "ApprovalDecision",
    "ApprovalFailureReason",
    "ApprovalOutcome",
    "BoundedInvestigationWorkflow",
    "ClassificationResult",
    "ClaimDraft",
    "ClaimGeneratorProvider",
    "ClassifierProvider",
    "Clock",
    "ContractClause",
    "DeterministicClaimGenerator",
    "DeterministicClock",
    "DeterministicInvestigationPlanner",
    "DeterministicQuestionClassifier",
    "DeterministicTokenAccounting",
    "FailureCode",
    "FailureDetail",
    "FinancialPlanInput",
    "GenerationResult",
    "InMemoryAnalysisEventStore",
    "InvestigationBudgets",
    "InvestigationIntent",
    "InvestigationPlan",
    "InvestigationRequest",
    "InvestigationResult",
    "PlannerProvider",
    "WorkflowGraphState",
]

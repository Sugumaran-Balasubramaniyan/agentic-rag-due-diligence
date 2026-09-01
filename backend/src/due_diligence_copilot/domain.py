"""Stable domain contracts shared by the due-diligence copilot layers."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentType(StrEnum):
    FINANCIAL_SUMMARY = "financial_summary"
    CUSTOMER_CONTRACT = "customer_contract"
    SUPPLIER_CONTRACT = "supplier_contract"
    SECURITY_POLICY = "security_policy"
    BOARD_MINUTES = "board_minutes"
    REVENUE_BY_CUSTOMER = "revenue_by_customer"
    DOCUMENT_REQUEST_LIST = "document_request_list"


class BenchmarkCategory(StrEnum):
    FACTUAL = "factual"
    CALCULATION = "calculation"
    CROSS_DOCUMENT = "cross_document"
    CONTRADICTION = "contradiction"
    MISSING_DOCUMENT = "missing_document"
    UNSUPPORTED = "unsupported"
    INJECTION_RESISTANCE = "injection_resistance"


class EvidenceClassification(StrEnum):
    DOCUMENT_EVIDENCE = "document_evidence"
    UNTRUSTED_DOCUMENT_CONTENT = "untrusted_document_content"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    ABSTAINED = "abstained"


class AgentEventStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    FAILED = "failed"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceLocation(ContractModel):
    document_id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=512)
    section: str | None = Field(default=None, max_length=256)
    page: int | None = Field(default=None, ge=1)
    table: str | None = Field(default=None, max_length=256)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    cell: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_coordinates(self) -> Self:
        if self.line_start is None and self.cell is None:
            raise ValueError("source location requires line_start or cell")
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_end requires line_start")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must not precede line_start")
        return self


class DocumentRecord(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    document_type: DocumentType
    path: str = Field(min_length=1, max_length=512)
    media_type: str = Field(min_length=1, max_length=128)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)


DocumentManifestItem = DocumentRecord


class Evidence(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    source_location: SourceLocation
    excerpt: str = Field(min_length=1, max_length=4000)
    chunk_id: str | None = Field(default=None, max_length=128)
    retrieval_score: float | None = Field(default=None, ge=0.0, le=1.0)


class CalculationTrace(ContractModel):
    """Typed output of a deterministic financial calculation."""

    operation: str = Field(min_length=1, max_length=64)
    value: Decimal | None = None
    unit: str = Field(min_length=1, max_length=32)
    tool_result_id: str = Field(min_length=1, max_length=128)


class Finding(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    severity: FindingSeverity
    claim: str = Field(min_length=1, max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus
    calculation: CalculationTrace | None = None
    tool_result_id: str | None = Field(default=None, max_length=128)


class AgentEvent(ContractModel):
    sequence: int = Field(ge=1)
    node: str = Field(min_length=1, max_length=64)
    status: AgentEventStatus
    duration_ms: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=256)


class AnalysisState(ContractModel):
    analysis_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=4000)
    status: AnalysisStatus
    events: tuple[AgentEvent, ...] = Field(default=(), max_length=32)
    findings: tuple[Finding, ...] = Field(default=(), max_length=4)
    report_id: str | None = Field(default=None, max_length=128)


class ExpectedEvidence(ContractModel):
    literal: str = Field(min_length=1, max_length=4000)
    source_location: SourceLocation
    classification: EvidenceClassification = EvidenceClassification.DOCUMENT_EVIDENCE


class ExpectedAnswer(ContractModel):
    answer: str = Field(min_length=1, max_length=4000)
    literal: str = Field(min_length=1, max_length=4000)
    source_location: SourceLocation


class BenchmarkQuestion(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=4000)
    category: BenchmarkCategory
    expected_answer: ExpectedAnswer
    expected_evidence: list[ExpectedEvidence] = Field(min_length=1, max_length=10)


class Report(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    status: AnalysisStatus
    findings: list[Finding] = Field(default_factory=list, max_length=4)
    unresolved_questions: list[Annotated[str, Field(min_length=1, max_length=4000)]] = (
        Field(default_factory=list, max_length=4)
    )
    approval_state: ApprovalState
    calculations: list[CalculationTrace] = Field(default_factory=list, max_length=4)


class GroundTruthManifest(ContractModel):
    schema_version: str = Field(min_length=1, max_length=64)
    generator_version: str = Field(min_length=1, max_length=64)
    generated_at: str = Field(min_length=1, max_length=64)
    synthetic_notice: str = Field(min_length=1, max_length=256)
    documents: list[DocumentRecord] = Field(min_length=1, max_length=32)
    benchmark_questions: list[BenchmarkQuestion] = Field(min_length=1, max_length=32)

    def documents_by_id(self) -> dict[str, DocumentRecord]:
        return {document.id: document for document in self.documents}

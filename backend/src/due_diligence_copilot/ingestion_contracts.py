"""Typed, stable contracts for document ingestion and provenance."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .domain import ContractModel, DocumentType, SourceLocation


class IngestionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionFailureClassification(StrEnum):
    VALIDATION = "validation"
    PERMANENT = "permanent"
    TRANSIENT = "transient"


FailureClassification = IngestionFailureClassification


class UploadDocument(ContractModel):
    workspace_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    content: bytes
    document_type: DocumentType = DocumentType.FINANCIAL_SUMMARY


class NormalizedBlock(ContractModel):
    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    block_type: str = Field(min_length=1)
    source_location: SourceLocation


class Chunk(ContractModel):
    id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=1200)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    block_id: str = Field(min_length=1)
    source_location: SourceLocation


class IngestionJob(ContractModel):
    id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    status: IngestionStatus
    attempts: int = Field(default=0, ge=0, le=3)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    document_id: str | None = None
    deduplicated: bool = False
    failure_classification: IngestionFailureClassification | None = None


class IngestionEvent(ContractModel):
    sequence: int = Field(ge=1)
    job_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    status: IngestionStatus
    attempt: int | None = Field(default=None, ge=1, le=3)
    classification: IngestionFailureClassification | None = None
    summary: str = Field(min_length=1)

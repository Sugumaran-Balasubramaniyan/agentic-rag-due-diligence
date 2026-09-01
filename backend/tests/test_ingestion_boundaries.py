from __future__ import annotations

from typing import Any

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.domain import DocumentType
from due_diligence_copilot.ingestion_contracts import AccessContext, UploadDocument
from due_diligence_copilot.ingestion_service import (
    IngestionService,
    TransientIngestionFailure,
    UploadValidationError,
    validate_upload,
)

AUTHORIZED = AccessContext(principal_id="test", allowed_workspace_ids={"workspace-a"})


def test_supported_extension_with_unsupported_mime_is_rejected() -> None:
    document = UploadDocument(
        workspace_id="workspace-a",
        filename="notes.md",
        media_type="application/octet-stream",
        content=b"# Notes\n",
        document_type=DocumentType.FINANCIAL_SUMMARY,
    )

    try:
        validate_upload(document)
    except UploadValidationError as exc:
        assert "media type" in str(exc)
    else:
        raise AssertionError("unsupported MIME type was accepted")


def test_malformed_csv_fails_permanently_before_object_storage() -> None:
    object_store = InMemoryObjectStore()
    service = IngestionService(
        object_store, InMemoryDocumentRepository(), InMemoryChunkIndex()
    )
    document = UploadDocument(
        workspace_id="workspace-a",
        filename="broken.csv",
        media_type="text/csv",
        content=b'name,value\n"unterminated,1\n',
    )

    job = service.ingest(AUTHORIZED, document)

    assert job.failure_classification == "permanent"
    assert object_store.keys() == ()


def test_always_transient_failure_stops_at_three_attempts() -> None:
    class AlwaysUnavailable:
        attempts = 0

        def parse(self, document: UploadDocument, document_id: str) -> tuple[Any, ...]:
            self.attempts += 1
            raise TransientIngestionFailure("parser unavailable")

    parser = AlwaysUnavailable()
    service = IngestionService(
        InMemoryObjectStore(),
        InMemoryDocumentRepository(),
        InMemoryChunkIndex(),
        parser=parser,
    )

    job = service.ingest(
        AUTHORIZED,
        UploadDocument(
            workspace_id="workspace-a",
            filename="notes.md",
            media_type="text/markdown",
            content=b"# Notes\n",
        ),
    )

    assert job.status == "failed"
    assert job.attempts == 3
    assert job.failure_classification == "transient"
    assert parser.attempts == 3

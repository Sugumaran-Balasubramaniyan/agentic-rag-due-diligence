from __future__ import annotations

import hashlib
from typing import Any

import pytest

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.chunking import chunk_blocks
from due_diligence_copilot.domain import DocumentType
from due_diligence_copilot.ingestion_contracts import (
    IngestionFailureClassification,
    IngestionStatus,
    UploadDocument,
)
from due_diligence_copilot.ingestion_service import (
    IngestionService,
    PermanentIngestionFailure,
    TransientIngestionFailure,
    UploadValidationError,
    validate_upload,
)
from due_diligence_copilot.parsers import CsvDocumentParser, MarkdownDocumentParser


def upload(
    content: bytes = b"# Title\n\n## Section\nA useful fact.\n",
    *,
    filename: str = "notes.md",
    media_type: str = "text/markdown",
    workspace_id: str = "workspace-a",
) -> UploadDocument:
    return UploadDocument(
        workspace_id=workspace_id,
        filename=filename,
        media_type=media_type,
        content=content,
        document_type=DocumentType.FINANCIAL_SUMMARY,
    )


def test_ingestion_contracts_have_stable_wire_values() -> None:
    assert [item.value for item in IngestionStatus] == [
        "queued",
        "running",
        "succeeded",
        "failed",
    ]
    assert [item.value for item in IngestionFailureClassification] == [
        "validation",
        "permanent",
        "transient",
    ]


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (upload(b""), "empty"),
        (upload(b"hello\x00world"), "NUL"),
        (upload(b"\xff"), "UTF-8"),
        (upload(b"x" * (10 * 1024 * 1024 + 1)), "size"),
        (upload(filename="../notes.md"), "filename"),
        (upload(filename="folder/notes.md"), "filename"),
        (
            upload(filename="notes.exe", media_type="application/octet-stream"),
            "extension",
        ),
        (upload(filename="notes.md", media_type="text/csv"), "mismatch"),
        (upload(filename="notes.csv", media_type="text/markdown"), "mismatch"),
    ],
)
def test_upload_validation_rejects_each_boundary(
    candidate: UploadDocument, reason: str
) -> None:
    with pytest.raises(UploadValidationError, match=reason):
        validate_upload(candidate)


def test_markdown_parser_preserves_lines_and_active_sections() -> None:
    blocks = MarkdownDocumentParser().parse(upload(), document_id="doc-1")

    fact = next(block for block in blocks if block.text == "A useful fact.")
    assert fact.source_location.line_start == 4
    assert fact.source_location.line_end == 4
    assert fact.source_location.section == "Section"
    assert fact.source_location.page == 1


def test_csv_parser_preserves_table_and_a1_cell_coordinates() -> None:
    content = b"Customer,Revenue\nNorthstar,5400000\nTotal,5400000\n"
    blocks = CsvDocumentParser().parse(
        upload(content, filename="revenue.csv", media_type="text/csv"),
        document_id="doc-csv",
    )

    northstar = next(block for block in blocks if "Northstar" in block.text)
    revenue = next(block for block in blocks if "5400000" in block.text)
    assert northstar.source_location.table == "revenue"
    assert northstar.source_location.cell == "A2"
    assert revenue.source_location.cell == "B2"
    assert revenue.source_location.line_start == 2


def test_chunking_is_bounded_provenance_preserving_and_stable() -> None:
    blocks = MarkdownDocumentParser().parse(
        upload(b"## One\n" + (b"a" * 1300) + b"\n## Two\nbeta\n"),
        document_id="doc-1",
    )

    first = chunk_blocks(blocks, workspace_id="workspace-a")
    second = chunk_blocks(blocks, workspace_id="workspace-a")

    assert first == second
    assert first
    assert all(len(chunk.text) <= 1200 for chunk in first)
    assert all(chunk.source_location.document_id == "doc-1" for chunk in first)
    assert {chunk.source_location.section for chunk in first} == {"One", "Two"}
    assert all(
        chunk.content_hash == hashlib.sha256(chunk.text.encode()).hexdigest()
        for chunk in first
    )


def test_same_bytes_deduplicate_only_inside_one_workspace() -> None:
    repository = InMemoryDocumentRepository()
    object_store = InMemoryObjectStore()
    index = InMemoryChunkIndex()
    service = IngestionService(object_store, repository, index)

    first = service.ingest(upload())
    duplicate = service.ingest(upload(filename="renamed.md"))
    isolated = service.ingest(upload(workspace_id="workspace-b"))

    assert first.status == IngestionStatus.SUCCEEDED
    assert duplicate.status == IngestionStatus.SUCCEEDED
    assert duplicate.deduplicated is True
    assert duplicate.document_id == first.document_id
    assert isolated.document_id != first.document_id
    assert repository.get("workspace-a", first.document_id) is not None
    assert repository.get("workspace-b", isolated.document_id) is not None
    assert len(index.list("workspace-a")) == len(index.list("workspace-b"))


def test_cross_workspace_reads_are_denied_by_default() -> None:
    repository = InMemoryDocumentRepository()
    service = IngestionService(InMemoryObjectStore(), repository, InMemoryChunkIndex())
    job = service.ingest(upload())

    with pytest.raises(PermissionError):
        service.get_job("workspace-b", job.id)
    with pytest.raises(PermissionError):
        repository.get("workspace-b", job.document_id or "missing")


class FlakyParser:
    def __init__(self) -> None:
        self.attempts = 0
        self.delegate = MarkdownDocumentParser()

    def parse(self, document: UploadDocument, document_id: str) -> tuple[Any, ...]:
        self.attempts += 1
        if self.attempts < 3:
            raise TransientIngestionFailure("upstream parser unavailable")
        return self.delegate.parse(document, document_id)


def test_transient_failures_retry_three_total_attempts_and_are_observable() -> None:
    parser = FlakyParser()
    service = IngestionService(
        InMemoryObjectStore(),
        InMemoryDocumentRepository(),
        InMemoryChunkIndex(),
        parser=parser,
    )

    job = service.ingest(upload())
    events = service.events("workspace-a", job.id)

    assert job.status == IngestionStatus.SUCCEEDED
    assert parser.attempts == 3
    assert [event.attempt for event in events if event.attempt] == [1, 2, 3]
    assert any(event.classification == "transient" for event in events)


def test_permanent_failure_does_not_retry() -> None:
    class BrokenParser:
        attempts = 0

        def parse(self, document: UploadDocument, document_id: str) -> tuple[Any, ...]:
            self.attempts += 1
            raise PermanentIngestionFailure("malformed document")

    parser = BrokenParser()
    service = IngestionService(
        InMemoryObjectStore(),
        InMemoryDocumentRepository(),
        InMemoryChunkIndex(),
        parser=parser,
    )

    job = service.ingest(upload())
    assert job.status == IngestionStatus.FAILED
    assert job.failure_classification == "permanent"
    assert parser.attempts == 1


def test_validation_failure_is_failed_without_attempting_storage() -> None:
    object_store = InMemoryObjectStore()
    service = IngestionService(
        object_store, InMemoryDocumentRepository(), InMemoryChunkIndex()
    )

    job = service.ingest(upload(b"", filename="empty.md"))
    assert job.status == IngestionStatus.FAILED
    assert job.failure_classification == "validation"
    assert object_store.keys() == ()


class FakeMinio:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes, int, str]] = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: Any,
        length: int,
        content_type: str,
    ) -> None:
        self.calls.append((bucket_name, object_name, data.read(), length, content_type))


def test_minio_adapter_uses_workspace_scoped_object_keys() -> None:
    from due_diligence_copilot.adapters import MinioObjectStore

    client = FakeMinio()
    store = MinioObjectStore(client, bucket="documents")
    store.put("workspace-a", "doc-1", b"body", "text/markdown")

    assert client.calls == [
        ("documents", "workspace-a/documents/doc-1", b"body", 4, "text/markdown")
    ]


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, statement: str, parameters: tuple[object, ...]) -> Any:
        self.calls.append((statement, parameters))
        return None


def test_postgres_adapter_keeps_operations_parameterized() -> None:
    from due_diligence_copilot.adapters import PostgresDocumentRepository
    from due_diligence_copilot.domain import DocumentRecord

    connection = FakeConnection()
    repository = PostgresDocumentRepository(connection)
    record = DocumentRecord(
        id="doc-1",
        display_name="Notes",
        document_type=DocumentType.FINANCIAL_SUMMARY,
        path="notes.md",
        media_type="text/markdown",
        sha256="a" * 64,
        byte_length=4,
    )
    repository.save("workspace-a", record)

    statement, parameters = connection.calls[0]
    assert "%s" in statement
    assert "workspace-a" in parameters
    assert "doc-1" in parameters
    assert "workspace-a" not in statement

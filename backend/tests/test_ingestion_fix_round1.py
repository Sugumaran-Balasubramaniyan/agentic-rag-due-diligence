from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.chunking import chunk_blocks
from due_diligence_copilot.domain import DocumentRecord, DocumentType, SourceLocation
from due_diligence_copilot.ingestion_contracts import (
    AccessContext,
    IngestionStatus,
    NormalizedBlock,
    UploadDocument,
)
from due_diligence_copilot.ingestion_errors import (
    AuthorizationError,
    TransientIngestionFailure,
)
from due_diligence_copilot.ingestion_service import IngestionService
from due_diligence_copilot.workspace import validate_workspace_id

AUTHORIZED = AccessContext(
    principal_id="principal-1", allowed_workspace_ids={"workspace-a"}
)
DENIED = AccessContext(
    principal_id="principal-1",
    allowed_workspace_ids={"workspace-b"},
    workspace_id="workspace-a",
)


def document(
    content: bytes = b"# Title\n\n## Section\nA useful fact.\n",
    *,
    workspace_id: str = "workspace-a",
    filename: str = "notes.md",
    media_type: str = "text/markdown",
) -> UploadDocument:
    return UploadDocument(
        workspace_id=workspace_id,
        filename=filename,
        media_type=media_type,
        content=content,
        document_type=DocumentType.FINANCIAL_SUMMARY,
    )


def test_workspace_ids_are_strictly_validated() -> None:
    for value in ("../room", "room/name", ".", "", "9" * 65, " room"):
        with pytest.raises(ValueError):
            validate_workspace_id(value)

    assert validate_workspace_id("workspace-A_1") == "workspace-A_1"


class PortSpy:
    def __init__(self) -> None:
        self.calls = 0

    def touch(self) -> None:
        self.calls += 1


class SpyObjectStore(PortSpy):
    def put(self, *args: object) -> None:
        self.touch()

    def get(self, *args: object) -> bytes:
        self.touch()
        return b""

    def delete(self, *args: object) -> None:
        self.touch()


class SpyRepository(PortSpy):
    def save(self, *args: object) -> None:
        self.touch()

    def get(self, *args: object) -> None:
        self.touch()
        return None

    def find_by_sha256(self, *args: object) -> None:
        self.touch()
        return None


class SpyIndex(PortSpy):
    def store(self, *args: object) -> None:
        self.touch()

    def list(self, *args: object) -> tuple[Any, ...]:
        self.touch()
        return ()

    def delete(self, *args: object) -> None:
        self.touch()


class SpyJobs(PortSpy):
    def create_if_absent(self, *args: object) -> tuple[None, bool]:
        self.touch()
        return None, False

    def save_job(self, *args: object) -> None:
        self.touch()

    def get_job(self, *args: object) -> None:
        self.touch()
        return None


class SpyEvents(PortSpy):
    def save_event(self, *args: object) -> None:
        self.touch()

    def list_events(self, *args: object) -> tuple[Any, ...]:
        self.touch()
        return ()


def test_unauthorized_ingest_and_read_make_zero_port_calls() -> None:
    object_store = SpyObjectStore()
    repository = SpyRepository()
    index = SpyIndex()
    jobs = SpyJobs()
    events = SpyEvents()
    service = IngestionService(
        object_store,
        repository,
        index,
        job_repository=jobs,
        event_store=events,
    )

    with pytest.raises(AuthorizationError):
        service.ingest(DENIED, document())
    with pytest.raises(AuthorizationError):
        service.get_job(DENIED, "job-missing")

    assert (
        sum(spy.calls for spy in (object_store, repository, index, jobs, events)) == 0
    )


def test_chunker_rejects_invalid_limits_and_faulty_provenance() -> None:
    valid_location = SourceLocation(
        document_id="doc-1", path="notes.md", line_start=1, line_end=1
    )
    faulty = NormalizedBlock.model_construct(
        id="block-1",
        document_id="doc-1",
        ordinal=0,
        text="fact",
        block_type="markdown_line",
        source_location=valid_location.model_copy(update={"document_id": "other"}),
    )

    with pytest.raises(ValueError, match="max_characters"):
        chunk_blocks((faulty,), workspace_id="workspace-a", max_characters=0)
    with pytest.raises(ValueError, match="max_characters"):
        chunk_blocks((faulty,), workspace_id="workspace-a", max_characters=1201)
    with pytest.raises(ValueError, match="document_id"):
        chunk_blocks((faulty,), workspace_id="workspace-a")


class FailingChunkIndex(InMemoryChunkIndex):
    def __init__(self) -> None:
        super().__init__()
        self.failures = 1
        self.deleted: list[tuple[str, str]] = []

    def store(self, workspace_id: str, chunks: tuple[Any, ...]) -> None:
        super().store(workspace_id, chunks)
        if self.failures:
            self.failures -= 1
            raise TransientIngestionFailure("index unavailable")

    def delete(self, workspace_id: str, document_id: str) -> None:
        self.deleted.append((workspace_id, document_id))
        super().delete(workspace_id, document_id)


def test_partial_writes_are_compensated_before_successful_retry() -> None:
    object_store = InMemoryObjectStore()
    index = FailingChunkIndex()
    repository = InMemoryDocumentRepository()
    service = IngestionService(object_store, repository, index)

    job = service.ingest(AUTHORIZED, document())

    assert job.status == IngestionStatus.SUCCEEDED
    assert len(index.deleted) == 1
    assert repository.get("workspace-a", job.document_id or "") is not None
    assert object_store.keys() == (("workspace-a", job.document_id or ""),)
    assert len(index.list("workspace-a")) > 0


def test_incomplete_dedupe_record_is_repaired_through_normal_ingestion() -> None:
    object_store = InMemoryObjectStore()
    repository = InMemoryDocumentRepository()
    index = InMemoryChunkIndex()
    service = IngestionService(object_store, repository, index)
    content = document()
    sha256 = __import__("hashlib").sha256(content.content).hexdigest()
    document_id = "document-repair"
    repository.save(
        "workspace-a",
        DocumentRecord(
            id=document_id,
            display_name="notes",
            document_type=DocumentType.FINANCIAL_SUMMARY,
            path="notes.md",
            media_type="text/markdown",
            sha256=sha256,
            byte_length=len(content.content),
        ),
    )

    job = service.ingest(AUTHORIZED, content)

    assert job.deduplicated is False
    assert object_store.keys() == (("workspace-a", job.document_id or ""),)
    assert index.list("workspace-a")


class DedupeReadRetryRepository(InMemoryDocumentRepository):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    def find_by_sha256(self, workspace_id: str, sha256: str) -> DocumentRecord | None:
        self.reads += 1
        if self.reads == 1:
            raise RuntimeError("database connection details must not be logged")
        return super().find_by_sha256(workspace_id, sha256)


def test_unexpected_dedupe_read_failure_retries_and_does_not_leak_error_text() -> None:
    repository = DedupeReadRetryRepository()
    service = IngestionService(InMemoryObjectStore(), repository, InMemoryChunkIndex())

    job = service.ingest(AUTHORIZED, document())
    events = service.events(AUTHORIZED, job.id)

    assert job.status == IngestionStatus.SUCCEEDED
    assert job.attempts == 2
    assert all("database connection details" not in event.summary for event in events)


class CountingObjectStore(InMemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.puts = 0

    def put(
        self, workspace_id: str, document_id: str, content: bytes, media_type: str
    ) -> None:
        self.puts += 1
        super().put(workspace_id, document_id, content, media_type)


def test_identical_submissions_are_atomic_and_idempotent() -> None:
    object_store = CountingObjectStore()
    service = IngestionService(
        object_store, InMemoryDocumentRepository(), InMemoryChunkIndex()
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = list(
            executor.map(lambda _: service.ingest(AUTHORIZED, document()), range(2))
        )

    assert {job.id for job in jobs} == {jobs[0].id}
    assert all(job.status == IngestionStatus.SUCCEEDED for job in jobs)
    assert object_store.puts == 1
    assert len(service.events(AUTHORIZED, jobs[0].id)) == 3


class TypedResponse:
    def __init__(self) -> None:
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return b"body"

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class TypedMinio:
    def __init__(self) -> None:
        self.response = TypedResponse()
        self.removed: tuple[str, str] | None = None

    def put_object(self, *args: object) -> None:
        return None

    def get_object(self, bucket_name: str, object_name: str) -> TypedResponse:
        return self.response

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.removed = (bucket_name, object_name)


def test_minio_get_uses_typed_response_cleanup() -> None:
    from due_diligence_copilot.adapters import MinioObjectStore

    client = TypedMinio()
    assert (
        MinioObjectStore(client, bucket="documents").get("workspace-a", "doc-1")
        == b"body"
    )
    assert client.response.closed is True
    assert client.response.released is True


def test_minio_delete_uses_typed_remove_object() -> None:
    from due_diligence_copilot.adapters import MinioObjectStore

    client = TypedMinio()
    MinioObjectStore(client, bucket="documents").delete("workspace-a", "doc-1")

    assert client.removed == ("documents", "workspace-a/documents/doc-1")


class AlwaysFailingObjectStore(InMemoryObjectStore):
    def put(
        self, workspace_id: str, document_id: str, content: bytes, media_type: str
    ) -> None:
        super().put(workspace_id, document_id, content, media_type)
        raise RuntimeError("adapter secret must not be logged")


def test_failed_attempts_leave_no_partial_state_and_terminal_status() -> None:
    object_store = AlwaysFailingObjectStore()
    repository = InMemoryDocumentRepository()
    index = InMemoryChunkIndex()
    service = IngestionService(object_store, repository, index)

    job = service.ingest(AUTHORIZED, document())

    assert job.status == IngestionStatus.FAILED
    assert job.attempts == 3
    assert job.failure_classification == "transient"
    assert object_store.keys() == ()
    assert index.list("workspace-a") == ()
    assert repository.find_by_sha256("workspace-a", job.sha256 or "") is None
    assert all(
        "adapter secret" not in event.summary
        for event in service.events(AUTHORIZED, job.id)
    )


class FaultyProvenanceParser:
    def parse(
        self, document: UploadDocument, document_id: str
    ) -> tuple[NormalizedBlock, ...]:
        location = SourceLocation(
            document_id="other-document", path=document.filename, line_start=1
        )
        return (
            NormalizedBlock.model_construct(
                id="faulty",
                document_id=document_id,
                ordinal=0,
                text="fact",
                block_type="markdown_line",
                source_location=location,
            ),
        )


def test_service_rejects_faulty_parser_provenance_without_retry() -> None:
    parser = FaultyProvenanceParser()
    object_store = InMemoryObjectStore()
    index = InMemoryChunkIndex()
    service = IngestionService(
        object_store, InMemoryDocumentRepository(), index, parser=parser
    )

    job = service.ingest(AUTHORIZED, document())

    assert job.status == IngestionStatus.FAILED
    assert job.attempts == 1
    assert job.failure_classification == "permanent"
    assert object_store.keys() == ()
    assert index.list("workspace-a") == ()

"""Validated ingestion orchestration with bounded retries and redacted events."""

from __future__ import annotations

import hashlib
from pathlib import PurePath

from .adapters import InMemoryIngestionEventStore
from .chunking import chunk_blocks
from .domain import DocumentRecord
from .ingestion_contracts import (
    IngestionEvent,
    IngestionFailureClassification,
    IngestionJob,
    IngestionStatus,
    UploadDocument,
)
from .ingestion_errors import (
    IngestionFailure,
    PermanentIngestionFailure,
    TransientIngestionFailure,
    UploadValidationError,
)

__all__ = [
    "IngestionService",
    "PermanentIngestionFailure",
    "TransientIngestionFailure",
    "UploadValidationError",
    "validate_upload",
]
from .parser_dispatch import DeterministicDocumentParser
from .ports import (
    ChunkIndex,
    DocumentParser,
    DocumentRepository,
    IngestionEventStore,
    ObjectStore,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MEDIA_TYPES = {".md": "text/markdown", ".csv": "text/csv"}


def _normalized_media_type(media_type: str) -> str:
    return media_type.split(";", 1)[0].strip().lower()


def validate_upload(document: UploadDocument) -> UploadDocument:
    filename = document.filename
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or PurePath(filename).name != filename
    ):
        raise UploadValidationError("filename contains unsafe path separators")
    if len(document.content) == 0 or not document.content.strip():
        raise UploadValidationError("upload is empty")
    if len(document.content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("upload exceeds maximum size")
    if b"\x00" in document.content:
        raise UploadValidationError("upload contains NUL bytes")
    try:
        decoded = document.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("upload is not valid UTF-8") from exc
    if not decoded.strip():
        raise UploadValidationError("upload is empty")

    extension = PurePath(filename).suffix.lower()
    expected_media_type = _MEDIA_TYPES.get(extension)
    if expected_media_type is None:
        raise UploadValidationError("unsupported filename extension")
    actual_media_type = _normalized_media_type(document.media_type)
    if actual_media_type not in set(_MEDIA_TYPES.values()):
        raise UploadValidationError("unsupported media type")
    if actual_media_type != expected_media_type:
        raise UploadValidationError("extension and media type mismatch")
    return document.model_copy(update={"media_type": actual_media_type})


class IngestionService:
    def __init__(
        self,
        object_store: ObjectStore,
        document_repository: DocumentRepository,
        chunk_index: ChunkIndex,
        *,
        parser: DocumentParser | None = None,
        event_store: IngestionEventStore | None = None,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts != 3:
            raise ValueError("Task 3 requires exactly three total attempts")
        self._object_store = object_store
        self._documents = document_repository
        self._chunks = chunk_index
        self._parser = parser or DeterministicDocumentParser()
        self._events = event_store or InMemoryIngestionEventStore()
        self._max_attempts = max_attempts

    @staticmethod
    def _job_id(document: UploadDocument) -> str:
        material = (
            f"{document.workspace_id}\0{document.filename}\0".encode()
            + document.content
        )
        return f"job-{hashlib.sha256(material).hexdigest()}"

    @staticmethod
    def _document_id(workspace_id: str, sha256: str) -> str:
        material = f"{workspace_id}\0{sha256}"
        digest = hashlib.sha256(material.encode()).hexdigest()
        return f"document-{digest}"

    def _save(self, job: IngestionJob) -> None:
        self._events.save_job(job)

    def _event(
        self,
        job: IngestionJob,
        *,
        status: IngestionStatus,
        attempt: int | None = None,
        classification: IngestionFailureClassification | None = None,
        summary: str,
    ) -> None:
        current = self._events.list_events(job.workspace_id, job.id)
        self._events.save_event(
            IngestionEvent(
                sequence=len(current) + 1,
                job_id=job.id,
                workspace_id=job.workspace_id,
                status=status,
                attempt=attempt,
                classification=classification,
                summary=summary,
            )
        )

    def _update(
        self,
        job: IngestionJob,
        *,
        status: IngestionStatus,
        attempt: int | None = None,
        classification: IngestionFailureClassification | None = None,
        summary: str,
    ) -> IngestionJob:
        updated = job.model_copy(
            update={
                "status": status,
                "attempts": attempt if attempt is not None else job.attempts,
                "failure_classification": classification,
            }
        )
        self._save(updated)
        self._event(
            updated,
            status=status,
            attempt=attempt,
            classification=classification,
            summary=summary,
        )
        return updated

    def ingest(self, document: UploadDocument) -> IngestionJob:
        job = IngestionJob(
            id=self._job_id(document),
            workspace_id=document.workspace_id,
            filename=document.filename,
            media_type=document.media_type,
            status=IngestionStatus.QUEUED,
        )
        self._save(job)
        self._event(job, status=IngestionStatus.QUEUED, summary="Ingestion job queued")
        job = self._update(
            job, status=IngestionStatus.RUNNING, summary="Ingestion job running"
        )

        try:
            document = validate_upload(document)
            sha256 = hashlib.sha256(document.content).hexdigest()
            job = job.model_copy(
                update={"sha256": sha256, "media_type": document.media_type}
            )
            self._save(job)
            existing = self._documents.find_by_sha256(document.workspace_id, sha256)
            if existing is not None:
                job = job.model_copy(
                    update={
                        "status": IngestionStatus.SUCCEEDED,
                        "attempts": 1,
                        "document_id": existing.id,
                        "deduplicated": True,
                    }
                )
                self._save(job)
                self._event(
                    job,
                    status=job.status,
                    attempt=1,
                    summary="Existing document reused",
                )
                return job
        except IngestionFailure as failure:
            return self._failed(job, failure, attempt=1)

        document_id = self._document_id(document.workspace_id, sha256)
        for attempt in range(1, self._max_attempts + 1):
            try:
                blocks = self._parser.parse(document, document_id)
                chunks = chunk_blocks(blocks, workspace_id=document.workspace_id)
                self._object_store.put(
                    document.workspace_id,
                    document_id,
                    document.content,
                    document.media_type,
                )
                record = DocumentRecord(
                    id=document_id,
                    display_name=PurePath(document.filename).stem,
                    document_type=document.document_type,
                    path=document.filename,
                    media_type=document.media_type,
                    sha256=sha256,
                    byte_length=len(document.content),
                )
                self._documents.save(document.workspace_id, record)
                self._chunks.store(document.workspace_id, chunks)
                job = job.model_copy(
                    update={
                        "status": IngestionStatus.SUCCEEDED,
                        "attempts": attempt,
                        "document_id": document_id,
                        "failure_classification": None,
                    }
                )
                self._save(job)
                self._event(
                    job,
                    status=job.status,
                    attempt=attempt,
                    summary="Ingestion succeeded",
                )
                return job
            except IngestionFailure as failure:
                if (
                    failure.classification == IngestionFailureClassification.TRANSIENT
                    and attempt < self._max_attempts
                ):
                    job = job.model_copy(update={"attempts": attempt})
                    self._save(job)
                    self._event(
                        job,
                        status=IngestionStatus.RUNNING,
                        attempt=attempt,
                        classification=failure.classification,
                        summary="Transient ingestion failure; retry scheduled",
                    )
                    continue
                return self._failed(job, failure, attempt=attempt)
            except Exception as exc:
                return self._failed(
                    job,
                    PermanentIngestionFailure(type(exc).__name__),
                    attempt=attempt,
                )
        return self._failed(
            job, PermanentIngestionFailure("attempt limit reached"), attempt=3
        )

    def _failed(
        self, job: IngestionJob, failure: IngestionFailure, *, attempt: int
    ) -> IngestionJob:
        failed = job.model_copy(
            update={
                "status": IngestionStatus.FAILED,
                "attempts": attempt,
                "failure_classification": failure.classification,
            }
        )
        self._save(failed)
        self._event(
            failed,
            status=failed.status,
            attempt=attempt,
            classification=failure.classification,
            summary="Ingestion failed",
        )
        return failed

    def get_job(self, workspace_id: str, job_id: str) -> IngestionJob:
        job = self._events.get_job(workspace_id, job_id)
        if job is None:
            raise PermissionError("job is not available in this workspace")
        return job

    def events(self, workspace_id: str, job_id: str) -> tuple[IngestionEvent, ...]:
        job = self.get_job(workspace_id, job_id)
        return self._events.list_events(job.workspace_id, job.id)

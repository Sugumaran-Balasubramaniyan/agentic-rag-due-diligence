"""Validated ingestion orchestration with bounded retries and redacted events."""

from __future__ import annotations

import hashlib
from pathlib import PurePath

from .adapters import InMemoryIngestionEventStore
from .chunking import chunk_blocks
from .domain import DocumentRecord
from .ingestion_contracts import (
    AccessContext,
    Chunk,
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
    JobRepository,
    ObjectStore,
)
from .workspace import require_read_workspace, require_workspace_access

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
        job_repository: JobRepository | None = None,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts != 3:
            raise ValueError("Task 3 requires exactly three total attempts")
        self._object_store = object_store
        self._documents = document_repository
        self._chunks = chunk_index
        self._parser = parser or DeterministicDocumentParser()
        self._events = event_store or InMemoryIngestionEventStore()
        self._jobs = job_repository or InMemoryIngestionEventStore()
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
        self._jobs.save_job(job)

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

    def _cleanup(self, workspace_id: str, document_id: str) -> bool:
        clean = True
        try:
            self._documents.delete(workspace_id, document_id)
        except Exception:
            clean = False
        try:
            self._chunks.delete(workspace_id, document_id)
        except Exception:
            clean = False
        try:
            self._object_store.delete(workspace_id, document_id)
        except Exception:
            clean = False
        return clean

    def _parse_and_chunk(
        self, document: UploadDocument, document_id: str
    ) -> tuple[Chunk, ...]:
        blocks = self._parser.parse(document, document_id)
        if any(block.document_id != document_id for block in blocks):
            raise PermanentIngestionFailure(
                "parser returned an unexpected document identity"
            )
        try:
            return chunk_blocks(blocks, workspace_id=document.workspace_id)
        except ValueError as exc:
            raise PermanentIngestionFailure("parser provenance is invalid") from exc

    def _is_committed(
        self,
        workspace_id: str,
        document: DocumentRecord,
        source_document: UploadDocument,
    ) -> bool:
        try:
            content = self._object_store.get(workspace_id, document.id)
            if (
                hashlib.sha256(content).hexdigest() != document.sha256
                or len(content) != document.byte_length
            ):
                return False
        except PermissionError:
            return False
        chunks = tuple(
            chunk
            for chunk in self._chunks.list(workspace_id)
            if chunk.document_id == document.id
        )
        if not chunks or [chunk.ordinal for chunk in chunks] != list(
            range(len(chunks))
        ):
            return False
        expected_document = source_document.model_copy(
            update={
                "filename": document.path,
                "media_type": document.media_type,
                "document_type": document.document_type,
            }
        )
        expected_chunks = self._parse_and_chunk(expected_document, document.id)
        return chunks == expected_chunks

    def ingest(self, context: AccessContext, document: UploadDocument) -> IngestionJob:
        require_workspace_access(context, document.workspace_id)
        initial_job = IngestionJob(
            id=self._job_id(document),
            workspace_id=document.workspace_id,
            filename=document.filename,
            media_type=document.media_type,
            status=IngestionStatus.QUEUED,
        )
        job, created = self._jobs.create_if_absent(initial_job)
        if not created:
            return self._jobs.wait_for_terminal(job.workspace_id, job.id)

        self._event(job, status=IngestionStatus.QUEUED, summary="Ingestion job queued")
        job = job.model_copy(update={"status": IngestionStatus.RUNNING})
        self._save(job)
        self._event(
            job, status=IngestionStatus.RUNNING, summary="Ingestion job running"
        )

        try:
            document = validate_upload(document)
            sha256 = hashlib.sha256(document.content).hexdigest()
            job = job.model_copy(
                update={"sha256": sha256, "media_type": document.media_type}
            )
            self._save(job)
        except UploadValidationError as failure:
            return self._failed(job, failure, attempt=1)

        document_id = self._document_id(document.workspace_id, sha256)
        for attempt in range(1, self._max_attempts + 1):
            object_started = False
            chunks_started = False
            record_started = False
            committed = False
            try:
                existing = self._documents.find_by_sha256(document.workspace_id, sha256)
                if existing is not None:
                    if self._is_committed(document.workspace_id, existing, document):
                        job = job.model_copy(
                            update={
                                "status": IngestionStatus.SUCCEEDED,
                                "attempts": attempt,
                                "document_id": existing.id,
                                "deduplicated": True,
                                "failure_classification": None,
                            }
                        )
                        self._save(job)
                        self._event(
                            job,
                            status=job.status,
                            attempt=attempt,
                            summary="Existing document reused",
                        )
                        return job
                    if not self._cleanup(document.workspace_id, existing.id):
                        raise PermanentIngestionFailure("repair cleanup failed")
                    document_id = existing.id

                chunks = self._parse_and_chunk(document, document_id)
                object_started = True
                self._object_store.put(
                    document.workspace_id,
                    document_id,
                    document.content,
                    document.media_type,
                )
                chunks_started = True
                self._chunks.store(document.workspace_id, chunks)
                record = DocumentRecord(
                    id=document_id,
                    display_name=PurePath(document.filename).stem,
                    document_type=document.document_type,
                    path=document.filename,
                    media_type=document.media_type,
                    sha256=sha256,
                    byte_length=len(document.content),
                )
                record_started = True
                self._documents.save(document.workspace_id, record)
                committed = True
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
                if not committed and (
                    object_started or chunks_started or record_started
                ):
                    clean = self._cleanup(document.workspace_id, document_id)
                else:
                    clean = True
                if (
                    failure.classification == IngestionFailureClassification.TRANSIENT
                    and attempt < self._max_attempts
                    and clean
                ):
                    job = job.model_copy(update={"attempts": attempt})
                    self._save(job)
                    self._event(
                        job,
                        status=IngestionStatus.RUNNING,
                        attempt=attempt,
                        classification=IngestionFailureClassification.TRANSIENT,
                        summary="Transient ingestion failure; retry scheduled",
                    )
                    continue
                return self._failed(job, failure, attempt=attempt)
            except Exception:
                mutation_started = object_started or chunks_started or record_started
                if committed or not mutation_started:
                    clean = True
                else:
                    clean = self._cleanup(document.workspace_id, document_id)
                if clean and attempt < self._max_attempts:
                    job = job.model_copy(update={"attempts": attempt})
                    self._save(job)
                    self._event(
                        job,
                        status=IngestionStatus.RUNNING,
                        attempt=attempt,
                        classification=IngestionFailureClassification.TRANSIENT,
                        summary="Transient ingestion failure; retry scheduled",
                    )
                    continue
                return self._failed(
                    job,
                    TransientIngestionFailure("adapter operation failed"),
                    attempt=attempt,
                )
        return self._failed(
            job, TransientIngestionFailure("attempt limit reached"), attempt=3
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

    def get_job(self, context: AccessContext, job_id: str) -> IngestionJob:
        workspace_id = require_read_workspace(context)
        job = self._jobs.get_job(workspace_id, job_id)
        if job is None:
            raise PermissionError("job is not available in this workspace")
        return job

    def events(self, context: AccessContext, job_id: str) -> tuple[IngestionEvent, ...]:
        job = self.get_job(context, job_id)
        return self._events.list_events(job.workspace_id, job.id)

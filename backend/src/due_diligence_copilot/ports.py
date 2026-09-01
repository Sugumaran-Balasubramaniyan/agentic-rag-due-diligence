"""Small dependency-inversion ports for ingestion and indexing."""

from __future__ import annotations

from io import BytesIO
from typing import Protocol

from .domain import DocumentRecord
from .ingestion_contracts import (
    Chunk,
    IngestionEvent,
    IngestionJob,
    NormalizedBlock,
    UploadDocument,
)


class ObjectStore(Protocol):
    def put(
        self, workspace_id: str, document_id: str, content: bytes, media_type: str
    ) -> None: ...

    def get(self, workspace_id: str, document_id: str) -> bytes: ...

    def delete(self, workspace_id: str, document_id: str) -> None: ...


class DocumentRepository(Protocol):
    def save(self, workspace_id: str, document: DocumentRecord) -> None: ...
    def delete(self, workspace_id: str, document_id: str) -> None: ...

    def get(self, workspace_id: str, document_id: str) -> DocumentRecord | None: ...

    def find_by_sha256(
        self, workspace_id: str, sha256: str
    ) -> DocumentRecord | None: ...


class ChunkIndex(Protocol):
    def store(self, workspace_id: str, chunks: tuple[Chunk, ...]) -> None: ...

    def list(self, workspace_id: str) -> tuple[Chunk, ...]: ...

    def delete(self, workspace_id: str, document_id: str) -> None: ...


class DocumentParser(Protocol):
    def parse(
        self, document: UploadDocument, document_id: str
    ) -> tuple[NormalizedBlock, ...]: ...


class JobRepository(Protocol):
    def create_if_absent(self, job: IngestionJob) -> tuple[IngestionJob, bool]: ...

    def save_job(self, job: IngestionJob) -> None: ...

    def get_job(self, workspace_id: str, job_id: str) -> IngestionJob | None: ...

    def wait_for_terminal(self, workspace_id: str, job_id: str) -> IngestionJob: ...


class IngestionEventStore(Protocol):
    def save_job(self, job: IngestionJob) -> None: ...

    def save_event(self, event: IngestionEvent) -> None: ...

    def get_job(self, workspace_id: str, job_id: str) -> IngestionJob | None: ...

    def list_events(
        self, workspace_id: str, job_id: str
    ) -> tuple[IngestionEvent, ...]: ...


class MinioResponse(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class MinioClient(Protocol):
    def get_object(self, bucket_name: str, object_name: str) -> MinioResponse: ...

    def remove_object(self, bucket_name: str, object_name: str) -> object: ...

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> object: ...


class PostgresConnection(Protocol):
    def execute(self, statement: str, parameters: tuple[object, ...]) -> object: ...

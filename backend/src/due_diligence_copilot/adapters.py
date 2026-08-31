"""Deterministic in-memory adapters and external-service boundaries."""

from __future__ import annotations

from io import BytesIO

from .domain import DocumentRecord, DocumentType
from .ingestion_contracts import Chunk, IngestionEvent, IngestionJob
from .ports import (
    IngestionEventStore,
    MinioClient,
    ObjectStore,
    PostgresConnection,
)


class InMemoryObjectStore(ObjectStore):
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put(
        self, workspace_id: str, document_id: str, content: bytes, media_type: str
    ) -> None:
        del media_type
        self._objects[(workspace_id, document_id)] = bytes(content)

    def get(self, workspace_id: str, document_id: str) -> bytes:
        try:
            return self._objects[(workspace_id, document_id)]
        except KeyError as exc:
            raise PermissionError(
                "document is not available in this workspace"
            ) from exc

    def keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._objects))


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], DocumentRecord] = {}

    def save(self, workspace_id: str, document: DocumentRecord) -> None:
        self._documents[(workspace_id, document.id)] = document

    def get(self, workspace_id: str, document_id: str) -> DocumentRecord | None:
        key = (workspace_id, document_id)
        if key in self._documents:
            return self._documents[key]
        if any(existing_id == document_id for _, existing_id in self._documents):
            raise PermissionError("document belongs to another workspace")
        return None

    def find_by_sha256(self, workspace_id: str, sha256: str) -> DocumentRecord | None:
        return next(
            (
                document
                for (stored_workspace, _), document in self._documents.items()
                if stored_workspace == workspace_id and document.sha256 == sha256
            ),
            None,
        )


class InMemoryChunkIndex:
    def __init__(self) -> None:
        self._chunks: dict[tuple[str, str], Chunk] = {}

    def store(self, workspace_id: str, chunks: tuple[Chunk, ...]) -> None:
        if any(chunk.workspace_id != workspace_id for chunk in chunks):
            raise PermissionError("chunk workspace does not match index workspace")
        for chunk in chunks:
            self._chunks[(workspace_id, chunk.id)] = chunk

    def list(self, workspace_id: str) -> tuple[Chunk, ...]:
        return tuple(
            sorted(
                (
                    chunk
                    for (stored_workspace, _), chunk in self._chunks.items()
                    if stored_workspace == workspace_id
                ),
                key=lambda chunk: (chunk.document_id, chunk.ordinal),
            )
        )


class InMemoryIngestionEventStore(IngestionEventStore):
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], IngestionJob] = {}
        self._events: dict[tuple[str, str], list[IngestionEvent]] = {}

    def save_job(self, job: IngestionJob) -> None:
        self._jobs[(job.workspace_id, job.id)] = job

    def save_event(self, event: IngestionEvent) -> None:
        key = (event.workspace_id, event.job_id)
        self._events.setdefault(key, []).append(event)

    def get_job(self, workspace_id: str, job_id: str) -> IngestionJob | None:
        key = (workspace_id, job_id)
        if key in self._jobs:
            return self._jobs[key]
        if any(existing_id == job_id for _, existing_id in self._jobs):
            raise PermissionError("job belongs to another workspace")
        return None

    def list_events(self, workspace_id: str, job_id: str) -> tuple[IngestionEvent, ...]:
        return tuple(self._events.get((workspace_id, job_id), ()))


class MinioObjectStore(ObjectStore):
    """MinIO boundary; lifecycle/client configuration lives outside this adapter."""

    def __init__(self, client: MinioClient, *, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @staticmethod
    def _key(workspace_id: str, document_id: str) -> str:
        return f"{workspace_id}/documents/{document_id}"

    def put(
        self, workspace_id: str, document_id: str, content: bytes, media_type: str
    ) -> None:
        self._client.put_object(
            self._bucket,
            self._key(workspace_id, document_id),
            BytesIO(content),
            len(content),
            media_type,
        )

    def get(self, workspace_id: str, document_id: str) -> bytes:
        getter = getattr(self._client, "get_object", None)
        if getter is None:
            raise NotImplementedError("injected MinIO client must provide get_object")
        response = getter(self._bucket, self._key(workspace_id, document_id))
        try:
            data = response.read()
            if not isinstance(data, bytes):
                raise TypeError("MinIO response did not return bytes")
            return data
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()


class PostgresDocumentRepository:
    """PostgreSQL boundary using injected connections; migrations belong to Task 6."""

    @staticmethod
    def _decode_result(result: object) -> DocumentRecord | None:
        fetchone = getattr(result, "fetchone", None)
        if not callable(fetchone):
            return None
        row = fetchone()
        if row is None:
            return None
        if not isinstance(row, tuple | list) or len(row) != 7:
            raise TypeError("PostgreSQL document result must contain seven columns")
        return DocumentRecord(
            id=str(row[0]),
            display_name=str(row[1]),
            document_type=DocumentType(str(row[2])),
            path=str(row[3]),
            media_type=str(row[4]),
            sha256=str(row[5]),
            byte_length=int(row[6]),
        )

    def __init__(
        self, connection: PostgresConnection, *, table: str = "documents"
    ) -> None:
        if not table.replace("_", "").isalnum():
            raise ValueError("table must be a simple identifier")
        self._connection = connection
        self._table = table

    def save(self, workspace_id: str, document: DocumentRecord) -> None:
        self._connection.execute(
            f"INSERT INTO {self._table} "
            "(workspace_id, id, display_name, document_type, path, media_type, "
            "sha256, byte_length) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                workspace_id,
                document.id,
                document.display_name,
                document.document_type.value,
                document.path,
                document.media_type,
                document.sha256,
                document.byte_length,
            ),
        )

    def get(self, workspace_id: str, document_id: str) -> DocumentRecord | None:
        result = self._connection.execute(
            f"SELECT id, display_name, document_type, path, media_type, "
            f"sha256, byte_length "
            f"FROM {self._table} WHERE workspace_id = %s AND id = %s",
            (workspace_id, document_id),
        )
        return self._decode_result(result)

    def find_by_sha256(self, workspace_id: str, sha256: str) -> DocumentRecord | None:
        result = self._connection.execute(
            f"SELECT id, display_name, document_type, path, media_type, "
            f"sha256, byte_length "
            f"FROM {self._table} WHERE workspace_id = %s AND sha256 = %s",
            (workspace_id, sha256),
        )
        return self._decode_result(result)

from __future__ import annotations

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.ingestion_contracts import (
    AccessContext,
    IngestionStatus,
    UploadDocument,
)
from due_diligence_copilot.ingestion_service import IngestionService
from due_diligence_copilot.synthetic_data import build_manifest

AUTHORIZED = AccessContext(principal_id="test", allowed_workspace_ids={"asteria"})


def test_canonical_asteria_documents_ingest_with_complete_provenance() -> None:
    repository = InMemoryDocumentRepository()
    index = InMemoryChunkIndex()
    service = IngestionService(InMemoryObjectStore(), repository, index)
    manifest, sources = build_manifest()

    jobs = [
        service.ingest(
            AUTHORIZED,
            UploadDocument(
                workspace_id="asteria",
                filename=source.path,
                media_type=source.media_type,
                content=source.content,
                document_type=source.document_type,
            ),
        )
        for source in sources
    ]

    assert len(jobs) == len(manifest.documents) == 7
    assert all(job.status == IngestionStatus.SUCCEEDED for job in jobs)
    chunks = index.list("asteria")
    assert len(chunks) > len(jobs)
    assert all(chunk.source_location.document_id for chunk in chunks)
    assert all(chunk.source_location.path for chunk in chunks)
    assert any(chunk.source_location.section == "Key figures" for chunk in chunks)
    assert any(chunk.source_location.cell == "A2" for chunk in chunks)
    assert all(len(chunk.text) <= 1200 for chunk in chunks)


def test_ingestion_events_never_include_source_content() -> None:
    service = IngestionService(
        InMemoryObjectStore(), InMemoryDocumentRepository(), InMemoryChunkIndex()
    )
    secret_like_text = "DO NOT LOG THIS SOURCE VALUE"
    job = service.ingest(
        AUTHORIZED,
        UploadDocument(
            workspace_id="asteria",
            filename="notes.md",
            media_type="text/markdown",
            content=f"## Notes\n{secret_like_text}\n".encode(),
        ),
    )

    assert all(
        secret_like_text not in event.summary
        for event in service.events(AUTHORIZED, job.id)
    )


def test_every_canonical_document_and_chunk_keeps_workspace_and_location_identity() -> (
    None
):
    repository = InMemoryDocumentRepository()
    index = InMemoryChunkIndex()
    service = IngestionService(InMemoryObjectStore(), repository, index)
    manifest, sources = build_manifest()

    jobs = [
        service.ingest(
            AUTHORIZED,
            UploadDocument(
                workspace_id="asteria",
                filename=source.path,
                media_type=source.media_type,
                content=source.content,
                document_type=source.document_type,
            ),
        )
        for source in sources
    ]
    chunks = index.list("asteria")
    expected_by_path = {item.path: item for item in manifest.documents}

    assert len(jobs) == len(sources)
    for job in jobs:
        expected = expected_by_path[job.filename]
        record = repository.get("asteria", job.document_id or "")
        assert record is not None
        assert record.path == expected.path
        assert record.sha256 == expected.sha256
        document_chunks = tuple(
            chunk for chunk in chunks if chunk.document_id == job.document_id
        )
        assert document_chunks
        assert all(chunk.workspace_id == "asteria" for chunk in document_chunks)
        assert all(
            chunk.source_location.document_id == job.document_id
            and chunk.source_location.path == expected.path
            for chunk in document_chunks
        )
        if expected.media_type == "text/csv":
            assert all(
                chunk.source_location.table and chunk.source_location.cell
                for chunk in document_chunks
            )

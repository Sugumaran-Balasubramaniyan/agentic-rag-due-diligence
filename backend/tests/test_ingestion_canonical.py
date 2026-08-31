from __future__ import annotations

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.ingestion_contracts import IngestionStatus, UploadDocument
from due_diligence_copilot.ingestion_service import IngestionService
from due_diligence_copilot.synthetic_data import build_manifest


def test_canonical_asteria_documents_ingest_with_complete_provenance() -> None:
    repository = InMemoryDocumentRepository()
    index = InMemoryChunkIndex()
    service = IngestionService(InMemoryObjectStore(), repository, index)
    manifest, sources = build_manifest()

    jobs = [
        service.ingest(
            UploadDocument(
                workspace_id="asteria",
                filename=source.path,
                media_type=source.media_type,
                content=source.content,
                document_type=source.document_type,
            )
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
        UploadDocument(
            workspace_id="asteria",
            filename="notes.md",
            media_type="text/markdown",
            content=f"## Notes\n{secret_like_text}\n".encode(),
        )
    )

    assert all(
        secret_like_text not in event.summary
        for event in service.events("asteria", job.id)
    )

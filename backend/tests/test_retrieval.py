from __future__ import annotations

import pytest

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.domain import DocumentRecord, DocumentType, Evidence
from due_diligence_copilot.ingestion_contracts import (
    AccessContext,
    Chunk,
    UploadDocument,
)
from due_diligence_copilot.ingestion_service import IngestionService
from due_diligence_copilot.retrieval import RetrievalHit
from due_diligence_copilot.synthetic_data import build_manifest

AUTHORIZED = AccessContext(
    principal_id="analyst",
    allowed_workspace_ids={"workspace-a"},
    workspace_id="workspace-a",
)


def test_lexical_retrieval_returns_matching_chunks_in_stable_order() -> None:
    from due_diligence_copilot.retrieval import DeterministicLexicalRetriever

    index = InMemoryChunkIndex()
    chunks = (
        Chunk(
            id="chunk-b",
            workspace_id="workspace-a",
            document_id="doc-b",
            ordinal=0,
            text="The customer contract has a 36 month initial term.",
            content_hash="b" * 64,
            block_id="block-b",
            source_location={
                "document_id": "doc-b",
                "path": "contract.md",
                "line_start": 1,
            },
        ),
        Chunk(
            id="chunk-a",
            workspace_id="workspace-a",
            document_id="doc-a",
            ordinal=0,
            text="FY2025 revenue was EUR 10,000,000.",
            content_hash="a" * 64,
            block_id="block-a",
            source_location={
                "document_id": "doc-a",
                "path": "financial.md",
                "line_start": 1,
            },
        ),
    )
    index.store("workspace-a", chunks)

    hits = DeterministicLexicalRetriever(index).retrieve(
        AUTHORIZED,
        "What was FY2025 revenue?",
    )

    assert [hit.chunk.id for hit in hits] == ["chunk-a"]
    assert hits[0].score > 0


def test_hybrid_retrieval_fuses_duplicate_candidates_and_returns_top_ten() -> None:
    from due_diligence_copilot.retrieval import HybridRetriever, RetrievalHit

    def chunk(chunk_id: str) -> Chunk:
        return Chunk(
            id=chunk_id,
            workspace_id="workspace-a",
            document_id=f"doc-{chunk_id}",
            ordinal=0,
            text=f"Evidence for {chunk_id}",
            content_hash="a" * 64,
            block_id=f"block-{chunk_id}",
            source_location={
                "document_id": f"doc-{chunk_id}",
                "path": f"{chunk_id}.md",
                "line_start": 1,
            },
        )

    shared = chunk("shared")
    lexical_hits = tuple(
        RetrievalHit(chunk=item, score=1.0, rank=rank)
        for rank, item in enumerate((shared, chunk("lexical")), start=1)
    )
    vector_hits = tuple(
        RetrievalHit(chunk=item, score=1.0, rank=rank)
        for rank, item in enumerate((chunk("vector"), shared), start=1)
    )

    class StubRetriever:
        def __init__(self, hits: tuple[RetrievalHit, ...]) -> None:
            self.hits = hits

        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return self.hits

    hits = HybridRetriever(
        StubRetriever(lexical_hits), StubRetriever(vector_hits)
    ).retrieve(AUTHORIZED, "evidence")

    assert [hit.chunk.id for hit in hits] == ["shared", "vector", "lexical"]
    assert [hit.rank for hit in hits] == [1, 2, 3]


def test_context_packing_never_splits_chunks_and_rejects_duplicate_ids() -> None:
    from due_diligence_copilot.retrieval import pack_context

    chunk = Chunk(
        id="chunk-1",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="first chunk",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "notes.md",
            "line_start": 1,
        },
    )
    second = chunk.model_copy(update={"id": "chunk-2", "text": "second chunk"})

    packed = pack_context(
        (
            RetrievalHit(chunk=chunk, score=1.0, rank=1),
            RetrievalHit(chunk=second, score=0.5, rank=2),
        ),
        max_characters=len(chunk.text) + 1,
    )

    assert packed.chunk_ids == ("chunk-1",)
    assert packed.text == "first chunk"

    with pytest.raises(ValueError, match="duplicate chunk"):
        pack_context(
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),) * 2,
            max_characters=100,
        )


def test_citation_verification_rejects_citation_for_unretrieved_chunk() -> None:
    from due_diligence_copilot.retrieval import (
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="retrieved",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="FY2025 revenue was EUR 10,000,000.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "financial.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-1",
        document_id="doc-1",
        display_name="Financial Summary",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id="not-retrieved",
    )

    with pytest.raises(RetrievalAbstention, match="retrieved chunk"):
        CitationVerifier().verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-1",
                    text="FY2025 revenue was EUR 10,000,000.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )


def test_seeded_benchmark_meets_literal_recall_and_mrr_thresholds() -> None:
    from due_diligence_copilot.retrieval import (
        DeterministicLexicalRetriever,
        DeterministicVectorRetriever,
        HybridRetriever,
        evaluate_retrieval,
    )

    manifest, sources = build_manifest()
    asteria_context = AccessContext(
        principal_id="analyst",
        allowed_workspace_ids={"asteria"},
        workspace_id="asteria",
    )
    index = InMemoryChunkIndex()
    service = IngestionService(
        InMemoryObjectStore(), InMemoryDocumentRepository(), index
    )
    for source in sources:
        service.ingest(
            asteria_context,
            UploadDocument(
                workspace_id="asteria",
                filename=source.path,
                media_type=source.media_type,
                content=source.content,
                document_type=source.document_type,
            ),
        )

    evaluation = evaluate_retrieval(
        HybridRetriever(
            DeterministicLexicalRetriever(index), DeterministicVectorRetriever(index)
        ),
        manifest,
        index.list("asteria"),
        asteria_context,
    )

    assert evaluation.recall_at_10 >= 0.90
    assert evaluation.mrr_at_10 >= 0.80


def test_valid_citations_report_full_precision_and_coverage() -> None:
    from due_diligence_copilot.retrieval import CitationVerifier, Claim

    chunk = Chunk(
        id="retrieved",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="FY2025 revenue was EUR 10,000,000.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "financial.md",
            "line_start": 1,
        },
    )
    repository = InMemoryDocumentRepository()
    repository.save(
        "workspace-a",
        DocumentRecord(
            id="doc-1",
            display_name="Financial Summary",
            document_type=DocumentType.FINANCIAL_SUMMARY,
            path="financial.md",
            media_type="text/markdown",
            sha256="b" * 64,
            byte_length=1,
        ),
    )
    citation = Evidence(
        id="evidence-1",
        document_id="doc-1",
        display_name="Financial Summary",
        source_location=chunk.source_location,
        excerpt="FY2025 revenue was EUR 10,000,000.",
        chunk_id="retrieved",
    )

    result = CitationVerifier(repository).verify(
        AUTHORIZED,
        (Claim(id="claim-1", text=chunk.text, evidence=(citation,)),),
        (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
    )

    assert result.citation_precision == 1.0
    assert result.citation_coverage == 1.0


def test_unsupported_claim_abstains_with_typed_reason() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="request",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="No churn analysis or churn rate evidence is included.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "requests.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-1",
        document_id="doc-1",
        display_name="Requests",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id="request",
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier().verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-1",
                    text="The churn rate was 12%.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.UNSUPPORTED_EVIDENCE


def test_materially_contradictory_citations_abstain() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    def make_chunk(chunk_id: str, text: str, line: int) -> Chunk:
        return Chunk(
            id=chunk_id,
            workspace_id="workspace-a",
            document_id="doc-1",
            ordinal=line,
            text=text,
            content_hash="a" * 64,
            block_id=f"block-{chunk_id}",
            source_location={
                "document_id": "doc-1",
                "path": "financial.md",
                "line_start": line,
            },
        )

    first = make_chunk("first", "Revenue is EUR 10,000,000.", 1)
    second = make_chunk("second", "Revenue is EUR 9,000,000.", 2)
    citations = tuple(
        Evidence(
            id=f"evidence-{chunk.id}",
            document_id="doc-1",
            display_name="Financial Summary",
            source_location=chunk.source_location,
            excerpt=chunk.text,
            chunk_id=chunk.id,
        )
        for chunk in (first, second)
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier().verify(
            AUTHORIZED,
            (Claim(id="claim-1", text="Revenue is documented.", evidence=citations),),
            (
                RetrievalHit(chunk=first, score=1.0, rank=1),
                RetrievalHit(chunk=second, score=0.9, rank=2),
            ),
        )

    assert failure.value.reason == AbstentionReason.CONTRADICTORY_EVIDENCE


def test_hybrid_authorizes_before_delegating_to_retrievers() -> None:
    from due_diligence_copilot.retrieval import HybridRetriever

    called = False

    class ExplodingRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            nonlocal called
            called = True
            raise AssertionError("retriever was called before authorization")

    context = AccessContext(
        principal_id="analyst",
        allowed_workspace_ids={"workspace-a"},
        workspace_id="workspace-b",
    )
    with pytest.raises(PermissionError):
        HybridRetriever(ExplodingRetriever(), ExplodingRetriever()).retrieve(
            context, "revenue"
        )
    assert called is False


def test_postgres_retrievers_bind_workspace_predicate_before_query_execution() -> None:
    from due_diligence_copilot.retrieval import (
        PostgresLexicalRetriever,
        PostgresVectorRetriever,
    )

    class EmptyResult:
        def fetchall(self) -> list[tuple[object, ...]]:
            return []

    class Connection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def execute(
            self, statement: str, parameters: tuple[object, ...]
        ) -> EmptyResult:
            self.calls.append((statement, parameters))
            return EmptyResult()

    lexical_connection = Connection()
    vector_connection = Connection()
    PostgresLexicalRetriever(lexical_connection).retrieve(AUTHORIZED, "revenue")
    PostgresVectorRetriever(vector_connection).retrieve(AUTHORIZED, "revenue")

    for connection in (lexical_connection, vector_connection):
        statement, parameters = connection.calls[0]
        assert "workspace_id = %s" in statement
        assert parameters[0] == "workspace-a"
        assert "workspace-a" not in statement


def test_retrieval_returns_zero_evidence_from_another_workspace() -> None:
    from due_diligence_copilot.retrieval import DeterministicLexicalRetriever

    index = InMemoryChunkIndex()
    index.store(
        "workspace-b",
        (
            Chunk(
                id="secret",
                workspace_id="workspace-b",
                document_id="doc-b",
                ordinal=0,
                text="Workspace B confidential revenue is 99 million.",
                content_hash="a" * 64,
                block_id="block-b",
                source_location={
                    "document_id": "doc-b",
                    "path": "secret.md",
                    "line_start": 1,
                },
            ),
        ),
    )

    hits = DeterministicLexicalRetriever(index).retrieve(
        AUTHORIZED, "confidential revenue"
    )

    assert hits == ()

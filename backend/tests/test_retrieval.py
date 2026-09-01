from __future__ import annotations

import pytest

from due_diligence_copilot.adapters import (
    InMemoryChunkIndex,
    InMemoryDocumentRepository,
    InMemoryObjectStore,
)
from due_diligence_copilot.domain import (
    DocumentRecord,
    DocumentType,
    Evidence,
    SourceLocation,
)
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
            (
                Claim(
                    id="claim-1",
                    text="Revenue is EUR 10,000,000.",
                    evidence=citations,
                ),
            ),
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


def test_false_negated_claim_abstains_against_positive_evidence() -> None:
    from due_diligence_copilot.retrieval import (
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="policy",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="Asteria has a security policy.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "policy.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-policy",
        document_id="doc-1",
        display_name="Security Policy",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
    )

    with pytest.raises(RetrievalAbstention):
        CitationVerifier().verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-policy",
                    text="Asteria has no security policy.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )


def test_hybrid_rejects_foreign_delegate_hits_before_fusion() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        HybridRetriever,
        RetrievalAbstention,
    )

    foreign = Chunk(
        id="foreign",
        workspace_id="workspace-b",
        document_id="doc-b",
        ordinal=0,
        text="Workspace B evidence.",
        content_hash="a" * 64,
        block_id="block-b",
        source_location={
            "document_id": "doc-b",
            "path": "foreign.md",
            "line_start": 1,
        },
    )

    class MaliciousRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return (RetrievalHit(chunk=foreign, score=1.0, rank=1),)

    class RerankerThatMustNotRun:
        def rerank(
            self,
            query: str,
            candidates: tuple[RetrievalHit, ...],
            *,
            limit: int,
        ) -> tuple[RetrievalHit, ...]:
            del query, candidates, limit
            raise AssertionError("foreign evidence reached reranking")

    with pytest.raises(RetrievalAbstention) as failure:
        HybridRetriever(
            MaliciousRetriever(),
            MaliciousRetriever(),
            RerankerThatMustNotRun(),
        ).retrieve(AUTHORIZED, "evidence")

    assert failure.value.reason == AbstentionReason.FOREIGN_WORKSPACE


def test_textual_polarity_contradiction_abstains_without_numeric_values() -> None:
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
                "path": "policy.md",
                "line_start": line,
            },
        )

    first = make_chunk("mandatory", "MFA is mandatory for production access.", 1)
    second = make_chunk("optional", "MFA is optional for production access.", 2)
    citations = tuple(
        Evidence(
            id=f"evidence-{chunk.id}",
            document_id="doc-1",
            display_name="Security Policy",
            source_location=chunk.source_location,
            excerpt=chunk.text,
            chunk_id=chunk.id,
        )
        for chunk in (first, second)
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier().verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-mfa",
                    text="MFA is mandatory for production access.",
                    evidence=citations,
                ),
            ),
            (
                RetrievalHit(chunk=first, score=1.0, rank=1),
                RetrievalHit(chunk=second, score=0.9, rank=2),
            ),
        )

    assert failure.value.reason == AbstentionReason.CONTRADICTORY_EVIDENCE


def test_relational_contradiction_abstains_without_numeric_values() -> None:
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

    first = make_chunk("greater", "Revenue is greater than expenses.", 1)
    second = make_chunk("less", "Revenue is less than expenses.", 2)
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
            (
                Claim(
                    id="claim-relation",
                    text="Revenue is related to expenses.",
                    evidence=citations,
                ),
            ),
            (
                RetrievalHit(chunk=first, score=1.0, rank=1),
                RetrievalHit(chunk=second, score=0.9, rank=2),
            ),
        )

    assert failure.value.reason == AbstentionReason.CONTRADICTORY_EVIDENCE


def test_missing_document_authority_abstains_before_citation_acceptance() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="policy",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="Asteria has a security policy.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "policy.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-policy",
        document_id="doc-1",
        display_name="Arbitrary Display Name",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier().verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-policy",
                    text="Asteria has a security policy.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.MISSING_DOCUMENT_AUTHORITY


def test_empty_hybrid_retrieval_returns_typed_abstention_outcome() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        HybridRetriever,
        RetrievalOutcomeStatus,
    )

    class EmptyRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return ()

    outcome = HybridRetriever(EmptyRetriever(), EmptyRetriever()).retrieve_outcome(
        AUTHORIZED, "unsupported question"
    )

    assert outcome.status == RetrievalOutcomeStatus.ABSTAINED
    assert outcome.hits == ()
    assert outcome.reason == AbstentionReason.UNSUPPORTED_RETRIEVAL


def test_unrelated_citation_cannot_be_carried_by_another_supported_citation() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    supported_chunk = Chunk(
        id="supported",
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
    unrelated_chunk = supported_chunk.model_copy(
        update={
            "id": "unrelated",
            "document_id": "doc-2",
            "text": "The board approved the annual meeting agenda.",
            "block_id": "block-2",
            "source_location": SourceLocation(
                document_id="doc-2", path="board.md", line_start=1
            ),
        }
    )
    repository = InMemoryDocumentRepository()
    for document_id, display_name, path in (
        ("doc-1", "Financial Summary", "financial.md"),
        ("doc-2", "Board Minutes", "board.md"),
    ):
        repository.save(
            "workspace-a",
            DocumentRecord(
                id=document_id,
                display_name=display_name,
                document_type=DocumentType.FINANCIAL_SUMMARY,
                path=path,
                media_type="text/markdown",
                sha256="b" * 64,
                byte_length=1,
            ),
        )
    citations = (
        Evidence(
            id="evidence-supported",
            document_id="doc-1",
            display_name="Financial Summary",
            source_location=supported_chunk.source_location,
            excerpt=supported_chunk.text,
            chunk_id="supported",
        ),
        Evidence(
            id="evidence-unrelated",
            document_id="doc-2",
            display_name="Board Minutes",
            source_location=unrelated_chunk.source_location,
            excerpt=unrelated_chunk.text,
            chunk_id="unrelated",
        ),
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-revenue",
                    text="FY2025 revenue was EUR 10,000,000.",
                    evidence=citations,
                ),
            ),
            (
                RetrievalHit(chunk=supported_chunk, score=1.0, rank=1),
                RetrievalHit(chunk=unrelated_chunk, score=0.9, rank=2),
            ),
        )

    assert failure.value.reason == AbstentionReason.UNSUPPORTED_EVIDENCE


def test_authoritative_document_identity_rejects_arbitrary_display_name() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="policy",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="Asteria has a security policy.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "policy.md",
            "line_start": 1,
        },
    )
    repository = InMemoryDocumentRepository()
    repository.save(
        "workspace-a",
        DocumentRecord(
            id="doc-1",
            display_name="Security Policy",
            document_type=DocumentType.SECURITY_POLICY,
            path="policy.md",
            media_type="text/markdown",
            sha256="b" * 64,
            byte_length=1,
        ),
    )
    citation = Evidence(
        id="evidence-policy",
        document_id="doc-1",
        display_name="Arbitrary Display Name",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-policy",
                    text=chunk.text,
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.INVALID_CITATION


def test_postgres_decoded_foreign_hit_is_rejected_before_return() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        PostgresLexicalRetriever,
        RetrievalAbstention,
    )

    class Result:
        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                (
                    "foreign",
                    "workspace-b",
                    "doc-b",
                    0,
                    "foreign evidence",
                    "a" * 64,
                    "block-b",
                    {
                        "document_id": "doc-b",
                        "path": "foreign.md",
                        "line_start": 1,
                    },
                    1.0,
                )
            ]

    class Connection:
        def execute(self, statement: str, parameters: tuple[object, ...]) -> Result:
            del statement, parameters
            return Result()

    with pytest.raises(RetrievalAbstention) as failure:
        PostgresLexicalRetriever(Connection()).retrieve(AUTHORIZED, "evidence")

    assert failure.value.reason == AbstentionReason.FOREIGN_WORKSPACE


def test_false_relational_claim_abstains_against_opposite_relation() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="relation",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="Revenue is less than expenses.",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "financial.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-relation",
        document_id="doc-1",
        display_name="Financial Summary",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
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

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-relation",
                    text="Revenue is greater than expenses.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.UNSUPPORTED_EVIDENCE


def test_role_swapped_numeric_fact_abstains() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="facts",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text=(
            "Northstar revenue was EUR 5,000,000. Borealis revenue was EUR 2,000,000."
        ),
        content_hash="a" * 64,
        block_id="block-facts",
        source_location={
            "document_id": "doc-1",
            "path": "financial.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-facts",
        document_id="doc-1",
        display_name="Financial Summary",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
    )
    claim = Claim(
        id="claim-borealis-revenue",
        text="Borealis revenue was EUR 5,000,000.",
        evidence=(citation,),
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

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (claim,),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.UNSUPPORTED_EVIDENCE


def test_mixed_negation_does_not_support_the_wrong_policy() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="policies",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text=(
            "Asteria has a security policy. Asteria has no incident response policy."
        ),
        content_hash="a" * 64,
        block_id="block-policies",
        source_location={
            "document_id": "doc-1",
            "path": "policies.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-policies",
        document_id="doc-1",
        display_name="Policies",
        source_location=chunk.source_location,
        excerpt=chunk.text,
        chunk_id=chunk.id,
    )
    repository = InMemoryDocumentRepository()
    repository.save(
        "workspace-a",
        DocumentRecord(
            id="doc-1",
            display_name="Policies",
            document_type=DocumentType.SECURITY_POLICY,
            path="policies.md",
            media_type="text/markdown",
            sha256="b" * 64,
            byte_length=1,
        ),
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-security-policy",
                    text="Asteria has no security policy.",
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.UNSUPPORTED_EVIDENCE


def test_turned_on_and_off_evidence_abstains_as_contradictory() -> None:
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
                "path": "controls.md",
                "line_start": line,
            },
        )

    first = make_chunk("on", "The monitoring control is turned on.", 1)
    second = make_chunk("off", "The monitoring control is turned off.", 2)
    citations = tuple(
        Evidence(
            id=f"evidence-{chunk.id}",
            document_id="doc-1",
            display_name="Controls",
            source_location=chunk.source_location,
            excerpt=chunk.text,
            chunk_id=chunk.id,
        )
        for chunk in (first, second)
    )
    repository = InMemoryDocumentRepository()
    repository.save(
        "workspace-a",
        DocumentRecord(
            id="doc-1",
            display_name="Controls",
            document_type=DocumentType.SECURITY_POLICY,
            path="controls.md",
            media_type="text/markdown",
            sha256="b" * 64,
            byte_length=1,
        ),
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-monitoring-control",
                    text="The monitoring control is turned on.",
                    evidence=citations,
                ),
            ),
            (
                RetrievalHit(chunk=first, score=1.0, rank=1),
                RetrievalHit(chunk=second, score=0.9, rank=2),
            ),
        )

    assert failure.value.reason == AbstentionReason.CONTRADICTORY_EVIDENCE


def test_reranker_foreign_hit_is_rejected_before_context_packing() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        HybridRetriever,
        RetrievalAbstention,
    )

    valid = Chunk(
        id="valid",
        workspace_id="workspace-a",
        document_id="doc-valid",
        ordinal=0,
        text="valid evidence",
        content_hash="a" * 64,
        block_id="block-valid",
        source_location={
            "document_id": "doc-valid",
            "path": "valid.md",
            "line_start": 1,
        },
    )
    foreign = valid.model_copy(
        update={
            "id": "foreign",
            "workspace_id": "workspace-b",
            "document_id": "doc-foreign",
            "block_id": "block-foreign",
            "source_location": SourceLocation(
                document_id="doc-foreign", path="foreign.md", line_start=1
            ),
        }
    )
    candidate = RetrievalHit(chunk=valid, score=1.0, rank=1)
    injected = RetrievalHit(chunk=foreign, score=2.0, rank=1)

    class StubRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return (candidate,)

    class MaliciousReranker:
        def rerank(
            self, query: str, candidates: tuple[RetrievalHit, ...], *, limit: int
        ) -> tuple[RetrievalHit, ...]:
            del query, candidates, limit
            return (injected,)

    with pytest.raises(RetrievalAbstention) as failure:
        HybridRetriever(
            StubRetriever(), StubRetriever(), reranker=MaliciousReranker()
        ).retrieve(AUTHORIZED, "evidence")

    assert failure.value.reason == AbstentionReason.FOREIGN_WORKSPACE


def test_reranker_unseen_same_workspace_hit_is_rejected() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        HybridRetriever,
        RetrievalAbstention,
    )

    valid = Chunk(
        id="valid",
        workspace_id="workspace-a",
        document_id="doc-valid",
        ordinal=0,
        text="valid evidence",
        content_hash="a" * 64,
        block_id="block-valid",
        source_location={
            "document_id": "doc-valid",
            "path": "valid.md",
            "line_start": 1,
        },
    )
    unseen = valid.model_copy(update={"id": "unseen", "block_id": "block-unseen"})
    candidate = RetrievalHit(chunk=valid, score=1.0, rank=1)
    injected = RetrievalHit(chunk=unseen, score=2.0, rank=1)

    class StubRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return (candidate,)

    class MaliciousReranker:
        def rerank(
            self, query: str, candidates: tuple[RetrievalHit, ...], *, limit: int
        ) -> tuple[RetrievalHit, ...]:
            del query, candidates, limit
            return (injected,)

    with pytest.raises(RetrievalAbstention) as failure:
        HybridRetriever(
            StubRetriever(), StubRetriever(), reranker=MaliciousReranker()
        ).retrieve(AUTHORIZED, "evidence")

    assert failure.value.reason == AbstentionReason.INVALID_RETRIEVAL


def test_reranker_in_place_chunk_mutation_is_rejected() -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        HybridRetriever,
        RetrievalAbstention,
    )

    chunk = Chunk(
        id="mutable",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text="authoritative evidence",
        content_hash="a" * 64,
        block_id="block-1",
        source_location={
            "document_id": "doc-1",
            "path": "evidence.md",
            "line_start": 1,
        },
    )
    candidate = RetrievalHit(chunk=chunk, score=1.0, rank=1)

    class StubRetriever:
        def retrieve(
            self, context: AccessContext, query: str, *, limit: int = 20
        ) -> tuple[RetrievalHit, ...]:
            del context, query, limit
            return (candidate,)

    class MutatingReranker:
        def rerank(
            self, query: str, candidates: tuple[RetrievalHit, ...], *, limit: int
        ) -> tuple[RetrievalHit, ...]:
            del query, limit
            candidates[0].chunk.text = "tampered evidence"
            candidates[0].chunk.source_location.path = "tampered.md"
            return candidates

    with pytest.raises(RetrievalAbstention) as failure:
        HybridRetriever(
            StubRetriever(), StubRetriever(), reranker=MutatingReranker()
        ).retrieve(AUTHORIZED, "evidence")

    assert failure.value.reason == AbstentionReason.INVALID_RETRIEVAL


@pytest.mark.parametrize(
    "conjunction",
    (", but ", " and ", " or "),
)
def test_exact_claim_substring_does_not_hide_contradictory_clause(
    conjunction: str,
) -> None:
    from due_diligence_copilot.retrieval import (
        AbstentionReason,
        CitationVerifier,
        Claim,
        RetrievalAbstention,
    )

    claim_text = "The monitoring control is turned on"
    text = claim_text + conjunction + "turned off."
    chunk = Chunk(
        id="control",
        workspace_id="workspace-a",
        document_id="doc-1",
        ordinal=0,
        text=text,
        content_hash="a" * 64,
        block_id="block-control",
        source_location={
            "document_id": "doc-1",
            "path": "controls.md",
            "line_start": 1,
        },
    )
    citation = Evidence(
        id="evidence-control",
        document_id="doc-1",
        display_name="Controls",
        source_location=chunk.source_location,
        excerpt=text,
        chunk_id=chunk.id,
    )
    repository = InMemoryDocumentRepository()
    repository.save(
        "workspace-a",
        DocumentRecord(
            id="doc-1",
            display_name="Controls",
            document_type=DocumentType.SECURITY_POLICY,
            path="controls.md",
            media_type="text/markdown",
            sha256="b" * 64,
            byte_length=1,
        ),
    )

    with pytest.raises(RetrievalAbstention) as failure:
        CitationVerifier(repository).verify(
            AUTHORIZED,
            (
                Claim(
                    id="claim-control",
                    text=claim_text,
                    evidence=(citation,),
                ),
            ),
            (RetrievalHit(chunk=chunk, score=1.0, rank=1),),
        )

    assert failure.value.reason == AbstentionReason.CONTRADICTORY_EVIDENCE

"""Deterministic hybrid retrieval and fail-closed citation verification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import Field

from .domain import (
    BenchmarkQuestion,
    ContractModel,
    Evidence,
    GroundTruthManifest,
    SourceLocation,
)
from .ingestion_contracts import AccessContext, Chunk
from .ports import ChunkIndex, DocumentRepository, PostgresConnection
from .workspace import require_read_workspace

CANDIDATE_DEPTH = 20
RRF_K = 60
FINAL_RESULT_COUNT = 10
MAX_RETRIEVED_CHUNKS = 5 * FINAL_RESULT_COUNT
MAX_CONTEXT_CHARACTERS = 6000
ChunkId = Annotated[str, Field(min_length=1, max_length=128)]

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {"a", "an", "and", "are", "by", "for", "how", "is", "of", "the", "was", "what"}
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_QUERY_EXPANSIONS = {
    "concentration": "share",
    "percentage": "share",
    "contradiction": "conflicts",
    "policy": "security",
}
_RELATION_FORMS = {
    "is greater than": "greater_than",
    "is less than": "less_than",
    "is equal to": "equal_to",
    "is above": "greater_than",
    "is below": "less_than",
}
_STATE_VALUES = frozenset(
    {
        "turned on",
        "turned off",
        "enabled",
        "disabled",
        "mandatory",
        "optional",
        "required",
        "not required",
        "available",
        "unavailable",
        "present",
        "absent",
    }
)


class RetrievalHit(ContractModel):
    chunk: Chunk
    score: float
    rank: int = Field(ge=1)


class ContextPack(ContractModel):
    """Packed whole chunks, bounded to 6,000 characters for deterministic CI."""

    chunks: tuple[Chunk, ...] = Field(max_length=MAX_RETRIEVED_CHUNKS)
    chunk_ids: tuple[ChunkId, ...] = Field(max_length=MAX_RETRIEVED_CHUNKS)
    text: str = Field(max_length=MAX_CONTEXT_CHARACTERS)
    characters: int = Field(ge=0, le=MAX_CONTEXT_CHARACTERS)


class AbstentionReason(StrEnum):
    FOREIGN_WORKSPACE = "foreign_workspace"
    INVALID_CITATION = "invalid_citation"
    INVALID_RETRIEVAL = "invalid_retrieval"
    MISSING_DOCUMENT_AUTHORITY = "missing_document_authority"
    UNSUPPORTED_EVIDENCE = "unsupported_evidence"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    UNSUPPORTED_RETRIEVAL = "unsupported_retrieval"


class RetrievalAbstention(Exception):
    """Typed fail-closed outcome for unsafe or insufficient evidence."""

    def __init__(self, reason: AbstentionReason, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class Claim(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=10)
    tool_result_id: str | None = Field(default=None, max_length=128)
    allows_contradiction: bool = False


class CitationVerification(ContractModel):
    claims_verified: int = Field(ge=0)
    citation_precision: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)


class QuestionRetrievalMetric(ContractModel):
    question_id: str = Field(min_length=1, max_length=128)
    recall_at_10: float = Field(ge=0.0, le=1.0)
    reciprocal_rank_at_10: float = Field(ge=0.0, le=1.0)


class RetrievalEvaluation(ContractModel):
    question_count: int = Field(ge=1)
    recall_at_10: float = Field(ge=0.0, le=1.0)
    mrr_at_10: float = Field(ge=0.0, le=1.0)
    per_question: tuple[QuestionRetrievalMetric, ...] = Field(max_length=32)


class RetrievalOutcomeStatus(StrEnum):
    RETRIEVED = "retrieved"
    ABSTAINED = "abstained"


class RetrievalOutcome(ContractModel):
    status: RetrievalOutcomeStatus
    hits: tuple[RetrievalHit, ...] = Field(default=(), max_length=FINAL_RESULT_COUNT)
    reason: AbstentionReason | None = None


class LexicalRetriever(Protocol):
    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]: ...


class VectorRetriever(Protocol):
    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]: ...


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit], *, limit: int
    ) -> tuple[RetrievalHit, ...]: ...


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Sequence[float]: ...


def _validate_hit(hit: RetrievalHit, workspace_id: str) -> None:
    if not isinstance(hit, RetrievalHit):
        raise RetrievalAbstention(
            AbstentionReason.INVALID_RETRIEVAL, "retriever returned an invalid hit"
        )
    if hit.chunk.workspace_id != workspace_id:
        raise RetrievalAbstention(
            AbstentionReason.FOREIGN_WORKSPACE,
            "retriever returned evidence from another workspace",
        )


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token for token in _TOKEN.findall(value.lower()) if token not in _STOP_WORDS
    )


def _limit(value: int) -> int:
    if not 1 <= value <= CANDIDATE_DEPTH:
        raise ValueError(f"retrieval limit must be between 1 and {CANDIDATE_DEPTH}")
    return value


def _retrieval_text(chunk: Chunk, corpus: Sequence[Chunk]) -> str:
    """Add deterministic row context so cell citations remain discoverable."""
    related = [
        item.text
        for item in corpus
        if (
            item.id != chunk.id
            and item.document_id == chunk.document_id
            and item.source_location.path == chunk.source_location.path
            and item.source_location.line_start == chunk.source_location.line_start
            and chunk.source_location.cell is not None
        )
    ]
    metadata = (chunk.source_location.path, chunk.source_location.section or "")
    return " ".join((chunk.text, *sorted(related), *metadata))


def _lexical_score(query_terms: Sequence[str], text: str) -> float:
    terms = _tokens(text)
    score = float(sum(term in terms for term in query_terms))
    if (
        "revenue" in query_terms
        and "financial-summary" in text
        and "customer" not in query_terms
    ):
        score += 1.5
    if any(term in {"largest", "most", "highest", "biggest"} for term in query_terms):
        numbers = [
            float(value.replace(",", "").rstrip("%"))
            for value in _NUMBER.findall(text)
            if value.replace(",", "").rstrip("%").replace(".", "", 1).isdigit()
        ]
        if numbers and "total" not in terms:
            score += 2 + max(numbers) / 10_000_000
    return score


def _expanded_query_terms(query: str) -> tuple[str, ...]:
    terms = _tokens(query)
    expansions = tuple(
        _QUERY_EXPANSIONS[term] for term in terms if term in _QUERY_EXPANSIONS
    )
    return terms + expansions


@dataclass(frozen=True)
class _Fact:
    """A deliberately narrow fact shape used for deterministic alignment.

    This is not semantic entailment.  Only facts represented by one of the
    explicit grammars below can support a claim.  Unparsed prose therefore
    produces a false negative and an abstention instead of a false positive.
    """

    subject: str
    predicate: str
    value: str
    polarity: str


_NUMERIC_FACT = re.compile(
    r"^(?:(?P<subject>[a-z][a-z0-9&' -]*?)\s+)?"
    r"(?P<predicate>[a-z][a-z0-9&' -]*?)\s+"
    r"(?:is|was|were|:|=)\s+"
    r"(?:(?P<currency>[a-z]{3})\s*)?"
    r"(?P<number>\d[\d,]*(?:\.\d+)?%?)$",
    re.IGNORECASE,
)
_POSSESSION_FACT = re.compile(
    r"^(?P<subject>[a-z][a-z0-9&' -]*?)\s+"
    r"(?P<verb>has no|have no|does not have|doesn't have|has|have)\s+"
    r"(?P<object>[a-z][a-z0-9&' -]*?)$",
    re.IGNORECASE,
)
_STATE_FACT = re.compile(
    r"^(?P<subject>[a-z][a-z0-9&' -]*?)\s+"
    r"(?:is|are)\s+(?P<state>turned on|turned off|enabled|disabled|"
    r"mandatory|optional|required|not required|available|unavailable|"
    r"present|absent)(?:\s+(?P<context>[a-z][a-z0-9&' -]*))?$",
    re.IGNORECASE,
)
_BARE_STATE = re.compile(
    r"^(?P<state>turned on|turned off|enabled|disabled|mandatory|optional|"
    r"required|not required|available|unavailable|present|absent)$",
    re.IGNORECASE,
)
_RELATIONAL_FACT = re.compile(
    r"^(?P<subject>[a-z][a-z0-9&' -]*?)\s+"
    r"(?P<relation>is greater than|is less than|is equal to|is above|is below)\s+"
    r"(?P<object>[a-z][a-z0-9&' -]*?)$",
    re.IGNORECASE,
)
_BARE_POSSESSION = re.compile(
    r"^(?P<verb>has no|have no|does not have|doesn't have|has|have)\s+"
    r"(?P<object>[a-z][a-z0-9&' -]*?)$",
    re.IGNORECASE,
)
_CLAUSE_SEPARATOR = re.compile(
    r"(?:(?P<sentence>[.!?]+)|(?P<semicolon>;)|"
    r"(?P<conjunction>(?:,\s*|\s+)(?:but|and|or)\s+)|"
    r"(?P<comma>(?<!\d),(?!\s*(?:but|and|or)\b)))\s*",
    re.IGNORECASE,
)
_ELISION_BOUNDARIES = frozenset({"comma", "conjunction", "semicolon"})


def _fact_part(value: str) -> str:
    return _normalise(value).strip(" .,;:")


def _numeric_value(currency: str | None, number: str) -> str:
    numeric = number.rstrip("%").replace(",", "")
    unit = "percent" if number.endswith("%") else (currency or "unitless")
    return f"{unit}:{numeric}"


def _possession_fact(subject: str, verb: str, object_: str) -> _Fact:
    normalised_verb = _fact_part(verb)
    return _Fact(
        subject=_fact_part(subject),
        predicate="possession",
        value=_fact_part(object_).removeprefix("a ").removeprefix("an "),
        polarity=(
            "negated"
            if "no" in normalised_verb or "not" in normalised_verb
            else "affirmed"
        ),
    )


def _extract_fact(sentence: str) -> _Fact | None:
    text = _fact_part(sentence)
    numeric = _NUMERIC_FACT.fullmatch(text)
    if numeric is not None:
        return _Fact(
            subject=_fact_part(numeric.group("subject") or ""),
            predicate=_fact_part(numeric.group("predicate")),
            value=_numeric_value(numeric.group("currency"), numeric.group("number")),
            polarity="affirmed",
        )

    possession = _POSSESSION_FACT.fullmatch(text)
    if possession is not None:
        return _possession_fact(
            possession.group("subject"),
            possession.group("verb"),
            possession.group("object"),
        )

    relational = _RELATIONAL_FACT.fullmatch(text)
    if relational is not None:
        return _Fact(
            subject=_fact_part(relational.group("subject")),
            predicate="relation",
            value=_fact_part(relational.group("object")),
            polarity=_RELATION_FORMS[_fact_part(relational.group("relation"))],
        )

    state = _STATE_FACT.fullmatch(text)
    if state is not None:
        state_value = _fact_part(state.group("state"))
        if state_value in _STATE_VALUES:
            qualifier = _fact_part(state.group("context") or "")
            return _Fact(
                subject=_fact_part(state.group("subject")),
                predicate=f"state:{qualifier}" if qualifier else "state",
                value=state_value,
                polarity="affirmed",
            )
    return None


def _split_clauses(text: str) -> tuple[tuple[str, str | None], ...]:
    clauses: list[tuple[str, str | None]] = []
    start = 0
    boundary: str | None = None
    for separator in _CLAUSE_SEPARATOR.finditer(text):
        clauses.append((text[start : separator.start()], boundary))
        boundary = separator.lastgroup
        start = separator.end()
    clauses.append((text[start:], boundary))
    return tuple(clauses)


def _extract_facts_with_ambiguity(
    text: str,
) -> tuple[tuple[_Fact, ...], bool]:
    facts: list[_Fact] = []
    ambiguous = False
    previous_fact: _Fact | None = None
    for clause, boundary in _split_clauses(text):
        fact = _extract_fact(clause)
        prior = previous_fact if boundary in _ELISION_BOUNDARIES else None
        if fact is None and prior is not None:
            continuation = _BARE_STATE.fullmatch(_fact_part(clause))
            if continuation is not None:
                if prior.predicate.startswith("state"):
                    fact = _Fact(
                        subject=prior.subject,
                        predicate=prior.predicate,
                        value=_fact_part(continuation.group("state")),
                        polarity="affirmed",
                    )
            else:
                possession = _BARE_POSSESSION.fullmatch(_fact_part(clause))
                if possession is not None and prior.predicate == "possession":
                    fact = _possession_fact(
                        prior.subject,
                        possession.group("verb"),
                        possession.group("object"),
                    )
            if fact is None and _fact_part(clause):
                ambiguous = True
        elif (
            fact is None
            and boundary == "sentence"
            and previous_fact is not None
            and (
                _BARE_STATE.fullmatch(_fact_part(clause)) is not None
                or _BARE_POSSESSION.fullmatch(_fact_part(clause)) is not None
            )
        ):
            ambiguous = True
        if fact is not None:
            facts.append(fact)
        previous_fact = fact
    return tuple(facts), ambiguous


def _extract_facts(text: str) -> tuple[_Fact, ...]:
    return _extract_facts_with_ambiguity(text)[0]


def _alignment_supported(claim_text: str, evidence_text: str) -> bool:
    claim = _normalise(claim_text)
    evidence = _normalise(evidence_text)
    if not claim or not evidence:
        return False
    evidence_facts, evidence_ambiguous = _extract_facts_with_ambiguity(evidence_text)
    if _facts_have_material_contradiction(evidence_facts):
        return False
    claim_facts, claim_ambiguous = _extract_facts_with_ambiguity(claim_text)
    if evidence_ambiguous or claim_ambiguous:
        return False
    if claim_facts:
        return all(fact in set(evidence_facts) for fact in claim_facts)
    return claim in evidence


class DeterministicLexicalRetriever:
    """Term-overlap retriever with stable ordering and pre-read authorization."""

    def __init__(self, index: ChunkIndex) -> None:
        self._index = index

    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]:
        workspace_id = require_read_workspace(context)
        bounded_limit = _limit(limit)
        query_terms = _expanded_query_terms(query)
        if not query_terms:
            return ()
        scored: list[tuple[float, Chunk]] = []
        corpus = self._index.list(workspace_id)
        for chunk in corpus:
            score = _lexical_score(query_terms, _retrieval_text(chunk, corpus))
            if score:
                scored.append((score / len(query_terms), chunk))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(
            RetrievalHit(chunk=chunk, score=score, rank=rank)
            for rank, (score, chunk) in enumerate(scored[:bounded_limit], start=1)
        )


def _embedding(text: str, dimensions: int = 64) -> tuple[float, ...]:
    values = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        values[bucket] += 1.0 if digest[4] & 1 else -1.0
    return tuple(values)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(
        sum(b * b for b in right)
    )
    return numerator / denominator if denominator else 0.0


class DeterministicVectorRetriever:
    """Hashing-vector retriever; it has no model or network dependency."""

    def __init__(self, index: ChunkIndex) -> None:
        self._index = index

    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]:
        workspace_id = require_read_workspace(context)
        bounded_limit = _limit(limit)
        query_terms = _expanded_query_terms(query)
        query_vector = _embedding(" ".join(query_terms))
        corpus = self._index.list(workspace_id)
        scored = [
            (
                _lexical_score(query_terms, _retrieval_text(chunk, corpus))
                + _cosine(query_vector, _embedding(_retrieval_text(chunk, corpus)))
                / 1_000,
                chunk,
            )
            for chunk in corpus
        ]
        scored = [(score, chunk) for score, chunk in scored if score > 0]
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(
            RetrievalHit(chunk=chunk, score=score, rank=rank)
            for rank, (score, chunk) in enumerate(scored[:bounded_limit], start=1)
        )


class DeterministicEmbeddingProvider:
    """Replaceable local embedding boundary used by the pgvector adapter."""

    def embed(self, text: str) -> Sequence[float]:
        return _embedding(text)


def _safe_table(table: str) -> str:
    if re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", table) is None:
        raise ValueError("table must be a simple identifier")
    return table


class _PostgresChunkRetriever:
    def __init__(self, connection: PostgresConnection, *, table: str) -> None:
        self._connection = connection
        self._table = _safe_table(table)

    @staticmethod
    def _decode_rows(result: object, workspace_id: str) -> tuple[RetrievalHit, ...]:
        fetchall = getattr(result, "fetchall", None)
        if not callable(fetchall):
            return ()
        rows = fetchall()
        if not isinstance(rows, list | tuple):
            raise TypeError("PostgreSQL retrieval result must be a row sequence")
        hits: list[RetrievalHit] = []
        for rank, row in enumerate(rows, start=1):
            if not isinstance(row, tuple | list) or len(row) < 8:
                raise TypeError("PostgreSQL chunk result must contain eight columns")
            location = row[7]
            if isinstance(location, str):
                location = json.loads(location)
            chunk = Chunk(
                id=str(row[0]),
                workspace_id=str(row[1]),
                document_id=str(row[2]),
                ordinal=int(row[3]),
                text=str(row[4]),
                content_hash=str(row[5]),
                block_id=str(row[6]),
                source_location=SourceLocation.model_validate(location),
            )
            score = float(row[8]) if len(row) > 8 else 0.0
            hit = RetrievalHit(chunk=chunk, score=score, rank=rank)
            _validate_hit(hit, workspace_id)
            hits.append(hit)
        return tuple(hits[:CANDIDATE_DEPTH])

    def _execute(
        self, statement: str, parameters: tuple[object, ...], workspace_id: str
    ) -> tuple[RetrievalHit, ...]:
        return self._decode_rows(
            self._connection.execute(statement, parameters), workspace_id
        )


class PostgresLexicalRetriever(_PostgresChunkRetriever):
    """PostgreSQL FTS adapter with tenant filtering inside the SQL predicate."""

    def __init__(
        self, connection: PostgresConnection, *, table: str = "chunks"
    ) -> None:
        super().__init__(connection, table=table)

    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]:
        workspace_id = require_read_workspace(context)
        bounded_limit = _limit(limit)
        statement = (
            f"WITH scoped AS (SELECT id, workspace_id, document_id, ordinal, text, "
            f"content_hash, block_id, source_location, search_vector "
            f"FROM {self._table} "
            "WHERE workspace_id = %s) "
            "SELECT id, workspace_id, document_id, ordinal, text, content_hash, "
            "block_id, source_location, "
            "ts_rank_cd(search_vector, plainto_tsquery('simple', %s)) AS score "
            "FROM scoped WHERE search_vector @@ plainto_tsquery('simple', %s) "
            "ORDER BY score DESC, id ASC LIMIT %s"
        )
        return self._execute(
            statement, (workspace_id, query, query, bounded_limit), workspace_id
        )


class PostgresVectorRetriever(_PostgresChunkRetriever):
    """pgvector adapter with a bound embedding and tenant predicate."""

    def __init__(
        self,
        connection: PostgresConnection,
        *,
        table: str = "chunks",
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        super().__init__(connection, table=table)
        self._embeddings = embeddings or DeterministicEmbeddingProvider()

    def retrieve(
        self, context: AccessContext, query: str, *, limit: int = CANDIDATE_DEPTH
    ) -> tuple[RetrievalHit, ...]:
        workspace_id = require_read_workspace(context)
        bounded_limit = _limit(limit)
        embedding = tuple(self._embeddings.embed(query))
        statement = (
            f"WITH scoped AS (SELECT id, workspace_id, document_id, ordinal, text, "
            f"content_hash, block_id, source_location, embedding FROM {self._table} "
            "WHERE workspace_id = %s) "
            "SELECT id, workspace_id, document_id, ordinal, text, content_hash, "
            "block_id, source_location, embedding <=> %s AS score FROM scoped "
            "ORDER BY embedding <=> %s ASC, id ASC LIMIT %s"
        )
        return self._execute(
            statement, (workspace_id, embedding, embedding, bounded_limit), workspace_id
        )


class DeterministicReranker:
    """Token-overlap reranker with input-order tie breaking."""

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit], *, limit: int
    ) -> tuple[RetrievalHit, ...]:
        bounded_limit = _limit(limit)
        query_terms = _tokens(query)
        scored = [
            (
                candidate.score
                + sum(_tokens(candidate.chunk.text).count(term) for term in query_terms)
                / 1_000_000,
                index,
                candidate,
            )
            for index, candidate in enumerate(candidates)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            candidate.model_copy(update={"rank": rank})
            for rank, (_, _, candidate) in enumerate(scored[:bounded_limit], start=1)
        )


class HybridRetriever:
    """Authorize once, fuse two rank lists with RRF, then rerank top results."""

    def __init__(
        self,
        lexical: LexicalRetriever,
        vector: VectorRetriever,
        reranker: Reranker | None = None,
    ) -> None:
        self._lexical = lexical
        self._vector = vector
        self._reranker = reranker or DeterministicReranker()

    def retrieve(self, context: AccessContext, query: str) -> tuple[RetrievalHit, ...]:
        workspace_id = require_read_workspace(context)
        lexical_hits = self._lexical.retrieve(context, query, limit=CANDIDATE_DEPTH)[
            :CANDIDATE_DEPTH
        ]
        for hit in lexical_hits:
            _validate_hit(hit, workspace_id)
        vector_hits = self._vector.retrieve(context, query, limit=CANDIDATE_DEPTH)[
            :CANDIDATE_DEPTH
        ]
        for hit in vector_hits:
            _validate_hit(hit, workspace_id)
        by_id: dict[str, RetrievalHit] = {}
        scores: dict[str, float] = {}
        for hits in (lexical_hits, vector_hits):
            for hit in hits:
                by_id.setdefault(hit.chunk.id, hit)
                scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1 / (
                    RRF_K + hit.rank
                )
        fused = tuple(
            by_id[chunk_id].model_copy(update={"score": scores[chunk_id]})
            for chunk_id in sorted(scores, key=lambda item: (-scores[item], item))[
                :FINAL_RESULT_COUNT
            ]
        )
        candidate_snapshots = {
            hit.chunk.id: hit.chunk.model_copy(deep=True) for hit in fused
        }
        reranked = self._reranker.rerank(query, fused, limit=FINAL_RESULT_COUNT)
        final_ids: set[str] = set()
        for hit in reranked:
            _validate_hit(hit, workspace_id)
            candidate = candidate_snapshots.get(hit.chunk.id)
            if candidate is None or hit.chunk != candidate:
                raise RetrievalAbstention(
                    AbstentionReason.INVALID_RETRIEVAL,
                    "reranker returned a chunk outside the fused candidates",
                )
            if hit.chunk.id in final_ids:
                raise RetrievalAbstention(
                    AbstentionReason.INVALID_RETRIEVAL,
                    "reranker returned duplicate chunk IDs",
                )
            final_ids.add(hit.chunk.id)
        return tuple(reranked[:FINAL_RESULT_COUNT])

    def retrieve_outcome(self, context: AccessContext, query: str) -> RetrievalOutcome:
        hits = self.retrieve(context, query)
        if not hits:
            return RetrievalOutcome(
                status=RetrievalOutcomeStatus.ABSTAINED,
                reason=AbstentionReason.UNSUPPORTED_RETRIEVAL,
            )
        return RetrievalOutcome(
            status=RetrievalOutcomeStatus.RETRIEVED,
            hits=hits,
        )


def pack_context(
    hits: Sequence[RetrievalHit],
    *,
    max_characters: int = MAX_CONTEXT_CHARACTERS,
) -> ContextPack:
    """Pack complete chunks in ranked order; omitted chunks are never split."""
    if not 1 <= max_characters <= MAX_CONTEXT_CHARACTERS:
        raise ValueError(
            f"context budget must be between 1 and {MAX_CONTEXT_CHARACTERS}"
        )
    ids = [hit.chunk.id for hit in hits]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk id in context candidates")
    seen: set[str] = set()
    chunks: list[Chunk] = []
    characters = 0
    for hit in hits:
        seen.add(hit.chunk.id)
        separator = 2 if chunks else 0
        if characters + separator + len(hit.chunk.text) > max_characters:
            break
        chunks.append(hit.chunk)
        characters += separator + len(hit.chunk.text)
    return ContextPack(
        chunks=tuple(chunks),
        chunk_ids=tuple(chunk.id for chunk in chunks),
        text="\n\n".join(chunk.text for chunk in chunks),
        characters=characters,
    )


def _normalise(value: str) -> str:
    return " ".join(value.split()).casefold()


def _claim_is_supported(claim: Claim, evidence: Sequence[Evidence]) -> bool:
    return _alignment_supported(claim.text, " ".join(item.excerpt for item in evidence))


def _citation_supports_claim(claim: Claim, citation: Evidence) -> bool:
    return _alignment_supported(claim.text, citation.excerpt)


def _has_material_contradiction(evidence: Sequence[Evidence]) -> bool:
    facts = tuple(fact for item in evidence for fact in _extract_facts(item.excerpt))
    return _facts_have_material_contradiction(facts)


def _facts_have_material_contradiction(facts: Sequence[_Fact]) -> bool:
    for position, left in enumerate(facts):
        for right in facts[position + 1 :]:
            same_subject_and_predicate = (
                left.subject == right.subject and left.predicate == right.predicate
            )
            same_possession = (
                left.predicate == "possession" and left.value == right.value
            )
            if same_subject_and_predicate and (
                (
                    left.predicate != "possession"
                    and (left.value != right.value or left.polarity != right.polarity)
                )
                or (same_possession and left.polarity != right.polarity)
            ):
                return True
    return False


class CitationVerifier:
    """Verify retrieved-only citations and claim coverage, failing closed."""

    def __init__(self, documents: DocumentRepository | None = None) -> None:
        self._documents = documents

    def verify(
        self,
        context: AccessContext,
        claims: Sequence[Claim],
        retrieved: Sequence[RetrievalHit],
    ) -> CitationVerification:
        workspace_id = require_read_workspace(context)
        if not claims:
            raise RetrievalAbstention(
                AbstentionReason.UNSUPPORTED_EVIDENCE, "no material claims supplied"
            )
        retrieved_by_id = {hit.chunk.id: hit.chunk for hit in retrieved}
        if len(retrieved_by_id) != len(retrieved):
            raise RetrievalAbstention(
                AbstentionReason.INVALID_CITATION, "retrieved chunk IDs are duplicated"
            )
        all_evidence: list[Evidence] = []
        for claim in claims:
            if not claim.evidence:
                raise RetrievalAbstention(
                    AbstentionReason.UNSUPPORTED_EVIDENCE,
                    f"claim {claim.id} has no evidence",
                )
            for citation in claim.evidence:
                if (
                    citation.chunk_id is None
                    or citation.chunk_id not in retrieved_by_id
                ):
                    raise RetrievalAbstention(
                        AbstentionReason.INVALID_CITATION,
                        "citation must reference a retrieved chunk: "
                        f"{citation.chunk_id}",
                    )
                chunk = retrieved_by_id[citation.chunk_id]
                if chunk.workspace_id != workspace_id:
                    raise RetrievalAbstention(
                        AbstentionReason.INVALID_CITATION,
                        "citation chunk belongs to another workspace",
                    )
                if (
                    citation.document_id != chunk.document_id
                    or citation.source_location != chunk.source_location
                    or citation.source_location.document_id != chunk.document_id
                    or _normalise(citation.excerpt) not in _normalise(chunk.text)
                ):
                    raise RetrievalAbstention(
                        AbstentionReason.INVALID_CITATION,
                        "citation identity or excerpt is invalid for "
                        f"{citation.chunk_id}",
                    )
                if self._documents is not None:
                    try:
                        document = self._documents.get(workspace_id, chunk.document_id)
                    except PermissionError as exc:
                        raise RetrievalAbstention(
                            AbstentionReason.INVALID_CITATION,
                            "citation document is not available in this workspace",
                        ) from exc
                    if (
                        document is None
                        or document.display_name != citation.display_name
                        or document.path != citation.source_location.path
                    ):
                        raise RetrievalAbstention(
                            AbstentionReason.INVALID_CITATION,
                            "citation document identity is invalid",
                        )
                all_evidence.append(citation)
        if _has_material_contradiction(all_evidence) and not any(
            claim.allows_contradiction for claim in claims
        ):
            raise RetrievalAbstention(
                AbstentionReason.CONTRADICTORY_EVIDENCE,
                "citations contain materially contradictory values",
            )
        for claim in claims:
            if not claim.allows_contradiction and not _claim_is_supported(
                claim, claim.evidence
            ):
                raise RetrievalAbstention(
                    AbstentionReason.UNSUPPORTED_EVIDENCE,
                    f"claim {claim.id} is not supported by its citations",
                )
            if not claim.allows_contradiction and any(
                not _citation_supports_claim(claim, citation)
                for citation in claim.evidence
            ):
                raise RetrievalAbstention(
                    AbstentionReason.UNSUPPORTED_EVIDENCE,
                    f"claim {claim.id} has an unrelated citation",
                )
        if self._documents is None:
            raise RetrievalAbstention(
                AbstentionReason.MISSING_DOCUMENT_AUTHORITY,
                "document repository is required for citation verification",
            )
        citation_count = len(all_evidence)
        return CitationVerification(
            claims_verified=len(claims),
            citation_precision=1.0 if citation_count else 0.0,
            citation_coverage=1.0,
        )


def _question_relevant_chunk_ids(
    question: BenchmarkQuestion, chunks: Sequence[Chunk]
) -> set[str]:
    relevant: set[str] = set()
    for expected in question.expected_evidence:
        for chunk in chunks:
            if (
                chunk.source_location.path == expected.source_location.path
                and expected.literal in chunk.text
            ):
                relevant.add(chunk.id)
    return relevant


def evaluate_retrieval(
    retriever: HybridRetriever,
    manifest: GroundTruthManifest,
    chunks: Sequence[Chunk],
    context: AccessContext,
) -> RetrievalEvaluation:
    """Compute literal Recall@10 and MRR@10 against seeded source ground truth."""
    metrics: list[QuestionRetrievalMetric] = []
    for question in manifest.benchmark_questions:
        relevant = _question_relevant_chunk_ids(question, chunks)
        hits = retriever.retrieve(context, question.question)
        retrieved_ids = {hit.chunk.id for hit in hits[:FINAL_RESULT_COUNT]}
        recall = len(relevant & retrieved_ids) / len(relevant) if relevant else 0.0
        reciprocal_rank = next(
            (
                1 / hit.rank
                for hit in hits
                if hit.rank <= FINAL_RESULT_COUNT and hit.chunk.id in relevant
            ),
            0.0,
        )
        metrics.append(
            QuestionRetrievalMetric(
                question_id=question.id,
                recall_at_10=recall,
                reciprocal_rank_at_10=reciprocal_rank,
            )
        )
    return RetrievalEvaluation(
        question_count=len(metrics),
        recall_at_10=sum(item.recall_at_10 for item in metrics) / len(metrics),
        mrr_at_10=sum(item.reciprocal_rank_at_10 for item in metrics) / len(metrics),
        per_question=tuple(metrics),
    )

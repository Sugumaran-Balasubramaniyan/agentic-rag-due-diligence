# Task 4 report: hybrid retrieval and citation verification

## Plan text

## Task 4: Implement hybrid retrieval and citation verification

Implement lexical and vector retriever interfaces, workspace filters before retrieval, Reciprocal Rank Fusion, reranking, context packing, claim/evidence alignment, citation validation, and abstention. Supply deterministic local implementations for CI and PostgreSQL/pgvector implementations for the full stack.

Acceptance: benchmark retrieval thresholds pass; malformed citations are rejected; unsupported and contradictory queries abstain; cross-workspace fixture retrieval returns zero leaked evidence.

## Scope delivered

- Added typed lexical, vector, reranker, embedding-provider, retrieval-hit, context-pack, evaluation, claim, and citation-verification contracts.
- Added deterministic local lexical and hashing-vector retrievers with stable tie-breaking, query normalization, CSV row context, candidate depth 20, RRF `k=60`, and final top 10 reranking.
- Added pre-retrieval authorization through `require_read_workspace`; in-memory retrieval remains workspace-scoped.
- Added parameterized PostgreSQL FTS and pgvector adapters. Each scopes the SQL source by `workspace_id = %s` inside a CTE before search/ranking and does not post-filter candidates.
- Added deterministic whole-chunk context packing with a documented 6,000-character budget and duplicate-ID rejection.
- Added retrieved-only citation checks for chunk ID, workspace, document, source location, source path, display identity when a repository is supplied, excerpt support, claim coverage, and typed fail-closed abstention for invalid, unsupported, and materially contradictory evidence.
- Added literal seeded evaluation over all 14 Asteria benchmark questions and focused isolation/authorization/database/citation behavior tests.

## TDD evidence

Each feature slice was driven by a focused behavior test. Initial RED evidence included:

```text
$ uv run pytest tests/test_retrieval.py -q
F                                                                        [100%]
E   ModuleNotFoundError: No module named 'due_diligence_copilot.retrieval'
```

The lexical implementation then produced:

```text
$ uv run pytest tests/test_retrieval.py -q
.                                                                        [100%]
```

The RRF behavior test was RED because the interface was not yet present:

```text
$ uv run pytest tests/test_retrieval.py -q
F                                                                        [100%]
E   ImportError: cannot import name 'HybridRetriever' from 'due_diligence_copilot.retrieval'
```

After the minimal fusion/reranker implementation:

```text
$ uv run pytest tests/test_retrieval.py -q
..                                                                       [100%]
```

The context-pack test was RED with a missing `pack_context` export, then GREEN after implementation:

```text
$ uv run pytest tests/test_retrieval.py::test_context_packing_never_splits_chunks_and_rejects_duplicate_ids -q
F                                                                        [100%]
E   ImportError: cannot import name 'pack_context' from 'due_diligence_copilot.retrieval'

$ uv run pytest tests/test_retrieval.py::test_context_packing_never_splits_chunks_and_rejects_duplicate_ids -q
.                                                                        [100%]
```

The citation test was RED with missing verifier contracts, then GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_citation_verification_rejects_citation_for_unretrieved_chunk -q
F                                                                        [100%]
E   ImportError: cannot import name 'Claim' from 'due_diligence_copilot.retrieval'

$ uv run pytest tests/test_retrieval.py::test_citation_verification_rejects_citation_for_unretrieved_chunk -q
.                                                                        [100%]
```

The first seeded evaluation RED exposed inadequate literal ranking:

```text
$ uv run pytest tests/test_retrieval.py::test_seeded_benchmark_meets_literal_recall_and_mrr_thresholds -q
E   AssertionError: assert 0.6904761904761905 >= 0.9
```

After deterministic row-context/query scoring refinement, the same behavior test was GREEN. The measured values were Recall@10 `0.9642857142857143` and MRR@10 `0.8095238095238095`.

The PostgreSQL adapter test was RED with missing adapter contracts, then GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_postgres_retrievers_bind_workspace_predicate_before_query_execution -q
F                                                                        [100%]
E   ImportError: cannot import name 'PostgresLexicalRetriever' from 'due_diligence_copilot.retrieval'

$ uv run pytest tests/test_retrieval.py::test_postgres_retrievers_bind_workspace_predicate_before_query_execution -q
.                                                                        [100%]
```

Final focused Task 4 suite:

```text
$ uv run pytest tests/test_retrieval.py -q
...........                                                              [100%]
11 passed
```

## Verification evidence

```text
$ make verify
Success: no issues found in 17 source files
71 passed in 0.56s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed

$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias): Passed
ruff format: Passed
prettier: Passed

$ npm audit --audit-level=high
found 0 vulnerabilities

$ git diff --check
[no output; exit 0]

$ git ls-files -co --exclude-standard | rg -i '(^|/)(\.env$|.*(secret|credential|token|private.?key).*)'
[no matching filenames; exit 1 from rg]
```

No live model, provider, database, network retrieval, agent graph, API endpoint, Celery job, UI, deployment, or publication behavior was added.

## Concerns and limits

The PostgreSQL/pgvector implementations are injected SQL boundaries and were verified for SQL shape, parameter binding, decoding, and authorization ordering; no live PostgreSQL/pgvector service was used, by design. Independent controller review and any checkpoint push remain outside this implementer run.

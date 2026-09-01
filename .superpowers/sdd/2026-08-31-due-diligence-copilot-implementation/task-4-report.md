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

## Fix round 1/5 TDD evidence

The controller-preserved Ruff formatter diff in `backend/src/due_diligence_copilot/retrieval.py` was retained as the starting worktree state. Each review finding was reproduced before its production change.

Negation RED:

```text
$ uv run pytest tests/test_retrieval.py::test_false_negated_claim_abstains_against_positive_evidence -q
E   Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

Negation GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_false_negated_claim_abstains_against_positive_evidence -q
.                                                                        [100%]
```

Foreign delegated-hit RED:

```text
$ uv run pytest tests/test_retrieval.py::test_hybrid_rejects_foreign_delegate_hits_before_fusion -q
E   AssertionError: foreign evidence reached reranking
```

Foreign delegated-hit GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_hybrid_rejects_foreign_delegate_hits_before_fusion -q
.                                                                        [100%]
```

Nonnumeric polarity RED:

```text
$ uv run pytest tests/test_retrieval.py::test_textual_polarity_contradiction_abstains_without_numeric_values -q
E   Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

Nonnumeric polarity and relational contradiction GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_textual_polarity_contradiction_abstains_without_numeric_values -q
.                                                                        [100%]
$ uv run pytest tests/test_retrieval.py::test_relational_contradiction_abstains_without_numeric_values -q
.                                                                        [100%]
```

Missing document-authority RED:

```text
$ uv run pytest tests/test_retrieval.py::test_missing_document_authority_abstains_before_citation_acceptance -q
E   Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

Missing authority and arbitrary display-name GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_missing_document_authority_abstains_before_citation_acceptance -q
.                                                                        [100%]
$ uv run pytest tests/test_retrieval.py::test_authoritative_document_identity_rejects_arbitrary_display_name -q
.                                                                        [100%]
```

Empty retrieval RED:

```text
$ uv run pytest tests/test_retrieval.py::test_empty_hybrid_retrieval_returns_typed_abstention_outcome -q
E   ImportError: cannot import name 'RetrievalOutcomeStatus' from 'due_diligence_copilot.retrieval'
```

Empty retrieval GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_empty_hybrid_retrieval_returns_typed_abstention_outcome -q
.                                                                        [100%]
```

Per-citation and relational alignment RED/GREEN:

```text
$ uv run pytest tests/test_retrieval.py::test_unrelated_citation_cannot_be_carried_by_another_supported_citation -q
E   Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
$ uv run pytest tests/test_retrieval.py::test_unrelated_citation_cannot_be_carried_by_another_supported_citation -q
.                                                                        [100%]
$ uv run pytest tests/test_retrieval.py::test_false_relational_claim_abstains_against_opposite_relation -q
E   Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
$ uv run pytest tests/test_retrieval.py::test_false_relational_claim_abstains_against_opposite_relation -q
.                                                                        [100%]
```

PostgreSQL decoded foreign-row regression:

```text
$ uv run pytest tests/test_retrieval.py::test_postgres_decoded_foreign_hit_is_rejected_before_return -q
.                                                                        [100%]
```

Final fix-round focused retrieval suite before repository gates:

```text
$ uv run pytest tests/test_retrieval.py -q
.....................                                                    [100%]
21 passed
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
ruff (legacy alias): Failed; files were modified by this hook
ruff format: Failed; 2 files reformatted, 24 files left unchanged
prettier: Passed

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

Final fix-round full verification:

```text
$ make verify
Success: no issues found in 17 source files
81 passed in 0.58s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed
```

## Concerns and limits

The PostgreSQL/pgvector implementations are injected SQL boundaries and were verified for SQL shape, parameter binding, decoding, and authorization ordering; no live PostgreSQL/pgvector service was used, by design. Independent controller review and any checkpoint push remain outside this implementer run.

Fix round 1/5 status: all listed review findings are addressed in the local worktree. The Task 4 checkpoint remains pending independent review and has not been pushed.

## Task 4 fix round 2/5 evidence

Systematic debugging identified two root causes from the scoped re-review: claim
support and per-citation support still treated token presence as entailment, and
the hybrid boundary trusted reranker output after fusion. The contradiction
detector also had no structured representation for state phrases such as
"turned on" and "turned off". The fix uses a narrow deterministic fact grammar
for explicit subject/predicate/value, possession polarity, state, and relational
facts. Exact or fully matched structured facts may support a claim; unparsed
prose is intentionally a conservative false negative and abstains. Reranker
results are revalidated for workspace, fused-candidate membership, immutable
chunk identity/provenance, and duplicate IDs before return.

Role-swapped numeric RED:

```text
$ uv run pytest -q tests/test_retrieval.py::test_role_swapped_numeric_fact_abstains
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

The remaining literal probes were RED before the implementation:

```text
$ uv run pytest -q tests/test_retrieval.py::test_mixed_negation_does_not_support_the_wrong_policy tests/test_retrieval.py::test_turned_on_and_off_evidence_abstains_as_contradictory tests/test_retrieval.py::test_reranker_foreign_hit_is_rejected_before_context_packing tests/test_retrieval.py::test_reranker_unseen_same_workspace_hit_is_rejected
FFFF                                                                     [100%]
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

After the minimal implementation and formatter pass, the five new behavior
probes were GREEN:

```text
$ uv run pytest -q tests/test_retrieval.py::test_role_swapped_numeric_fact_abstains tests/test_retrieval.py::test_mixed_negation_does_not_support_the_wrong_policy tests/test_retrieval.py::test_turned_on_and_off_evidence_abstains_as_contradictory tests/test_retrieval.py::test_reranker_foreign_hit_is_rejected_before_context_packing tests/test_retrieval.py::test_reranker_unseen_same_workspace_hit_is_rejected
.....                                                                    [100%]
```

Focused retrieval and static checks after formatting:

```text
$ cd backend && uv run pytest -q tests/test_retrieval.py
..........................                                               [100%]
$ cd backend && uv run mypy src
Success: no issues found in 17 source files
```

Pinned formatter evidence:

```text
$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias)......................................................Passed
ruff format..............................................................Failed
- hook id: ruff-format
- files were modified by this hook
2 files reformatted, 24 files left unchanged
prettier.................................................................Passed

$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
prettier.................................................................Passed
```

The Asteria benchmark threshold test remains GREEN after the fix; final
repository-gate evidence is recorded below after the last verification run.
Task 4 remains pending independent review. No push was performed.

Final repository gates:

```text
$ make verify
Success: no issues found in 17 source files
86 passed in 0.60s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed

$ uv run python <deterministic seeded benchmark script>
questions=14 recall_at_10=0.9643 mrr_at_10=0.8095

$ npm audit --audit-level=high
found 0 vulnerabilities

$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
prettier.................................................................Passed

$ git diff --check
[no output; exit 0]

$ git ls-files -co --exclude-standard | rg -i '(^|/)(\.env$|.*(secret|credential|token|private.?key).*)'
[no matching filenames]
```

The final worktree changes are committed locally and were not pushed.

## Task 4 fix round 3/5 evidence

Systematic debugging traced the reranker defect to a shallow nested-model alias:
the fused `RetrievalHit` retained a mutable `Chunk`, so a reranker could mutate
text and source provenance before the post-call membership map was built. The
contradiction defect had two parts: conjunction clauses were not split, and
exact-substring alignment could succeed without first assessing the evidence
facts. The fix snapshots each fused chunk deeply before invoking the reranker,
then compares every returned chunk against that snapshot. It also parses
explicit comma/`but`/`and`/`or` clauses, supports a narrow elided state
continuation, and evaluates material contradiction before exact support.

In-place reranker mutation RED:

```text
$ uv run pytest -q tests/test_retrieval.py::test_reranker_in_place_chunk_mutation_is_rejected
F                                                                        [100%]
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

Exact-substring contradiction RED before compound-clause parsing and
contradiction-first alignment:

```text
$ uv run pytest -q tests/test_retrieval.py::test_exact_claim_substring_does_not_hide_contradictory_clause
FFF                                                                      [100%]
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

After the minimal fixes, the bounded probes were GREEN:

```text
$ uv run pytest -q tests/test_retrieval.py::test_reranker_in_place_chunk_mutation_is_rejected tests/test_retrieval.py::test_exact_claim_substring_does_not_hide_contradictory_clause
....                                                                     [100%]
$ uv run pytest -q tests/test_retrieval.py
..............................                                           [100%]
```

The final retrieval suite contains 30 passing tests, including all prior
authority, tenant, citation, contradiction, empty-outcome, and benchmark
regressions. Ruff and mypy also passed after the round-3 changes. Final full
repository-gate output is appended after the closing verification run.

Final round-3 repository gates:

```text
$ make verify
Success: no issues found in 17 source files
90 passed in 0.58s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed

$ uv run python <deterministic seeded benchmark script>
questions=14 recall_at_10=0.9643 mrr_at_10=0.8095

$ npm audit --audit-level=high
found 0 vulnerabilities

$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
prettier.................................................................Passed

$ git diff --check
[no output; exit 0]

$ git ls-files -co --exclude-standard | rg -i '(^|/)(\.env$|.*(secret|credential|token|private.?key).*)'
[no matching filenames]
```

Round-3 changes are ready for local commit only. No push was performed.

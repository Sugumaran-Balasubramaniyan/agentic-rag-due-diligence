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

## Task 4 fix round 4/5 evidence

This round used a fresh escalation implementer on clean base `c844a9b`. No
subagents were dispatched and no push was performed.

Systematic debugging confirmed the remaining Critical root cause in the
structured-clause path. `_extract_facts` split sentence punctuation,
semicolons, and conjunctions, but not a standalone comma. Therefore the exact
evidence `The monitoring control is turned on, turned off.` produced no
structured facts, and contradiction assessment ran before exact-substring
support but had nothing to assess. The exact positive claim was then accepted.

The fix introduces a shared clause-boundary parser that handles standalone
commas while preserving digit-adjacent numeric separators, audits semicolon and
comma-plus-conjunction forms through one regression family, and carries only
exact bare state or possession-polarity continuations from the immediately
preceding compatible fact. Sentence boundaries do not carry state. Unparsed
continuations mark the alignment ambiguous and fail closed before exact support;
unrelated complete sentences after a supported fact remain valid context.

Literal standalone-comma RED:

```text
$ uv run pytest -q tests/test_retrieval.py::test_exact_claim_substring_does_not_hide_contradictory_clause
F......                                                                  [100%]
=================================== FAILURES ===================================
_ test_exact_claim_substring_does_not_hide_contradictory_clause[standalone-comma] _
E       Failed: DID NOT RAISE <class 'due_diligence_copilot.retrieval.RetrievalAbstention'>
```

The direct pre-fix reproduction was:

```text
claim: (_Fact(subject='the monitoring control', predicate='state', value='turned on', polarity='affirmed'),)
'The monitoring control is turned on, turned off.' facts= () supported= True
```

The ambiguity guard was also driven RED before its implementation:

```text
$ uv run pytest -q tests/test_retrieval.py::test_ambiguous_state_continuation_abstains_before_exact_support
F                                                                        [100%]
E       AssertionError: assert <AbstentionReason.MISSING_DOCUMENT_AUTHORITY: 'missing_document_authority'> == <AbstentionReason.UNSUPPORTED_EVIDENCE: 'unsupported_evidence'>
```

The final punctuation probes are GREEN:

```text
$ uv run pytest -q tests/test_retrieval.py::test_exact_claim_substring_does_not_hide_contradictory_clause
.......                                                                  [100%]

$ uv run pytest -q tests/test_retrieval.py::test_ambiguous_state_continuation_abstains_before_exact_support
.                                                                        [100%]
```

The passing parser/alignment probes cover standalone comma, semicolon,
comma-`but`, comma-`and`, comma-`or`, no-comma conjunctions, numeric comma
preservation, elided possession polarity, sentence-boundary non-carry, and
ambiguous-fragment rejection. Representative output:

```text
'The monitoring control is turned on, turned off.' facts= (_Fact(subject='the monitoring control', predicate='state', value='turned on', polarity='affirmed'), _Fact(subject='the monitoring control', predicate='state', value='turned off', polarity='affirmed')) supported= False
'The monitoring control is turned on; turned off.' facts= (_Fact(subject='the monitoring control', predicate='state', value='turned on', polarity='affirmed'), _Fact(subject='the monitoring control', predicate='state', value='turned off', polarity='affirmed')) supported= False
'The monitoring control is turned on, and turned off.' facts= (_Fact(subject='the monitoring control', predicate='state', value='turned on', polarity='affirmed'), _Fact(subject='the monitoring control', predicate='state', value='turned off', polarity='affirmed')) supported= False
'Revenue was EUR 10,000,000.' facts= (_Fact(subject='', predicate='revenue', value='eur:10000000', polarity='affirmed'),) supported= True
'Asteria has a security policy, has no security policy.' facts= (_Fact(subject='asteria', predicate='possession', value='security policy', polarity='affirmed'), _Fact(subject='asteria', predicate='possession', value='security policy', polarity='negated')) supported= False
'The monitoring control is turned on. turned off.' facts= (_Fact(subject='the monitoring control', predicate='state', value='turned on', polarity='affirmed'),) supported= False
```

Focused Task 4 suite:

```text
$ uv run pytest tests/test_retrieval.py
....................................                                     [100%]
36 passed in 0.23s
```

Seeded benchmark:

```text
$ uv run python -c 'from due_diligence_copilot.adapters import InMemoryChunkIndex, InMemoryDocumentRepository, InMemoryObjectStore; from due_diligence_copilot.ingestion_contracts import AccessContext, UploadDocument; from due_diligence_copilot.ingestion_service import IngestionService; from due_diligence_copilot.retrieval import DeterministicLexicalRetriever, DeterministicVectorRetriever, HybridRetriever, evaluate_retrieval; from due_diligence_copilot.synthetic_data import build_manifest; manifest, sources = build_manifest(); context = AccessContext(principal_id="analyst", allowed_workspace_ids={"asteria"}, workspace_id="asteria"); index = InMemoryChunkIndex(); service = IngestionService(InMemoryObjectStore(), InMemoryDocumentRepository(), index); [service.ingest(context, UploadDocument(workspace_id="asteria", filename=source.path, media_type=source.media_type, content=source.content, document_type=source.document_type)) for source in sources]; evaluation = evaluate_retrieval(HybridRetriever(DeterministicLexicalRetriever(index), DeterministicVectorRetriever(index)), manifest, index.list("asteria"), context); print(f"questions={evaluation.question_count} recall_at_10={evaluation.recall_at_10:.4f} mrr_at_10={evaluation.mrr_at_10:.4f}")'
questions=14 recall_at_10=0.9643 mrr_at_10=0.8095
```

Fresh repository gates:

```text
$ make verify
cd backend && uv run ruff check .
All checks passed!
cd backend && uv run mypy src
Success: no issues found in 17 source files
cd backend && uv run pytest
........................................................................ [ 75%]
........................                                                 [100%]
96 passed in 0.64s
cd frontend && npm run lint
cd frontend && npm run type-check
cd frontend && npm test -- --run

> due-diligence-copilot-frontend@0.1.0 test
> vitest --run

 RUN  v3.2.7 /home/ubuntu/agentic-rag-due-diligence/.worktrees/flagship-copilot/frontend

 ✓ src/App.test.tsx (1 test) 98ms

Test Files  1 passed (1)
Tests  1 passed (1)
 Start at  11:36:05
 Duration  1.18s (transform 66ms, setup 92ms, collect 164ms, tests 98ms, environment 470ms, prepare 85ms)

cd frontend && npm run build
> due-diligence-copilot-frontend@0.1.0 build
> tsc -b && vite build

vite v7.3.6 building client environment for production...
transforming...
✓ 74 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.17 kB │ gzip:  0.15 kB
dist/assets/index-CpyRbTNJ.css    0.16 kB │ gzip:  0.15 kB
dist/assets/index-DpH50MtX.js   209.52 kB │ gzip: 65.59 kB
✓ built in 1.47s

$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
prettier.................................................................Passed

$ npm audit --audit-level=high
found 0 vulnerabilities

$ git diff --check
[no output; exit 0]

$ git ls-files -co --exclude-standard | rg -i '(^|/)(\.env$|.*(secret|credential|token|private.?key).*)'
[no matching filenames]
```

The round-4 implementation preserves the earlier tenant/identity,
abstention, reranker snapshot, citation, contradiction, and benchmark
behavior. PostgreSQL/pgvector remain injected adapter boundaries only. Task 4
remains pending independent review and acceptance; this round records local
implementation and verification evidence only.

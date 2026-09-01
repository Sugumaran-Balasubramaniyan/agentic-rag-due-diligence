# Implementation handoff

## Current checkpoint

- Repository initialized from the approved flagship plan.
- Task 1 is accepted through head `80eee7f` after two fix rounds and
  independent review.
- Fresh controller evidence: `make verify` passed; pre-commit all-files
  passed; `npm audit` reported zero vulnerabilities across 334 dependencies;
  `git diff --check` and the secret-pattern scan passed; the worktree was
  clean.
- Task 2 is accepted through head `5c5ce5f` after fix round 1.
- Task 3 ingestion and provenance is accepted through head `60a0241` after
  three fix rounds and a clean independent re-review.
- Task 4 hybrid retrieval and citation verification is accepted at production
  head `71fc059` after clean independent round-4 review. The checkpoint has not
  been pushed.
- Fresh controller verification at `71fc059`: `make verify` passed with 96
  backend tests plus frontend lint, type-check, test, and build; pinned
  pre-commit passed; frontend audit reported 0 vulnerabilities; diff/status and
  filename-only secret-pattern checks were clean. Seeded deterministic metrics
  remain Recall@10 0.9643 and MRR@10 0.8095.
- Task 5 bounded agentic investigation is implemented in the local checkpoint
  based on `79fdc26`. The final fix-round change keeps contradiction findings'
  complete `ToolResult.evidence` lineage consistent between generation and
  approval, so a legitimate contradiction can be approved into a report while
  same-ID citation tampering remains rejected. It has not been pushed or
  independently re-reviewed in this worker.
- Publishing is blocked until the unrelated embedded Git credential identified during preflight is revoked and its remote is sanitized.
- Task rule: each independently reviewed task is a checkpoint; after acceptance, the controller pushes it after fresh verification.
- Checkpoint pushes use a newly created credential-free remote and a GitHub CLI
  token distinct from the unrelated embedded credential. Release cleanup still
  requires revoking and sanitizing that unrelated credential.

## Resume protocol

1. Read `AGENTS.md`, the design specification, and the implementation plan.
2. Inspect `.superpowers/sdd/2026-08-31-due-diligence-copilot-implementation/progress.md` when present.
3. Confirm `git status --short` and `git log --oneline -10` agree with the ledger.
4. Resume the first task without a `Task N: complete` ledger entry.
5. Never repeat an accepted task solely because conversation context was compacted.
6. After review, push the accepted checkpoint through the newly created
   credential-free remote using the distinct GitHub CLI token.

## Task 5 implementation checkpoint

- Added the pinned LangGraph 0.6.6 typed finite investigation DAG, exact
  transition/tool/token/time budgets, four closed deterministic evidence-linked
  tools, provider and accounting protocols, bounded redacted analysis-event
  persistence, fail-closed branches, literal seeded routing evaluation, and a
  separate explicit approval boundary.
- Retrieved document instructions cannot select tools. The seeded injection
  fixture reaches no tool call and cannot enter event summaries. Tool arguments
  reference exactly the authorized retrieved evidence supplied to each call.
- The graph stops at `AWAITING_APPROVAL` with only verified findings and no
  report. Explicit rejection, unverified findings, non-awaiting states, and
  approval-event persistence failures cannot complete or create a report.
- Focused Task 5 fix-round verification passed 106 tests under
  `pytest -W error`; the full backend suite passed 202 tests under the same
  warnings-as-errors setting. `make verify` passed with Ruff, strict mypy over
  20 source files, frontend lint/type-check, one frontend test, and the
  production build.
- Literal tool routing measured 14/14 (`1.0000`, target `>=0.90`). Pinned
  pre-commit passed all hooks, and frontend `npm audit --audit-level=high`
  found 0 vulnerabilities. Current imports are warning-free without global
  suppression; the initial LangGraph serializer warning was removed by the
  exact compatible `langchain-core==0.3.79` pin in fix round 1.
- No API, Celery, database migration, UI, deployment, live-provider, external
  action, or durable database event integration is claimed. No push was
  performed. Durable persistence remains Task 6.
- Next step: independent re-review/acceptance of the round-5 fix, then Task 6
  persistence and API integration.

## Task 2 checkpoint

- Implemented typed Pydantic contracts, deterministic Asteria Systems SAS synthetic Markdown/CSV generation, manifest hashes/byte lengths, literal provenance validation, 14 benchmark questions, and the module CLI.
- Controller evidence after fix round 1: `make verify` passed with 13 backend tests overall; the worker's direct pre-commit executable was unavailable, but the controller independently ran `uvx --from pre-commit==4.3.0 pre-commit run --all-files` successfully; `npm audit` reported zero vulnerabilities across 334 dependencies; byte-identical canonical regeneration passed; `git diff --check`, clean status, and the secret scan passed.
- Task 2 is accepted through head `5c5ce5f` after fix round 1.


## Task 3 implementation checkpoint

- Implemented validated UTF-8 Markdown and CSV ingestion with a 10 MiB limit, filename and MIME safeguards, SHA-256 workspace-scoped deduplication, exact Markdown line and section provenance, CSV table and A1 cell provenance, deterministic 1,200-character chunks, typed job and event contracts, bounded three-attempt retries, and redacted event persistence.
- Added focused Protocol ports, deterministic in-memory adapters, and injected MinIO and PostgreSQL boundaries without migrations or external-service requirements.
- RED evidence: the initial Task 3 contract probe failed because IngestionStatus was absent; the expanded suite initially failed collection because ingestion modules were absent. GREEN evidence: focused Task 3 suite passed 26 tests; full backend suite passed 40 tests.
- Fresh controller verification: make verify passed; pinned pre-commit all-files passed; independent review remains pending by instruction.


## Task 3 fix round 1 checkpoint

- Controller fix round completed locally: strict workspace IDs, typed AccessContext authorization, context-only job/event reads, atomic job creation, compensating deletes and commit-marker ordering, repair-aware deduplication, bounded retries, redacted terminal failures, provenance identity checks, typed MinIO lifecycle, chunk limits, and PostgreSQL identifier allowlist are covered.
- Current reconciled evidence: fix-round suite 11 passed; focused ingestion/adapter regression set 42 passed; `make verify` passed with 55 backend tests plus frontend lint/type/test/build; pinned pre-commit passed; `npm audit` found 0 vulnerabilities; diff and secret scans passed.
- Task 3 remains pending independent review. Do not push this checkpoint until controller review accepts it.

## Task 3 fix round 2 checkpoint

- Added document-record compensation for persist-then-raise failures, exact complete-chunk integrity checks for dedupe, requested parser document identity enforcement, and condition-notified terminal coalescing for concurrent identical submissions.
- RED was 4 failed/11 passed for the four new behavior tests. GREEN was 15 focused fix tests and 46 focused ingestion/adapter tests. `make verify` passed with 59 backend tests plus frontend lint/type/test/build; pinned pre-commit passed; `npm audit` found 0 vulnerabilities; diff and bounded changed-file secret scans passed.
- Task 3 remains pending independent review. Do not push this checkpoint until controller review accepts it.

## Task 3 fix round 3 checkpoint

- Corrected the generic retry compensation boundary so unexpected failures during read-only dedupe integrity reconstruction preserve valid committed document, object, and chunk state; current-attempt writes still compensate.
- Evidence: 16 focused fix tests, 47 focused ingestion/adapter tests, and `make verify` with 60 backend tests plus frontend lint/type/test/build passed. Pinned pre-commit and `npm audit` passed.
- Task 3 remains pending independent review. No push was performed.

## Task 3 accepted checkpoint

- Task 3 ingestion and provenance is accepted at production head `60a0241`.
  The fix-round-3 independent re-review found the final Critical issue
  addressed with no new breakage.
- The accepted checkpoint provides strict workspace and access-context
  isolation, validated UTF-8 Markdown/CSV ingestion, workspace-scoped SHA-256
  deduplication, exact source provenance, deterministic chunking, atomic job
  coalescing, bounded retries with redacted events, commit-marker repair and
  compensation, complete-chunk integrity validation, and mutation-aware
  preservation of valid committed state during read-only dedupe failures.
- Fresh controller evidence: `make verify` passed with 60 backend tests plus
  frontend lint, type-check, test, and production build; pinned pre-commit
  passed; frontend `npm audit` reported 0 vulnerabilities; `git diff` and
  status checks passed; and the filename-only secret scan found no matches.
- MinIO and PostgreSQL remain injected adapter boundaries only. This checkpoint
  does not claim external-service integration or production deployment.
- Task 4 is next.

## Task 4 implementation checkpoint

- Implemented deterministic lexical/vector retrieval, typed retriever and
  reranker ports, pre-retrieval workspace authorization, RRF with candidate
  depth 20 and final top 10, deterministic reranking, bounded whole-chunk
  context packing, retrieved-only citation verification, claim alignment, and
  typed fail-closed abstention.
- Added parameterized PostgreSQL full-text and pgvector retrieval boundaries
  with workspace predicates inside scoped SQL, plus deterministic local
  implementations for CI.
- Added literal Recall@10/MRR@10 evaluation against all 14 Asteria benchmark
  questions. Current local metrics are Recall@10 0.9643 and MRR@10 0.8095,
  above the specification thresholds of 0.90 and 0.80.
- Added malformed citation, unsupported/contradictory abstention,
  authorization ordering, SQL workspace binding, context budget, and
  cross-workspace isolation tests. Focused Task 4 tests: 11 passed; full
  backend suite: 71 passed.
- Fresh local gates: `make verify`, pinned pre-commit, frontend `npm audit`,
  diff check, and filename-only secret scan passed. No live provider or
  database integration is claimed. Task 4 remains pending independent review;
  no push was performed.
- Next task: Task 5.

## Task 4 fix round 1/5 checkpoint

- Preserved the controller's Ruff formatter change in `retrieval.py` and
  hardened claim alignment to fail closed on negation, numeric, relational,
  and unsupported paraphrases. Every citation must contribute support to its
  claim; missing document authority now abstains and arbitrary display names
  are rejected against the authoritative repository.
- Hybrid retrieval validates every delegated hit's workspace before fusion or
  reranking; PostgreSQL-decoded rows receive the same workspace validation.
  Textual polarity and relational contradictions no longer have a wording
  bypass and produce typed contradiction abstentions.
- Added a typed `RetrievalOutcome` abstention path for empty hybrid retrieval,
  while preserving tuple retriever ports. Focused retrieval suite: 21 passed.
- Full fix-round backend suite: 81 passed; frontend lint, type-check, test,
  and build also passed. The first pinned pre-commit run reformatted the
  controller-preserved retrieval file and the test file; remaining Ruff line
  findings were fixed, and the second pinned run passed without modification.
- Task 4 remains pending independent review. No push was performed.

## Task 4 fix round 2/5 checkpoint

- Replaced aggregate and per-citation token-overlap support with conservative
  deterministic alignment for exact text and explicit structured facts:
  subject/predicate/value, possession polarity, explicit state, and explicit
  relational forms. Unparsed prose remains unsupported and abstains; this is a
  deliberate conservative false-negative boundary, not a semantic-entailment
  claim.
- Revalidated every reranker result after fusion for authorized workspace,
  fused-candidate membership, immutable chunk identity/provenance, and duplicate
  IDs before retrieval return. Added regressions for foreign and unseen
  same-workspace reranker injections, role-swapped numeric facts, mixed policy
  negation, and turned-on/turned-off contradiction.
- Fresh evidence: focused retrieval suite 26 passed; mypy reported no issues in
  17 source files; the 14-question Asteria benchmark measured Recall@10
  0.9643 and MRR@10 0.8095; `make verify` passed with 86 backend tests plus
  frontend lint/type-check/test/build; pinned pre-commit was clean on the
  closing run after its formatter pass; `npm audit --audit-level=high` found 0
  vulnerabilities; diff check and filename-only secret scan found no issues.
- Task 4 remains pending independent review. No push was performed.

## Task 4 fix round 3/5 checkpoint

- Added a deep pre-reranker snapshot of each fused chunk. Final reranker output
  is checked against the snapshot for workspace, fused membership, immutable
  identity/provenance/text, and duplicate IDs; only ordering/rank and score
  changes remain permitted.
- Contradiction assessment now precedes exact-substring support. Explicit
  comma/`but`/`and`/`or` clauses are parsed, including a narrow elided state
  continuation such as `turned on and turned off`, and contradictory state or
  polarity facts abstain.
- Fresh evidence: mutation and conjunction regressions are GREEN; focused
  retrieval suite is 30 passed; Ruff and mypy are clean; the 14-question
  benchmark measured Recall@10 0.9643 and MRR@10 0.8095; `make verify` passed
  with 90 backend tests plus frontend lint/type-check/test/build; pinned
  pre-commit passed cleanly; `npm audit --audit-level=high` found 0
  vulnerabilities; diff check and filename-only secret scan found no issues.
- Task 4 remains pending independent review. No push was performed.

## Task 4 fix round 4/5 checkpoint

- Fresh escalation repair on clean base `c844a9b` closes the standalone-comma
  compound-evidence bypass. Structured clause extraction now handles standalone
  commas through the same boundary path as semicolons and conjunctions, keeps
  numeric separators intact, carries only structurally safe immediate state or
  possession-polarity continuations, and fails closed on ambiguous continuations
  before exact-substring support.
- Added the literal `turned on, turned off` regression plus semicolon,
  comma-`but`, comma-`and`, comma-`or`, and no-comma conjunction probes. The
  focused Task 4 suite reports 36 passed; the full backend suite reports 96
  passed. The seeded benchmark remains Recall@10 0.9643 and MRR@10 0.8095.
- Fresh `make verify`, pinned pre-commit, frontend high-severity audit, diff
  check, and filename-only secret scan passed. No live provider or database
  integration is claimed.
- Task 4 remains pending independent review and acceptance. This is a local
  fix-round checkpoint only; no push was performed.

## Task 4 accepted checkpoint

- Task 4 hybrid retrieval and citation verification is accepted at production
  head `71fc059` after independent round-4 review found the standalone-comma
  and punctuation Critical finding addressed with no new Critical or Important
  breakage.
- The accepted checkpoint provides evidence-first, fail-closed citation and
  claim alignment; typed abstention for unsupported, contradictory, malformed,
  ambiguous, and unauthorized evidence; workspace filtering before retrieval,
  fusion, reranking, and citation acceptance; immutable reranker candidate
  validation; and deterministic local retrieval with Recall@10 0.9643 and MRR@10
  0.8095 on the seeded benchmark.
- Controller verification at the accepted head passed `make verify` with 96
  backend tests plus frontend lint, type-check, test, and build; pinned
  pre-commit; frontend audit with 0 vulnerabilities; clean diff/status; and no
  secret-pattern filenames.
- PostgreSQL/pgvector, model/provider, and production integration remain
  injected or documented boundaries only; no live external integration or
  deployment is claimed. Task 5 bounded agentic investigation is next.
- This checkpoint is accepted locally but has not been pushed.

## Task 5 fix round 1/5 checkpoint

- Starting from committed Task 5 implementation `aaf04d4`, the sole-implementer
  fix round closes the approval type/persistence bypass, binds every verified
  draft to one unique successful tool-result ID, derives final evidence only
  from CitationVerifier-reviewed citations, and carries typed Decimal financial
  calculation traces with retained CSV currency units.
- Provider and routing contracts now enforce bounded cardinality/text/token
  outputs, global budgets of at most 12 transitions, 6 tools, 8,000 model
  tokens, and 30 seconds, plus exact literal benchmark-ID equality. Financial
  unit compatibility is symmetric and invalid mixed-unit operations abstain.
- The warning-free dependency set pins `langgraph==0.6.6` and
  `langchain-core==0.3.79`. Fresh verification reports 156 backend tests plus
  frontend lint/type-check/test/build passing with warnings treated as errors;
  the fix-round focused suite reports 60 passed. No live provider, database,
  deployment, external acceptance, or production report finalization is
  claimed.
- Minor event-store defensive-copy and hard-wall/timer-start timing concerns
  remain explicitly deferred; durable database event persistence remains Task
  6. This checkpoint is not an acceptance claim and has not been pushed.


### Task 5 fix round 2/5 checkpoint (2026-09-01)

Started from committed `8b384fa`. Round-2 regressions cover forged approval provenance, contradiction-category bypass, mutable budgets, nested provider bounds and actual serialized token accounting, and canonical routing-manifest integrity. Verification is green: focused Task 5 suite `76 passed`; full warning-as-error backend suite `172 passed`; `make verify` passed; pinned pre-commit passed; frontend audit found 0 vulnerabilities; literal routing is `14/14`, accuracy `1.0000`.

Critical and important findings in this fix request are addressed. Minor event-store defensive-copy and timer start/hard-wall timing concerns remain explicitly deferred. This checkpoint does not claim external acceptance, live-provider quality, or Task 6 durable database integration.


### Task 5 fix round 3/5 checkpoint (2026-09-01)

Started from `d80df01`. Round-3 regressions and fixes cover exact tool/result class mapping, unique finding correspondence, nested output limits and output-size token accounting, canonical evidence lineage into approval, verifier output validation, immutable routing expectations, and injected shared provenance keys. Verification: focused Task 5 suite `79 passed`; full `make verify` `181 passed`; pinned pre-commit passed; frontend audit found 0 vulnerabilities; routing `14/14`, accuracy `1.0000`.

Minor event-store defensive-copy and elapsed timer start/hard-wall timing concerns remain deferred. The default provenance key is process-local until a shared durable secret boundary is supplied; Task 6 owns durable persistence/key integration. No external acceptance or live-provider claim is made.


## Task 5 fix round 4 checkpoint

- Started from `831f551` with the round-4 regression suite present and production files unchanged. The intentional RED run reported 17 failures and 2 passes.
- Hardened approval with canonical full-`Evidence` fingerprints, exact approved-tool to exact result-class checks, independent duplicate result and finding ID rejection, all-results-success validation, and one-to-one finding lineage.
- Isolated routing expectations in a private immutable canonical mapping and retained the public routing dictionary only as a compatibility view. Added explicit Pydantic bounds to tool, result, finding, retrieval, context, routing, and nested string contracts.
- Focused Task 5 verification: 104 passed under `pytest -W error`; Ruff and strict mypy passed. No push was performed. The latest instruction limited the closing test run to focused Task 5 suites.

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
- Next task: Task 4.
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

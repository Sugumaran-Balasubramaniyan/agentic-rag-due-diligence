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
- Next task: Task 3, ingestion and provenance.
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
- RED evidence: the initial Task 3 contract probe failed because IngestionStatus was absent; the expanded suite initially failed collection because ingestion modules were absent. GREEN evidence: focused Task 3 suite passed 26 tests; full backend suite passed 39 tests.
- Fresh controller verification: make verify passed; pinned pre-commit all-files passed; independent review remains pending by instruction.


## Task 3 fix round 1 checkpoint

- Controller fix round completed locally: strict workspace IDs, typed AccessContext authorization, context-only job/event reads, atomic job creation, compensating deletes and commit-marker ordering, repair-aware deduplication, bounded retries, redacted terminal failures, provenance identity checks, typed MinIO lifecycle, chunk limits, and PostgreSQL identifier allowlist are covered.
- Current reconciled evidence: fix-round suite 11 passed; focused ingestion/adapter regression set 42 passed; `make verify` passed with 55 backend tests plus frontend lint/type/test/build; pinned pre-commit passed; `npm audit` found 0 vulnerabilities; diff and secret scans passed.
- Task 3 remains pending independent review. Do not push this checkpoint until controller review accepts it.

## Task 3 fix round 2 checkpoint

- Added document-record compensation for persist-then-raise failures, exact complete-chunk integrity checks for dedupe, requested parser document identity enforcement, and condition-notified terminal coalescing for concurrent identical submissions.
- RED was 4 failed/11 passed for the four new behavior tests. GREEN was 15 focused fix tests and 46 focused ingestion/adapter tests. `make verify` passed with 59 backend tests plus frontend lint/type/test/build; pinned pre-commit passed; `npm audit` found 0 vulnerabilities; diff and bounded changed-file secret scans passed.
- Task 3 remains pending independent review. Do not push this checkpoint until controller review accepts it.

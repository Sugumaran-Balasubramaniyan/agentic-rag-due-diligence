# Task 3 report: ingestion and provenance

## Implementation

- Added stable typed contracts for uploads, normalized blocks, chunks, jobs, events, ingestion status, and failure classification.
- Added deterministic UTF-8 Markdown and CSV parsing. Markdown keeps exact non-empty line spans, page 1, and active level-two sections. CSV keeps table names, row spans, and A1 cell coordinates.
- Added upload validation for the 10 MiB limit, empty data, NUL bytes, invalid UTF-8, unsafe filenames, unsupported extensions and MIME types, and extension/MIME mismatches.
- Added deterministic provenance-preserving chunking capped at 1,200 characters. Chunks never combine normalized blocks and IDs derive from workspace, document, ordinal, and content hash.
- Added workspace-scoped SHA-256 deduplication, queued/running/succeeded/failed lifecycle, maximum three total transient attempts, and redacted attempt/transition events.
- Added focused Protocol ports and deterministic in-memory object, document, chunk, and event adapters.
- Added injected MinIO and PostgreSQL adapter boundaries. PostgreSQL operations use parameter tuples and decode cursor rows; schema migrations remain Task 6 work.
- Added canonical Asteria integration coverage and cross-workspace deny-by-default coverage.

## RED/GREEN evidence

- RED: `uv run pytest tests/test_ingestion.py -q` failed with the expected missing-contract assertion: `IngestionStatus` was absent.
- RED: `uv run pytest tests/test_ingestion_full.py -q` failed during collection with the expected `ModuleNotFoundError` because Task 3 modules did not exist.
- GREEN: `uv run pytest tests/test_ingestion.py tests/test_ingestion_full.py tests/test_ingestion_canonical.py tests/test_ingestion_boundaries.py -q` passed 26 tests.
- RED/GREEN regression: `tests/test_postgres_adapter_reads.py` first failed because the adapter returned `None`; after row decoding, `uv run pytest tests/test_postgres_adapter_reads.py -q` passed.
- Final backend suite: 40 passed.

## Exact full verification

- `make verify` — passed: Ruff, mypy, 40 backend tests, frontend ESLint, TypeScript check, 1 frontend test, and Vite production build.
- `uvx --from pre-commit==4.3.0 pre-commit run --all-files` — passed: Ruff, Ruff format, and Prettier hooks.
- `git diff --check` — passed.

## Files

- `backend/src/due_diligence_copilot/ingestion_contracts.py`
- `backend/src/due_diligence_copilot/ingestion_errors.py`
- `backend/src/due_diligence_copilot/parsers.py`
- `backend/src/due_diligence_copilot/parser_dispatch.py`
- `backend/src/due_diligence_copilot/chunking.py`
- `backend/src/due_diligence_copilot/ports.py`
- `backend/src/due_diligence_copilot/adapters.py`
- `backend/src/due_diligence_copilot/ingestion_service.py`
- `backend/tests/test_ingestion.py`
- `backend/tests/test_ingestion_full.py`
- `backend/tests/test_ingestion_canonical.py`
- `backend/tests/test_ingestion_boundaries.py`
- `backend/tests/test_postgres_adapter_reads.py`
- `FUTURE_HANDOFF.md`

## Self-review

- Scope is limited to ingestion, provenance, storage/index ports, deterministic adapters, and tests. No API endpoints, jobs, retrieval, embeddings, or agent behavior were added.
- Source content is not placed in event summaries; failures are classified and persisted without exception text.
- Storage and index keys carry workspace identity, repository lookups are workspace-filtered, and service job reads reject another workspace.
- The PostgreSQL adapter expects an injected DB-API-like result with `fetchone`; it does not create tables or manage transactions, intentionally leaving schema/migration/runtime integration to Task 6.

## Concerns

- External MinIO/PostgreSQL services were not started, by task instruction; only injected client/connection boundary behavior was verified.
- Independent review is intentionally pending. This report does not mark Task 3 accepted.


## Fix Round 1 evidence

- Addressed strict workspace identifiers and authenticated AccessContext authorization. Ingestion and context-only job/event reads reject unauthorized access before storage, repository, index, event, or job port calls.
- Added scoped object/chunk deletes, object/chunk-first ordering, document-record commit marker ordering, compensation on failed writes, and repair-aware deduplication with object/chunk consistency checks.
- Added atomic in-memory JobRepository.create_if_absent and deterministic job IDs; identical sequential and concurrent submissions do not repeat writes or lifecycle events.
- Moved dedupe reads and parser/chunk/storage operations through the bounded three-attempt processing loop; unexpected failures are classified as redacted transient failures and terminal jobs are failed. Parser provenance mismatches are permanent failures.
- Completed typed MinIO get response cleanup and remove_object boundary, strict chunk limits, and PostgreSQL table allowlist.
- Expanded canonical integration assertions to each generated document and each produced chunk.

### RED/GREEN

- RED: controller diagnostic run of `tests/test_ingestion_fix_round1.py` was 4 failed, 4 passed: obsolete read signatures and missing upper chunk bound.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_ingestion_fix_round1.py -q` — 11 passed.
- GREEN: focused ingestion/adapter set (`test_ingestion.py`, `test_ingestion_full.py`, `test_ingestion_canonical.py`, `test_ingestion_boundaries.py`, `test_postgres_adapter_reads.py`, `test_ingestion_fix_round1.py`) — 42 passed.
- GREEN: `make verify` — 55 backend tests passed; frontend lint, type-check, 1 frontend test, and production build passed.

### Exact full verification

- `make verify` — passed: Ruff, strict mypy, 55 backend tests, frontend ESLint, TypeScript check, 1 frontend test, and Vite build.
- `uvx --from pre-commit==4.3.0 pre-commit run --all-files` — passed: Ruff, Ruff format, and Prettier.
- `npm audit` — passed: found 0 vulnerabilities.
- `git diff --check` — passed.
- Secret-pattern scan over the repository — passed with no matches.

### Fix Round 1 files

- `backend/src/due_diligence_copilot/workspace.py`
- `backend/tests/test_ingestion_fix_round1.py`
- Updated ingestion contracts, errors, service, chunking, ports, adapters, canonical/full/boundary tests, and PostgreSQL adapter tests.
- Updated `FUTURE_HANDOFF.md`.

### Fix Round 1 self-review

- Scope remains limited to Task 3 ingestion/provenance, ports/adapters, and tests. No API endpoints, Celery jobs, retrieval, embeddings, migrations, or agent behavior were added.
- Workspace scope is resolved from AccessContext; no read method accepts a caller-selected workspace namespace. MinIO and in-memory keys are workspace-scoped.
- Lifecycle events contain fixed summaries only and never exception text or source content. Failed write attempts compensate before retry/failure, and a document record is saved only after object/chunks.
- Earlier report references to 26 focused and 40 full backend tests describe the pre-fix baseline. Current reconciled counts are 42 focused regression tests, including 11 fix-round tests, and 55 full backend tests.

### Fix Round 1 concerns

- External MinIO/PostgreSQL services remain intentionally unstarted; injected typed boundaries are tested. PostgreSQL migrations remain Task 6.
- Task 3 remains pending independent review; this report does not mark it accepted.

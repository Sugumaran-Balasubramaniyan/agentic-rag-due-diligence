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

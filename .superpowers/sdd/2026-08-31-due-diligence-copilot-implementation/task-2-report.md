# Task 2 implementation report: deterministic synthetic data room

## Implementation

- Added stable Pydantic v2 contracts in `backend/src/due_diligence_copilot/domain.py` for `DocumentType`, `SourceLocation`, `DocumentRecord` and manifest items, `Evidence`, `Finding`, `AgentEvent`, `AnalysisStatus`, `Report`, benchmark ground truth, and supporting enums.
- Added `backend/src/due_diligence_copilot/synthetic_data.py` with fixed UTF-8 source templates, fixed schema and generator versions, fixed generated timestamp, SHA-256 and byte-length manifest records, literal Markdown-line and CSV-cell provenance, source-byte validation, traversal-safe output paths, and a module CLI.
- Generated the canonical fictional Asteria Systems SAS data room at `data/synthetic/asteria-data-room/`. Every entity and data value is synthetic. No binary or PDF generation was added.
- Seeded revenue and customer concentration, EBITDA, change of control, supplier escalation, missing SOC 2, security-policy and board-minute contradiction, unsupported churn, and an embedded prompt-injection instruction classified as `untrusted_document_content`.
- Added 13 benchmark questions covering factual, calculation, cross-document, contradiction, missing-document, unsupported/abstain, and injection-resistance cases.
- Documented CLI usage and scope in `README.md`; updated `FUTURE_HANDOFF.md` only after implementation and verification to mark Task 2 pending independent review.

## TDD evidence

RED command, before production implementation:

```text
$ cd backend && uv run pytest tests/test_synthetic_data.py -q
ERROR collecting tests/test_synthetic_data.py
ModuleNotFoundError: No module named due_diligence_copilot.domain
exit_code=2
```

The failure was caused by the missing production contract module, not a test typo.

GREEN focused command after implementing the minimum contracts and generator:

```text
$ cd backend && uv run pytest tests/test_synthetic_data.py -q
........                                                                 [100%]
exit_code=0
```

A later test-first boundary check for empty output names produced the expected RED failure, then passed after `safe_output_path` rejected empty relative paths.

## Full verification

Fresh final command from the repository root:

```text
$ make verify
ruff: All checks passed
mypy: Success: no issues found in 4 source files
backend pytest: 9 passed in 0.35s
frontend eslint: passed
frontend type-check: passed
frontend vitest: 1 test file, 1 test passed
frontend build: 74 modules transformed, build succeeded
exit_code=0
```

Additional focused checks passed during implementation: CLI generation reported 7 documents and 13 benchmark questions; repeated temporary generation was byte-identical; manifest validation returned no errors; document byte lengths and SHA-256 values matched emitted bytes; `git diff --check` passed.

## Generated files

- `data/synthetic/asteria-data-room/financial-summary.md`
- `data/synthetic/asteria-data-room/major-customer-contract.md`
- `data/synthetic/asteria-data-room/critical-supplier-contract.md`
- `data/synthetic/asteria-data-room/security-policy.md`
- `data/synthetic/asteria-data-room/board-minutes.md`
- `data/synthetic/asteria-data-room/revenue-by-customer.csv`
- `data/synthetic/asteria-data-room/document-request-list.md`
- `data/synthetic/asteria-data-room/manifest.json`

## Self-review

The implementation is bounded to typed contracts, deterministic data generation, provenance and manifest validation, CLI, fixtures, tests, README, and handoff. It does not implement ingestion, retrieval, agents, API behavior, or model-provider behavior. Source locations are document-relative and all benchmark expected answers and evidence contain literal values plus locations; CSV references resolve by exact A1 cell value. The generator has no network, clock, randomness, or environment-secret access.

## Concerns

Task 2 is pending the independent review checkpoint required by the controller. Future ingestion must preserve the manifest path, document IDs, CSV cell coordinates, and literal validation contract.

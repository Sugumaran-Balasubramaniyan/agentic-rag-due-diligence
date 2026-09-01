# Evidence-First Agentic RAG Due-Diligence Copilot

This repository is being built as a production-ready reference implementation for cited research, bounded agentic investigation, and human-approved M&A due-diligence reporting.

The authoritative design and implementation plan are available under `docs/superpowers/`. Verified setup instructions, architecture, evaluation results, screenshots, and the interview demo will replace this bootstrap note as implementation progresses.

Current status: Task 2 deterministic synthetic data room implemented; independent review is pending. No production-readiness or evaluation claim is made.

## Deterministic Task 1 checks

Requires Python 3.12, `uv`, Node.js 22, npm, and GNU Make. No provider or
credential is required.

```bash
cd backend && uv sync --locked
cd ../frontend && npm ci
cd .. && make verify
```

The root Makefile exposes the individual `backend-lint`, `backend-type`,
`backend-test`, `frontend-lint`, `frontend-type`, `frontend-test`, and
`frontend-build` checks as well as the combined `verify` target.


## Synthetic data room

Task 2 provides a deterministic, fictional data room for Asteria Systems SAS. All entities and data are synthetic. The canonical UTF-8 Markdown and CSV fixtures, hashes, source locations, and benchmark ground truth live at `data/synthetic/asteria-data-room/`.

Generate or validate the room from the backend package with:

```bash
cd backend && uv run python -m due_diligence_copilot.synthetic_data
```

Use `--output PATH` for a separate fixture directory. The generator uses no network, clock, randomness, or environment secrets; rerunning it produces byte-identical files. Ingestion, retrieval, and agent behavior are not part of this task.

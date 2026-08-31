# Evidence-First Agentic RAG Due-Diligence Copilot

This repository is being built as a production-ready reference implementation for cited research, bounded agentic investigation, and human-approved M&A due-diligence reporting.

The authoritative design and implementation plan are available under `docs/superpowers/`. Verified setup instructions, architecture, evaluation results, screenshots, and the interview demo will replace this bootstrap note as implementation progresses.

Current status: repository bootstrap only. No production-readiness or evaluation claim is made yet.

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

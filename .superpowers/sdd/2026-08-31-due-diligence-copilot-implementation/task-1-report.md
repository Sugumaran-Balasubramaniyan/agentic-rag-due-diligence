# Task 1 report: Bootstrap executable project contracts

## Implementation

- Added a Python 3.12 backend `src/` workspace with FastAPI, Pydantic v2,
  pinned runtime/dev dependencies, `uv.lock`, liveness/readiness endpoints,
  and a provider-free FastAPI smoke test.
- Added a React 19/TypeScript/Vite frontend with TanStack Query, pinned npm
  dependencies, `package-lock.json`, an accessible deterministic shell, and a
  provider-free render smoke test.
- Added root Makefile targets for backend lint/type/test and frontend
  lint/type/test/build, plus README commands.
- Added `.env.example`, `.gitignore` updates, pre-commit configuration, a
  deterministic GitHub Actions CI skeleton, and ADRs 0001-0002.
- Recorded the independently reviewed task checkpoint/push rule in
  `AGENTS.md`, the implementation plan global constraints, and
  `FUTURE_HANDOFF.md`.
- No domain behavior, credentials, live-provider calls, database, or external
  service dependency was added.

## TDD evidence

### RED

Tests were added before application implementation.

Backend command:

```text
uv run --with pytest --with fastapi --with httpx pytest tests/test_app.py -v
```

Relevant output:

```text
collected 0 items / 1 error
ModuleNotFoundError: No module named 'due_diligence_copilot'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
exit=2
```

Frontend command:

```text
npm test -- --run src/App.test.tsx
```

Relevant output:

```text
npm error enoent Could not read package.json
exit=254
```

These failures were caused by the missing project contracts, not by test
assertion typos.

### GREEN

Clean installs:

```text
cd backend && uv sync --locked
```

Result: exit 0; Python 3.12.3 environment created and 31 packages installed.

```text
cd frontend && npm ci
```

Result: exit 0; 286 packages installed from `package-lock.json`.

Focused backend command:

```text
uv run pytest tests/test_app.py -v
```

Relevant output: `1 passed in 0.70s`, exit 0.

Focused frontend command:

```text
npm test -- --run src/App.test.tsx
```

Relevant output: `Test Files 1 passed (1)`, `Tests 1 passed (1)`, exit 0.

## Full verification

Command:

```text
make verify
```

Fresh final result: exit 0.

- `uv run ruff check .`: All checks passed.
- `uv run mypy src`: Success, no issues found in 2 source files.
- `uv run pytest`: 1 passed.
- `npm run lint`: passed.
- `npm run type-check`: passed.
- `npm test -- --run`: 1 test file and 1 test passed.
- `npm run build`: Vite 7.1.3 production build passed; 74 modules transformed.
- `git diff --check`: passed.
- Common credential/private-key pattern scan: no matches.
- `npm audit --omit=dev --json`: zero production vulnerabilities.

## Changed files

- `.env.example`, `.gitignore`, `.pre-commit-config.yaml`, `Makefile`.
- `.github/workflows/ci.yml`.
- `AGENTS.md`, `FUTURE_HANDOFF.md`, `README.md`.
- `backend/pyproject.toml`, `backend/uv.lock`.
- `backend/src/due_diligence_copilot/__init__.py` and `main.py`.
- `backend/tests/test_app.py`.
- `frontend/package.json`, `frontend/package-lock.json`.
- `frontend/index.html`, `frontend/eslint.config.js`, Vite/TypeScript config,
  and `frontend/src/*` shell/test files.
- `docs/adr/0001-bootstrap-runtime-contracts.md` and
  `docs/adr/0002-deterministic-provider-boundary.md`.
- This report.

## Self-review

- The backend uses the requested `src` layout and exposes only health smoke
  behavior.
- The frontend has no product workflow and its smoke test exercises a visible
  heading plus deterministic-mode status.
- Root commands are explicit and CI invokes the same `make verify` contract.
- Lockfiles are committed and generated install/build artifacts are ignored.
- No credentials or live-provider requirement are present.
- The original design spec remains authoritative; no domain contract was
  invented in this task.

## Concerns

- `npm ci` reports two development-tree advisories from transitive packages
  and one deprecated transitive package warning. Production dependencies have
  zero vulnerabilities in the checked audit. The dev dependency tree should
  be refreshed before release if upstream versions provide a compatible fix.
- The pre-commit configuration is a deterministic hook skeleton; installing
  pre-commit itself is intentionally not required for the Task 1 smoke suite.
- Publishing remains blocked by the pre-existing unrelated embedded Git
  credential noted in `FUTURE_HANDOFF.md`; this task did not inspect or use it.

## Commit

Implementation commit: `dfb79f7 feat: bootstrap executable project contracts`.

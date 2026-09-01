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


## Fix Round 1

Addressed the independent review findings. CI now runs `uv sync --locked` in `backend/` and `npm ci` in `frontend/` before `make verify`. Actions are pinned to official full SHAs with release comments: checkout v4.2.2 (`11bd71901bbe5b1630ceea73d27597364c9af683`), setup-python v5.6.0 (`a26af69be951a213d495a4c3e4e4022e16d87065`), setup-uv v6.3.1 (`bd01e18f51369d5a26f1651c3cb451d3417e3bba`), and setup-node v4.4.0 (`49933ea5288caeca8642d1e84afbd3f7d6820020`). Runtime selectors are pinned to Python 3.12.3 and Node 22.22.2.

Pre-commit was corrected so `rev` is repository-level and Prettier is scoped to `frontend/`. Exact validation commands and evidence:

```text
uvx --from pre-commit==4.3.0 pre-commit validate-config
exit=0
uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias) ... Passed
ruff format ... Passed
prettier ... Passed
exit=0
```

The frontend TDD cycle was restarted honestly. After removing `frontend/src/App.tsx`, the exact command `npm test -- --run src/App.test.tsx` failed with Vitest import analysis: `Error: Failed to resolve import "./App" from "src/App.test.tsx"`, `Test Files no tests`, `exit=1`. Reimplementing the minimal App from the unchanged smoke test and rerunning the same command produced `Test Files 1 passed (1)`, `Tests 1 passed (1)`, `exit=0`.

Fresh verification on the committed fix (`7209a5d`) used a new `mktemp` clone with no existing `backend/.venv` or `frontend/node_modules`, then ran `uv sync --locked`, `npm ci`, and `make verify`. The corrected command exited 0; the full clone matrix reported backend lint/type/test green, frontend lint/type/test/build green, and the frontend test count was 1 passed. The first probe incorrectly ran `uv sync` from `/tmp` and exited 2 before testing the project; it was discarded and not treated as project evidence.

Additional fix-round gates:

```text
make verify -> exit=0
git diff --check -> exit=0
common credential/private-key scan -> no matches
npm audit --omit=dev --json -> vulnerabilities total 0
```

Remaining concern: `npm ci` still reports two development-tree advisories (one high and one critical) plus deprecation warnings; production-only audit is clean.

Fix implementation commit: `7209a5d fix: harden Task 1 verification contracts`.


## Fix Round 2

Addressed the verified re-review findings. The CI runner is now `ubuntu-24.04`; ADR 0003 documents that Actions and language runtimes remain full-version/SHA pinned while GitHub controls patching of the hosted image. The CI workflow retains full action SHA pins, Python 3.12.3, Node 22.22.2, and runs `uv sync --locked` and `npm ci` before `make verify`.

Baseline audit captured before the dependency change:

```text
npm audit --json
metadata.vulnerabilities.high = 1
metadata.vulnerabilities.critical = 1
metadata.vulnerabilities.total = 2
Direct findings: Vite high, Vitest critical
exit=1
```

Only the direct dev dependencies requested by review were changed, with exact pins: Vite `7.3.6` and Vitest `3.2.7`. The lockfile was regenerated with the targeted npm install; the resulting transitive changes are the Vite/Vitest dependency closure. `npm ci` installed the patched versions, confirmed by `node -p` output `7.3.6` and `3.2.7`.

Post-update complete-tree audit:

```text
npm audit --json
metadata.vulnerabilities.info = 0
metadata.vulnerabilities.low = 0
metadata.vulnerabilities.moderate = 0
metadata.vulnerabilities.high = 0
metadata.vulnerabilities.critical = 0
metadata.vulnerabilities.total = 0
exit=0
```

Focused frontend evidence:

```text
npm test -- --run src/App.test.tsx
RUN v3.2.7
Test Files 1 passed; Tests 1 passed; exit=0
npm run build
vite v7.3.6 building client environment for production
74 modules transformed; exit=0
```

Full local gates:

```text
make verify -> exit=0; backend lint/type/test and frontend lint/type/test/build passed
uvx --from pre-commit==4.3.0 pre-commit run --all-files -> ruff passed, ruff format passed, prettier passed; exit=0
git diff --check -> exit=0
common credential/private-key scan -> no matches
npm audit --json -> zero vulnerabilities across 334 dependencies; exit=0
```

Fresh-clone proof used the committed tree `45cd9f4`: `mktemp` clone, assertions that `backend/.venv` and `frontend/node_modules` were absent, `uv sync --locked`, `npm ci`, and `make verify`. It exited 0; the clone reported Vitest 3.2.7, Vite 7.3.6, one frontend test passed, and the production build passed.

Self-review: exact direct dependency pins are present in both `package.json` and the lockfile; no blind force fix or unrelated direct dependency upgrade was used; the mutable `ubuntu-latest` alias is gone; pre-commit configuration validates and runs cleanly. Remaining install output contains only upstream deprecation warnings for transitive packages; the complete audit is clean.

Fix implementation commit: `45cd9f4 fix: pin CI runner and patched frontend tools`.

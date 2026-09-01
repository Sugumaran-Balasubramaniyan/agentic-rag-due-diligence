# ADR 0001: Bootstrap runtime contracts

## Status

Accepted for Task 1.

## Decision

Use a monorepo with a Python 3.12 `backend/` src-layout workspace and a
React/TypeScript/Vite `frontend/` workspace. The root Makefile is the stable
verification interface for backend lint/type/test and frontend
lint/type/test/build commands.

## Consequences

The application shells can be installed and tested independently without a
database, model, provider, or credential. Later tasks may add domain behavior
behind these contracts without replacing the workspace layout.

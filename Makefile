.DEFAULT_GOAL := verify

.PHONY: backend-lint backend-type backend-test frontend-lint frontend-type frontend-test frontend-build verify

backend-lint:
	cd backend && uv run ruff check .

backend-type:
	cd backend && uv run mypy src

backend-test:
	cd backend && uv run pytest

frontend-lint:
	cd frontend && npm run lint

frontend-type:
	cd frontend && npm run type-check

frontend-test:
	cd frontend && npm test -- --run

frontend-build:
	cd frontend && npm run build

verify: backend-lint backend-type backend-test frontend-lint frontend-type frontend-test frontend-build

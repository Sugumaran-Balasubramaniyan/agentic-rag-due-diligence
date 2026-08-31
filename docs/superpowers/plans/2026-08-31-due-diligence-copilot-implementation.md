# Due-Diligence Copilot Implementation Plan

**Spec:** `docs/superpowers/specs/2026-08-31-due-diligence-copilot-design.md`

**Global constraints:** Use TDD for production behavior. Preserve provenance and workspace isolation. Keep PR CI deterministic. Do not publish unsupported metrics or production claims. Implementers and reviewers use `gpt-5.6-luna`; the controller performs integration rulings and final acceptance. Commit every accepted task. Update `FUTURE_HANDOFF.md` after each milestone.

## Task 1: Bootstrap executable project contracts

Create the Python and web workspaces, locked dependency manifests, task runner, `.env.example`, pre-commit configuration, CI skeleton, and architecture decision records. Add failing then passing smoke tests proving the FastAPI application and React application can load without external services. Provide deterministic commands for lint, type-check, test, and build. Do not add business behavior.

Acceptance: clean installs; backend and frontend smoke tests pass; lint/type/build commands are documented and executable; no credential or live-provider requirement.

## Task 2: Build the deterministic synthetic data room

Define domain schemas for documents, locations, evidence, findings, agent events, analysis state, and reports. Build a deterministic generator for fictional contracts, financial statements, policies, board notes, and spreadsheets containing known facts, risks, contradictions, missing-document cases, and prompt-injection text. Emit a manifest with hashes and literal ground truth.

Acceptance: repeated generation is byte-stable; hashes match; every benchmark answer points to a valid source location; fixtures contain no third-party or private data.

## Task 3: Implement ingestion and provenance

Implement validated upload, hashing, deduplication, parsing adapters, normalized blocks, provenance-preserving chunking, table/cell extraction, job states, retries, and indexing interfaces. Provide an in-memory implementation for deterministic tests and PostgreSQL/MinIO adapters behind interfaces. Reject unsupported, malformed, oversized, and cross-workspace inputs.

Acceptance: red-green tests cover successful ingestion and each failure boundary; every chunk retains source coordinates; retries are bounded and observable.

## Task 4: Implement hybrid retrieval and citation verification

Implement lexical and vector retriever interfaces, workspace filters before retrieval, Reciprocal Rank Fusion, reranking, context packing, claim/evidence alignment, citation validation, and abstention. Supply deterministic local implementations for CI and PostgreSQL/pgvector implementations for the full stack.

Acceptance: benchmark retrieval thresholds pass; malformed citations are rejected; unsupported and contradictory queries abstain; cross-workspace fixture retrieval returns zero leaked evidence.

## Task 5: Implement bounded agentic investigation

Implement the typed workflow and approved deterministic tools for financial calculations, contract inspection, contradictions, and missing documents. Enforce recursion, tool-call, time, and token budgets. Persist redacted events and route only verified findings to approval/reporting.

Acceptance: tests cover every transition, budget exhaustion, provider/tool failure, injected instructions, deterministic calculations, abstention, and approval boundary; tool-routing target is met.

## Task 6: Implement persistence, jobs, and public API

Implement repositories, database models/migrations, Celery jobs, FastAPI endpoints, SSE event streaming, problem-details errors, liveness/readiness, and metrics. Enforce workspace authorization in service and database paths. Add a read-only demo policy using the same contracts.

Acceptance: API integration tests cover the complete ingestion-to-report lifecycle, authorization failures, idempotency, event ordering, provider failure, and demo mutation denial.

## Task 7: Build the evidence-first React experience

First write and critique a compact visual plan with exact color, type, layout, and signature interaction. Then implement data-room status, cited investigation, agent timeline, evidence drawer, approval queue, report, evaluation, and operations views. Use real API schemas and accessible, responsive interactions.

Acceptance: component and Playwright tests cover the five interview scenarios; keyboard focus, reduced motion, mobile layout, loading, empty, and actionable error states are verified; screenshot critique is recorded.

## Task 8: Add evaluation, security, and observability

Implement the golden-dataset runner, retrieval/citation/abstention/tool-routing metrics, prompt-injection and tenant-isolation suites, OpenTelemetry spans, structured redacted logs, Prometheus metrics, and Grafana dashboards. Generate machine-readable and human-readable reports without fabricating results.

Acceptance: deterministic quality gates meet the specification; security fixtures all pass; trace/log correlation works; reports state environment and limitations.

## Task 9: Package the full local and Kubernetes deployments

Create production-oriented multi-stage containers, Docker Compose services, migrations/seeding workflow, health checks, resource limits, Helm chart, kind smoke automation, backup/restore notes, and failure runbooks. Keep secrets out of images and manifests.

Acceptance: Compose starts from clean state and completes a seeded query; Helm installs on kind, becomes ready, and exercises query/approval/report; image and manifest security checks pass.

## Task 10: Build the Hugging Face demo mode

Implement the pre-indexed embedded retrieval bundle, anonymous read-only workspace, disabled upload/admin paths, bounded generation policy, Space configuration, and graceful no-key deterministic fallback. Preserve API compatibility with the full stack.

Acceptance: local Space-equivalent container runs the five demo scenarios; mutation attempts fail closed; no secret is required for deterministic fallback; deployment instructions are exact.

## Task 11: Create interview-grade documentation

Replace the bootstrap README with the verified project narrative, architecture, quick start, measured results, security model, deployment choices, screenshots, limitations, and role mapping. Add focused technical guides, ADRs, diagrams, a ten-minute demo script, and interview questions explaining each major design decision and trade-off.

Acceptance: every claim is supported by a command, test, report, or captured artifact; a new reader can run the deterministic demo from the README; no inflated experience or production claim appears.

## Task 12: Final audit and release preparation

Run the complete deterministic verification matrix, dependency/secret/security scans, Compose and kind smoke tests, accessibility checks, final screenshot review, and independent whole-branch review. Fix all critical and important findings. Prepare but do not perform GitHub push, portfolio deployment, or Hugging Face publication until the credential gate and external-side-effect approval are satisfied.

Acceptance: fresh evidence records all gates and limitations; worktree is clean; handoff contains exact release commands and blockers; final reviewer approves spec compliance and code quality.


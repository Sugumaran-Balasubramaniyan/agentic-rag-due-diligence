# Evidence-First Agentic RAG Due-Diligence Copilot — Design

## Product intent

Build a public, interview-ready reference implementation of a secure internal M&A due-diligence copilot. The system must ingest a deterministic synthetic data room, answer questions with source-level evidence, execute bounded cross-document investigations, and require human approval before finalizing reports.

The primary audience is a senior AI/ML engineering hiring panel evaluating production RAG, agentic workflows, Python quality, evaluation, observability, deployment, security, and technical leadership.

## Binding product behavior

### Cited research

- Every material answer claim is linked to document, page, section, table, or spreadsheet-cell evidence.
- Answers abstain when evidence is missing or contradictory beyond the configured confidence threshold.
- Retrieved document instructions are untrusted content and cannot alter system or workflow policy.

### Agentic investigation

- A typed, bounded state machine classifies, plans, retrieves, reranks, invokes approved tools, verifies claims, assesses completeness, and either requests approval, abstains, or fails safely.
- Approved deterministic tools cover financial calculations, contract-clause inspection, contradiction detection, and missing-document analysis.
- The UI exposes a redacted execution timeline and the evidence used by every finding.

### Reporting and approval

- Reports contain findings, severity, evidence, calculations, uncertainty, unresolved questions, and approval state.
- Research may run autonomously; consequential report finalization requires explicit human approval.
- No workflow sends external messages, edits source documents, or performs business transactions.

## Architecture

- React/TypeScript/Vite frontend with TanStack Query and accessible custom components.
- Python 3.12 FastAPI backend using Pydantic v2, SQLAlchemy, and Alembic.
- Celery and Redis for background ingestion; PostgreSQL 16, pgvector, and MinIO in the full local stack.
- Docling parsing with preserved page, section, table, and cell provenance.
- PostgreSQL full-text and pgvector retrieval fused by Reciprocal Rank Fusion, followed by cross-encoder reranking.
- `BAAI/bge-small-en-v1.5` and `cross-encoder/ms-marco-MiniLM-L-6-v2` are the documented defaults, behind replaceable interfaces.
- LangGraph provides the agent state machine; model generation is behind Mistral, OpenAI-compatible local, and deterministic test adapters.
- OpenTelemetry, structured logs, Prometheus, and Grafana expose traces and operational metrics.
- Docker Compose is the canonical full local deployment; Helm on kind proves Kubernetes packaging.
- The Hugging Face demo uses identical API contracts, a pre-indexed corpus, an embedded retrieval adapter, and read-only controls.

## API and domain contracts

Required endpoints:

- `POST /api/v1/workspaces`
- `POST /api/v1/workspaces/{id}/documents`
- `GET /api/v1/ingestion-jobs/{id}`
- `POST /api/v1/workspaces/{id}/questions`
- `GET /api/v1/analyses/{id}`
- `GET /api/v1/analyses/{id}/events`
- `POST /api/v1/analyses/{id}/approval`
- `GET /api/v1/reports/{id}`
- `/health/live`, `/health/ready`, and `/metrics`

Required public schemas:

- `Evidence`: document ID, display name, page, section, table/cell, excerpt, chunk ID, retrieval score.
- `Finding`: category, severity, claim, evidence, confidence, verification status.
- `AgentEvent`: sequence, node, status, duration, and redacted summary.
- Analysis status: `queued`, `running`, `needs_input`, `awaiting_approval`, `completed`, `abstained`, or `failed`.

## Security boundaries

- Workspace identity is propagated into storage and retrieval; authorization is deny-by-default and isolation is tested.
- Public demo users can query only the preloaded workspace and cannot upload, mutate, or invoke expensive administration.
- File ingestion validates size, type, and content structure and never follows arbitrary URLs.
- Secrets are environment-only. Logs, events, fixtures, and committed files contain no credentials or private documents.
- Prompt injection, unsupported claims, malformed inputs, provider failures, and budget exhaustion fail closed and remain observable.

## Evaluation and acceptance

- Seeded corpus provenance completeness: 100%.
- Retrieval Recall@10: at least 0.90; MRR@10: at least 0.80.
- Citation precision: at least 0.95; citation coverage: at least 0.90.
- Seeded deterministic financial calculations: 100% correct.
- Unsupported-question abstention and tool routing: at least 0.90 each.
- Cross-workspace leakage: zero across the complete fixture suite.
- Every curated prompt-injection fixture is blocked or ignored.
- Pull-request CI is deterministic and has no live model dependency.
- Docker Compose and kind/Helm smoke tests exercise ingestion/query/approval/report paths.
- Performance and live-provider quality are reported from captured runs, not asserted without evidence.

## Experience and documentation

The application resembles a deal-room control surface, not a generic chatbot. Its signature interaction is an evidence rail connecting workflow steps and report claims to sources. The UI must be responsive, keyboard accessible, reduced-motion aware, and explicit about empty/error states.

The final repository includes a concise README, architecture and data-flow diagrams, retrieval and agent explanations, evaluation methodology, threat model, deployment guide, runbooks, ADRs, and a ten-minute interview demonstration guide. Every public claim links to reproducible evidence.


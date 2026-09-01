# Bounded Agentic Investigation Implementation Plan

> **For agentic workers:** This plan is executed inline in the supplied worktree because the task explicitly forbids subagent dispatch. Each step uses checkbox syntax and must be completed with fresh RED/GREEN evidence.

**Goal:** Add a typed, finite LangGraph investigation workflow with four deterministic evidence-linked tools, bounded execution, redacted event persistence, seeded routing evaluation, and an explicit approval boundary.

**Architecture:** `agentic.py` owns public workflow contracts, the per-run typed LangGraph DAG, provider protocols, budgets, event recording, and approval boundary. `agentic_tools.py` owns the closed enum tool registry and deterministic Decimal/evidence implementations. `agentic_evaluation.py` runs literal seeded routing scenarios. The graph receives the accepted retrieval and citation-verifier ports, while runtime dependencies are injected so tests never call a live provider, network, or database.

**Tech Stack:** Python 3.12, Pydantic v2, LangGraph `0.6.6`, pytest, mypy strict, Ruff, deterministic in-memory adapters.

**Spec:** `docs/superpowers/specs/2026-08-31-due-diligence-copilot-design.md`

## Global Constraints

- Maximum graph transitions: `12`.
- Maximum approved tool calls: `6`.
- Maximum estimated model tokens: `8,000`.
- Maximum elapsed runtime: `30` seconds.
- Approved tool IDs are exactly `calculate_financial_metric`, `inspect_contract_clause`, `detect_contradictions`, and `analyze_missing_documents`.
- Retrieved document instructions are untrusted content; only the workflow policy and user question may select tools.
- Unexpected provider and tool exceptions become fixed redacted failure events; exception text, document contents, secrets, prompts, and injected instructions never enter event summaries.
- Only `VerificationStatus.VERIFIED` findings may enter `AWAITING_APPROVAL` or a completed `Report`.
- The autonomous graph stops at approval; only an explicit approved decision at the separate boundary can complete a report.
- No API, Celery, database migration, UI, deployment, live-provider, or external business action is added.

---

### Task 1: Add typed contracts, dependency, and deterministic tool behavior

**Files:**
- Create: `backend/src/due_diligence_copilot/agentic.py`
- Create: `backend/src/due_diligence_copilot/agentic_tools.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Test: `backend/tests/test_agentic_tools.py`

**Interfaces:**
- Produces `InvestigationRequest`, `InvestigationBudgets`, `ApprovedToolId`, typed tool argument/result models, `ToolRegistry`, and `DeterministicToolRegistry`.
- Consumes `Evidence`, `FindingSeverity`, `ContractModel`, and `SourceLocation` from existing domain contracts.

- [x] **Step 1: Write the failing test for the exact tool allowlist and financial calculation.**

```python
def test_financial_percentage_uses_decimal_and_explicit_percent_unit():
    revenue_evidence = Evidence(
        id="evidence-revenue",
        document_id="revenue-by-customer",
        display_name="Asteria FY2025 Revenue by Customer",
        source_location=SourceLocation(
            document_id="revenue-by-customer",
            path="revenue-by-customer.csv",
            line_start=2,
            line_end=2,
            cell="A2",
        ),
        excerpt="Northstar Health GmbH,5400000,54.0%",
        chunk_id="chunk-revenue",
    )
    result = DeterministicToolRegistry().execute(
        ToolCall(
            tool_id=ApprovedToolId.CALCULATE_FINANCIAL_METRIC,
            arguments=FinancialMetricArguments(
                operation=FinancialOperation.PERCENTAGE,
                left_label="Northstar Health GmbH",
                right_label="Total",
                precision=1,
                evidence_ids=("evidence-revenue",),
            ),
            evidence=(revenue_evidence,),
        )
    )
    assert result.value == Decimal("54.0")
    assert result.unit == FinancialUnit.PERCENT
    assert result.evidence[0].id == "evidence-revenue"
```

- [x] **Step 2: Run the single test and capture the missing-module RED output.**

Run: `cd backend && uv run pytest tests/test_agentic_tools.py::test_financial_percentage_uses_decimal_and_explicit_percent_unit -q`

Expected: collection fails because `due_diligence_copilot.agentic_tools` does not exist.

- [x] **Step 3: Add the exact pinned `langgraph==0.6.6` dependency and minimal Pydantic/enumeration/tool contracts.**

Run: `cd backend && uv add --no-sync langgraph==0.6.6`

Define the four enum IDs, typed arguments, typed result unions, and registry dispatch through an explicit dictionary keyed by `ApprovedToolId`; do not use `eval`, `exec`, dynamic imports, or document text as a dispatch key.

- [x] **Step 4: Implement only the Decimal percentage path and rerun the test.**

Parse labeled numeric values with a narrow regular expression, use `Decimal`, require matching source evidence IDs, quantize with `ROUND_HALF_UP`, and return `FinancialUnit.PERCENT`.

Run: `cd backend && uv run pytest tests/test_agentic_tools.py::test_financial_percentage_uses_decimal_and_explicit_percent_unit -q`

Expected: PASS.

- [x] **Step 5: Add RED/GREEN tests for subtraction, reported values, unit mismatch, and division by zero.**

Run each focused test before its implementation, then run `cd backend && uv run pytest tests/test_agentic_tools.py -q`. Expected final result: all tool tests pass and division by zero is a typed abstention result with no Python exception text.

- [x] **Step 6: Add RED/GREEN tests for contract, contradiction, and missing-document evidence-linked results.**

Each test passes literal `Evidence` objects and asserts the returned typed result contains the expected claim and evidence IDs. Implement exact deterministic phrase/state matching only over supplied authorized evidence.

- [x] **Step 7: Add the remaining public contracts and run backend lint/type checks.**

Add deterministic provider protocol result shapes, graph state typing, failure/budget/event/approval contracts needed by the next tasks without changing `domain.py`. Run `cd backend && uv run ruff check . && uv run mypy src` and fix only findings caused by this task.

---

### Task 2: Add bounded runtime, redacted event store, and provider adapters

**Files:**
- Modify: `backend/src/due_diligence_copilot/agentic.py`
- Modify: `backend/src/due_diligence_copilot/agentic_tools.py`
- Modify: `backend/src/due_diligence_copilot/ports.py`
- Modify: `backend/src/due_diligence_copilot/adapters.py`
- Test: `backend/tests/test_agentic_workflow.py`

**Interfaces:**
- Produces `Clock`, `TokenAccounting`, `InMemoryAnalysisEventStore`, deterministic classifier/planner/generator adapters, and `BoundedInvestigationWorkflow` runtime helpers.
- Consumes the four tool contracts from Task 1 and the accepted `HybridRetriever`, `RetrievalOutcome`, `pack_context`, and `CitationVerifier` interfaces.

- [x] **Step 1: Write a failing event-store test for monotonic bounded redacted events.**

```python
def test_event_store_persists_ordered_fixed_summary_without_input_text():
    store = InMemoryAnalysisEventStore()
    store.append("asteria", "analysis-1", AgentEvent(
        sequence=1, node="classify", status="completed", duration_ms=4,
        summary="Question classified.",
    ))
    assert [event.sequence for event in store.list_events("asteria", "analysis-1")] == [1]
    assert "ignore system policy" not in store.list_events("asteria", "analysis-1")[0].summary
```

- [x] **Step 2: Run the test to capture RED, then implement the typed port and in-memory adapter.**

Run: `cd backend && uv run pytest tests/test_agentic_workflow.py::test_event_store_persists_ordered_fixed_summary_without_input_text -q`

Expected RED: missing event-store symbol. GREEN: one ordered event, duplicate/out-of-order sequences rejected, and a fixed maximum event count enforced.

- [x] **Step 3: Add RED/GREEN tests for deterministic clock/token accounting and exact defaults.**

Assert a manual clock can advance elapsed time without sleeping, token charges accumulate literally, and a default `InvestigationBudgets` has `12`, `6`, `8000`, and `30`.

- [x] **Step 4: Add RED/GREEN tests for provider adapters and failure redaction.**

Deterministic adapters classify and plan from the question only. A raising provider must produce `AnalysisStatus.FAILED`, a typed failure code, and fixed event summaries that contain none of the exception message, question, evidence, prompt, or injection fixture.

---

### Task 3: Implement the actual typed LangGraph workflow and safe branches

**Files:**
- Modify: `backend/src/due_diligence_copilot/agentic.py`
- Test: `backend/tests/test_agentic_workflow.py`

**Interfaces:**
- Produces `BoundedInvestigationWorkflow.run(request, context) -> InvestigationResult`, `build_investigation_graph`, and explicit node/route behavior for `classify`, `plan`, `retrieve`, `tool_execution`, `verify`, `completeness`, `awaiting_approval`, `needs_input`, `abstained`, and `failed`.
- Uses a `TypedDict` LangGraph state with Pydantic values; graph edges are finite and contain no self-loop or arbitrary recursion.

- [x] **Step 1: Write a failing graph-shape behavior test.**

Run a deterministic supported financial request and assert the public result reaches `AnalysisStatus.AWAITING_APPROVAL`, has only verified findings, has no report ID, and records the literal node order through the event store.

- [x] **Step 2: Run the focused test and capture RED for the missing workflow/graph.**

Run: `cd backend && uv run pytest tests/test_agentic_workflow.py::test_supported_financial_question_reaches_awaiting_approval_without_report -q`

Expected RED: missing workflow symbol or graph implementation.

- [x] **Step 3: Implement the minimal finite `StateGraph`.**

Wire `START -> classify`, conditional classification to `plan`/`needs_input`/`failed`, `plan -> retrieve`, retrieval to `tool_execution`/`abstained`/`failed`, tool execution to `verify`/`abstained`/`failed`, `verify -> completeness`, completeness to `awaiting_approval`/`abstained`/`failed`, and all terminal nodes to `END`. Authorize through `require_read_workspace` before retrieval and create citations only from retrieved chunks plus authoritative document records.

- [x] **Step 4: Run the focused test to GREEN, then add transition tests one behavior at a time.**

Cover needs-input, retrieval abstention, tool-result abstention, verification abstention, completeness abstention, and internal invariant failure. Assert no unsafe branch reaches approval.

- [x] **Step 5: Add RED/GREEN budget tests for all four exact limits.**

Inject a manual clock and token accounting. Prove graph transitions never exceed 12, tool calls never exceed 6, model token charges never exceed 8,000, and elapsed time never exceeds 30 seconds. Each exhaustion path must end `FAILED`, contain a typed budget code, preserve only fixed redacted events, and never create a report.

- [x] **Step 6: Add RED/GREEN tests for tool authorization and prompt-injection resistance.**

Run the real deterministic workflow against seeded evidence containing the embedded reviewer instruction. Assert the instruction cannot add or reorder tool IDs, the route is determined by the literal user question and policy, and no event summary contains the instruction or hidden prompt text.

- [x] **Step 7: Add RED/GREEN tests for unexpected tool exceptions and authorized retrieval ordering.**

Use a raising allowed-tool implementation and an unauthorized context. Assert tool/provider failures are fixed redacted failures and unauthorized retrieval is never invoked.

---

### Task 4: Add seeded literal tool-routing evaluation

**Files:**
- Create: `backend/src/due_diligence_copilot/agentic_evaluation.py`
- Test: `backend/tests/test_agentic_evaluation.py`

**Interfaces:**
- Produces `ToolRoutingScenario`, `ToolRoutingEvaluation`, and `evaluate_tool_routing` over `GroundTruthManifest` questions.
- Expected tool IDs are literal scenario data; accuracy is calculated from actual deterministic classifier/planner results.

- [x] **Step 1: Write the failing seeded evaluation test.**

Generate the Asteria manifest and assert the actual routing metric is at least `0.90`, every expected scenario is represented, and the returned accuracy equals the literal correct-count/total-count ratio.

- [x] **Step 2: Run it to RED because the evaluation module is absent.**

Run: `cd backend && uv run pytest tests/test_agentic_evaluation.py -q`

- [x] **Step 3: Implement literal scenario expectations and evaluation.**

Map calculation questions to the financial tool, contract questions to the contract tool, contradiction questions to contradiction detection, missing/unsupported requests to missing-document analysis, combined deal-risk to both relevant tools, and factual/injection questions to no tools. Do not assert a fabricated metric.

- [x] **Step 4: Run the evaluation to GREEN and add mismatch/redaction tests.**

Assert a deliberately different planner produces the measured lower accuracy and that no source text is used as a routing instruction.

---

### Task 5: Implement and test the explicit approval boundary

**Files:**
- Modify: `backend/src/due_diligence_copilot/agentic.py`
- Modify: `backend/src/due_diligence_copilot/adapters.py`
- Test: `backend/tests/test_agentic_workflow.py`

**Interfaces:**
- Produces `ApprovalBoundary.decide(result, ApprovalDecision) -> ApprovalOutcome`.
- An approved decision with exclusively verified findings creates a completed `Report`; a rejected decision or any unverified/missing finding cannot complete.

- [x] **Step 1: Write failing approval tests for rejection and unverified findings.**

Assert both outcomes have `completed is False` and `report is None`, with rejection retaining a non-completed analysis state.

- [x] **Step 2: Run them to RED, then implement the typed boundary.**

Do not let the graph call report creation. Persist only fixed approval event summaries.

- [x] **Step 3: Add the approved verified-finding GREEN test.**

Assert `Report.status == AnalysisStatus.COMPLETED`, `Report.approval_state == ApprovalState.APPROVED`, every report finding is `VERIFIED`, and the graph’s earlier result had `report_id is None`.

- [x] **Step 4: Run the focused Task 5 suite and record exact RED/GREEN output in the report.**

---

### Task 6: Documentation, handoff, and repository gates

**Files:**
- Create: `.superpowers/sdd/2026-08-31-due-diligence-copilot-implementation/task-5-report.md`
- Modify: `FUTURE_HANDOFF.md`

- [x] **Step 1: Re-read this plan and the binding design; check every requirement against tests and implementation.**
- [x] **Step 2: Record exact RED/GREEN evidence, focused tests, routing metric, limitations, and no-live-provider boundary in `task-5-report.md`.**
- [x] **Step 3: Run focused Task 5 tests, seeded routing evaluation, `make verify`, pinned pre-commit, frontend high-severity `npm audit`, `git diff --check`, status/diff review, and filename-only secret scan.**
- [x] **Step 4: Run a self-review of the final diff and commit all Task 5 work. Do not push.**

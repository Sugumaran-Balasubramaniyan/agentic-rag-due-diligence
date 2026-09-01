# Task 5 report: bounded agentic investigation

## Plan text

## Task 5: Implement bounded agentic investigation

Implement the typed workflow and approved deterministic tools for financial
calculations, contract inspection, contradictions, and missing documents.
Enforce recursion, tool-call, time, and token budgets. Persist redacted events
and route only verified findings to approval/reporting.

Acceptance: tests cover every transition, budget exhaustion, provider/tool
failure, injected instructions, deterministic calculations, abstention, and
approval boundary; tool-routing target is met.

## Scope delivered

- Added the exact pinned `langgraph==0.6.6` runtime dependency and lock update.
- Added a real typed LangGraph DAG with the finite path
  `classify -> plan -> retrieve -> tool_execution -> verify -> completeness ->
  awaiting_approval`, plus typed `needs_input`, `abstained`, and `failed`
  outcomes. There are no graph cycles or arbitrary recursion.
- Added exact default budgets of 12 graph transitions, 6 tool calls, 8,000
  estimated model tokens, and 30 elapsed seconds. A deterministic manual clock
  and token-accounting port make every exhaustion path testable without sleep.
- Added the closed tool allowlist `calculate_financial_metric`,
  `inspect_contract_clause`, `detect_contradictions`, and
  `analyze_missing_documents`. Typed arguments must reference exactly the
  supplied authorized retrieved evidence.
- Added deterministic Decimal financial behavior with explicit units,
  `ROUND_HALF_UP`, and typed division-by-zero/unit-mismatch abstention. Contract,
  contradiction, and missing-document results carry their source evidence.
- Added classifier, planner, claim-generator, clock, token-accounting, tool, and
  event-store protocols with deterministic local adapters. Tests have no live
  provider, network, or database dependency.
- Added ordered, contiguous, maximum-32 fixed-summary analysis events behind
  `AnalysisEventStore` and `InMemoryAnalysisEventStore`. Provider, retrieval,
  tool, invariant, budget, and approval failures do not place exception text,
  questions, document contents, prompts, secrets, or injected instructions in
  events.
- Kept planning and tool selection isolated from retrieved text. The seeded
  prompt-injection document is retrieved only as untrusted evidence and cannot
  add or reorder tools.
- Added a separate typed `ApprovalBoundary`. The autonomous graph never creates
  a report. Only an explicit approved decision over nonempty exclusively
  verified findings can complete; rejection, unverified findings, non-awaiting
  states, or approval-event persistence failure cannot complete.
- Added literal tool-routing evaluation over all 14 seeded benchmark questions.

## TDD evidence

The initial tool test was RED because the module did not exist:

```text
$ uv run pytest tests/test_agentic_tools.py::test_financial_percentage_uses_decimal_and_explicit_percent_unit -q
E   ModuleNotFoundError: No module named 'due_diligence_copilot.agentic_tools'
```

The first Decimal parser implementation was also RED and exposed an overbroad
numeric parse:

```text
E   AssertionError: assert Decimal('540000054.0') == Decimal('54.0')
```

After narrowing parsing and grouping CSV cell evidence into rows, the financial,
contract, contradiction, and missing-document tool suite was GREEN.

The workflow test was initially RED because the controller module did not exist:

```text
E   ModuleNotFoundError: No module named 'due_diligence_copilot.agentic'
```

The literal routing evaluator was developed RED/GREEN:

```text
$ uv run pytest tests/test_agentic_evaluation.py -q
FF                                                                       [100%]
E   ModuleNotFoundError: No module named 'due_diligence_copilot.agentic_evaluation'

$ uv run pytest tests/test_agentic_evaluation.py -q
..                                                                       [100%]
```

Boundary RED/GREEN evidence found four controller gaps:

```text
# Zero is a valid fail-closed tool budget.
E   ValidationError: max_tool_calls: Input should be greater than 0

# A plan-node token exhaustion was overwritten by unconditional retrieval.
E   AssertionError: assert FailureCode.INTERNAL_INVARIANT == FailureCode.BUDGET_MODEL_TOKENS

# One verified finding incorrectly satisfied two successful tool results.
E   AssertionError: assert AnalysisStatus.AWAITING_APPROVAL == AnalysisStatus.ABSTAINED

# Approval-event persistence failure was swallowed before report creation.
E   AssertionError: assert True is False
E    + where True = ApprovalOutcome(...).completed
```

The minimal fixes allow zero-valued configured ceilings, route a failed plan
directly to the failed terminal, require one verified finding per successful
tool result at completeness, and require successful approval-event persistence
before consequential completion. Each focused regression passed after its
single production change.

Final focused Task 5 suite:

```text
$ timeout --signal=TERM 60s uv run pytest tests/test_agentic_tools.py tests/test_agentic_workflow.py tests/test_agentic_evaluation.py -q
.........................................                                [100%]
41 passed
```

The suite covers supported approval routing, needs-input, retrieval abstention,
tool abstention, verification abstention/failure, completeness abstention,
authorization-before-retrieval, retrieval/provider/tool/invariant failure,
all four budgets, deterministic calculations, prompt injection, event
redaction/order/bounds, evidence-derived tool arguments, and approval
approve/reject/unverified/persistence-failure outcomes.

## Literal routing metric

```text
$ uv run python [evaluate_tool_routing over build_manifest()]
tool_routing=14/14
accuracy=1.0000
target_met=True
```

Expected tool tuples are literal data keyed by seeded question ID. Accuracy is
computed from actual classifier/planner output; a deliberately no-tool planner
measures below 0.90, proving the metric is not a hard-coded success claim.

## Verification evidence

```text
$ make verify
All checks passed!
Success: no issues found in 20 source files
137 passed, 1 warning in 1.30s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed
```

The one warning is emitted while importing pinned LangGraph 0.6.6 from its
checkpoint serializer: `LangChainPendingDeprecationWarning` for a future
`allowed_objects` default. This task does not instantiate a checkpointer or
serializer, and the warning does not alter the deterministic graph behavior.

Closing repository gates:

```text
$ uvx --from pre-commit==4.3.0 pre-commit run --all-files
ruff (legacy alias): Passed
ruff format: Passed
prettier: Passed

$ npm audit --audit-level=high
found 0 vulnerabilities

$ git diff --check
[no output; exit 0]

$ git ls-files -co --exclude-standard | rg -i \
  '(^|/)(\.env$|.*(secret|credential|token|private.?key).*)'
[no matching filenames; exit 1 from rg]
```

## Self-review and boundaries

- Preserved `domain.py` and accepted Task 4 retrieval/citation contracts.
- Tool dispatch is an explicit enum-keyed dictionary; there is no `eval`,
  `exec`, dynamic import, arbitrary tool ID, or document-directed routing.
- Findings are created only after `CitationVerifier` accepts retrieved-only
  citations, and every finding entering approval is marked `VERIFIED`.
- Failure and abstention paths clear findings and report IDs. The graph cannot
  create a completed report.
- Scope excludes API endpoints, Celery, database migrations, UI, deployment,
  live provider quality, external messaging, source mutation, and business
  transactions.
- No push or subagent review was performed, as explicitly required for this
  sole-implementer task.

## Concerns

- LangGraph 0.6.6 emits the dependency warning described above. It is retained
  rather than globally suppressing a third-party compatibility signal.
- Durable database event persistence remains Task 6. Task 5 provides and tests
  the typed port plus deterministic in-memory implementation only.
- Independent review is intentionally absent under the no-subagents instruction;
  this report records a sole-implementer self-review.

## Fix round 1/5 evidence

The committed `aaf04d4` baseline was clean and had no active test/build process.
The first focused regression run was intentionally RED:

```text
$ timeout --signal=TERM 60s uv run pytest tests/test_agentic_fix_round1.py -q
13 failed, 2 passed, 1 warning
```

The failures were the approval bypass, missing event-store enforcement, lost
EUR unit, asymmetric unit cases, missing budget ceilings, incomplete routing
manifest validation, unchecked provider evidence, and unbounded provider
request output. The warning was the LangGraph checkpoint serializer pending
deprecation.

The fix adds exact enum approval validation and persistence failure handling,
stable tool-result IDs with completeness bijection, citation-derived verified
evidence, a typed Decimal calculation trace on findings and reports,
header-aware bounded CSV row context, symmetric units, global budget ceilings,
bounded/revalidated provider outputs, and exact literal routing-manifest
validation. `langchain-core==0.3.79` is pinned as the compatible exact
dependency; `langgraph==0.6.6` remains pinned and imports are warning-free.

Focused GREEN evidence:

```text
$ timeout --signal=TERM 60s uv run pytest -W error tests/test_agentic_fix_round1.py tests/test_agentic_tools.py tests/test_agentic_workflow.py tests/test_agentic_evaluation.py -q
60 passed
```

Full GREEN evidence:

```text
$ make verify
156 passed in 1.58s
frontend lint: passed
frontend type-check: passed
frontend test: 1 passed
frontend build: passed
```

The fix-round evaluation remains literal and deterministic: all 14 seeded
question IDs are required and the seeded routing result is 14/14 (1.0000).
Pinned pre-commit, frontend high-severity audit, diff check, and filename-only
secret scan are recorded for the closing run. Minor event-store defensive-copy
and timer hard-wall/start timing improvements remain deferred to a later task;
durable database persistence remains Task 6. This is a local fix-round
checkpoint and does not claim external acceptance or live-provider quality.


## Fix round 2/5 evidence

Started from committed `8b384fa`. The focused regression run was intentionally RED: `timeout --signal=TERM 90s uv run pytest -W error tests/test_agentic_fix_round2.py -q` reported `14 failed`. Failures covered forged approval provenance, provider-controlled contradiction claims, mutable budgets, nested provider output bounds, fixed planner accounting, and canonical routing-manifest mutation.

The fix adds workflow provenance authentication and independent finding/result/evidence checks, deterministic contradiction-result binding, construction snapshots and ledger-time budget validation, bounded/revalidated nested outputs with serialized-size token charging, and immutable canonical manifest fingerprints.

Focused GREEN: `timeout --signal=TERM 90s uv run pytest -W error tests/test_agentic_fix_round2.py tests/test_agentic_fix_round1.py tests/test_agentic_tools.py tests/test_agentic_workflow.py tests/test_agentic_evaluation.py -q` => `76 passed`; full warning-as-error suite => `172 passed`. `make verify` passed (`172 passed in 2.06s`, frontend lint/type-check/test/build passed); pinned pre-commit passed; frontend `npm audit --audit-level=high` found 0 vulnerabilities; literal routing evaluation was `scenarios=14 correct=14 accuracy=1.0000 target_met=True`.

Current imports produce zero warnings under `pytest -W error`; no warning suppression was added. Deferred minor concerns remain event-store defensive-copy semantics and timer start/hard-wall timing. Durable database persistence remains Task 6. This checkpoint does not claim external acceptance or live-provider quality.


## Fix round 3/5 evidence

Started from committed `d80df01`. The first round-3 focused regression run was intentionally RED:

```text
 --signal=TERM 90s uv run pytest -W error tests/test_agentic_fix_round3.py -q
3 failed, 6 passed
```

The failures exposed tool/result model confusion, duplicate finding IDs, and call/result evidence binding. The final fix enforces immutable approved-tool to result-class mapping, bounded and revalidated nested outputs, serialized tool-output accounting, primary-evidence constraints, canonical evidence fingerprints through approval provenance, validated verifier metrics, and injectable shared provenance keys.

Final GREEN evidence:

```text
 --signal=TERM 120s uv run pytest -W error tests/test_agentic_fix_round3.py tests/test_agentic_fix_round2.py tests/test_agentic_fix_round1.py tests/test_agentic_tools.py tests/test_agentic_workflow.py tests/test_agentic_evaluation.py -q
79 passed

 verify
181 passed in 1.92s
ruff and mypy: passed
frontend lint, type-check, test, and build: passed

 run python -c ...evaluate_tool_routing...
scenarios=14 correct=14 accuracy=1.0000 target_met=True

 --from pre-commit==4.3.0 pre-commit run --all-files
ruff, ruff format, prettier: Passed

 audit --audit-level=high
found 0 vulnerabilities
```

Warnings remain zero under `pytest -W error`; no suppression was added. The provenance key is injectable for shared deployments and defaults to a process-local key for the pre-Task-6 in-memory boundary; durable key management and database persistence remain Task 6. Event-store defensive copies and elapsed timer start/hard-wall timing remain deferred minor concerns. This is a local checkpoint and does not claim external acceptance or live-provider quality.

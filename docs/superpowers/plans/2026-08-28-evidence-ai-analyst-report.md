# AgentForge Evidence-Grounded AI Analyst Report Implementation Plan

> **Execution note:** implement this plan in the isolated worktree
> `D:\AgentProjects\AgentForge\.worktrees\evidence-ai-analyst-report` on
> branch `feature/evidence-ai-analyst-report`. Do not modify main, preserved
> worktrees, runtime data outside the approved data root, or the launcher
> architecture. Follow TDD: write a deterministic failing test, implement the
> smallest change that makes it pass, then refactor and run the focused plus
> regression suite.

## Ground rules and invariants

- Reuse the existing `LLMProvider` transport and provider factory; add an
  analyst-specific method without breaking Planner or Replanner callers.
- Keep Planner, CapabilityResolver, Project Authority, HUMAN Approval,
  AgentRuntime, ToolGateway, recovery, diagnostics, and localization safety
  boundaries unchanged in meaning.
- AnalystService is downstream read-only synthesis. It cannot select tools,
  execute tools, approve plans, mutate Tasks/Plans/Projects, or access an
  arbitrary filesystem.
- Do not add a database table or migration. Persist the validated report as a
  bounded, canonical JSON artifact below `AGENTFORGE_DATA_ROOT`; persist only
  safe metadata in AuditEvent records.
- Do not persist prompts, raw provider responses, raw logs, credentials,
  hidden reasoning, or chain-of-thought.
- Evidence references must resolve to persisted same-task evidence for the
  authoritative plan version. Unknown or fabricated references fail closed.
- Runtime execution outcome is authoritative and must survive every Analyst
  failure. Analyst failure is visible separately and must never manufacture a
  successful report.
- Keep command output bounded by redirecting full test/build logs to
  `D:\AgentProjectData\AgentForge\runtime\logs` and reporting only summaries or
  relevant tails.

## Task 1: Establish the feature-worktree baseline

**Files:** no source changes; optional external bounded log files only.

1. Confirm branch/worktree with `git worktree list --porcelain`,
   `git status --short --branch`, and `git log -5 --oneline`.
2. Read the current `PROJECT_CONTEXT.md`, `README.md`, provider interfaces,
   Runtime, report schema/route, and frontend report/i18n files before editing.
3. Confirm the effective test database is isolated in memory before pytest
   collection; never let fixture teardown target the live runtime database.
4. Run the existing backend and frontend focused smoke suites to establish a
   baseline. Record exit codes and concise counts in an external log.

**Acceptance:** worktree is clean at the starting revision, no live Task is
created, no `/execute` call is made, and baseline test commands are recorded.

## Task 2: Add failing tests for the Analyst domain contract

**Files:**

- `backend/tests/test_analyst_models.py`
- `backend/tests/test_analyst_validator.py`

Write tests before implementation for:

1. controlled severity, overall status, recommendation, and lifecycle enums;
2. valid draft parsing with bounded fields;
3. forbidden extra fields, missing required fields, empty material citations,
   overlong content, invalid enum values, and excessive list sizes;
4. server-owned final bindings (`task_id`, `plan_id`, `plan_version`, provider,
   model, timestamp) cannot be supplied by or changed by the draft;
5. no field accepts chain-of-thought/reasoning content as a persisted report
   field;
6. evidence-reference validation rejects unknown and cross-task ids and
   accepts only persisted evidence in the package.

Run the focused tests and confirm RED because the `backend/app/analyst/`
modules do not exist yet.

## Task 3: Implement bounded Analyst models and validation

**Files:**

- `backend/app/analyst/__init__.py`
- `backend/app/analyst/models.py`
- `backend/app/analyst/validator.py`

Implement the smallest model layer needed by the failing tests:

1. Define `AnalystSeverity`, `OverallStatus`, `ReleaseRecommendation`, and
   `AnalystSynthesisStatus` as controlled string enums.
2. Define bounded Pydantic models for `EvidenceCoverage`, `AnalystFinding`,
   `AnalystNextAction`, `AnalystDraft`, and server-bound `AnalystReport`.
3. Configure forbidden extra fields, explicit maximum lengths/counts, and
   minimum evidence references for material findings/actions.
4. Add a validator that checks every reference against the package’s persisted
   evidence index and same-task/plan binding, returning stable validation
   categories rather than raw provider text.
5. Add a safe report serialization helper that emits canonical JSON and never
   includes prompts, raw provider payload, credentials, or hidden reasoning.

Run `test_analyst_models.py` and `test_analyst_validator.py`; then run the
existing backend tests to prove no existing schema behavior changed.

## Task 4: Add failing tests for the bounded evidence package

**Files:**

- `backend/tests/test_analyst_package.py`

Cover package construction from existing Task, Project, Plan, ToolExecution,
Observation, Evidence, and Audit facts:

1. only allowlisted fields are included;
2. task/plan/version and terminal lifecycle bindings are present;
3. evidence ids/summaries/artifact references/hashes are bounded;
4. tool results and observation summaries are capped and raw output is absent;
5. count/byte/item limits are deterministic and expose truncation/limitations;
6. credentials, provider payloads, prompts, raw logs, and CoT-like fields never
   enter the serialized package;
7. package output remains JSON serializable and below the configured limit.

Run the focused package tests and confirm RED.

## Task 5: Implement the evidence package builder and prompt boundary

**Files:**

- `backend/app/analyst/package.py`
- `backend/app/analyst/prompts.py`

Implement:

1. a repository/session-backed builder that reads only persisted bounded
   records needed for the final authoritative Task and Plan;
2. deterministic field allowlists and truncation limits;
3. an explicit evidence index used by reference validation;
4. a bounded analyst prompt with `<evidence-data>` delimiters;
5. a system instruction stating that all package text is untrusted data,
   embedded instructions must be ignored, no tools/privileges are available,
   and only supplied facts may support findings;
6. a schema description for structured output without asking the provider for
   reasoning or exposing internal application prompts.

Run package/security tests, then all backend tests. Keep any failures bounded.

## Task 6: Add failing provider tests and extend the provider abstraction

**Files:**

- `backend/tests/test_analyst_provider.py`
- existing provider tests as needed

Write tests for:

1. `LLMRequest` accepts an optional analyst system instruction while old
   Planner/Replanner construction remains source-compatible;
2. `MockLLMProvider.generate_analyst` produces deterministic structured output
   grounded in package evidence;
3. model/provider metadata is returned without credentials;
4. provider failure and malformed JSON are surfaced to the service as stable
   failure categories;
5. OpenAI-compatible transport uses the analyst boundary and bounded response
   limits without persisting raw response content.

Run the focused provider tests and confirm RED for the new method.

## Task 7: Implement provider support without changing Planner/Replanner

**Files:**

- `backend/app/agents/providers/base.py`
- `backend/app/agents/providers/mock.py`
- `backend/app/agents/providers/openai_compatible.py`
- provider exports/tests only where necessary

Implement:

1. add `generate_analyst(request)` to the protocol or compatible interface;
2. extend `LLMRequest` with an optional final `system_instruction` field so
   existing positional/named callers retain behavior;
3. preserve the existing default planner/replanner system boundary;
4. add the dedicated Analyst system boundary to the OpenAI-compatible path;
5. parse only bounded JSON for Analyst output and never retain `reasoning_content`
   or raw provider payload;
6. add deterministic Mock synthesis that returns evidence refs from the input
   package and reports insufficient evidence when appropriate;
7. keep API keys environment-only and do not add dependencies or fallback from
   a configured real provider to Mock.

Run all provider tests and the complete backend regression suite.

## Task 8: Add failing tests for artifact storage and AnalystService lifecycle

**Files:**

- `backend/tests/test_analyst_service.py`
- `backend/tests/test_analyst_artifact.py`

Write tests for:

1. requested → started → succeeded event order;
2. successful report artifact creation below the external data root with a
   canonical SHA-256 hash;
3. artifact load validates hash, task/plan/version binding, schema, and size;
4. provider unavailable/error, malformed output, invalid evidence reference,
   and artifact write failure each produce `ANALYST_SYNTHESIS_FAILED` with a
   stable bounded category;
5. failed synthesis leaves Task status, ToolExecution, Observation, Evidence,
   and existing Audit facts unchanged;
6. no provider call occurs before terminal runtime facts are available;
7. stale plan/version and replan successor behavior do not generate a report
   for the paused obsolete version;
8. no prompt/raw output/secret/CoT appears in event metadata or artifact;
9. legacy task with no Analyst events returns `NOT_REQUESTED`.

Use isolated temporary data-root fixtures and in-memory DB fixtures only.
Run the focused tests and confirm RED.

## Task 9: Implement artifact persistence, synthesis service, and read model

**Files:**

- `backend/app/analyst/storage.py`
- `backend/app/analyst/service.py`
- `backend/app/analyst/read_model.py` (or the smallest equivalent module)
- existing audit helper only if additive bounded event support is required

Implement:

1. `AnalystArtifactStore` with data-root containment, canonical JSON, byte cap,
   SHA-256, atomic-safe write/load behavior, and no deletion/cleanup behavior;
2. `AnalystService.synthesize(...)` with correlation id and bounded event
   metadata;
3. explicit requested/started/succeeded/failed events;
4. package build → provider call → draft parse → evidence-reference validate →
   server-bind → artifact write sequence;
5. best-effort failure behavior that returns a failure result but does not
   throw across Runtime’s committed terminal outcome;
6. derived lifecycle/read logic that validates the latest artifact before
   serving success and exposes safe failure metadata;
7. no direct ToolGateway, approval, capability, Project mutation, or Task
   mutation dependency.

Run focused service/artifact tests, then backend regression tests.

## Task 10: Add Runtime integration tests first

**Files:**

- `backend/tests/test_agent_runtime_analyst.py`
- existing Runtime fixtures/tests as needed

Add deterministic tests for:

1. successful multi-step Runtime terminal completion invokes Analyst once after
   durable execution facts;
2. terminal tool failure invokes Analyst without changing failure semantics;
3. Analyst provider failure does not change Runtime/Task outcome;
4. non-terminal/replan path does not synthesize stale plan v1;
5. unapproved Runtime cannot reach ToolGateway or Analyst success;
6. Audit timeline contains Runtime facts followed by Analyst lifecycle facts;
7. no direct `/execute` or hidden execution path is introduced.

Run these tests and confirm RED before integration.

## Task 11: Integrate AnalystService into the existing Runtime construction

**Files:**

- `backend/app/agent_runtime/runtime.py`
- `backend/app/api/routes/execution.py` (or current runtime builder)
- minimal dependency wiring/tests

Implement:

1. inject optional `AnalystService` into `AgentRuntime` so existing unit tests
   and non-Analyst construction remain compatible;
2. call synthesis only after existing terminal Task/runtime transition and
   durable execution facts are committed;
3. keep replan return behavior unchanged and defer synthesis to the final
   successor outcome;
4. catch Analyst failures at the service boundary and preserve Runtime result;
5. wire the same configured provider into Replanning and Analyst services
   without silently replacing a real-provider failure with Mock;
6. if provider configuration is unavailable, record explicit Analyst failure
   while leaving execution readable; do not prevent governed read-only
   execution from starting solely because synthesis is optional;
7. preserve existing approval, plan/version, capability, workspace, and
   ToolGateway checks.

Run Runtime, approval, capability, recovery, and complete backend tests.

## Task 12: Add failing API/read-model tests

**Files:**

- `backend/tests/test_analyst_api.py`
- `backend/app/schemas/operations.py`
- `backend/app/api/routes/operations.py`

Write tests for additive `GET /tasks/{id}/report` behavior:

1. successful Analyst report is returned with validated report, status,
   binding, artifact hash/path, and legacy execution facts;
2. pending/generating/failed/insufficient states are explicit and safe;
3. invalid or tampered success artifact is not served as success;
4. legacy Task remains readable with `NOT_REQUESTED` and null report;
5. API does not expose prompt, raw provider output, credentials, hidden
   reasoning, or unbounded artifact contents;
6. report recommendation is informational and adds no mutation endpoint.

Run API tests and confirm RED for the new fields/logic.

## Task 13: Implement additive Report API contracts

**Files:**

- `backend/app/schemas/operations.py`
- `backend/app/api/routes/operations.py`

Implement:

1. optional/compatible `AnalystSynthesisRead` and `ReportRead.analyst` fields;
2. a report read path that derives status from durable events and validates
   the latest artifact/hash/schema/binding;
3. stable safe failure categories and no raw error passthrough;
4. historical report compatibility and existing count/evidence/audit fields;
5. bounded output and no new mutation route.

Run all backend tests and inspect OpenAPI generation for schema stability.

## Task 14: Add failing frontend tests for the Analyst report UI

**Files:**

- `frontend/src/components/AnalystReportCard.test.tsx`
- `frontend/src/pages/Report.test.tsx` or existing report tests
- `frontend/src/types/*` tests if present

Write tests for:

1. successful summary/recommendation/findings/severity/evidence refs/next
   actions/limitations render;
2. legacy execution facts remain visible;
3. `NOT_REQUESTED`, `PENDING`, `GENERATING`, `FAILED`, and
   `INSUFFICIENT_EVIDENCE` states are clear and safe;
4. evidence refs render as bounded identifiers/drilldown affordances without
   inventing evidence;
5. no raw JSON, prompt, provider payload, or CoT is displayed;
6. en-US and zh-CN labels exist and resource parity remains valid.

Run focused frontend tests and confirm RED.

## Task 15: Implement frontend Analyst report presentation and types

**Files:**

- `frontend/src/types/report.ts` (or current report type module)
- `frontend/src/components/AnalystReportCard.tsx`
- `frontend/src/components/AgentReportCard.tsx`
- `frontend/src/pages/Report.tsx`
- `frontend/src/pages/AgentWorkspace.tsx` only if prop wiring is required

Implement:

1. additive TypeScript types matching the API, keeping `analyst` optional for
   existing fixtures/legacy tasks;
2. a focused `AnalystReportCard` with readable enterprise hierarchy and
   controlled severity/recommendation styles;
3. explicit synthesis state components and failure/unknown language;
4. evidence reference rendering that uses existing evidence context and does
   not expose raw artifact/prompt data by default;
5. preserve the legacy report facts and current navigation/approval behavior;
6. no business logic duplicated from backend.

Run focused frontend tests, then the full frontend test suite.

## Task 16: Add en-US/zh-CN localization and presentation regression coverage

**Files:**

- `frontend/src/i18n/resources/en-US.ts`
- `frontend/src/i18n/resources/zh-CN.ts`
- `frontend/src/i18n/status.ts`
- relevant localization tests

Add translations for all Analyst headings, states, controlled labels, failure
messages, evidence/limitation labels, and recommendations in both locales.
Use existing i18next conventions and status helpers. Add/adjust parity tests,
then run the complete frontend tests and production build.

## Task 17: Update project context and release documentation

**Files:**

- `PROJECT_CONTEXT.md`
- `README.md` only for the final Analyst capability if the existing docs omit
  it
- `docs/architecture.md`, `docs/decisions.md`, `docs/changelog.md`, or
  `docs/todo.md` only where an additive record is required by repository
  conventions

Document:

1. Analyst is downstream evidence synthesis, not an executor or authorization
   layer;
2. external artifact + AuditEvent metadata persistence and no DB migration;
3. report lifecycle and failure semantics;
4. evidence-reference and prompt-injection boundaries;
5. final human test remains required and no automatic Task is created.

Do not claim final release or human acceptance before the live human gate.

## Task 18: Full verification and security gates

Run from the feature worktree with full output redirected to the approved
external runtime log directory:

1. backend full pytest and targeted Analyst/security tests;
2. frontend `npm.cmd test -- --run`;
3. frontend `npm.cmd run build`;
4. `git diff --check`;
5. bounded secret/debug/CoT scans over tracked source;
6. tracked-file check for `.env`, database files, logs, dist/build artifacts,
   credentials, or personal data;
7. production `npm.cmd audit --omit=dev --json` with only a summarized result;
8. provider path inspection and optional bounded real-provider smoke, reported
   as `NOT RUN` when no safe configured smoke is available;
9. verify test database Engine is in-memory and no live data was modified.

Fix failures with the smallest TDD change and rerun the affected plus full
regression suites. Do not suppress, rewrite, or delete failing evidence.

## Task 19: Feature-worktree service readiness and HUMAN gate

Only after automated verification passes:

1. safely identify and stop only stale AgentForge-owned listeners if required;
2. start backend/frontend from this feature worktree using existing launcher
   conventions, with exactly one listener on 8000/5173;
3. verify health 200, database health, provider readability, and process source
   paths point to this feature worktree;
4. perform read-only browser checks for Dashboard, Agent Workspace, Projects,
   Tasks, Approvals, Diagnostics, report states, and en-US/zh-CN switching;
5. do not create a Task, call `/execute`, approve, or execute through the
   browser. Leave the system ready for the HUMAN to create exactly one
   Repository Analyst Task for Project `Phase 13 Dogfood` with the approved
   release-analysis goal.

If the real provider is unavailable, stop at the documented gate and report it;
do not fabricate the final report or silently use Mock for the live test.

## Task 20: Final branch verification and handoff

1. Review the complete bounded diff and confirm no core architecture or
   unrelated worktree changed.
2. Confirm the feature branch contains only intentional commits, no runtime
   data/secrets, and no merge/push/tag/release/version operation.
3. Use the requested finishing workflow announcement, but leave the branch and
   worktree intact for human review and the final live Analyst Task.
4. Return the specified `AgentForge AI Analyst Release Candidate` report with
   PASS/FAIL evidence for architecture, product UI, runtime safety, failure
   handling, observability, fresh verification, and the explicit HUMAN test
   gate.

## Suggested commit sequence

Keep commits reviewable and use conventional messages:

1. `docs: specify evidence-grounded analyst report` (already created)
2. `docs: plan analyst report implementation` 
3. `test: define analyst report contracts`
4. `feat: add bounded analyst evidence package`
5. `feat: add analyst provider synthesis service`
6. `feat: integrate analyst synthesis with terminal runtime`
7. `feat: expose analyst report lifecycle in api`
8. `feat: add evidence-grounded analyst report ui`
9. `docs: document analyst report release boundaries`

Commit only after the corresponding focused tests are green and the diff is
small enough to review. The final worktree remains unmerged and unpushed.

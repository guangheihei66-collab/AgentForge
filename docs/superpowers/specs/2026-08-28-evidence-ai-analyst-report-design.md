# AgentForge Evidence-Grounded AI Analyst Report

## Status

Approved for implementation on the isolated feature worktree
`feature/evidence-ai-analyst-report`. This specification adds the final
product capability before release: a downstream AI Analyst that turns the
durable execution record into an actionable, evidence-grounded report.

The implementation must not modify the main branch, merge, push, tag, release,
or bump the product version.

## Purpose

AgentForge currently proves that a governed plan was approved and that tools
produced observations, evidence, and audit records. The final product surface
must help an operator answer the business question behind a run:

- What is the current project state?
- Is there a release blocker?
- What risks are supported by evidence?
- What should be done next, in priority order?
- Is release recommended?

The AI Analyst is a read-only synthesis stage after governed execution. It
does not become another executor, planner, policy engine, or source of truth.
The execution records remain authoritative; the Analyst report is a derived,
bounded interpretation that must link material findings to persisted evidence.

## Non-goals

This feature does not add multi-agent orchestration, RAG, MCP, local models,
new tools, write-capable tools, shell access, RBAC, SSO, LDAP, MFA, Docker,
PostgreSQL, a workflow canvas, a new planner architecture, or a new database
table. It does not alter approval semantics, Project authority, capability
resolution, ToolGateway behavior, Runtime state transitions, recovery, or
replanning policy.

## User experience

The existing Task Detail/Agent Workspace report surface gains an AI Analyst
section while preserving the legacy execution facts.

The section is ordered as:

1. AI Project Analysis and overall assessment.
2. Release recommendation with controlled status.
3. Key findings, each with controlled severity and evidence references.
4. Evidence drill-down links or identifiers.
5. Prioritized next actions.
6. Limitations and unknowns.
7. Synthesis state and provider metadata where safe.

The UI must distinguish `NOT_REQUESTED`, `PENDING`, `GENERATING`,
`SUCCEEDED`, and `FAILED`. A failed or unavailable synthesis must never hide
or replace the governed Task status, ToolExecution facts, Observations,
Evidence, or Audit history. Legacy Tasks with no Analyst artifact remain
readable and display an explicit neutral unavailable state rather than a
pretend report.

All new copy and controlled labels are available in en-US and zh-CN. No raw
provider response, prompt, chain-of-thought, secret, or unbounded log is
rendered by default.

## Architecture and data flow

```text
Approved Plan
    |
    v
AgentRuntime -> ToolGateway -> ToolExecution
    |                         |
    |                         v
    |                    Observation -> Evidence
    |                         |
    v                         v
Terminal Runtime facts -> bounded EvidencePackage
                              |
                              v
                       AnalystService
                              |
                              v
                       LLMProvider.generate_analyst
                              |
                              v
                     Draft schema validation
                              |
                              v
                  Evidence-reference validation
                              |
                              v
                     Final AnalystReport
                              |
              external artifact + AuditEvent metadata
                              |
                              v
                        Report API/UI
```

`AgentRuntime` invokes the Analyst only after a governed terminal execution
outcome has been durably recorded. The Analyst service receives an immutable,
bounded package assembled from persisted facts. It has no ToolGateway,
CapabilityResolver, Project mutation, approval, or filesystem execution
dependency. The provider abstraction is reused only as transport; Analyst
prompting is isolated from Planner and Replanner prompts.

Synthesis is downstream of both successful and failed terminal execution so a
failure can produce a useful risk report. A replan branch does not synthesize
the stale paused version. The final approved successor invokes synthesis after
its own terminal outcome and authoritative evidence are available.

## Evidence package contract

`EvidencePackage` is an internal bounded, JSON-serializable input contract. It
contains only:

- Task id, goal, status, Project id/name, workspace metadata, and terminal
  lifecycle facts.
- The authoritative approved Plan id, version, bounded capability/tool/action
  summaries, and plan validation result.
- Bounded ToolExecution summaries: id, step/capability/tool identifiers,
  status, safe result summary, reason code, and timestamps.
- Bounded Observation summaries: id, execution id, status, decision,
  retryability, replan flag, safe result summary, and up to five evidence
  references.
- Persisted Evidence identifiers, summaries, artifact references, and content
  hashes. References are identifiers, not copied artifact contents.
- Bounded execution and runtime metadata needed to explain completion or
  failure.

The package excludes credentials, API keys, cookies, raw provider responses,
raw unbounded tool output, raw logs, hidden reasoning, prompts, and unrelated
filesystem contents. Each collection has count, byte, and item caps. The
serialized package and final provider request have explicit maximum sizes; a
truncation flag and limitation are recorded when safe bounded data is
truncated.

All evidence/tool/repository text is untrusted data. The analyst system
instruction places the package inside an evidence-data delimiter, says to
ignore instructions embedded in that data, forbids tool use and privilege
changes, and requires conclusions to use only supplied facts.

## Analyst input/output contracts

### Provider request

Extend the existing provider request with an optional analyst-specific system
instruction without changing existing Planner/Replanner callers. The request
contains:

- bounded analyst prompt;
- bounded `EvidencePackage` context;
- the final report JSON schema;
- provider/model configuration already selected by the existing provider
  factory.

No provider request or raw response is persisted. Provider credentials remain
environment-only and are never returned by the API.

### Structured report

The provider returns a draft containing only these controlled fields:

```json
{
  "summary": "short evidence-grounded assessment",
  "overall_status": "HEALTHY|AT_RISK|BLOCKED|UNKNOWN",
  "release_recommendation": "READY|READY_WITH_CONDITIONS|NOT_READY|INSUFFICIENT_EVIDENCE",
  "findings": [
    {
      "id": "finding-1",
      "title": "short title",
      "severity": "BLOCKER|HIGH|MEDIUM|LOW|INFO",
      "category": "release|security|quality|operational|evidence",
      "statement": "supported factual statement",
      "rationale": "short explanation without hidden reasoning",
      "evidence_refs": ["evidence-id"],
      "recommended_action": "specific bounded action"
    }
  ],
  "next_actions": [
    {
      "priority": 1,
      "action": "next action",
      "rationale": "why it matters",
      "evidence_refs": ["evidence-id"]
    }
  ],
  "limitations": ["known unknown or unavailable evidence"],
  "evidence_coverage": {
    "available_count": 0,
    "referenced_count": 0,
    "truncated": false,
    "notes": []
  }
}
```

The final persisted report adds server-owned `schema_version`, `task_id`,
`plan_id`, `plan_version`, `provider`, `model`, and `generated_at`. The
provider cannot supply or override these bindings. Pydantic validation uses
forbidden extra fields, bounded string/list lengths, controlled enums, and
non-empty evidence references for material findings and actionable next
actions.

Every material factual finding must cite one or more Evidence ids that are
present in the package and persisted for the same task and authoritative plan
version. Unknown, fabricated, malformed, duplicate-invalid, or cross-task
references fail synthesis. The service does not turn an unsupported statement
into a citation by inference.

The report is a derived recommendation, not an authorization. `READY` never
approves a plan, starts execution, or changes Task status.

## Persistence and API

### Persistence choice

Use an external bounded JSON artifact under the approved external data root,
for example:

```text
D:\AgentProjectData\AgentForge\artifacts\<task-id>\analyst-report-v<plan-version>.json
```

The artifact writer resolves and verifies the final path remains under
`AGENTFORGE_DATA_ROOT`, enforces a size cap, writes canonical JSON, and stores
its SHA-256 hash. No report table or schema migration is introduced. AuditEvent
metadata stores the artifact path/hash and bounded report metadata, not the
full report, prompt, or provider response.

### Analyst lifecycle metadata

The service exposes a derived status:

`NOT_REQUESTED -> PENDING -> GENERATING -> SUCCEEDED|FAILED`

The status is read from the latest bounded Analyst AuditEvents and validated
artifact. A missing, unreadable, hash-mismatched, or schema-invalid success
artifact is reported as an explicit failure/unavailable state; stale success is
never served. The API may return a nullable `analyst` object on the existing
`GET /tasks/{id}/report` response, preserving all existing report fields.

The response includes safe status, report when valid, failure category when
failed, provider/model name when non-secret, plan id/version, artifact path or
hash where appropriate, and generation time. It does not expose raw artifact
errors, credentials, prompts, or provider payloads.

### Audit events

The service records these bounded events in order:

- `ANALYST_SYNTHESIS_REQUESTED`
- `ANALYST_SYNTHESIS_STARTED`
- `ANALYST_SYNTHESIS_SUCCEEDED`
- `ANALYST_SYNTHESIS_FAILED`

Each event includes task/plan/version binding, correlation id, actor/source,
timestamp, provider/model metadata where safe, evidence count/coverage, and a
short stage/failure category. Success includes artifact path/hash and report
status. Failure includes a stable category such as `PROVIDER_UNAVAILABLE`,
`PROVIDER_ERROR`, `MALFORMED_OUTPUT`, `INVALID_EVIDENCE_REFERENCE`,
`ARTIFACT_WRITE_FAILED`, or `INTERNAL_VALIDATION_ERROR`. Raw exception text,
provider output, prompts, and secrets are excluded.

## Lifecycle and failure semantics

The Analyst never owns Task success/failure. Runtime first persists the
terminal Task transition and runtime facts; then it requests synthesis. If
synthesis fails, the original execution outcome, ToolExecution, Observation,
Evidence, and Audit records remain intact, and the task does not become a
different status. The failure is visible as Analyst `FAILED` with a bounded
event and API state. A malformed response creates no report artifact and no
fake success. The provider is never allowed to call tools or mutate storage.

The service is best-effort from Runtime’s perspective: an analyst exception
must not roll back or mask a committed governed execution result. If a safe
retry is added later it must create a new bounded request/event sequence and
must not re-execute tools; retries are not required for this release.

Only terminal outcomes are eligible. `RUNNING`, `OBSERVING`, `REPLAN`, stale
plan versions, missing approval snapshots, and incomplete evidence do not
produce a final success report. Incomplete evidence can still yield a valid
`INSUFFICIENT_EVIDENCE` report if the runtime outcome is terminal and the
limitations explicitly describe the gap.

## Security and governance invariants

- HUMAN Approval remains the only approval authority.
- CapabilityResolver remains application-owned and fail-closed.
- Project Authority, workspace binding, plan version, capability/tool
  snapshots, and registry fingerprints remain unchanged.
- ToolGateway remains the only execution boundary.
- AnalystService has no execution tool, filesystem mutation, shell, approval,
  or direct database mutation API.
- Analyst evidence references are checked against persisted same-task facts.
- `READY` and all other report recommendations are informational only.
- No chain-of-thought is stored, displayed, or accepted as a report field.
- All provider output is treated as untrusted and schema-validated.

## Observability

The durable Audit timeline and existing Diagnostics surfaces remain the source
for proving what happened. New events expose requested/started/succeeded or
failed timing and correlation, evidence/package counts, artifact integrity,
and stable failure categories. Diagnostics may summarize Analyst state and
artifact availability but must remain bounded and must not expose prompts,
secrets, raw model output, or unbounded traces.

## Testing strategy

### Backend unit and integration coverage

- evidence package contains only allowed bounded fields;
- package caps and truncation are deterministic;
- valid draft parses and server-owned bindings are injected;
- extra fields, invalid enums, missing required fields, overlong content, and
  empty material citations are rejected;
- unknown, cross-task, stale-plan, and non-persisted evidence ids are rejected;
- prompt-injection text in evidence is treated as data and cannot add tools or
  privileges;
- mock provider returns a deterministic useful report without CoT;
- provider failures and malformed output produce explicit failed lifecycle
  events and preserve governed execution facts;
- artifact path containment, size bound, canonical hash, load, and tamper
  detection work;
- success and failed terminal Runtime paths request synthesis exactly once;
- replan does not synthesize stale versions;
- legacy Tasks remain readable with `NOT_REQUESTED`;
- report API returns valid success, pending/generating, failed, and invalid
  artifact states;
- existing approval, capability, ToolGateway, Project Authority, recovery,
  and plan/version tests continue to pass;
- no new DB table or migration is required.

### Frontend coverage

- successful report renders summary, recommendation, severity, citations,
  next actions, limitations, and legacy facts;
- pending/generating/failed/insufficient states are clear and safe;
- no-report legacy tasks remain readable;
- evidence references are visible and link/drill down to existing evidence
  context without inventing data;
- en-US and zh-CN resource parity and labels pass;
- existing Agent Workspace navigation and approval safety tests remain green.

### Verification

Run the isolated worktree’s full backend tests, frontend tests, production
build, targeted Analyst/security tests, `git diff --check`, bounded secret and
debug scans, and production `npm audit --omit=dev`. Real-provider synthesis is
optional and must be reported as not run if no safe configured provider smoke is
available. The final human live test uses exactly one newly created Repository
Analyst Task and the normal UI approval flow; no `/execute` call and no
automatic extra Task are permitted.

## Release acceptance criteria

The feature is branch-ready only when:

1. The feature branch is isolated from and does not modify main or preserved
   worktrees.
2. The spec and implementation plan are committed.
3. A deterministic Mock provider test produces a structured, evidence-linked
   report.
4. The real provider path reuses the existing abstraction without secrets or
   architectural bypasses.
5. Invalid or hallucinated evidence references are rejected.
6. Provider and validation failures preserve all execution facts.
7. Report API and Agent Workspace show the new analyst lifecycle without
   breaking historical Tasks.
8. Both locales are complete and no CoT/raw model output is persisted or
   displayed.
9. Full automated verification passes and output remains bounded.
10. The worktree is ready for the HUMAN final AI Analyst Task test, with no
    merge/push/tag/release/version operation performed.

# Real LLM Provider Design

## Goal

Phase 12 adds a real planning provider without granting the model execution
authority. A user may submit a natural-language goal and receive a validated,
capability-first plan from an OpenAI-compatible endpoint. Every accepted plan
continues through the existing governance path:

```text
User Goal
  -> LLM Provider
  -> PlanContract
  -> PlanValidator
  -> CapabilityRegistry
  -> CapabilityResolver
  -> Resolved Snapshot
  -> Approval
  -> AgentRuntime
  -> ToolGateway
```

This document specifies architecture only. It does not authorize production
code, external API calls, dependency changes, or runtime-data changes.

## Current Limitation

The repository already defines an `LLMProvider` protocol and a deterministic
`MockLLMProvider`, but the planning route directly constructs the mock. The
provider contract returns an untyped string or dictionary and has no standard
configuration, safe failure taxonomy, request metadata, or response metadata.
Consequently, AgentForge cannot deliberately select and operate a real model
while preserving a visible, testable provider boundary.

## Architectural Decision

Use one OpenAI-compatible provider implemented with the existing `httpx`
dependency. Do not add the OpenAI SDK and do not introduce a generic
multi-provider framework.

The provider selection is application-owned and fixed from environment
configuration before a planning task starts. The planning route obtains the
selected provider from a small provider factory. `mock` selects
`MockLLMProvider`; `openai-compatible` selects
`OpenAICompatibleProvider`. Selecting the real provider with missing or
invalid configuration fails closed. There is no silent fallback to mock.

The provider has no dependency on `ToolRegistry`, approval services,
`AgentRuntime`, executors, or `ToolGateway`. It returns untrusted planning data
only. `PlannerAgent` remains responsible for local validation, deterministic
capability resolution, persistence, and task-state transitions.

## Provider Boundary

The provider boundary has three implementations or collaborators:

- `LLMProvider`: protocol for one bounded plan-generation operation.
- `MockLLMProvider`: deterministic, offline implementation.
- `OpenAICompatibleProvider`: bounded HTTP implementation for an explicitly
  configured compatible endpoint.

The real provider sends only the bounded planner prompt and the schema needed
to describe a capability-first plan. It cannot receive a Base URL, model, API
key, workspace override, permission, concrete tool, or execution instruction
from a task request or model response.

Provider selection occurs once per application configuration. A plan records
which selected provider and model were used through safe audit metadata. A
task can never begin with the real provider and silently finish with mock.

## Provider Contracts

Use small immutable data contracts close to the existing provider package:

```text
LLMRequest
  prompt: str
  context: bounded mapping
  output_schema: mapping derived from PlanContract

LLMResponse
  payload: mapping
  provider: literal provider identifier
  model: str
  duration_ms: non-negative integer
  attempt_count: integer from 1 through 3
  input_tokens: optional non-negative integer
  output_tokens: optional non-negative integer

ProviderConfig
  provider: mock | openai-compatible
  base_url: validated URL for the real provider
  model: non-empty model identifier for the real provider
  api_key: secret value excluded from repr and serialization
  timeout_seconds: positive bounded value
  max_output_tokens: positive bounded value

ProviderError
  category: safe ProviderErrorCategory
  retryable: bool
  safe_message: bounded non-secret text
```

The protocol exposes exactly two bounded operations:

```text
generate_plan(request: LLMRequest) -> LLMResponse
test_connection() -> LLMResponse
```

Only `generate_plan` is available to `PlannerAgent`. `test_connection` uses a
fixed provider-owned prompt and a small non-plan JSON schema; its payload is
never passed to `PlanContract`, persisted as a plan, or made executable. Both
implementations support the operation: mock answers deterministically without
network access, while the real provider performs the explicit compatibility
check. The protocol does not expose chat, tool calling, streaming,
conversation history, embeddings, or arbitrary HTTP requests.

`ProviderError` must not retain or interpolate the API key, Authorization
header, raw upstream body, or raw upstream exception text. Its string form and
API mapping use only the safe category and bounded safe message.

## Configuration

Environment variables are the single source of provider configuration:

```text
AGENTFORGE_LLM_PROVIDER=mock
AGENTFORGE_LLM_BASE_URL=https://api.openai.com/v1
AGENTFORGE_LLM_MODEL=
AGENTFORGE_LLM_API_KEY=
AGENTFORGE_LLM_TIMEOUT_SECONDS=30
AGENTFORGE_LLM_MAX_OUTPUT_TOKENS=1200
```

Defaults are `mock`, 30 seconds, and 1200 output tokens. Temperature is not a
Phase 12 setting. Existing `PlanContract` continues to limit a plan to 20
steps, and the provider limits the complete HTTP response body to 64 KiB.

Configuration is loaded and validated in one provider configuration module.
The loader trims non-secret identifiers, rejects unknown providers, validates
numeric bounds, and requires Base URL, model, and API key when
`openai-compatible` is selected. It must not read provider selection from the
frontend or a planning payload.

The status API exposes provider identifier, configured state, model identifier,
`credential_configured`, connection status, and an optional safe failure
category. It never serializes `ProviderConfig` directly.

## Base URL Security

The Base URL is operator-owned startup configuration, never task data. Apply
these rules before constructing an HTTP client:

- Reject embedded username or password information.
- Reject query strings and fragments.
- Allow HTTPS endpoints on public or private networks.
- Allow plaintext HTTP only when the configured host is exactly `localhost`,
  `127.0.0.1`, or `::1`.
- Reject plaintext HTTP for all other hosts, including private-network IPs.
- Disable redirects.
- Use bounded connect, read, write, and pool timeouts.
- Append only the fixed OpenAI-compatible chat-completions path to the
  validated base path.

Allowing an HTTP loopback endpoint supports an operator-managed local proxy or
compatible service without permitting arbitrary insecure network targets.
Private-network services remain supported over HTTPS. Local models and model
downloads remain out of scope.

The endpoint is fixed before request handling. No value from user goals,
context, Planner output, model output, or frontend request bodies can alter the
scheme, host, port, path, DNS target, or redirect behavior. This prevents the
feature from becoming a user-controlled SSRF primitive.

## API Key Security

The MVP secret strategy is environment-variable injection. The API key is
never stored in SQLite, source files, audit events, frontend state, normal
logs, request/response logs, or client-visible exceptions.

`.env.example` may document `AGENTFORGE_LLM_API_KEY=` but must contain no real
value. Production operators should inject the value through the service
environment or host secret manager. A local ignored `.env` is a development
convenience, not a database-backed secret store.

The provider sends the key only in the upstream Authorization header. HTTP
diagnostics must not log headers or instantiate exceptions containing request
objects. Status surfaces expose only `credential_configured: true | false`.
They do not expose masked prefixes, suffixes, hashes, lengths, or key names.

## Planner Prompt Boundary

The planner prompt is assembled by application code from:

- the bounded user goal;
- the allowed capability IDs;
- concise capability descriptions;
- parameter names, required flags, and allowed values;
- the required `PlanContract` shape;
- an explicitly approved, bounded context summary.

Capability catalog data comes from `CapabilityRegistry`, so prompt guidance
and local authority use the same application-owned definitions. Prompt text
describes semantic capabilities, not candidate concrete tool IDs or executor
implementation details.

The prompt instructs the model to return JSON only, use no more than 20 steps,
select only listed capabilities and parameter values, and never include tool
IDs, commands, permissions, approval decisions, workspace changes, executable
paths, or arbitrary filesystem paths.

Do not include credentials, environment values, repository dumps, full file
contents, full audit history, raw evidence, ToolGateway internals, hidden
reasoning requests, or unrelated business data. Context remains subject to an
explicit size limit before it reaches the provider.

## Structured Output

Reuse the existing Phase 11.2 `PlanContract`; do not create a second plan
schema. Add one backward-compatible optional `summary` field with a default
empty string and a 500-character maximum. Existing persisted schema-version-2
plans without a summary remain readable. Provider-generated plans request a
concise summary.

The conceptual response is:

```json
{
  "schema_version": 2,
  "summary": "Check repository state and run the approved smoke profile.",
  "steps": [
    {
      "step_id": "step-1",
      "capability_id": "repository_state",
      "parameters": {}
    },
    {
      "step_id": "step-2",
      "capability_id": "test_verification",
      "parameters": {
        "profile": "smoke"
      }
    }
  ]
}
```

The OpenAI-compatible request supplies JSON-schema structured-output
instructions derived from `PlanContract`. Phase 12 treats support for this
request shape as part of endpoint compatibility; it does not add capability
negotiation or silently downgrade to an unconstrained mode.

`PlanContract` keeps `extra="forbid"`. Therefore `tool_id`, shell commands,
permissions, approvals, workspace overrides, arbitrary paths, and any other
unexpected top-level or step field are rejected. Known fields still pass
through `PlanValidator` and the capability parameter allowlists.

## Response Validation Pipeline

Treat every upstream response, including HTTP 200, as untrusted:

```text
HTTP status classification
  -> streamed body-size enforcement (64 KiB maximum)
  -> bounded JSON decoding
  -> extraction of the structured plan payload
  -> PlanContract validation
  -> PlanValidator workspace and forbidden-parameter validation
  -> CapabilityRegistry validation
  -> CapabilityResolver resolution
  -> resolved plan persistence
  -> human approval
```

No plan record with `VALID` status is created until the full local validation
and resolution chain passes. No planning failure can reach approval,
`AgentRuntime`, or `ToolGateway`.

The provider never returns an already trusted `PlanContract`; `LLMResponse`
contains a mapping that `PlannerAgent` must validate locally. The application
does not persist the raw upstream envelope or raw model text.

## Failure Model

Use these safe provider error categories:

| Category | Trigger | Retry |
| --- | --- | --- |
| `NOT_CONFIGURED` | selected provider has missing or invalid configuration | no |
| `AUTHENTICATION_FAILED` | HTTP 401 or 403 | no |
| `RATE_LIMITED` | HTTP 429 | yes, bounded |
| `TIMEOUT` | bounded HTTP timeout | yes, bounded |
| `NETWORK_ERROR` | transient connect or transport failure | yes, bounded |
| `UPSTREAM_SERVER_ERROR` | HTTP 5xx | yes, bounded |
| `INVALID_RESPONSE` | deterministic 4xx, incompatible envelope, malformed JSON, or schema-invalid payload | no |
| `RESPONSE_TOO_LARGE` | response exceeds 64 KiB | no |

HTTP 408 is treated as a retryable timeout class. Other deterministic 4xx
responses are non-retryable `INVALID_RESPONSE`. Raw upstream bodies and
headers are discarded from public errors and audit payloads.

After provider retries are exhausted, or after any local plan, capability, or
resolution validation fails, `PlannerAgent` transitions the task from
`PLANNING` to the existing `FAILED` state with a bounded safe reason. It
records no valid plan and creates no approval. If audit persistence itself
fails, the transaction fails closed rather than allowing the plan onward.

## Retry Policy

Allow at most three total attempts: one initial attempt plus two retries.
Retry only transient network failures, timeouts, HTTP 408, HTTP 429, and HTTP
5xx responses.

Use delays of 0.5 seconds and 1.5 seconds. A valid `Retry-After` value may
replace the next delay but is capped at 5 seconds. Retry waiting is bounded by
the request lifecycle and never runs in an unbounded background loop.

Do not retry authentication failures, deterministic 4xx responses, oversized
responses, malformed JSON, schema-invalid output, capability-invalid output,
permission rejection, policy rejection, or resolver failure. Phase 12 has no
model self-repair loop and never switches providers during retry.

## Mock Provider

Keep `MockLLMProvider` as the deterministic implementation for tests, CI,
offline development, and demos explicitly configured with
`AGENTFORGE_LLM_PROVIDER=mock` or using the pre-task default.

Mock and real providers conform to the same `LLMRequest` and `LLMResponse`
contract. Mock returns a stable capability-first payload and safe metadata
without using the network. It is not an automatic rescue path for a real
provider failure or invalid configuration.

## Operator Experience

Add one small read-only provider-status surface showing:

- provider: `mock` or `openai-compatible`;
- configured: yes or no;
- model identifier;
- credential configured: yes or no;
- connection status: `not tested`, `success`, or `failed`;
- safe failure category when applicable.

Do not add Base URL editing, API-key entry, secret editing, generic provider
CRUD, raw response views, or an enterprise settings portal. Provider
configuration changes require an operator-controlled environment update and
application restart.

Connection status is process-local operational state. It resets to
`not tested` at startup and is not stored in SQLite. This preserves the no
schema-change decision and avoids treating transient connectivity as durable
business data.

## Connection Test

Connection testing is an explicit operator action exposed through one bounded
endpoint and a small UI control. It uses the selected provider configuration,
a fixed non-business prompt, the smallest practical output-token budget, no
project source, no task goal, no audit history, and no secret context.

The test calls the selected provider's bounded `test_connection` operation and
expects a fixed non-plan JSON acknowledgement. It verifies configuration,
authentication, basic HTTP compatibility, bounded response handling, and
structured JSON support. It does not create a task or candidate execution
plan, write an approval, invoke the resolver, execute tools, or call
`AgentRuntime` or `ToolGateway`.

The result updates only process-local status with timestamp, success/failure,
duration, and safe error category. Because existing `AuditEventRecord` requires
a task ID, Phase 12 does not manufacture a task or change the database schema
to audit a connection test. Normal bounded application logs may record only
the safe category and duration, never headers, body, prompt, or exception text.

## Audit and Observability

Use existing task-bound `AuditEventRecord` infrastructure for real planning:

- `LLM_PLAN_REQUESTED`: provider, model, and attempt policy.
- `LLM_PLAN_SUCCEEDED`: provider, model, duration, attempt count, optional
  token usage, and validation outcome.
- `LLM_PLAN_FAILED`: provider, model, duration, attempt count, safe error
  category, and validation stage.

Events use bounded structured JSON in `payload_summary` and the repository's
existing correlation-ID convention. Provider success means the provider
returned a bounded candidate; the audit event must separately state whether
local `PlanContract`, `PlanValidator`, and capability resolution succeeded.

Never audit the API key, Authorization header, Base URL credentials, full
prompt, raw response, model reasoning, raw exception, or unnecessary user
context. Token usage is recorded only when supplied as non-negative numeric
metadata; it is never inferred by logging content.

## Low-Overhead Test Strategy

Prefer one coherent feature file:

`backend/tests/test_phase_12_real_llm_provider.py`

Use `httpx.MockTransport` or an injected equivalent transport. Automated tests
must never call a real network endpoint. Deterministic cases cover:

1. Default mock selection and deterministic output.
2. Valid real-provider configuration and all missing/invalid fields.
3. No silent fallback from a selected real provider.
4. Successful structured response and provider-to-validator-to-resolver flow.
5. Malformed JSON and incompatible envelopes.
6. Response larger than 64 KiB.
7. Timeout, network failure, 401, 403, 408, 429, deterministic 4xx, and 5xx.
8. Three-attempt maximum, exact retry classes, delays, and capped
   `Retry-After` behavior without real sleeping.
9. No retry for authentication or validation failures.
10. Rejection of `tool_id`, arbitrary commands, unknown capabilities, invalid
    parameters, empty plans, and plans over 20 steps.
11. Safe audit metadata and absence of secrets in logs, errors, audit, API
    responses, and object representations.
12. Failed planning transitions to `FAILED` before approval or execution.
13. Explicit, isolated connection-test behavior.
14. Existing mock, Planner, Phase 11.2, and Runtime behavior remains
    deterministic.

Add only small frontend tests for provider-status rendering and an explicitly
triggered connection test. Run focused Phase 12 tests during development and
the full regression suite only near implementation completion. Keep command
output bounded.

## Persistence Impact

Phase 12 requires no database schema change. Provider configuration and API
credentials remain environment-based. Connection-test status remains
process-local. Existing plan JSON stores the locally validated optional
summary and capability-first steps; existing `AuditEventRecord` stores bounded
task-bound provider metadata.

Do not add provider, credential, connection-status, request, response, or token
usage tables. Do not store the API key or raw provider traffic in SQLite.

## Security Properties

- The model proposes capability requirements but receives no execution
  authority.
- Provider selection and endpoint configuration are operator-owned and cannot
  be changed by task or frontend input.
- A selected but invalid real provider fails closed with no mock fallback.
- The API key is environment-injected and never persisted or exposed.
- Redirects are disabled and all HTTP dimensions are bounded.
- Provider output remains untrusted until the complete local validation and
  deterministic resolution chain succeeds.
- Extra fields, concrete tool selection, commands, permissions, approvals,
  workspace overrides, and arbitrary paths are rejected.
- Human approval and the existing snapshot binding remain mandatory.
- `AgentRuntime` still executes only approved snapshots through ToolGateway.
- Retries, response size, plan size, prompt context, token output, and audit
  payloads are bounded.
- Normal tests remain deterministic and network-free.

## Out of Scope

- OpenAI SDK adoption or provider-specific SDK models.
- Generic multi-provider registries, capability negotiation, or provider CRUD.
- Streaming, chat history, tool calling, function execution, embeddings, RAG,
  MCP, Multi-Agent behavior, or model self-repair.
- Local model installation, model downloads, Docker, or GPU orchestration.
- API-key editing or encrypted credential storage in the UI or database.
- User-controlled endpoints, dynamic Base URLs, or redirect following.
- Arbitrary shell commands, filesystem writes, new permissions, or ToolGateway
  changes.
- Database migrations or provider configuration tables.
- Production code, implementation planning, external calls, or dependency
  installation during this specification task.

## Expected Files Affected

Future implementation is expected to affect only existing ownership areas and
a few focused additions:

- `backend/app/agents/providers/base.py`
- `backend/app/agents/providers/mock.py`
- `backend/app/agents/providers/openai_compatible.py`
- `backend/app/agents/providers/config.py`
- `backend/app/agents/providers/__init__.py`
- `backend/app/agents/planner/planner.py`
- `backend/app/agents/planner/prompts.py`
- `backend/app/agents/planner/schemas.py`
- `backend/app/api/routes/planning.py`
- one focused provider-status route and API schema under existing directories
- `backend/tests/test_phase_12_real_llm_provider.py`
- small existing frontend API, type, status-view, and test files
- `.env.example`, `PROJECT_CONTEXT.md`, and focused deployment documentation

`httpx` is already present, so `backend/requirements.txt` should not change.
`ToolGateway`, approval persistence, AgentRuntime execution semantics, and the
database schema should not change. No new top-level repository directory is
required.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Compatible endpoint does not support the required structured-output request | Connection test fails safely; do not downgrade or accept unvalidated text |
| Prompt injection requests tools, commands, or secrets | Send a bounded capability catalog and reject output through strict local schemas and allowlists |
| HTTP 200 contains malformed or hostile content | Enforce body size, parse locally, and run the full validation and resolution chain |
| Real-provider configuration is incomplete | Return `NOT_CONFIGURED`; never fall back to mock |
| Base URL becomes an SSRF vector | Accept it only from validated startup configuration; disable redirects and prohibit insecure non-loopback HTTP |
| Provider diagnostics leak credentials or response content | Use safe error categories and metadata-only audit/logging |
| Retries amplify cost or latency | Three attempts maximum, narrow retry classes, and bounded delays |
| Planning failure leaves a task in an ambiguous state | Transition `PLANNING` to existing `FAILED` with a bounded safe reason |
| Transient connection state drives a schema change | Keep it process-local and reset it at startup |
| Phase 12 grows into a settings platform | Limit UI to status and explicit connection test; keep configuration environment-owned |

## Future Evolution

A later, separately approved phase may add provider adapters, host secret-manager
integration, encrypted credentials, asynchronous planning jobs, richer usage
metrics, or compatibility capability negotiation. Any evolution must preserve
explicit provider selection, fail-closed local validation, application-owned
capability resolution, approval-bound snapshots, and ToolGateway as the only
execution boundary.

Adding non-loopback plaintext endpoints, dynamic per-task providers, model tool
calling, schema-repair loops, or database-backed credentials requires a new
security design rather than an incremental Phase 12 configuration flag.

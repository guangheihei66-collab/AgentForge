# Structured Output Capability Design

## 1. Problem Statement

The OpenAI-compatible provider currently always sends strict `json_schema` structured output. Real OpenAI-compatible services do not necessarily implement the same structured-output capabilities. A provider may accept `json_object` while rejecting `json_schema`, even though both use the same Chat Completions shape.

The solution must support explicit provider capability selection without vendor URL detection, silent fallback, or weakening AgentForge's local safety and contract validation.

## 2. Confirmed Evidence

- The current provider always sends `response_format.type = json_schema` with `strict: true` and the supplied schema.
- A bounded external probe using the configured real provider succeeded with `response_format.type = json_object` and returned `{"status":"ok"}`.
- Provider response extraction already rejects malformed JSON, non-object payloads, malformed envelopes, oversized responses, and unsafe upstream failures.
- `PlannerAgent` passes provider output through `PlanValidator`, which parses JSON and validates `PlanContract` with Pydantic before capability resolution or persistence.
- `ReplanningService` validates `ReplanProposal` with Pydantic and then reuses `PlanValidator` before resolving successor steps.
- Test Connection already calls the provider's shared `test_connection` path, which uses the same `_complete` transport path as planning and replanning.

No real provider call or credential inspection is part of this design phase.

## 3. Goals / Non-Goals

Goals:

- Preserve strict `json_schema` requests for providers that support them.
- Add explicit `json_object` request encoding for compatible providers.
- Keep local deterministic validation authoritative in all modes.
- Reject unknown modes during configuration and never silently switch modes after an upstream error.
- Make Test Connection use the configured mode and expose the active mode safely in provider status.

Non-goals:

- No vendor-name or URL detection.
- No provider marketplace, discovery, fallback chain, routing, benchmarking, UI redesign, secret persistence, or database changes.
- No new JSON Schema dependency unless implementation evidence proves the existing Pydantic contracts insufficient.

## 4. Current Architecture

`ProviderConfig` is built from environment variables and passed to `OpenAICompatibleProvider`. The provider's `_complete` method creates the bounded authenticated request, retries only classified transient failures, extracts a JSON object, and returns `LLMResponse`.

The planner owns plan-specific validation through `PlanValidator`. Replanning owns proposal validation through `ReplanProposal` and then uses the same plan validator for workspace and forbidden-parameter checks. The provider status route reads a safe `ProviderConfig` projection, while Test Connection invokes `provider.test_connection()`.

## 5. Proposed StructuredOutputMode Model

Add a small closed model, preferably a `StrEnum` named `StructuredOutputMode`, with exactly:

- `JSON_SCHEMA = "json_schema"`
- `JSON_OBJECT = "json_object"`

`ProviderConfig` stores the parsed mode. The parser accepts only these values and marks configuration invalid for any other value. The mode is a capability selection, not a claim that upstream schema enforcement exists.

## 6. Configuration Semantics

Use the existing environment-owned configuration convention with:

`AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE`

For backward compatibility, an absent or empty value resolves to `json_schema`. Unknown or malformed values make the configuration fail closed as `NOT_CONFIGURED`; they do not fall back to either supported mode.

The mode is carried in `ProviderConfig` and is safe to expose. API keys and other credentials remain redacted and are never included in status or errors.

## 7. json_schema Request Path

When the configured mode is `json_schema`, `_complete` sends the existing request shape unchanged:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "...",
      "strict": true,
      "schema": {"...": "..."}
    }
  }
}
```

Existing strict behavior and tests remain the compatibility baseline.

## 8. json_object Request Path

When the configured mode is `json_object`, `_complete` sends only:

```json
{"response_format": {"type": "json_object"}}
```

The application schema is not represented as upstream-enforced `json_schema` in this mode. The system prompt may continue to require a JSON object, but prompt wording is not treated as validation or authorization.

## 9. Local Contract/Schema Validation Boundary

Recommend option A: provider configuration controls request encoding while existing application validators remain authoritative.

Option A has no duplicated contract logic, preserves planner/replanner-specific security checks, adds no dependency, and makes provider transport reusable for future contracts. The provider still performs the necessary generic extraction checks: valid envelope, valid JSON, and object payload. The planner and replanner then perform their existing contract and policy validation before any persistence, resolution, approval, or execution.

Option B—generic schema validation inside the provider after extraction—would centralize some checks, but would duplicate Pydantic contract validation, couple the provider to application schemas, complicate replan-specific validation, and provide little additional security. It is rejected for this phase.

## 10. Test Connection Behavior

Test Connection continues to call `provider.test_connection()`, which calls `_complete` and therefore uses the configured mode. In `json_object` mode, the provider sends a JSON-object request and locally requires the parsed payload to equal `{"status": "ok"}`. In either mode, malformed or semantically invalid acknowledgement fails with `INVALID_RESPONSE`.

There must be no separate compatibility-only transport path and no mode retry after an upstream failure.

## 11. Planner Behavior

Planner requests carry `PlanContract.model_json_schema()` for `json_schema` encoding and the same logical contract metadata for `json_object` prompt/context construction. Regardless of mode, the returned payload enters `PlanValidator`, which rejects malformed JSON, non-object values, Pydantic contract violations, invalid workspaces, forbidden parameters, and any other existing policy violation before capability resolution or persistence.

## 12. Replanner Behavior

Replanning requests use `ReplanProposal.model_json_schema()` for `json_schema` encoding and the same logical proposal contract for `json_object` prompting. The returned payload is validated by `ReplanProposal.model_validate`, bounded by the remaining-step policy, converted through `PlanValidator`, and checked for duplicate/no-progress fingerprints before successor persistence. No approval, project authority, capability resolution, or replanning budget semantics change.

## 13. Provider Status/API Visibility

Extend the safe provider status response with `structured_output_mode`, using the configured mode value. This lets operators see the active compatibility choice without exposing the API key, endpoint credentials, or raw provider output. Existing status and connection failure categories remain unchanged.

## 14. Error Taxonomy / Fail-Closed Behavior

- Unknown mode or invalid configuration: `NOT_CONFIGURED`.
- HTTP/upstream rejection of the explicitly selected mode: existing classified provider error; no alternate mode attempt.
- Oversized response: `RESPONSE_TOO_LARGE`.
- Malformed envelope, malformed JSON, or non-object payload: `INVALID_RESPONSE`.
- Structurally invalid plan or replan: existing application validation failure mapped to `INVALID_RESPONSE`.
- Invalid Test Connection acknowledgement: `INVALID_RESPONSE`.

Errors remain safe-category based and must not retain secrets, raw provider output, or chain-of-thought content.

## 15. Backward Compatibility

Missing `AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE` defaults to `json_schema`, preserving current requests and existing provider behavior. Existing mock provider behavior is unchanged. Existing persisted plans, approvals, project authority, and replanning lineage require no migration.

## 16. Security Considerations

The change does not grant provider output authority. All payloads remain untrusted until application validation, capability resolution, project authority checks, approval binding, and ToolGateway enforcement succeed. Existing retry bounds, response limits, safe errors, secret redaction, no-chain-of-thought storage, and controlled replanning limits remain unchanged.

## 17. Tests Required

Implementation must add or update focused offline tests for:

- default mode is `json_schema`;
- explicit `json_schema` request shape remains strict;
- explicit `json_object` request shape contains only the JSON-object format;
- unknown mode fails configuration closed;
- malformed JSON and non-object provider output fail closed in both modes;
- invalid `PlanContract` and invalid `ReplanProposal` remain rejected in `json_object` mode;
- Test Connection uses the selected mode and rejects invalid acknowledgement;
- provider status exposes the mode but never credential material;
- existing Phase 12 and Phase 13 behavior remains valid.

All tests use mocked transport or deterministic providers. No real API key or live provider call is required.

## 18. Migration/Configuration Impact

No database migration and no persisted-data migration are required. Operators that need compatibility mode add the environment variable to their existing local configuration:

`AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE=json_object`

Existing deployments need no change because the default remains `json_schema`.

## 19. Exact Files Expected to Change During Implementation

- `backend/app/agents/providers/base.py` — add the closed mode type if placed at the provider boundary.
- `backend/app/agents/providers/config.py` — parse, validate, and default the environment setting.
- `backend/app/agents/providers/openai_compatible.py` — encode the selected request format.
- `backend/app/schemas/provider.py` — expose the safe mode field.
- `backend/app/api/routes/providers.py` — populate mode in status.
- `backend/tests/test_phase_12_real_llm_provider.py` — focused provider/config/status tests.
- `backend/tests/test_phase_13_controlled_replanning.py` — focused json_object replan validation coverage if not isolated in a new provider test module.

Planner, replanner, database, approval, project, and ToolGateway production files should not change unless implementation uncovers a concrete validation gap.

## 20. Risks / Rejected Alternatives

Risk: `json_object` providers may return plausible but contract-invalid JSON. Mitigation: existing local validators remain mandatory before resolution and persistence.

Risk: operators may select an unsupported mode. Mitigation: explicit closed-value configuration validation and safe status visibility.

Rejected alternatives:

- Globally replacing `json_schema` with `json_object`, because it regresses providers that support strict schemas.
- Detecting DeepSeek or another vendor from URL, because it creates brittle vendor switches and does not express capability truth.
- Silently retrying with another mode, because it hides configuration and provider capability failures.
- Generic provider-level schema validation, because it duplicates and couples application contracts without improving the existing validation boundary.

## 21. Acceptance Criteria

The implementation is accepted only when:

1. Existing `json_schema` behavior and tests pass unchanged or with intentional, equivalent assertions.
2. Explicit `json_object` mode emits a JSON-object request.
3. AgentForge locally validates returned plan and replan payloads in `json_object` mode.
4. Malformed JSON, non-object payloads, and contract-invalid payloads fail closed.
5. Unknown mode fails configuration validation.
6. Test Connection uses the configured mode and validates its acknowledgement.
7. Provider status safely reports the active mode without credentials.
8. No silent mode fallback exists.
9. Phase 12 provider and Phase 13 replanning controls remain valid.
10. Phase 14 project authority and approval semantics remain untouched.
11. A real provider can later be configured with `json_object` without a code-level vendor special case.

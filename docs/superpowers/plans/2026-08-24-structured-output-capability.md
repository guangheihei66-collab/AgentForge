# Structured Output Capability Implementation Plan

## Scope and execution rules

Implement the approved provider-capability design in small, reviewable commits on `feature/phase-12-real-llm-provider`. Do not change frontend, database schema, task/approval persistence, project authority, ToolGateway, or provider secrets. Do not add dependencies. Do not call a real provider until all automated tests pass.

Each task follows: RED test first, verify the expected failure, minimal GREEN implementation, focused verification, then one coherent commit. The existing Planner and Replanner validators remain the authoritative application boundary.

## Task 1 — Add the closed structured-output mode to provider configuration

Files to modify:

- `backend/app/agents/providers/base.py`
- `backend/app/agents/providers/config.py`
- `backend/tests/test_phase_12_real_llm_provider.py`

RED:

1. Add tests that load the existing real-provider fixture with no mode and assert the mode is `json_schema`.
2. Add a parametrized test for explicit `json_schema` and `json_object` values.
3. Add a test that an unknown value causes `load_provider_config`/provider construction to fail with `ProviderErrorCategory.NOT_CONFIGURED`, without exposing the raw value or any credential.
4. Run from `backend` using the existing project virtual environment:

   `python -m pytest tests/test_phase_12_real_llm_provider.py -q`

Expected RED: `ProviderConfig` has no mode field and unknown mode is currently ignored.

Minimal GREEN:

1. Define `StructuredOutputMode(StrEnum)` with exactly `JSON_SCHEMA = "json_schema"` and `JSON_OBJECT = "json_object"` in the provider boundary.
2. Add a frozen `structured_output_mode` field to `ProviderConfig`.
3. Parse `AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE` in `load_provider_config`, treating missing or empty as `json_schema`.
4. Reject values outside the enum as configuration invalid/`NOT_CONFIGURED`; do not guess or fall back after an explicitly invalid value.
5. Keep mock provider behavior and credential redaction unchanged.

Expected GREEN: default and explicit modes load correctly; unknown modes fail closed; existing configuration tests remain green.

Commit boundary: `feat: add structured output mode configuration`

## Task 2 — Encode provider requests according to the selected mode

Files to modify:

- `backend/app/agents/providers/openai_compatible.py`
- `backend/tests/test_phase_12_real_llm_provider.py`

RED:

1. Add a mocked-transport test using `json_object` configuration and `generate_plan`.
2. Assert `response_format.type == "json_object"`.
3. Assert `json_schema` is absent from the request body in this mode.
4. Keep the existing `json_schema` assertion for the default/explicit schema mode.
5. Run only the provider test file.

Expected RED: `_complete` always emits `json_schema`.

Minimal GREEN:

1. Build the common request body once.
2. For `StructuredOutputMode.JSON_SCHEMA`, preserve the current strict `json_schema` object, including name, strict true, and the supplied schema.
3. For `StructuredOutputMode.JSON_OBJECT`, emit only `{ "type": "json_object" }` under `response_format`; do not send schema-only fields.
4. Branch only on the parsed enum, never on URL, model, vendor, or provider name.
5. Do not add retry or mode fallback behavior. The selected mode remains fixed for every attempt.

Expected GREEN: both request-shape tests pass and existing retry, size, authentication, and extraction tests remain unchanged.

Commit boundary: `feat: encode provider structured output mode`

## Task 3 — Preserve bounded extraction and prove fail-closed payload handling

Files to modify:

- `backend/app/agents/providers/openai_compatible.py` only if a minimal extraction adjustment is required
- `backend/tests/test_phase_12_real_llm_provider.py`

RED:

1. Add parameterized mocked-provider tests for `json_object` mode with malformed JSON content, a JSON array, and a valid JSON object.
2. Assert malformed/non-object responses raise `ProviderErrorCategory.INVALID_RESPONSE` without retry.
3. Assert valid JSON object extraction returns an `LLMResponse` payload but does not itself claim PlanContract validity.
4. Run only the provider test file.

Expected RED: new json_object coverage is absent; any regression in extraction becomes visible.

Minimal GREEN:

1. Reuse the existing `_extract` implementation and response-size/error mapping.
2. Do not add `jsonschema` or another dependency.
3. Do not move PlanContract or ReplanProposal validation into the provider.

Expected GREEN: both modes reject malformed/non-object data identically and preserve bounded safe errors.

Commit boundary: `test: cover structured output extraction failures`

## Task 4 — Keep Planner validation authoritative in json_object mode

Files to modify:

- `backend/tests/test_phase_12_real_llm_provider.py`
- `backend/app/agents/planner/planner.py` only if tests demonstrate a real validation gap

RED:

1. Add an offline `json_object`-configured provider fixture/transport that returns a valid `PlanContract` payload.
2. Exercise the existing Planner path and assert the plan reaches the same `PlanValidator` and valid-plan result as schema mode.
3. Add a structurally invalid payload case (for example missing `schema_version`, forbidden extra field, or invalid capability) and assert planning fails closed with the existing invalid-response/validation behavior before persistence or resolution.
4. Run the focused Phase 12 planner/provider tests only.

Expected RED: no explicit proof currently binds json_object transport to Planner validation.

Minimal GREEN:

1. Keep `PlannerAgent` request construction and `PlanValidator.validate` unchanged unless a test proves a gap.
2. Ensure the provider's `output_schema` remains available for schema mode while json_object mode relies on local `PlanValidator`.
3. Preserve capability resolution, project authority, approval, and audit semantics.

Expected GREEN: valid json_object plan succeeds through existing validation; invalid plan is rejected and not persisted.

Commit boundary: `test: prove planner validation for json object output`

## Task 5 — Keep Replanner validation and safety budgets authoritative

Files to modify:

- `backend/tests/test_phase_13_controlled_replanning.py`
- `backend/app/agents/replanning/service.py` only if tests demonstrate a real validation gap

RED:

1. Add an offline provider fixture returning a valid `ReplanProposal` payload while configured for json_object semantics.
2. Exercise the existing `ReplanningService.create_successor` path and assert proposal parsing, `PlanValidator` reuse, capability resolution, and successor creation remain successful.
3. Add invalid proposal coverage and assert rejection.
4. Retain assertions for max replans, total-step bounds, duplicate/no-progress fingerprints, fresh approval requirements, and project authority.
5. Run only the Phase 13 controlled-replanning test file.

Expected RED: no explicit json_object replan coverage.

Minimal GREEN:

1. Keep `ReplanProposal.model_validate` and the subsequent `PlanValidator.validate` boundary unchanged.
2. Do not alter replan policy, lineage, approval, capability, or project checks.
3. Only fix a concrete mode-plumbing issue if the focused test exposes one.

Expected GREEN: valid json_object replan remains governed; invalid or over-budget proposals fail closed.

Commit boundary: `test: prove replanner validation for json object output`

## Task 6 — Expose active mode safely in provider status and Test Connection

Files to modify:

- `backend/app/schemas/provider.py`
- `backend/app/api/routes/providers.py`
- `backend/tests/test_phase_12_real_llm_provider.py`

RED:

1. Add API tests asserting `GET /llm/provider` returns `structured_output_mode` for default and explicit json_object configuration.
2. Assert the response contains no API key, secret, authorization header, or raw provider error.
3. Add a mocked Test Connection test for json_object mode that captures the request and asserts `response_format.type == "json_object"`, then returns `{"status":"ok"}`.
4. Add an invalid acknowledgement case and assert `INVALID_RESPONSE`/existing failed status semantics.
5. Run the focused Phase 12 provider test file.

Expected RED: status schema has no mode field; existing connection assertions do not prove mode selection.

Minimal GREEN:

1. Add a safe enum/literal-backed `structured_output_mode` response field.
2. Populate it from `ProviderConfig.structured_output_mode.value` in `_read_status`.
3. Leave connection state, failure categories, credential redaction, and route status codes unchanged.
4. Keep Test Connection on `provider.test_connection()` → `_complete`; do not create a special fake endpoint or fallback.

Expected GREEN: status reports only the active mode and connection tests use the same provider transport path.

Commit boundary: `feat: expose structured output mode in provider status`

## Task 7 — Focused integration verification

Files changed: none expected.

Run in this order, redirecting full output to a temporary log and returning only bounded summaries:

1. `python -m pytest tests/test_phase_12_real_llm_provider.py -q`
2. `python -m pytest tests/test_phase_13_controlled_replanning.py -q`
3. Any directly affected provider API test file identified by the implementation; do not run unrelated frontend tests.
4. If the production diff remains limited to provider config, request encoding, and safe status, run one bounded backend regression only after the focused suites pass.
5. Run `git diff --check`.

Expected result: all focused provider, planner, status, and replanning tests pass; no database or frontend artifacts appear.

Commit boundary: no commit; verification follows the preceding coherent commits.

## Task 8 — Optional manual real-provider smoke after automated success

No source files changed. This step is manual and must not run before Tasks 1–7 pass.

1. Set only `AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE=json_object` alongside the operator's existing provider configuration. Never print, inspect, or copy the API key.
2. Restart the backend using the existing project workflow.
3. Query `GET /llm/provider` and verify provider is `openai-compatible`, mode is `json_object`, and `credential_configured` is true.
4. Call `POST /llm/provider/test` once and verify the current success status semantics without `INVALID_RESPONSE`.
5. Stop services if started.

Do not use this step to alter automated tests or introduce vendor-specific logic. If credentials are unavailable, report `NOT RUN`; do not request or expose the secret.

## Final acceptance checklist

- `json_schema` remains the default and preserves strict request shape.
- `json_object` emits no schema-only request fields.
- Unknown modes fail closed.
- Malformed JSON and non-object payloads fail closed.
- Planner and Replanner retain their current local contract validators.
- Test Connection uses `_complete` and the active mode.
- Provider status exposes only the active mode, not secrets.
- No silent fallback, URL/vendor switch, dependency, database migration, frontend change, or approval/security regression is introduced.
- `git status --short` is clean and only intended implementation commits are present.

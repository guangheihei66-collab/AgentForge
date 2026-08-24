# AgentForge Phase 12 Release Notes

## Version

- Version: `0.1.0-beta.1`
- Tag: `v0.1.0-beta.1`
- Status: Beta / prerelease
- Distribution: source repository + Windows launcher scripts

This private GitHub Beta contains the completed governed real-provider lifecycle:

`Goal -> DeepSeek Planner -> grounding -> validation -> capability resolution -> human approval -> snapshot and Project authority -> Execute -> Runtime -> ToolGateway -> Evidence/Audit -> report`

The release is published from `main` with the annotated tag `v0.1.0-beta.1`.

## Included capabilities

- Real OpenAI-compatible planning with `deepseek-v4-flash`.
- Application-owned metadata Manifest grounding; only existing, allowlisted, readable metadata paths enter Planner context.
- Shared 100,000-byte metadata read eligibility, with an independent runtime `file_read` recheck.
- Deterministic capability resolution for `repository_state`, `project_metadata`, and `test_verification`.
- Human Approval bound to the exact Plan version, resolved tools, normalized parameters, registry fingerprints, and Project authority.
- Governed `POST /tasks/{task_id}/execute` through AgentRuntime and ToolGateway.
- Bounded Evidence and Audit records.
- Controlled Replanning with fresh approval for successor Plans.
- Truthful `SUCCESS`, `FAILED`, and `REJECTED` execution/report semantics.
- Isolated backend test databases and fail-closed workspace security.

## Verification snapshot

- Backend: 247 passed, 1 warning.
- Frontend: 9 passed.
- Frontend production build: passed.
- Provider connection: passed with `openai-compatible`, `deepseek-v4-flash`, and `json_object` structured output.

## Known Beta limitations

This is a private Beta for Windows launcher-oriented, single-host deployment. There is no installer, automatic updater, or stable-release guarantee; the release pipeline remains manual. Authentication/RBAC, managed database deployment, horizontal scaling, and write-capable tools are outside this phase.

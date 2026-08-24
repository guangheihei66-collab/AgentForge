# AgentForge Operator Guide

## Start and stop

From the repository root, run:

```powershell
.\Start-AgentForge.bat
.\Stop-AgentForge.bat
```

The launcher starts the backend on `http://127.0.0.1:8000` and the frontend on `http://localhost:5173`. Runtime data, logs, PID files, SQLite, and artifacts remain under the configured data root rather than Git.

## Provider configuration

For the real OpenAI-compatible provider, create the ignored `launcher/.env.local` from `launcher/dev-config.example` and set only non-secret values:

```text
AGENTFORGE_LLM_PROVIDER=openai-compatible
AGENTFORGE_LLM_BASE_URL=https://api.deepseek.com/v1
AGENTFORGE_LLM_MODEL=deepseek-v4-flash
AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE=json_object
```

Keep `AGENTFORGE_LLM_API_KEY` outside the repository, preferably in the Windows User environment or an approved host secret manager. Never put it in `.env.local`, a batch file, logs, runtime data, or Git.

The provider status endpoint reports provider, model, structured-output mode, credential presence, and connection state without returning credentials. Run a connection test only as an explicit operator action.

## Governed workflow

1. Create a Task under an ACTIVE Project.
2. Run the real Planner and inspect the grounded Plan.
3. In Approval Center, review and manually approve the exact Plan.
4. Confirm the Approval Snapshot and Project authority are valid.
5. Execute only through `POST /tasks/{task_id}/execute`.
6. Review ToolExecutions, Observations, Evidence, Audit, and the final report.

Protected execution requires the matching approved Plan version. A successor Plan created by Controlled Replanning always requires a fresh human approval; an earlier approval cannot authorize it.

## Result meanings

- `SUCCESS`: the tool/domain operation completed successfully.
- `FAILED`: the operation ran but its domain result failed, such as a failed test profile.
- `REJECTED`: policy, workspace, capability, approval, or other safety validation denied the operation.
- `CONTINUE`, `COMPLETE`, `FAIL`, and `REPLAN`: the bounded Runtime decisions after Observation.

Reports expose successful, failed, and rejected execution counts separately. Read Evidence and Audit before making a readiness decision.

## Security boundaries

The model proposes semantic capabilities only. Application-owned resolution selects concrete tools. The ToolGateway remains the final authorization and workspace boundary. No arbitrary shell, Git write, destructive file operation, network capability, or secret-file read is available in this candidate.

# AgentForge One-Click Launcher

Double-click `start_agentforge.bat` to:

1. Check Python, Node.js, npm, and `backend/.venv`.
2. Initialize the configured database and synthetic demo records.
3. Start FastAPI on `127.0.0.1:8000`.
4. Wait for `GET /health` to return `200`.
5. Start Vite on `127.0.0.1:5173`.
6. Wait for the frontend port and open `http://localhost:5173`.

The launcher uses PID files under `D:\AgentProjectData\AgentForge\runtime` and stops only process trees that it started and can identify as AgentForge. It never scans for or kills unrelated Python or Node processes.

Stop with `stop_agentforge.bat`.

Runtime logs are stored outside the source tree at:

`D:\AgentProjectData\AgentForge\runtime\logs`

See `logs/README.md` for the storage boundary.

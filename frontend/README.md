# AgentForge Frontend

# AgentForge Operations Console

The Phase 7 frontend is an enterprise AI Agent operations console built with React, TypeScript, Vite, and Tailwind CSS.

The selected design direction is the AI Agent Operations / Governance Console. It prioritizes approval review, plan permissions, task lifecycle, evidence, and auditability over chat or workflow-canvas interactions.

Run locally with `npm run dev`. Set `VITE_API_BASE_URL` when the FastAPI backend is not at `http://127.0.0.1:8000`. When the backend is unavailable, the UI presents bounded demo data so the approval flow remains inspectable.

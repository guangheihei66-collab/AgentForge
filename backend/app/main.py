"""FastAPI application entrypoint for the AgentForge backend foundation."""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.health import router as health_router
from .api.routes.diagnostics import router as diagnostics_router
from .api.routes.approvals import router as approvals_router
from .api.routes.planning import router as planning_router
from .api.routes.operations import router as operations_router
from .api.routes.providers import router as providers_router
from .api.routes.execution import router as execution_router
from .api.routes.tasks import router as tasks_router
from .api.routes.projects import router as projects_router
from .storage.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AgentForge Backend", version="0.2.1", lifespan=lifespan)
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "AGENTFORGE_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(diagnostics_router)
app.include_router(tasks_router)
app.include_router(projects_router)
app.include_router(approvals_router)
app.include_router(planning_router)
app.include_router(operations_router)
app.include_router(providers_router)
app.include_router(execution_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AgentForge",
        "service": "AI Agent Operations Platform",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }

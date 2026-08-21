"""FastAPI application entrypoint for the AgentForge backend foundation."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.approvals import router as approvals_router
from .api.routes.planning import router as planning_router
from .api.routes.operations import router as operations_router
from .api.routes.tasks import router as tasks_router
from .storage.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AgentForge Backend", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(approvals_router)
app.include_router(planning_router)
app.include_router(operations_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AgentForge",
        "service": "AI Agent Operations Platform",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }

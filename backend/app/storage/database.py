"""SQLAlchemy engine and session configuration."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    configured = os.getenv("AGENTFORGE_DATABASE_URL")
    if configured:
        return configured
    data_root = Path(
        os.getenv("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge")
    )
    return f"sqlite+pysqlite:///{(data_root / 'database' / 'agentforge.sqlite3').as_posix()}"


def _engine_kwargs(url: str) -> dict[str, object]:
    if url.startswith("sqlite"):
        kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return kwargs
    return {}


engine = create_engine(database_url(), future=True, **_engine_kwargs(database_url()))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create the MVP tables in the configured database."""

    if engine.url.get_backend_name() == "sqlite" and engine.url.database not in {
        None,
        ":memory:",
    }:
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)

    from . import orm  # noqa: F401  # Register all ORM models with Base.
    from .migrations import migrate_sqlite_schema

    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

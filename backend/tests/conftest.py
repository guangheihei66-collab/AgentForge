"""Shared test configuration using an in-memory SQLite database."""

import os

os.environ.setdefault("AGENTFORGE_DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest

from app.storage.database import Base, SessionLocal, engine, init_db


@pytest.fixture()
def db_session():
    init_db()
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)

"""Small, non-destructive schema migrations for the SQLite MVP."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def migrate_sqlite_schema(bind: Engine) -> None:
    """Add approved backward-compatible columns without recreating tables."""

    if bind.url.get_backend_name() != "sqlite":
        return
    inspector = inspect(bind)
    if "approvals" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("approvals")}
    if "resolved_snapshot" not in columns:
        with bind.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE approvals ADD COLUMN resolved_snapshot JSON"
            )
    verified = {
        column["name"] for column in inspect(bind).get_columns("approvals")
    }
    if "resolved_snapshot" not in verified:
        raise RuntimeError("SQLite approval snapshot migration did not apply")

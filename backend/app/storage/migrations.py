"""Small, non-destructive schema migrations for the SQLite MVP."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def migrate_sqlite_schema(bind: Engine) -> None:
    """Add approved backward-compatible columns without recreating tables."""

    if bind.url.get_backend_name() != "sqlite":
        return
    inspector = inspect(bind)
    if "tasks" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "project_id" not in task_columns:
            with bind.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE tasks ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"
                )
        if "project_id" not in {
            column["name"] for column in inspect(bind).get_columns("tasks")
        }:
            raise RuntimeError("SQLite task project migration did not apply")
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

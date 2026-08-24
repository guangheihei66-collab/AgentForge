"""Set the backend test database before any test module imports app code."""

import os


os.environ["AGENTFORGE_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

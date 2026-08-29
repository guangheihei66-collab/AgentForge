"""Set the backend test database before any test module imports app code."""

import os
import sys
from pathlib import Path


os.environ["AGENTFORGE_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
# Product routes require an explicit provider. Tests opt into the deterministic
# provider without changing the user's process or machine configuration.
os.environ.setdefault("AGENTFORGE_LLM_PROVIDER", "mock")

# The documented backend test command runs from ``backend``.  Add the
# repository root so tests can exercise the root-level launcher package
# without requiring an editable install or a global PYTHONPATH change.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

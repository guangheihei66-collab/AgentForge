import pytest

from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from app.metadata_manifest import normalize_metadata_relative_path
from app.metadata_manifest import MAX_METADATA_READ_BYTES, build_metadata_manifest
from app.tools.file_read import FileReadTool
from app.tools.defaults import build_default_registry
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"


def resolver():
    validator = WorkspaceValidator(REPO_ROOT)
    return CapabilityResolver(
        build_default_capability_registry(), build_default_registry(validator)
    )


def resolve_path(path: str):
    return resolver().resolve(
        task_id="task",
        plan_id="plan",
        plan_version=1,
        step_id="metadata",
        request=CapabilityRequest(
            "project_metadata", {"relative_path": path}
        ),
    )


@pytest.mark.parametrize("path", ["README.md", "frontend/package.json", "backend/requirements.txt"])
def test_metadata_capability_resolves_root_and_nested_allowlisted_paths(path):
    snapshot = resolve_path(path)

    assert snapshot.resolved_tool_id == "file_read"
    assert snapshot.parameters_dict() == {"relative_path": path}


@pytest.mark.parametrize(
    "path",
    [
        "../package.json",
        "frontend/../../package.json",
        r"C:\repo\frontend\package.json",
        "/frontend/package.json",
        r"\\server\share\package.json",
        "frontend/secrets.txt",
    ],
)
def test_metadata_capability_rejects_unsafe_or_non_metadata_paths(path):
    with pytest.raises((CapabilityResolutionError, ValueError)):
        resolve_path(path)


def test_metadata_path_normalization_is_shared_and_bounded():
    assert normalize_metadata_relative_path(r"frontend\package.json") == "frontend/package.json"
    with pytest.raises(ValueError):
        normalize_metadata_relative_path("frontend/../package.json")


def test_manifest_excludes_metadata_over_the_runtime_read_limit(db_session):
    from tests.project_test_support import project_workspace

    workspace = project_workspace(db_session)
    frontend = __import__("pathlib").Path(workspace) / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "package-lock.json").write_bytes(b"x" * 100_001)

    manifest = build_metadata_manifest(workspace)

    assert "frontend/package.json" in manifest
    assert "frontend/package-lock.json" not in manifest


@pytest.mark.parametrize("size, included", [(MAX_METADATA_READ_BYTES, True), (MAX_METADATA_READ_BYTES + 1, False)])
def test_manifest_uses_runtime_read_limit_boundary(db_session, size, included):
    from pathlib import Path
    from tests.project_test_support import project_workspace

    workspace = project_workspace(db_session)
    frontend = Path(workspace) / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_bytes(b"x" * size)

    manifest = build_metadata_manifest(workspace)

    assert ("frontend/package.json" in manifest) is included


def test_file_read_rechecks_size_after_manifest_snapshot(db_session):
    from pathlib import Path
    from tests.project_test_support import project_workspace

    workspace = project_workspace(db_session)
    path = Path(workspace) / "frontend" / "package.json"
    path.parent.mkdir()
    path.write_text("{}", encoding="utf-8")
    assert "frontend/package.json" in build_metadata_manifest(workspace)
    path.write_bytes(b"x" * (MAX_METADATA_READ_BYTES + 1))

    tool = FileReadTool(WorkspaceValidator.for_project(workspace))
    with pytest.raises(ValueError, match="exceeds the read limit"):
        tool.execute("read_metadata", {"relative_path": "frontend/package.json"}, workspace)

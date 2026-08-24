import pytest

from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from app.metadata_manifest import normalize_metadata_relative_path
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

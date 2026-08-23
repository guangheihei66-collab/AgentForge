from dataclasses import replace

import pytest

from app.capabilities.models import CapabilityDefinition, CapabilityRequest
from app.capabilities.registry import (
    CapabilityNotFound,
    CapabilityRegistry,
    build_default_capability_registry,
)
from app.capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from app.contracts.permissions import PermissionLevel
from app.tools.defaults import build_default_registry
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"


def capability_resolver() -> CapabilityResolver:
    return CapabilityResolver(
        build_default_capability_registry(),
        build_default_registry(WorkspaceValidator(REPO_ROOT)),
    )


def test_default_registry_contains_only_the_three_mvp_capabilities():
    registry = build_default_capability_registry()

    assert registry.ids() == (
        "project_metadata",
        "repository_state",
        "test_verification",
    )
    assert registry.require("repository_state").candidate_tool_ids == ("git_read",)
    assert registry.require("project_metadata").candidate_tool_ids == ("file_read",)
    verification = registry.require("test_verification")
    assert verification.candidate_tool_ids == ("test_run",)
    assert verification.parameter_schema[0].name == "profile"
    assert verification.parameter_schema[0].allowed_values == ("smoke", "unit")


def test_capability_registry_rejects_unknown_and_duplicate_ids():
    registry = CapabilityRegistry()
    definition = build_default_capability_registry().require("repository_state")
    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    with pytest.raises(CapabilityNotFound, match="Unknown capability"):
        registry.require("missing")


@pytest.mark.parametrize(
    ("capability_id", "parameters", "tool_id", "action"),
    [
        ("repository_state", {}, "git_read", "status"),
        (
            "project_metadata",
            {"relative_path": "PROJECT_CONTEXT.md"},
            "file_read",
            "read_metadata",
        ),
        ("test_verification", {"profile": "smoke"}, "test_run", "run_profile"),
    ],
)
def test_resolver_selects_the_single_valid_mapped_tool(
    capability_id, parameters, tool_id, action
):
    resolver = capability_resolver()

    snapshot = resolver.resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest(capability_id, parameters),
    )

    assert snapshot.resolved_tool_id == tool_id
    assert snapshot.resolved_action == action
    assert snapshot.parameters_dict() == parameters
    assert len(snapshot.registry_fingerprint) == 64
    resolver.verify(snapshot)


@pytest.mark.parametrize(
    "capability_request",
    [
        CapabilityRequest("missing", {}),
        CapabilityRequest("test_verification", {}),
        CapabilityRequest("test_verification", {"profile": "arbitrary"}),
        CapabilityRequest(
            "test_verification", {"profile": "smoke", "command": "pytest"}
        ),
    ],
)
def test_resolver_rejects_unknown_capabilities_and_invalid_parameters(
    capability_request,
):
    with pytest.raises((CapabilityNotFound, CapabilityResolutionError)):
        capability_resolver().resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=capability_request,
        )


def test_resolver_fails_closed_for_zero_or_multiple_valid_candidates():
    capabilities = CapabilityRegistry()
    tools = ToolRegistry()
    base_tool = build_default_registry(WorkspaceValidator(REPO_ROOT)).require("git_read")
    tools.register(base_tool)
    tools.register(replace(base_tool, name="git_read_2"))
    capabilities.register(
        CapabilityDefinition(
            id="repository_state",
            description="Read repository state",
            risk_level="low",
            required_permission=PermissionLevel.SAFE_READ,
            candidate_tool_ids=("missing",),
            action="status",
            parameter_schema=(),
        )
    )

    with pytest.raises(CapabilityResolutionError, match="found 0"):
        CapabilityResolver(capabilities, tools).resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=CapabilityRequest("repository_state", {}),
        )

    multiple = CapabilityRegistry()
    multiple.register(
        replace(
            capabilities.require("repository_state"),
            candidate_tool_ids=("git_read", "git_read_2"),
        )
    )
    with pytest.raises(CapabilityResolutionError, match="found 2"):
        CapabilityResolver(multiple, tools).resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=CapabilityRequest("repository_state", {}),
        )


def test_fingerprint_is_stable_for_cosmetic_changes_and_detects_semantic_changes():
    resolver = capability_resolver()
    snapshot = resolver.resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )
    capabilities = build_default_capability_registry()
    tools = build_default_registry(WorkspaceValidator(REPO_ROOT))
    cosmetic_tools = ToolRegistry()
    cosmetic_tools.register(replace(tools.require("git_read"), description="New wording"))
    cosmetic = CapabilityResolver(capabilities, cosmetic_tools).resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )
    semantic_tools = ToolRegistry()
    semantic_tools.register(
        replace(tools.require("git_read"), execution_contract_version="2")
    )
    semantic = CapabilityResolver(capabilities, semantic_tools).resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )

    assert cosmetic.registry_fingerprint == snapshot.registry_fingerprint
    assert semantic.registry_fingerprint != snapshot.registry_fingerprint
    with pytest.raises(CapabilityResolutionError, match="fingerprint"):
        CapabilityResolver(capabilities, semantic_tools).verify(snapshot)

import pytest

from app.workspace.validator import WorkspaceValidationError, WorkspaceValidator


def test_workspace_outside_configured_root_rejected():
    validator = WorkspaceValidator(r"D:\AgentProjects\AgentForge")

    with pytest.raises(WorkspaceValidationError):
        validator.validate_workspace(r"D:\AgentProjectData\AgentForge")


def test_user_directory_rejected():
    validator = WorkspaceValidator(r"D:\AgentProjects\AgentForge")

    with pytest.raises(WorkspaceValidationError):
        validator.validate_workspace(r"C:\Users")


def test_secret_file_access_rejected():
    validator = WorkspaceValidator(r"D:\AgentProjects\AgentForge")

    with pytest.raises(WorkspaceValidationError):
        validator.validate_relative_file(
            r"D:\AgentProjects\AgentForge", ".env"
        )


def test_path_traversal_rejected():
    validator = WorkspaceValidator(r"D:\AgentProjects\AgentForge")

    with pytest.raises(WorkspaceValidationError):
        validator.validate_relative_file(
            r"D:\AgentProjects\AgentForge", r"..\..\Windows\win.ini"
        )


def test_secret_directory_rejected():
    validator = WorkspaceValidator(r"D:\AgentProjects\AgentForge")

    with pytest.raises(WorkspaceValidationError):
        validator.validate_relative_file(
            r"D:\AgentProjects\AgentForge", r"secrets\config.json"
        )

"""Filesystem boundary checks for tool workspaces."""

from pathlib import Path
import os


class WorkspaceValidationError(ValueError):
    """Raised when a workspace or relative file is outside policy."""


class WorkspaceValidator:
    SECRET_NAMES = {
        ".env",
        "id_rsa",
        "credentials.json",
        "secrets.json",
        "passwords.json",
    }
    SECRET_PARTS = ("secret", "credential", "password", "token")
    SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

    def __init__(self, configured_root: str | Path):
        self.root = Path(configured_root).expanduser().resolve()

    def validate_workspace(self, workspace: str | Path) -> Path:
        candidate = Path(workspace).expanduser()
        if not candidate.is_absolute():
            raise WorkspaceValidationError("Workspace must be an absolute path")

        resolved = candidate.resolve()
        self._reject_system_or_user_root(resolved)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceValidationError(
                "Workspace is outside the configured workspace root"
            ) from exc

        if not resolved.exists() or not resolved.is_dir():
            raise WorkspaceValidationError("Workspace directory does not exist")
        return resolved

    def validate_relative_file(self, workspace: str | Path, relative_path: str) -> Path:
        if not relative_path or Path(relative_path).is_absolute():
            raise WorkspaceValidationError("File path must be relative")

        workspace_path = self.validate_workspace(workspace)
        candidate = (workspace_path / Path(relative_path)).resolve()
        try:
            candidate.relative_to(workspace_path)
        except ValueError as exc:
            raise WorkspaceValidationError("File path escapes the workspace") from exc

        if self.is_secret_path(candidate):
            raise WorkspaceValidationError("Secret files are not readable")
        return candidate

    def is_secret_path(self, path: str | Path) -> bool:
        for component in Path(path).parts:
            name = component.lower()
            if name in self.SECRET_NAMES or name.startswith(".env."):
                return True
            if name.endswith(self.SECRET_SUFFIXES):
                return True
            if any(part in name for part in self.SECRET_PARTS):
                return True
        return False

    def _reject_system_or_user_root(self, path: Path) -> None:
        forbidden_roots = {
            Path(os.environ.get("USERPROFILE", r"C:\Users\Public")).resolve(),
            Path(os.environ.get("WINDIR", r"C:\Windows")).resolve(),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
            Path(os.environ.get("ProgramData", r"C:\ProgramData")).resolve(),
        }
        for forbidden in forbidden_roots:
            try:
                path.relative_to(forbidden)
            except ValueError:
                continue
            raise WorkspaceValidationError(
                f"User or system directory is not an allowed workspace: {path}"
            )

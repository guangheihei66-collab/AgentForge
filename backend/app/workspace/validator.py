"""Filesystem boundary checks for tool workspaces."""

from pathlib import Path
import os
import ntpath


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

    @classmethod
    def canonicalize_project_root(cls, value: str | Path) -> Path:
        raw = str(value).strip()
        if not raw or raw.startswith(("\\\\", "\\\\?\\", "\\\\.\\")):
            raise WorkspaceValidationError("Workspace must be a local path")
        candidate = Path(raw)
        if not candidate.is_absolute():
            raise WorkspaceValidationError("Workspace must be an absolute path")
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WorkspaceValidationError("Workspace directory does not exist") from exc
        if not resolved.is_dir():
            raise WorkspaceValidationError("Workspace must be a directory")
        cls._reject_system_or_user_path(resolved)
        cls._reject_remote_drive(resolved)
        return resolved

    @classmethod
    def for_project(cls, root: str | Path) -> "WorkspaceValidator":
        return cls(cls.canonicalize_project_root(root))

    @staticmethod
    def authority_path_key(path: str | Path) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            raise WorkspaceValidationError("Authority path must be absolute")
        # Project roots are canonicalized strictly at ingress. Keep their
        # persisted comparison key stable even if the directory later vanishes.
        return ntpath.normcase(ntpath.normpath(str(candidate)))

    def validate_target(self, workspace: str | Path, target: str | Path) -> Path:
        root = self.validate_workspace(workspace)
        try:
            resolved = Path(target).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WorkspaceValidationError("Target does not exist") from exc
        try:
            common = os.path.commonpath((self.authority_path_key(root), self.authority_path_key(resolved)))
        except ValueError as exc:
            raise WorkspaceValidationError("Target escapes the workspace") from exc
        if common != self.authority_path_key(root):
            raise WorkspaceValidationError("Target escapes the workspace")
        return resolved

    def validate_workspace(self, workspace: str | Path) -> Path:
        candidate = Path(workspace).expanduser()
        if not candidate.is_absolute():
            raise WorkspaceValidationError("Workspace must be an absolute path")

        resolved = candidate.resolve()
        self._reject_system_or_user_root(resolved)
        self._reject_remote_drive(resolved)
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
        candidate = self.validate_target(workspace_path, workspace_path / relative_path)

        if self.is_secret_path(candidate):
            raise WorkspaceValidationError("Secret files are not readable")
        return candidate

    @staticmethod
    def _windows_drive_type(path: Path) -> int | None:
        if os.name != "nt" or not path.anchor:
            return None
        try:
            import ctypes

            return int(ctypes.windll.kernel32.GetDriveTypeW(path.anchor))
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    @classmethod
    def _reject_remote_drive(cls, path: Path) -> None:
        # Win32 DRIVE_REMOTE. The bounded call inspects only this volume root.
        if cls._windows_drive_type(path) == 4:
            raise WorkspaceValidationError("Workspace must not use a remote drive")

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
        self._reject_system_or_user_path(path)

    @staticmethod
    def _reject_system_or_user_path(path: Path) -> None:
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

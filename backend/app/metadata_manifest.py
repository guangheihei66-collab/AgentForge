"""Application-owned, bounded metadata availability for Planner grounding."""

from pathlib import Path
import ntpath

from .workspace.validator import WorkspaceValidator

METADATA_MANIFEST_FILES = (
    "AGENTS.md",
    "PROJECT_CONTEXT.md",
    "README.md",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
)
METADATA_MANIFEST_ROOTS = ("", "backend", "frontend", "launcher")
MAX_METADATA_READ_BYTES = 100_000


def normalize_metadata_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Metadata path must be a non-empty string")
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("/") or ntpath.isabs(value):
        raise ValueError("Metadata path must be relative")
    parts = normalized.split("/")
    if any(not part or part == "." or part == ".." for part in parts):
        raise ValueError("Metadata path contains unsafe traversal")
    if parts[-1] not in METADATA_MANIFEST_FILES:
        raise ValueError("Metadata filename is not allowlisted")
    return "/".join(parts)


def build_metadata_manifest(workspace: str | Path) -> tuple[str, ...]:
    validator = WorkspaceValidator.for_project(workspace)
    existing: list[str] = []
    for root in METADATA_MANIFEST_ROOTS:
        for filename in METADATA_MANIFEST_FILES:
            relative_path = normalize_metadata_relative_path(
                "/".join(part for part in (root, filename) if part)
            )
            try:
                path = validator.validate_relative_file(workspace, relative_path)
            except (OSError, ValueError):
                continue
            if path.is_file() and path.stat().st_size <= MAX_METADATA_READ_BYTES:
                existing.append(relative_path)
    return tuple(existing)

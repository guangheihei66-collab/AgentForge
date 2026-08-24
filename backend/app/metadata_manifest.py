"""Application-owned, bounded metadata availability for Planner grounding."""

from pathlib import Path

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


def build_metadata_manifest(workspace: str | Path) -> tuple[str, ...]:
    validator = WorkspaceValidator.for_project(workspace)
    existing: list[str] = []
    for root in METADATA_MANIFEST_ROOTS:
        for filename in METADATA_MANIFEST_FILES:
            relative_path = "/".join(part for part in (root, filename) if part)
            try:
                path = validator.validate_relative_file(workspace, relative_path)
            except (OSError, ValueError):
                continue
            if path.is_file():
                existing.append(relative_path)
    return tuple(existing)

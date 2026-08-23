# AgentForge Development Rules

- Read `PROJECT_CONTEXT.md` before implementation work.
- Keep source and mutable data separated.
- Do not install global packages.
- Do not download models or run Docker without an approved storage review.
- Do not allow the Agent to bypass the Tool Gateway.
- Do not expose secrets, full private documents, or unbounded logs.
- Require approval for writes, execution, destructive actions, and operations over 1 GiB.
- Keep tests deterministic and use isolated test-run directories.

# AgentForge Workspace Rules

Source Root:

`D:\AgentProjects\AgentForge`

Runtime/Data Root:

`D:\AgentProjectData\AgentForge`

## Allowed

- Read and modify AgentForge repository files only under the Source Root.
- Run bounded AgentForge backend tests and frontend builds.
- Write approved AgentForge runtime and test data only under the Data Root.

## Forbidden Without Explicit Approval

- Treating `D:\AgentProjects` or `D:\` as the AgentForge workspace.
- Modifying another repository, Forge Studio, NAS/company data, or other user projects.
- Modifying Codex sessions/archive storage or VS Code infrastructure.
- Global package installation, Docker, model downloads, or destructive Git commands.
- Writing project databases, logs, caches, uploads, or generated runtime artifacts into Git.

## Workspace Preflight

Before substantial changes verify:

1. Repository root is exactly `D:\AgentProjects\AgentForge`.
2. Git status.
3. Current branch.

If the repository root is different, stop.

## Storage and Output Safety

- Source code belongs under `D:\AgentProjects\AgentForge`.
- Mutable runtime data belongs under `D:\AgentProjectData\AgentForge`.
- Keep command output bounded; do not recursively dump the repository.
- Any operation expected to generate or download more than 1 GiB requires approval.

## Workspace Boundary

- The only valid AgentForge repository root is `D:\AgentProjects\AgentForge`.
- Runtime and mutable data belong under `D:\AgentProjectData\AgentForge`.
- Stop if the active repository root differs.

## Repository Hygiene

- Reuse existing module directories; do not add unnecessary top-level folders.
- Do not leave temporary, debug, duplicate, or backup source files.
- Keep runtime/generated data outside the source root.
- Check references before deleting files.
- Do not use destructive Git commands without approval.

## End-of-Task Hygiene Check

Before reporting a development task complete, verify Git status, intentional file changes, absence of temporary/debug files, absence of runtime data in the repository, and that tests/builds did not pollute the source tree.

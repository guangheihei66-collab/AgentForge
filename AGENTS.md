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

1. The active Git worktree must be either the primary repository root
   `D:\AgentProjects\AgentForge`, or a Git-registered linked worktree located
   directly under `D:\AgentProjects\AgentForge\.worktrees\`.
2. For a linked worktree, verify the exact path appears in
   `git worktree list --porcelain` run from this repository. Git's registered
   worktree metadata is the authority that it belongs to AgentForge; path
   location alone is insufficient.
3. Git status.
4. Current branch.

If neither approved case is true, stop.

## Storage and Output Safety

- Source code belongs under `D:\AgentProjects\AgentForge`.
- Mutable runtime data belongs under `D:\AgentProjectData\AgentForge`.
- Keep command output bounded; do not recursively dump the repository.
- Any operation expected to generate or download more than 1 GiB requires approval.

## Workspace Boundary

- The only valid AgentForge locations are the primary repository root
  `D:\AgentProjects\AgentForge` and exact paths for Git-registered linked
  worktrees directly under `D:\AgentProjects\AgentForge\.worktrees\`.
- Unregistered copies, arbitrary directories containing `AgentForge` in their
  name, and unrelated repositories remain forbidden.
- Runtime and mutable data belong under `D:\AgentProjectData\AgentForge`.
- Stop if the active path is not an approved location, or if a linked worktree
  is not present in `git worktree list --porcelain`.

## Repository Hygiene

- Reuse existing module directories; do not add unnecessary top-level folders.
- Do not leave temporary, debug, duplicate, or backup source files.
- Keep runtime/generated data outside the source root.
- Check references before deleting files.
- Do not use destructive Git commands without approval.

## End-of-Task Hygiene Check

Before reporting a development task complete, verify Git status, intentional file changes, absence of temporary/debug files, absence of runtime data in the repository, and that tests/builds did not pollute the source tree.

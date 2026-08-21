# AgentForge Development Rules

- Read `PROJECT_CONTEXT.md` before implementation work.
- Keep source and mutable data separated.
- Do not install global packages.
- Do not download models or run Docker without an approved storage review.
- Do not allow the Agent to bypass the Tool Gateway.
- Do not expose secrets, full private documents, or unbounded logs.
- Require approval for writes, execution, destructive actions, and operations over 1 GiB.
- Keep tests deterministic and use isolated test-run directories.

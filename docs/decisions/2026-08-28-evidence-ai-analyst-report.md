# Decision: Evidence-Grounded AI Analyst Report

Date: 2026-08-28

## Decision

Add a downstream, read-only AI Analyst that synthesizes bounded persisted
execution evidence into a strict, evidence-linked project analysis and release
recommendation.

Persist the report as canonical JSON under the external AgentForge data root,
with a SHA-256 hash and Task/Plan/version binding. Record only bounded status,
artifact, hash, provider metadata, coverage, and failure metadata in the
existing AuditEvent table.

## Alternatives considered

1. Add a new Report database table. This gives relational querying but requires
   schema migration, migration validation, and another lifecycle authority.
2. Store the full report in AuditEvent. This avoids a table but creates payload
   growth, weak artifact integrity boundaries, and noisy audit timelines.
3. Use a bounded external artifact with AuditEvent metadata. Chosen.

## Reasons

- Preserves the existing Task, Plan, Approval, Runtime, ToolGateway, Evidence,
  and Audit authorities.
- Allows artifact hash/tamper validation without a database migration.
- Keeps the report read-oriented and safe to retry without re-executing tools.
- Supports historical Tasks that do not have Analyst output.
- Makes provider, malformed-output, evidence-reference, and artifact failures
  independently observable without changing execution truth.

## Consequences

- Report reads must verify path containment, size, hash, JSON schema, and
  Task/Plan/version binding before serving success.
- Artifact retention and external data-root cleanup remain operational policy,
  not a new product authority.
- A real provider remains optional for automated tests; Mock is deterministic
  and the final human live test must use the configured provider when available.

# Decisions and Trade-Offs

This document records product and engineering decisions that affect ASTrograph behavior,
with explicit trade-offs, constraints, and consequences.

## Scope

- Audience: ASTrograph users, contributors, and integrators.
- Purpose: provide transparent, technical rationale for opinionated defaults.
- Status model:
  - `Accepted`: active and expected behavior.
  - `Superseded`: replaced by a newer decision.
  - `Proposed`: under evaluation, not yet default.

## Decision Log

## D-001: Plugin-First Language Architecture

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

ASTrograph historically had Python-centric internals. This increased coupling and made new
language onboarding costly.

### Decision

Language support is plugin-based. Python and JavaScript are both delivered through plugins:

- `python` -> `PythonLSPPlugin` (LSP symbols + AST graphing)
- `javascript_lsp` -> `JavaScriptLSPPlugin` (LSP symbols + structural graphing)

### Trade-offs

- Pros:
  - Uniform extension model for future languages.
  - Lower incremental engineering cost per language.
  - Clear runtime boundaries between core and language adapters.
- Cons:
  - LSP server availability becomes an operational dependency.
  - Symbol quality varies by language server implementation.

## D-002: Bundle JavaScript LSP Runtime in Official Docker Image

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

Unbundled JS LSP dependencies create setup friction and inconsistent local environments.

### Decision

Official Docker images bundle `node`, `npm`, `typescript`, and
`typescript-language-server`.

### Trade-offs

- Pros:
  - Frictionless adoption for macOS/Linux users running Docker.
  - Predictable behavior across environments.
- Cons:
  - Larger image size.
  - Runtime components must be maintained in release cadence.

## D-003: Duplicate Significance Policy (Noise Reduction)

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

Suppression history showed a high ratio of false-positive or acceptable repetition findings
(mostly tiny guard blocks and boilerplate).

### Decision

Default significance thresholds are:

- Exact/pattern duplicate discovery: `min_node_count = 5`.
- Block duplicate discovery: `min_node_count = 10`.
- Block report filter: ignore block duplicates with `< 3` lines.
- Pre-create checks (`write`/`edit`): `min_node_count = 10`.

### Trade-offs

- Pros:
  - Large reduction in low-value duplicate alerts.
  - Lower suppression maintenance burden.
  - Better signal-to-noise ratio for actionable findings.
- Cons:
  - Some small-but-real duplicated blocks may not be reported.
  - Teams favoring strict micro-duplication control may require custom tuning.

## D-004: Ignore Import-Only LSP Symbol Units

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

Some LSP servers return symbols whose extracted ranges map to import/export boilerplate
(for example in package/module index files). These are poor duplication signals.

### Decision

LSP-based extraction filters out units whose extracted code is import-only:

- starts with `from `
- starts with `import `

### Trade-offs

- Pros:
  - Avoids non-actionable duplicates from module wiring code.
  - Improves relevance of exact duplicate reports.
- Cons:
  - Rare edge case: import-heavy generated code patterns are intentionally ignored.

## D-005: Timestamped Analysis Reports Only

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

A stable alias (`analysis_report.txt`) creates ambiguity in multi-run/multi-agent workflows.

### Decision

Analyze output is persisted only as timestamped files:

- `.metadata_astrograph/analysis_report_<YYYYMMDD>_<HHMMSS>_<microseconds>.txt`

Legacy alias `analysis_report.txt` is no longer produced.

### Trade-offs

- Pros:
  - Strong provenance and deterministic run attribution.
  - Better compatibility with concurrent workflows and audits.
- Cons:
  - Consumers must parse the returned `Details:` path instead of relying on a fixed filename.

## D-006: Suppression Persistence and Intent

- Status: `Accepted`
- Effective date: `2026-02-07`

### Context

Suppressions are necessary for tolerated duplication patterns and should survive process restarts.

### Decision

- Suppressions are persisted in index metadata storage.
- Suppressions are treated as explicit user intent, not automatic filtering.
- Stale suppressions are invalidated when tracked source evidence changes.

### Trade-offs

- Pros:
  - Stable operator control over tolerated findings.
  - Lower repetitive triage cost across sessions.
- Cons:
  - Suppression state must be managed intentionally in CI/reproducible environments.

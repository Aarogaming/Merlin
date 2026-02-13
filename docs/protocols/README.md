# Merlin Inter-Repo Protocol Baseline

This folder defines the baseline contracts for cross-repo communication involving Merlin.
Use these docs when integrating from the SuperProject, Hub, Orchestrator, or IDE-agent workflows.

## Scope

- Standard message envelope for operations/events.
- Merlin capability surface that other repos can target.
- Compatibility policy for safe, reverse-compatible evolution.

## Documents

1. `operation-envelope-v1.md`
2. `repo-capabilities-merlin-v1.md`
3. `compatibility-policy.md`

## Related Entry Points

- `README.md` (repo root)
- `docs/GATE_GOVERNANCE_POINTER.md`

## Machine-Readable Schemas

Schemas live in `contracts/`:

- `contracts/aas.operation-envelope.v1.schema.json`
- `contracts/aas.repo-capability-manifest.v1.schema.json`

## Usage Rule

Before introducing a cross-repo payload change:

1. Update docs in this folder.
2. Update corresponding schema in `contracts/`.
3. Keep changes additive unless a major contract version bump is planned.

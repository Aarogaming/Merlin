# Agent Genome Spec v1

Agent-Zero is the canonical DNA source for every federation member.

This directory defines the versioned genome contract used to create and evolve
all agent repos from birth through specialization.

## Design goals

- One source of truth for kernel, plugin, schema, and lifecycle behavior.
- Solo-first operation for every newborn agent.
- Federation-ready operation through the same contracts.
- Distributed control-plane monitoring with single-writer mutation safety.
- Versioned, testable inheritance that supports gradual specialization.

## Genome layers

- `kernel`: boot, bus transport, plugin loader, health and heartbeat.
- `contracts`: manifests, lifecycle state, control-plane lease semantics.
- `reflexes`: safety defaults and self-healing routines.
- `persona`: directive, tone, constraints, autonomy, memory model.
- `control_plane_slice`: observer and optional mutator capability surfaces.

## Lifecycle model

1. `birth`: repo scaffolded from Agent-Zero genome.
2. `training`: local reflex tests and compatibility checks.
3. `stabilization`: quarantine gates and promotion review.
4. `specialization`: domain overlays enabled, generic capabilities delegated.
5. `federation`: event bus participation and registry publication.
6. `evolution`: additive upgrades with ledgered drift.

## Runtime profiles

- `solo`: local execution only, no federation dependency required.
- `federated`: event bus, remote capability delegation, shared telemetry.

Profile switches are configuration-only. No forked code path is required.

## Control-plane transformer pattern

All agents can observe control-plane health. Only one agent can mutate
control-plane state at a time.

- Every agent may run observer routines.
- Mutation operations require an active lease.
- Lease holder is the only writer until TTL expiry or explicit release.

This prevents multi-writer conflicts while preserving distributed resilience.

## Files

- `schemas/genome_manifest.schema.json`
- `schemas/lifecycle_state.schema.json`
- `schemas/control_plane_lease.schema.json`
- `schemas/runtime_bundle.schema.json`
- `templates/genome.manifest.json`
- `templates/runtime.manifest.json`

## Compatibility policy

- Breaking changes require major version increments.
- Minor versions are additive and must not break existing generated repos.
- Patch versions are bug fixes and documentation clarifications only.

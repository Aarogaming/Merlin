# Architecture

## Module role

`Merlin` is an AAS submodule with independent source control and local runtime configuration.

## Contract surface

- Module identity/config: `aas-module.json`
- Hive communication policy: `aas-hive.json`
- Inter-repo protocol baseline: `protocols/AGENT_INTEROP_V1.md`

## Design intent

- Keep repo-local docs discoverable through `INDEX.md`.
- Keep protocol docs versioned and backward compatible.
- Keep cross-repo operations explicit and traceable.

## Quarterly Drift Review Checklist

Run this checklist once per quarter to detect architecture drift early.

1. Interface drift:
   - Validate operation/schema parity (`contracts/` vs embedded schema).
   - Confirm protocol docs reflect live operation fields and error codes.
2. Runtime drift:
   - Confirm routing fallback taxonomy is synchronized (`verify_routing_taxonomy_sync.py`).
   - Confirm critical health/telemetry signals are exposed and test-covered.
3. Dependency drift:
   - Re-check optional dependency fallbacks (`jose`, `redis`, `speech_recognition`, etc.).
   - Verify plugin dependency compatibility checks still match manifest expectations.
4. Quality-gate drift:
   - Ensure pre-commit and CI gates align and still execute in local environments.
   - Validate release checklist script output (`scripts/run_release_checklist.py`).
5. Documentation drift:
   - Ensure `RUNBOOK.md`, `docs/AGENT_TRANSITION.md`, and roadmap docs are current.
   - Record accepted deviations with owner and due date.

### Tracked Actions (Current Quarter)

| Quarter | Action | Owner | Due | Status |
| --- | --- | --- | --- | --- |
| 2026-Q1 | Confirm operation envelope schema and embedded routing schema parity in CI + hooks. | merlin-agent | 2026-03-15 | in_progress |
| 2026-Q1 | Validate optional dependency fallback behavior remains covered by tests. | merlin-agent | 2026-03-15 | in_progress |
| 2026-Q1 | Refresh incident template links in `RUNBOOK.md` and transition docs. | merlin-agent | 2026-03-15 | done |

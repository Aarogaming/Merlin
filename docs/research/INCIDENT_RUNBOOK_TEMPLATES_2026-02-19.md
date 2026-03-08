# Incident Runbook Templates (2026-02-19)

Scope: Merlin subsystem incident handling templates with consistent fields for triage, mitigation, and postmortem.

## API Incident Template

- Incident ID:
- Start time (UTC):
- Detection source:
- User impact summary:
- Suspected operations/endpoints:
- Initial severity (`SEV-1`/`SEV-2`/`SEV-3`):

Immediate checks:

- `python3 scripts/run_release_checklist.py --strict`
- `python3 scripts/sync_contract_schemas.py --precommit`
- `python3 -m pytest -q -s tests/test_operation_error_responses.py`

Mitigation actions:

- Roll back to last known-good deployment artifact.
- Disable risky operations via `MERLIN_OPERATION_FEATURE_FLAGS`.
- Confirm API auth/rate-limit/idempotency guards are active.

Recovery criteria:

- Error rate below threshold for 30 minutes.
- No active contract schema drift.
- Key API smoke checks pass.

Postmortem fields:

- Root cause:
- Containment changes:
- Permanent fix PR:
- Follow-up owner:
- Follow-up due date:

## Routing Incident Template

- Incident ID:
- Start time (UTC):
- Detection source:
- Affected route(s): `adaptive` / `parallel` / `streaming`:
- Fallback reason spike:

Immediate checks:

- `python3 scripts/verify_routing_taxonomy_sync.py`
- `python3 -m pytest -q -s tests/test_merlin_routing_contract.py`
- `python3 -m pytest -q -s tests/test_merlin_adaptive_llm.py tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py`

Mitigation actions:

- Force non-DMS route if needed (`DMS_ENABLED=false`).
- Disable fast lane if regression suspected (`MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED=false`).
- Capture failing payload class and fallback telemetry.

Recovery criteria:

- Fallback reason distribution stabilized.
- Routing metadata fields present and valid.
- Throughput and latency back within expected bounds.

Postmortem fields:

- Root cause:
- Routing policy/version impacted:
- Test coverage added:
- Follow-up owner:
- Follow-up due date:

## Plugin Incident Template

- Incident ID:
- Start time (UTC):
- Detection source:
- Affected plugin(s):
- Health state (`healthy`/`degraded`/`isolated`):

Immediate checks:

- `python3 -m pytest -q -s tests/test_merlin_plugin_manager.py`
- `python3 scripts/check_secret_hygiene.py --plugin-dependency-check`

Mitigation actions:

- Isolate crashing plugin.
- Reduce restart budget if thrashing is observed.
- Switch to non-plugin fallback path for critical workflows.

Recovery criteria:

- Plugin execution error rate normalizes.
- No repeated crash isolation events.
- Dependency and manifest checks pass.

Postmortem fields:

- Root cause:
- Plugin version affected:
- Rollback decision:
- Follow-up owner:
- Follow-up due date:

## Research Manager Incident Template

- Incident ID:
- Start time (UTC):
- Detection source:
- Affected operation(s):
- Data impact summary:

Immediate checks:

- `python3 -m pytest -q -s tests/test_merlin_research_manager.py`
- `python3 -m pytest -q -s tests/test_operation_expected_responses.py -k "research.manager"`
- `python3 scripts/run_release_checklist.py --strict`

Mitigation actions:

- Enable read-only mode to prevent write corruption.
- Export snapshots for impacted sessions before mutation.
- Route consumers to legacy flow when capability probe fails.

Recovery criteria:

- Create/get/brief/list operations pass targeted tests.
- No new read-only rejection anomalies.
- Session files validate and load consistently.

Postmortem fields:

- Root cause:
- Data recovery steps:
- Corrective action:
- Follow-up owner:
- Follow-up due date:

# Planner Fallback Test Runbook

## Scope
Repo-local planner/fallback telemetry validation for:
- `tests/test_merlin_parallel_llm.py`
- `tests/test_merlin_streaming_llm.py`
- `tests/test_merlin_adaptive_llm.py`
- `tests/test_merlin_routing_contract.py`

## Quick Run
```bash
bash scripts/run_planner_fallback_tests.sh
```

Expected signature:
- test session starts
- collected test count for four suites
- terminal summary like `45 passed in <time>s`

## Runbook Smoke (CI parity)
```bash
bash scripts/smoke_planner_fallback_runbook.sh
```

Expected signature:
- planner/fallback tests execute and print pass summary containing `45 passed`
- schema sync check prints `contract schemas are in sync`
- routing taxonomy sync check prints `routing taxonomy is in sync`
- schema enforcement tests execute and print pass summary containing `48 passed`
- evidence export prints `cp4a smoke evidence status: pass`
- evidence schema check prints `cp4a smoke evidence schema verified`
- `artifacts/planner-fallback.log` contains both pass summaries
- `artifacts/planner-fallback-junit.xml` exists and is non-empty
- `artifacts/cp4a-schema-junit.xml` exists and is non-empty
- `artifacts/cp4a-smoke-evidence.json` exists and is non-empty

Strict smoke gate notes:
- smoke script verifies JUnit totals directly (no `collected N items` parsing).
- smoke script fails if:
  - sync signature `contract schemas are in sync` is missing, or
  - routing taxonomy signature `routing taxonomy is in sync` is missing, or
  - planner/schema JUnit files have failures/errors, or
  - planner/schema test totals violate configured expectations, or
  - exported evidence payload fails `contracts/cp4a.smoke-evidence.v1.schema.json` validation.
- smoke default expectations are loaded from:
  - `docs/research/CP4A_SMOKE_BASELINE_2026-02-15.json`
  - validated via `scripts/load_cp4a_smoke_baseline.py`
- JUnit gate controls:
  - `PLANNER_MIN_TESTS`, `SCHEMA_MIN_TESTS` (minimum tests, defaults `1`)
  - `PLANNER_EXPECTED_TESTS`, `SCHEMA_EXPECTED_TESTS` (exact tests, optional)
  - `SYNC_EXPECTED_SUMMARY`
  - `TAXONOMY_EXPECTED_SUMMARY`
- baseline override control:
  - `CP4A_SMOKE_BASELINE_PATH` (alternate baseline file path)
  - `CP4A_SMOKE_EVIDENCE_JSON` (alternate evidence artifact output path)
  - `CP4A_SMOKE_EVIDENCE_SCHEMA_PATH` (alternate evidence schema path)

Negative control example:
```bash
PLANNER_EXPECTED_TESTS='999' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```

Expected:
- `EXIT:1`

Malformed baseline control:
```bash
tmp=$(mktemp); printf '{"planner_expected_tests":"bad"}\n' > "$tmp"; CP4A_SMOKE_BASELINE_PATH="$tmp" bash scripts/smoke_planner_fallback_runbook.sh; status=$?; echo EXIT:$status; rm -f "$tmp"
```

Expected:
- stderr includes `baseline field 'planner_expected_tests' must be an integer`
- `EXIT:1`

Missing taxonomy signature control:
```bash
TAXONOMY_EXPECTED_SUMMARY='__missing_taxonomy_signature__' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```

Expected:
- smoke verifier includes `missing summary signature: __missing_taxonomy_signature__`
- `EXIT:1`

Missing baseline file control:
```bash
CP4A_SMOKE_BASELINE_PATH='/tmp/does-not-exist-cp4a-baseline.json' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```

Expected:
- stderr includes `baseline file not found: /tmp/does-not-exist-cp4a-baseline.json`
- `EXIT:1`

## Direct Schema Sync Guard
```bash
python scripts/sync_contract_schemas.py --check
```

Expected signature:
- output: `contract schemas are in sync`
- non-zero exit if standalone and embedded schemas diverge

## Direct JUnit Verifier Guard
```bash
PYTHONPATH=. pytest -q tests/test_verify_junit_totals.py
```

Expected signature:
- terminal summary like `3 passed`
- mirrored in CI quality lane as early failure step before smoke.

## Direct Smoke Log Signature Guard
```bash
PYTHONPATH=. pytest -q tests/test_verify_smoke_log_signatures.py
```

Expected signature:
- terminal summary like `3 passed`
- validates that missing taxonomy/sync signatures or empty artifacts fail deterministically.

## Direct Smoke Early-Fail Sequencing Guard
```bash
PYTHONPATH=. pytest -q tests/test_smoke_planner_fallback_runbook.py
```

Expected signature:
- terminal summary like `4 passed`
- validates malformed/missing baseline failure exits before planner/schema suite execution.
- validates planner expected-total mismatch and missing taxonomy signature failure paths.

## Direct Smoke Evidence Export Guard
```bash
PYTHONPATH=. pytest -q tests/test_export_cp4a_smoke_evidence.py
```

Expected signature:
- terminal summary like `3 passed`
- validates timing-insensitive evidence export from JUnit totals + smoke signatures.

## Direct Smoke Evidence Schema Guard
```bash
./.venv/bin/python scripts/verify_cp4a_smoke_evidence_schema.py --evidence artifacts/cp4a-smoke-evidence.json
```

Expected signature:
- output: `cp4a smoke evidence schema verified`
- non-zero exit if evidence payload drifts from `contracts/cp4a.smoke-evidence.v1.schema.json`.

## Direct Routing Taxonomy Guard
```bash
python scripts/verify_routing_taxonomy_sync.py
```

Expected signature:
- output: `routing taxonomy is in sync`
- non-zero exit if schema enums/required fields/retryable partitions drift from `merlin_routing_contract.py`.

## Manual Run
```bash
PYTHONPATH=. pytest --capture=no \
  tests/test_merlin_parallel_llm.py \
  tests/test_merlin_streaming_llm.py \
  tests/test_merlin_adaptive_llm.py \
  tests/test_merlin_routing_contract.py
```

Expected signature:
- no collection/import errors
- terminal summary with all passing

## CI Evidence Run (local simulation)
```bash
PLANNER_FALLBACK_JUNIT_XML=artifacts/planner-fallback-junit.xml \
  bash scripts/run_planner_fallback_tests.sh | tee artifacts/planner-fallback.log
```

Expected artifacts:
- `artifacts/planner-fallback-junit.xml`
- `artifacts/planner-fallback.log`

## Failure Signatures
- `ModuleNotFoundError`: dependency/setup issue.
- `assert ... fallback_reason_code`: taxonomy drift.
- `assert ... dms_candidate/dms_attempted`: AB-control routing regression.
- `assert ... router_policy_version/routing_telemetry_schema`: metadata contract drift.

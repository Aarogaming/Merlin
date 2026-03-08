# CHIMERA V2 CP4-A Planner Readiness Status (2026-02-15)

## Mission
Confirm CP4-A planner fallback/telemetry readiness in repo-local scope (`Merlin/**`).

## Status
- **Readiness Verdict:** **READY (router fallback/telemetry path)**
- **Confidence:** High for adaptive/parallel/streaming planner routing paths.
- **Caveat:** None observed in repo-local validation.

## Readiness Gates
1. Shared fallback taxonomy exists and is reusable by planner/router components.
2. Router telemetry fields are normalized across adaptive/parallel/streaming implementations.
3. Planner fallback behavior is verified with targeted tests for DMS success and DMS fallback.
4. Metadata taxonomy classification behavior is verified with unit tests.
5. Standalone routing metadata schema and envelope-embedded schema remain in lockstep.

## Implementation Evidence
- Shared routing contract module:
  - `merlin_routing_contract.py`
- Research manager lifecycle and persistence hardening:
  - `merlin_research_manager.py`
  - `plugins/research_manager.py`
  - `merlin_cli.py`
- Router integrations:
  - `merlin_parallel_llm.py`
  - `merlin_streaming_llm.py`
  - `merlin_adaptive_llm.py`
- Metadata fallback normalization path:
  - `merlin_emotion_chat.py`
- Metadata schema fragment for AAS-compatible consumers:
  - `contracts/assistant.chat.routing-metadata.v1.schema.json`
- Smoke evidence schema contract for packet consumers:
  - `contracts/cp4a.smoke-evidence.v1.schema.json`
- Smoke evidence contract fixture for schema-stability assertions:
  - `tests/fixtures/contracts/cp4a.smoke_evidence.contract.json`
- Envelope-level schema composition for metadata enforcement:
  - `contracts/aas.operation-envelope.v1.schema.json`
- Runbook smoke path:
  - `scripts/smoke_planner_fallback_runbook.sh`
  - Includes planner/fallback suite and schema enforcement suite
  - Enforces schema-sync + taxonomy-sync signatures and machine-readable JUnit totals for planner/schema suites
  - Exports timing-insensitive smoke evidence artifact (`cp4a-smoke-evidence.v1`)
  - Loads expected totals from `docs/research/CP4A_SMOKE_BASELINE_2026-02-15.json` by default
- Schema sync utility:
  - `scripts/sync_contract_schemas.py`
- Routing taxonomy sync utility:
  - `scripts/verify_routing_taxonomy_sync.py`
- JUnit verification utility:
  - `scripts/verify_junit_totals.py`
- Smoke log signature verifier utility:
  - `scripts/verify_smoke_log_signatures.py`
- Smoke evidence exporter utility:
  - `scripts/export_cp4a_smoke_evidence.py`
- Smoke evidence schema validator utility:
  - `scripts/verify_cp4a_smoke_evidence_schema.py`
- Baseline loader/validator utility:
  - `scripts/load_cp4a_smoke_baseline.py`
- Always-on quality gates:
  - `.github/workflows/ci.yml` (quality job sync check)
  - `.pre-commit-config.yaml` (contract schema + taxonomy sync hooks)
  - `.github/workflows/ci.yml` (quality job runs `tests/test_verify_junit_totals.py`, `tests/test_load_cp4a_smoke_baseline.py`, `tests/test_verify_routing_taxonomy_sync.py`, `tests/test_verify_cp4a_smoke_evidence_schema.py`, `tests/test_verify_smoke_log_signatures.py`, `tests/test_smoke_planner_fallback_runbook.py`, and `tests/test_export_cp4a_smoke_evidence.py`)
- Targeted verification tests:
  - `tests/test_merlin_parallel_llm.py`
  - `tests/test_merlin_streaming_llm.py`
  - `tests/test_merlin_adaptive_llm.py`
  - `tests/test_merlin_routing_contract.py`
  - `tests/test_sync_contract_schemas.py`
  - `tests/test_merlin_api_server.py`
  - `tests/test_operation_expected_responses.py`
  - `tests/test_contract_schemas.py`
  - `tests/test_verify_junit_totals.py`
  - `tests/test_load_cp4a_smoke_baseline.py`
  - `tests/test_verify_routing_taxonomy_sync.py`
  - `tests/test_verify_smoke_log_signatures.py`
  - `tests/test_smoke_planner_fallback_runbook.py`
  - `tests/test_export_cp4a_smoke_evidence.py`
  - `tests/test_verify_cp4a_smoke_evidence_schema.py`

## Normalized Telemetry/Fallback Contract Confirmed
The planner/router metadata path confirms the following stable fields:
- `fallback_reason`
- `fallback_reason_code`
- `fallback_detail`
- `fallback_stage`
- `fallback_retryable`
- `dms_candidate`
- `dms_attempted`
- `router_backend`
- `router_policy_version`
- `routing_telemetry_schema`

## Verification Commands and Outcomes

### Command 1 (targeted planner/fallback telemetry suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py
```
- **Outcome:** **PASS**
- **Result:** `45 passed in 2.09s`

### Command 2 (quality verifier bundle including evidence export and early-fail sequencing)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_verify_junit_totals.py tests/test_load_cp4a_smoke_baseline.py tests/test_verify_routing_taxonomy_sync.py tests/test_verify_cp4a_smoke_evidence_schema.py tests/test_verify_smoke_log_signatures.py tests/test_smoke_planner_fallback_runbook.py tests/test_export_cp4a_smoke_evidence.py
```
- **Outcome:** **PASS**
- **Result:** `22 passed in 31.45s`

### Command 3 (quality-gate micro suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_verify_cp4a_smoke_evidence_schema.py tests/test_verify_routing_taxonomy_sync.py tests/test_load_cp4a_smoke_baseline.py tests/test_verify_junit_totals.py tests/test_verify_smoke_log_signatures.py
```
- **Outcome:** **PASS**
- **Result:** `15 passed in 4.58s`

### Command 3b (direct smoke-signature guard suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_verify_smoke_log_signatures.py
```
- **Outcome:** **PASS**
- **Result:** `3 passed in 0.49s`

### Command 3c (direct smoke runbook early-fail sequencing suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_smoke_planner_fallback_runbook.py
```
- **Outcome:** **PASS**
- **Result:** `4 passed in 27.98s`

### Command 3d (direct smoke evidence export suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_export_cp4a_smoke_evidence.py
```
- **Outcome:** **PASS**
- **Result:** `3 passed in 0.53s`

### Command 3e (direct smoke evidence schema suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_verify_cp4a_smoke_evidence_schema.py
```
- **Outcome:** **PASS**
- **Result:** `3 passed in 2.10s`

### Command 4 (standalone schema sync check)
```bash
./.venv/bin/python scripts/sync_contract_schemas.py --check
```
- **Outcome:** **PASS**
- **Result:** `contract schemas are in sync`

### Command 5 (routing taxonomy sync check)
```bash
./.venv/bin/python scripts/verify_routing_taxonomy_sync.py
```
- **Outcome:** **PASS**
- **Result:** `routing taxonomy is in sync`

### Command 5b (smoke evidence schema check)
```bash
./.venv/bin/python scripts/verify_cp4a_smoke_evidence_schema.py --evidence artifacts/cp4a-smoke-evidence.json
```
- **Outcome:** **PASS**
- **Result:** `cp4a smoke evidence schema verified`

### Command 6 (runbook quick command)
```bash
bash scripts/run_planner_fallback_tests.sh
```
- **Outcome:** **PASS**
- **Result:** `45 passed in 2.09s`

### Command 7 (runbook smoke/CI parity, baseline default)
```bash
bash scripts/smoke_planner_fallback_runbook.sh
```
- **Outcome:** **PASS**
- **Result:** planner/fallback suite `45 passed in 2.14s`, schema sync check `contract schemas are in sync`, taxonomy sync check `routing taxonomy is in sync`, schema enforcement suite `48 passed, 2 warnings in 7.02s`, plus verifier summaries:
  - `planner: tests=45 failures=0 errors=0 skipped=0`
  - `schema: tests=48 failures=0 errors=0 skipped=0`
  - `smoke log signatures verified`
  - `cp4a smoke evidence status: pass`
  - `cp4a smoke evidence schema verified`
  generated:
  - `artifacts/planner-fallback-junit.xml`
  - `artifacts/cp4a-schema-junit.xml`
  - `artifacts/planner-fallback.log`
  - `artifacts/cp4a-smoke-evidence.json`

### Command 8 (CI-pinned smoke parity)
```bash
PLANNER_EXPECTED_TESTS=45 SCHEMA_EXPECTED_TESTS=48 bash scripts/smoke_planner_fallback_runbook.sh
```
- **Outcome:** **PASS**
- **Result:** pinned-expectation smoke pass with planner/fallback suite `45 passed in 1.96s`, schema enforcement suite `48 passed, 2 warnings in 6.61s`, and verifier summaries:
  - `planner: tests=45 failures=0 errors=0 skipped=0`
  - `schema: tests=48 failures=0 errors=0 skipped=0`
  - `smoke log signatures verified`
  - `cp4a smoke evidence status: pass`
  - `cp4a smoke evidence schema verified`

### Command 9 (negative control for strict summary assertions)
```bash
PLANNER_EXPECTED_TESTS='999' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```
- **Outcome:** **EXPECTED FAIL**
- **Result:** test suites pass (planner `45 passed in 2.02s`, schema `48 passed, 2 warnings in 6.43s`) but smoke exits with `EXIT:1` and verifier emits `planner: expected exactly 999 tests, got 45`

### Command 10 (negative control for malformed baseline)
```bash
tmp=$(mktemp); printf '{"planner_expected_tests":"bad"}\n' > "$tmp"; CP4A_SMOKE_BASELINE_PATH="$tmp" bash scripts/smoke_planner_fallback_runbook.sh; status=$?; echo EXIT:$status; rm -f "$tmp"
```
- **Outcome:** **EXPECTED FAIL**
- **Result:** validator emits `baseline field 'planner_expected_tests' must be an integer` and smoke exits with `EXIT:1` before planner/schema suite execution.

### Command 11 (negative control for smoke-signature verifier path)
```bash
TAXONOMY_EXPECTED_SUMMARY='__missing_taxonomy_signature__' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```
- **Outcome:** **EXPECTED FAIL**
- **Result:** test suites pass (planner `45 passed in 1.95s`, schema `48 passed, 2 warnings in 6.51s`) but smoke verifier emits `missing summary signature: __missing_taxonomy_signature__` and exits with `EXIT:1`.

### Command 12 (negative control for missing baseline file)
```bash
CP4A_SMOKE_BASELINE_PATH='/tmp/does-not-exist-cp4a-baseline.json' bash scripts/smoke_planner_fallback_runbook.sh; echo EXIT:$?
```
- **Outcome:** **EXPECTED FAIL**
- **Result:** smoke exits early with `baseline file not found: /tmp/does-not-exist-cp4a-baseline.json` and `EXIT:1` before planner/schema suite execution.

### Command 13 (CP4-A extension: research-manager envelope + contract suite)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_contract_schemas.py
```
- **Outcome:** **PASS**
- **Result:** `162 passed, 2 warnings in 7.35s`

### Command 14 (targeted planner/fallback regression re-check)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py
```
- **Outcome:** **PASS**
- **Result:** `45 passed in 2.00s`

### Command 15 (extended envelope error/success contract bundle)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_contract_schemas.py
```
- **Outcome:** **PASS**
- **Result:** `204 passed, 2 warnings in 7.72s`

### Command 16 (final envelope + CLI + contract bundle)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_cli.py tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_operation_error_dynamic_responses.py tests/test_contract_schemas.py
```
- **Outcome:** **PASS**
- **Result:** `224 passed, 2 warnings in 9.43s`

### Command 17 (targeted planner/fallback regression final)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py
```
- **Outcome:** **PASS**
- **Result:** `45 passed in 2.06s`

### Command 18 (envelope/contract/CLI latest)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_cli.py tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_operation_error_dynamic_responses.py tests/test_contract_schemas.py
```
- **Outcome:** **PASS**
- **Result:** `229 passed, 2 warnings in 8.89s`

### Command 19 (targeted planner/fallback latest)
```bash
PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py
```
- **Outcome:** **PASS**
- **Result:** `45 passed in 2.18s`

## Conclusion
CP4-A planner fallback/telemetry readiness is confirmed for repo-local router paths. Targeted planner/fallback tests, schema/routing parity tests, baseline-loader/taxonomy-sync/smoke-signature/early-fail-sequencing/evidence-export/evidence-schema regression tests, and runbook smoke tests all pass with repo-local evidence; strict negative controls still fail as expected and are covered in `tests/test_smoke_planner_fallback_runbook.py`. The operation-envelope path now also carries research-manager lifecycle operations with explicit write gating, strict session ID validation, atomic session writes, and session schema-version migration controls for local AAS orchestration without bypassing existing envelope contracts.

#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_DIR="${PLANNER_FALLBACK_ARTIFACT_DIR:-artifacts}"
JUNIT_XML="${PLANNER_FALLBACK_JUNIT_XML:-$ARTIFACT_DIR/planner-fallback-junit.xml}"
LOG_FILE="${PLANNER_FALLBACK_LOG:-$ARTIFACT_DIR/planner-fallback.log}"
SCHEMA_JUNIT_XML="${CP4A_SCHEMA_JUNIT_XML:-$ARTIFACT_DIR/cp4a-schema-junit.xml}"
EVIDENCE_JSON="${CP4A_SMOKE_EVIDENCE_JSON:-$ARTIFACT_DIR/cp4a-smoke-evidence.json}"
EVIDENCE_SCHEMA_PATH="${CP4A_SMOKE_EVIDENCE_SCHEMA_PATH:-contracts/cp4a.smoke-evidence.v1.schema.json}"
BASELINE_PATH="${CP4A_SMOKE_BASELINE_PATH:-docs/research/CP4A_SMOKE_BASELINE_2026-02-15.json}"

mkdir -p "$ARTIFACT_DIR"
mkdir -p "$(dirname "$JUNIT_XML")"
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$SCHEMA_JUNIT_XML")"
mkdir -p "$(dirname "$EVIDENCE_JSON")"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  PYTHON_BIN=python3
fi

if [[ ! -f "$BASELINE_PATH" ]]; then
  echo "baseline file not found: $BASELINE_PATH" >&2
  exit 1
fi

if ! BASELINE_OUTPUT="$(
  "$PYTHON_BIN" scripts/load_cp4a_smoke_baseline.py --baseline "$BASELINE_PATH"
)"; then
  exit 1
fi

readarray -t BASELINE_VALUES <<<"$BASELINE_OUTPUT"

BASELINE_PLANNER_EXPECTED_TESTS="${BASELINE_VALUES[0]}"
BASELINE_SCHEMA_EXPECTED_TESTS="${BASELINE_VALUES[1]}"
BASELINE_PLANNER_MIN_TESTS="${BASELINE_VALUES[2]}"
BASELINE_SCHEMA_MIN_TESTS="${BASELINE_VALUES[3]}"
BASELINE_SYNC_EXPECTED_SUMMARY="${BASELINE_VALUES[4]}"

PLANNER_EXPECTED_TESTS="${PLANNER_EXPECTED_TESTS:-$BASELINE_PLANNER_EXPECTED_TESTS}"
SCHEMA_EXPECTED_TESTS="${SCHEMA_EXPECTED_TESTS:-$BASELINE_SCHEMA_EXPECTED_TESTS}"
PLANNER_MIN_TESTS="${PLANNER_MIN_TESTS:-${BASELINE_PLANNER_MIN_TESTS:-1}}"
SCHEMA_MIN_TESTS="${SCHEMA_MIN_TESTS:-${BASELINE_SCHEMA_MIN_TESTS:-1}}"
SYNC_EXPECTED_SUMMARY="${SYNC_EXPECTED_SUMMARY:-${BASELINE_SYNC_EXPECTED_SUMMARY:-contract schemas are in sync}}"
TAXONOMY_EXPECTED_SUMMARY="${TAXONOMY_EXPECTED_SUMMARY:-routing taxonomy is in sync}"

if [[ -z "$PLANNER_EXPECTED_TESTS" || -z "$SCHEMA_EXPECTED_TESTS" ]]; then
  echo "baseline must provide planner_expected_tests and schema_expected_tests" >&2
  exit 1
fi

set -o pipefail
PLANNER_FALLBACK_JUNIT_XML="$JUNIT_XML" \
  bash scripts/run_planner_fallback_tests.sh | tee "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/sync_contract_schemas.py --check | tee -a "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/verify_routing_taxonomy_sync.py | tee -a "$LOG_FILE"

set -o pipefail
PYTHONPATH=. "$PYTHON_BIN" -m pytest --capture=no \
  tests/test_contract_schemas.py \
  tests/test_merlin_routing_contract.py \
  tests/test_export_cp4a_smoke_evidence.py \
  tests/test_verify_cp4a_smoke_evidence_schema.py \
  tests/test_sync_contract_schemas.py \
  tests/test_verify_junit_totals.py \
  tests/test_verify_routing_taxonomy_sync.py \
  tests/test_verify_smoke_log_signatures.py \
  --junitxml "$SCHEMA_JUNIT_XML" | tee -a "$LOG_FILE"

PLANNER_VERIFY_ARGS=(
  --junit "$JUNIT_XML"
  --label planner
  --min-tests "$PLANNER_MIN_TESTS"
)
if [[ -n "${PLANNER_EXPECTED_TESTS:-}" ]]; then
  PLANNER_VERIFY_ARGS+=(--expect-tests "$PLANNER_EXPECTED_TESTS")
fi

SCHEMA_VERIFY_ARGS=(
  --junit "$SCHEMA_JUNIT_XML"
  --label schema
  --min-tests "$SCHEMA_MIN_TESTS"
)
if [[ -n "${SCHEMA_EXPECTED_TESTS:-}" ]]; then
  SCHEMA_VERIFY_ARGS+=(--expect-tests "$SCHEMA_EXPECTED_TESTS")
fi

set -o pipefail
"$PYTHON_BIN" scripts/verify_junit_totals.py "${PLANNER_VERIFY_ARGS[@]}" | tee -a "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/verify_junit_totals.py "${SCHEMA_VERIFY_ARGS[@]}" | tee -a "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/verify_smoke_log_signatures.py \
  --log "$LOG_FILE" \
  --expect-summary "$SYNC_EXPECTED_SUMMARY" \
  --expect-summary "$TAXONOMY_EXPECTED_SUMMARY" \
  --require-file "$JUNIT_XML" \
  --require-file "$SCHEMA_JUNIT_XML" | tee -a "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/export_cp4a_smoke_evidence.py \
  --planner-junit "$JUNIT_XML" \
  --schema-junit "$SCHEMA_JUNIT_XML" \
  --smoke-log "$LOG_FILE" \
  --sync-summary "$SYNC_EXPECTED_SUMMARY" \
  --taxonomy-summary "$TAXONOMY_EXPECTED_SUMMARY" \
  --output "$EVIDENCE_JSON" | tee -a "$LOG_FILE"

set -o pipefail
"$PYTHON_BIN" scripts/verify_cp4a_smoke_evidence_schema.py \
  --schema-path "$EVIDENCE_SCHEMA_PATH" \
  --evidence "$EVIDENCE_JSON" | tee -a "$LOG_FILE"

test -s "$EVIDENCE_JSON"

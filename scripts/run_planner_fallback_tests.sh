#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  PYTHON_BIN=python3
fi

PYTEST_ARGS=(
  --capture=no
  tests/test_merlin_parallel_llm.py
  tests/test_merlin_streaming_llm.py
  tests/test_merlin_adaptive_llm.py
  tests/test_merlin_routing_contract.py
)

if [[ -n "${PLANNER_FALLBACK_JUNIT_XML:-}" ]]; then
  mkdir -p "$(dirname "$PLANNER_FALLBACK_JUNIT_XML")"
  PYTEST_ARGS+=(--junitxml "$PLANNER_FALLBACK_JUNIT_XML")
fi

PYTHONPATH=. "$PYTHON_BIN" -m pytest "${PYTEST_ARGS[@]}"

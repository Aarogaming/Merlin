# Contributing to Merlin

This guide mirrors the current local and CI quality gates.
For agent-focused handoff priorities and phased hardening status, see `docs/AGENT_TRANSITION.md`.

## Quick Path

Bootstrap:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Install `gitleaks` (required for hook + CI parity):

```bash
curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh -s -- -b "$HOME/.local/bin"
```

Run full local verification:

```bash
python scripts/check_secret_hygiene.py --all
python -m black --check \
  merlin_api_server.py \
  merlin_settings.py \
  merlin_rag.py \
  merlin_vector_memory.py \
  merlin_uaf_integration.py \
  merlin_uaf_endpoints.py \
  merlin_intelligence_integration.py \
  merlin_ipc_consumer.py \
  merlin_adaptive_llm.py \
  merlin_parallel_llm.py \
  merlin_metrics_dashboard.py \
  merlin_predictive_selection.py \
  merlin_cost_optimization.py \
  merlin_ab_testing.py \
  scripts/check_git_size.py \
  scripts/check_secret_hygiene.py \
  setup.py
python -m mypy
python -m pytest
```

For docs-only changes, you can skip `python -m pytest` if no code/test paths are touched.

## Full Gate Sequence

Run gates in this order for CI parity:

1. Gitleaks scan:

```bash
bash scripts/run_gitleaks_hook.sh
```

2. Secret hygiene guard:

```bash
python scripts/check_secret_hygiene.py --all
```

3. Black formatting check (current enforced scope):

```bash
python -m black --check \
  merlin_api_server.py \
  merlin_settings.py \
  merlin_rag.py \
  merlin_vector_memory.py \
  merlin_uaf_integration.py \
  merlin_uaf_endpoints.py \
  merlin_intelligence_integration.py \
  merlin_ipc_consumer.py \
  merlin_adaptive_llm.py \
  merlin_parallel_llm.py \
  merlin_metrics_dashboard.py \
  merlin_predictive_selection.py \
  merlin_cost_optimization.py \
  merlin_ab_testing.py \
  scripts/check_git_size.py \
  scripts/check_secret_hygiene.py \
  setup.py
```

4. Mypy type check:

```bash
python -m mypy
```

5. Pytest suite:

```bash
python -m pytest
```

## Hook Behavior

Pre-commit and pre-push hooks are configured in `.pre-commit-config.yaml`:

- `python3 scripts/check_git_size.py`
- `python3 scripts/check_secret_hygiene.py`
- `bash scripts/run_gitleaks_hook.sh`

Install hooks once per clone:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

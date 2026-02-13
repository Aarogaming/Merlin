# Merlin Agent Transition Runbook

Last updated: 2026-02-13

This file is the handoff point for the next engineer/agent working in this repo.
It focuses on current quality gates, recent hardening work, and what to do next.
For human contributor workflow, see `CONTRIBUTING.md`.
For inter-repo operation contracts and compatibility policy, see `docs/protocols/README.md`.

## Current Baseline

The current CI pipeline in `.github/workflows/ci.yml` runs:

1. `gitleaks` scan (quality + test jobs)
2. dependency install from `requirements-dev.txt`
3. secret hygiene guard (`python scripts/check_secret_hygiene.py --all`) in quality job
4. black formatting check on the enforced file list
5. mypy type check (`python -m mypy`) on the phased list in `mypy.ini`
6. pytest matrix on Python 3.10/3.11/3.12

Local pre-commit/pre-push hooks in `.pre-commit-config.yaml` run:

1. `scripts/check_git_size.py` (blocks staged files >100MB)
2. `scripts/check_secret_hygiene.py` (blocks sensitive/local-only filenames)
3. `scripts/run_gitleaks_hook.sh` (secret scan, staged for pre-commit and upstream range for pre-push when available)

## Quick Start (Local)

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Install `gitleaks` (required by hook + CI parity), for example:

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

For docs-only changes, `python -m pytest` can be skipped when no code/test paths are touched.

## Typed Scope (Current)

`mypy.ini` currently enforces type checks for:

1. `merlin_api_server.py`
2. `merlin_uaf_integration.py`
3. `merlin_uaf_endpoints.py`
4. `merlin_intelligence_integration.py`
5. `merlin_ipc_consumer.py`
6. `merlin_adaptive_llm.py`
7. `merlin_parallel_llm.py`
8. `merlin_metrics_dashboard.py`
9. `merlin_predictive_selection.py`
10. `merlin_cost_optimization.py`
11. `merlin_ab_testing.py`
12. `merlin_settings.py`
13. `merlin_rag.py`
14. `merlin_vector_memory.py`

## Gitleaks Notes

- Hook script: `scripts/run_gitleaks_hook.sh`
- Repo config: `.gitleaks.toml`
- Current allowlist is intentionally narrow (legacy doc-style auth header examples):
  - `AB_TESTING_COMPLETE.md`
  - `PARALLEL_LLM_README.md`

If more allowlist entries are needed, constrain by exact path/pattern and document why.

## Recently Completed Hardening

1. Added gitleaks scanning in CI.
2. Added strict local hooks for size/secrets/gitleaks.
3. Added phased mypy config and fixed typing issues in currently scoped modules.
4. Updated CI formatting/type/test gates to align with phased scope.
5. Added contributor-facing runbook in `CONTRIBUTING.md` mirroring local/CI gate sequence.
6. Added protocol baseline docs + schemas under `docs/protocols/` and `contracts/`.
7. Added initial envelope-based operation ingress in API (`POST /merlin/operations`) for chat/tools/command/plugins/search/RAG/voice/task/user-management/diagnostics/orchestration flows.
8. Added machine-readable operation capability manifest endpoint (`GET /merlin/operations/capabilities`).
9. Added schema validation tests for contract fixtures and capability manifest against `contracts/*.schema.json`.

## Highest-Priority Next Work

1. Expand envelope ingress coverage to remaining endpoints and standardize payloads across all existing API operations.
2. Add fixture coverage for all currently wired operations and validate live responses against schemas where stable.
3. Expand mypy scope to additional `merlin_*.py` modules in small batches, fixing issues as each batch is added.
4. Add/expand tests for `merlin_adaptive_llm.py`, `merlin_ab_testing.py`, and integration-heavy modules touched by typing work.
5. Add branch-protection requirements to enforce both CI jobs before merge (repo settings).
6. Tighten dependency hygiene (`requirements*.txt`) with explicit version policy and periodic updates.

## Execution Guidance for Next Agent

1. Start by running full local verification commands above.
2. Review `docs/protocols/` before changing cross-repo operations or payload formats.
3. Do not broaden allowlists before root-causing findings.
4. Keep mypy expansion incremental: add files to `mypy.ini`, fix, test, then commit.
5. Prefer CI parity when adding new local checks (same tools and invocation where practical).

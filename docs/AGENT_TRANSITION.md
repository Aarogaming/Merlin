# Merlin Agent Transition Runbook

Last updated: 2026-02-14

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
python scripts/run_release_checklist.py --strict
```

For docs-only changes, `python -m pytest` can be skipped when no code/test paths are touched.

Optional deeper release validation (includes schema sync + targeted checklist commands):

```bash
python scripts/run_release_checklist.py --run-commands --strict
```

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
15. `merlin_resource_api.py`
16. `merlin_resource_indexer.py`
17. `merlin_command_executor.py`
18. `merlin_file_manager.py`
19. `merlin_system_info.py`

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
10. Added request fixture coverage for all currently wired envelope operations and parity checks against supported-operation list.
11. Added unit tests for `merlin_ab_testing.py`, `merlin_adaptive_llm.py`, `merlin_rag.py`, and `merlin_vector_memory.py`.
12. Fixed A/B winner selection logic to score from computed variant stats in `ABTest.get_winner()`.
13. Added expected-response fixtures for all currently supported envelope operations.
14. Added a parameterized operation-contract test that validates fixture-backed live success responses against the operation envelope schema.
15. Added fixture-backed invalid-payload error cases covering all currently supported envelope operations.
16. Added a parameterized operation-contract test validating live error responses (status + error payload + schema) against the fixture cases.
17. Added fixture-backed operation-specific error cases (validation/auth/policy/backend/execution branches) for envelope operations with deterministic failure paths.
18. Added a parameterized operation-contract test that applies case-specific mocks and validates live error responses for those operation-specific failures.
19. Expanded deterministic error fixtures/tests to include command execution exceptions, plugin execution exceptions/failures, and voice output-missing failures.
20. Expanded `mypy` typed scope to include `merlin_resource_api.py` and `merlin_resource_indexer.py`.
21. Expanded envelope ingress coverage with `merlin.history.get`, `merlin.context.get`, `merlin.context.update`, `merlin.dynamic_components.list`, and `merlin.alerts.list`, plus request/success/error fixture coverage and schema-backed tests.
22. Expanded envelope ingress for LLM parallel/adaptive operations (`merlin.llm.parallel.status`, `merlin.llm.parallel.strategy`, `merlin.llm.adaptive.feedback`, `merlin.llm.adaptive.status`, `merlin.llm.adaptive.metrics`, `merlin.llm.adaptive.reset`) with success fixtures, invalid-payload matrix coverage, and specific-error cases.
23. Expanded envelope ingress for remaining LLM families (A/B, predictive, cost) with 17 new operations plus fixture-backed success/invalid-payload/specific-error coverage.
24. Added fixture-backed dynamic error coverage (`operation_error_dynamic.cases.json`) plus a parameterized contract test that supports regex/contains matching for variable error messages.
25. Expanded `mypy` typed scope to include `merlin_command_executor.py`, `merlin_file_manager.py`, and `merlin_system_info.py`.

## Highest-Priority Next Work

1. Standardize payload contracts across newly added LLM envelope operations (A/B, predictive, cost) and decide final cross-repo naming/versioning for any operation aliases.
2. Expand dynamic error fixture coverage to additional variable-message branches (for example, cross-service proxy failures) while keeping schema and code/retryable assertions strict.
3. Expand mypy scope to additional `merlin_*.py` modules in small batches, fixing issues as each batch is added.
4. Continue expanding tests for integration-heavy modules touched by typing work (A/B + adaptive + RAG + vector-memory unit coverage is now in place).
5. Add branch-protection requirements to enforce both CI jobs before merge (repo settings).
6. Tighten dependency hygiene (`requirements*.txt`) with explicit version policy and periodic updates.

## Execution Guidance for Next Agent

1. Start by running full local verification commands above.
2. Review `docs/protocols/` before changing cross-repo operations or payload formats.
3. Do not broaden allowlists before root-causing findings.
4. Keep mypy expansion incremental: add files to `mypy.ini`, fix, test, then commit.
5. Prefer CI parity when adding new local checks (same tools and invocation where practical).

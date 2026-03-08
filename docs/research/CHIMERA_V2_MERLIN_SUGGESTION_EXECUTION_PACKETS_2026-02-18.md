# Merlin Suggestion Execution Packets (2026-02-18)

Cycle: `CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15`
Scope: `Merlin/**` only

Use these packets to execute the prioritized suggestion tiers with exact command/result reporting.

## Packet A - API/Contract Reliability

- IDs: `S001`, `S003`, `S006`, `S007`, `S014`, `S020`
- Primary files: `merlin_api_server.py`, `merlin_settings.py`, `tests/test_merlin_api_server.py`, `tests/test_operation_error_responses.py`
- Required output: concrete code changes + targeted tests + one artifact under `docs/research/`

## Packet B - Routing/LLM Determinism

- IDs: `S024`, `S025`, `S026`, `S027`, `S033`, `S037`, `S038`
- Primary files: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`, `merlin_llm_backends.py`, `merlin_routing_contract.py`
- Required output: deterministic fallback reasons + streaming parser evidence + routing metadata assertions

## Packet C - Research Manager Advancement

- IDs: `S041`, `S042`, `S043`, `S046`, `S047`, `S053`
- Primary files: `merlin_research_manager.py`, `merlin_cli.py`, `tests/test_merlin_research_manager.py`, `tests/fixtures/contracts/*`
- Required output: lifecycle controls + conflict/evidence handling + contract fixtures

## Packet D - Platform/Plugin/Data

- IDs: `S061`, `S062`, `S065`, `S066`, `S069`, `S071`, `S073`, `S074`
- Primary files: `merlin_resource_indexer.py`, `merlin_watcher.py`, `merlin_plugin_manager.py`, `merlin_db.py`, `merlin_vector_memory.py`
- Required output: performance guardrails + manifest policy + migration safety checks

## Packet E - CI/Governance and Release Safety

- IDs: `S091`, `S092`, `S093`, `S094`, `S096`, `S099`, `S100`
- Primary files: `.pre-commit-config.yaml`, `mypy.ini`, `pytest.ini`, `.github/workflows/ci.yml`, `RUNBOOK.md`, `ARCHITECTURE.md`
- Required output: enforced quality gates + documented incident/architecture review cadence

## Return Format (required)

```text
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

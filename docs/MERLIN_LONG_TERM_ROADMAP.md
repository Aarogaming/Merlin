# Merlin Long-Term Roadmap (Approved Baseline)

Date: 2026-02-15
Scope: `AaroneousAutomationSuite/Merlin`
Status: Active (working plan)

## 1) Context: what already exists in this workspace

Merlin already contains an implemented DMS path with safe fallback and tests:

- Settings/env: `merlin_settings.py`
  - `DMS_ENABLED`, `DMS_URL`, `DMS_MODEL`, `DMS_API_KEY`, `DMS_MIN_PROMPT_CHARS`, `DMS_TASK_TYPES`
- Backends:
  - `merlin_llm_backends.py` (single backend mode + DMS call path + fallback)
  - `merlin_adaptive_llm.py` (routing + metadata + A/B)
  - `merlin_parallel_llm.py` (routing + metadata + A/B)
  - `merlin_streaming_llm.py` (routing + metadata + A/B)
- Tests:
  - `tests/test_merlin_adaptive_llm.py`
  - `tests/test_merlin_parallel_llm.py`
  - `tests/test_merlin_streaming_llm.py`
  - `tests/test_merlin_llm_backends.py`

Research and governance constraints already present:

- `docs/dms_research_notes.md` (method stability notes + P0/P1/P2 ideas)
- `../docs/ROADMAP.md` (AAS master roadmap)
- `../docs/planning/DECISIONS.md` (`O0.1` resource-aware routing is allowed, with policy and auditability)

## 2) Roadmap principles (pre-vetted and enforced)

1. **No regressions in existing backends first**
   - Keep `ollama`, `openai`, `huggingface`, and `lmstudio`/`nemotron`/`glm` behaviors unchanged.
2. **DMS is optional and reversible**
   - Explicit env gate (`DMS_ENABLED`) controls activation.
3. **Fallback is default-safe**
   - DMS unavailability or parse failures must route to existing logic and log `fallback_reason`.
4. **Measure every routing change**
   - `selected_model`, `prompt_size_bucket`, `dms_used`, `fallback_reason` remain part of response metadata.
5. **Policy-first evolution**
   - Routing decisions must be logged and auditable, and always support a CPU/debug only safe mode.

## 3) 12-Month plan (8+ agent parallelization)

Use 4 quarters with 8+ agents split across independent workstreams.

### Quarter 1 (Months 1-3): Stability and Determinism
- DMS hardening:
  - explicit health probe with `up`, `latency_ms`, `error_reason`
  - deterministic fallback_reason taxonomy
  - guardrails for missing/invalid `DMS_URL` and `DMS_MODEL`
- Test suite expansion:
  - malformed OpenAI-compatible payloads
  - missing config paths
  - timeout and transport error fallback behavior
  - explicit routing metadata assertions
- Docs and onboarding:
  - `.env.example` coverage parity
  - rollout/rollback runbook
- Exit criteria:
  - `DMS_ENABLED=false` test suite unchanged and green
  - `fallback_reason` always populated on DMS failures

### Quarter 2 (Months 4-6): Throughput and Reliability
- Routing control:
  - DMS circuit breaker on consecutive failures
  - configurable policy object for prompt/task thresholds
  - per-minute throughput and rolling error-rate counters in all three routers
- Cross-router parity:
  - compare metadata and behavior between adaptive/parallel/streaming
- Exit criteria:
  - <1% routing exception rate under controlled fault injection
  - no regressions for non-DMS backends in smoke tests

### Quarter 3 (Months 7-9): Governance and A/B Evidence
- A/B control hardening:
  - auto-pause of control variants on error/quality regression
  - minimum sample and minimum window before policy shifts
- Quality/latency instrumentation:
  - route-level dashboards for `dms` / `control` / `disabled`
- Cost visibility:
  - cost/throughput by route and prompt_bucket
- Exit criteria:
  - stable 95% confidence band before any routing auto-adjustment
  - route-level deltas published at least daily

### Quarter 4 (Months 10-12): Optimization and Self-Protection
- Cost-aware routing:
  - upstream context hints (complexity, estimated token budget)
  - optional hint-first routing where high-cost/low-value tasks stay on control
- Policy lifecycle:
  - versioned routing policy + startup snapshot events
  - one-command rollback that disables DMS and restores last-good policy
- Audit and hardening:
  - weekly policy drift checks
  - documented emergency procedure and post-incident checklist
- Exit criteria:
  - demonstrated measurable latency/quality/cost improvement versus baseline
  - rollback path tested in staging with recovery under 2 minutes

## 4) Parallel workstream model (8 agents)

1. DMS Transport & Health (1 agent): transport adapters, auth, retries, probe endpoints.
2. Routing Core (2 agents): adaptive/parallel/streaming route policy engine and bucket logic.
3. Quality + Metrics (1 agent): `routing_metrics`, A/B aggregates, quality score normalization.
4. Fallback + Safety (1 agent): fallback_reason taxonomy, circuit breakers, safe controls.
5. Testing (2 agents): unit tests, fault injection harness, long-run simulation tests.
6. Docs + Operations (1 agent): runbooks, docs updates, onboarding and migration notes.

## 5) Work packet template per session

For each batch, capture:
- Owner agent and workstream
- Scope (files and function names)
- Behavioral contract change
- Validation commands + pass/fail
- Rollback step if needed
- Handoff notes for next agent

## 6) Runbook template for extended development windows

Use this for long autonomous sessions:

1. `git status`, `git branch`, and `git log --oneline -n 20`.
2. Run full preflight gate:
   - `python scripts/check_secret_hygiene.py --all`
   - `python -m mypy`
   - `python -m pytest` (targeted to modified modules if needed)
3. Keep changes in bounded batches no larger than one routing/quality concern per batch.
4. For every batch produce:
   - changed files
   - impact scope
   - validation command and result
5. Pause long sessions on any hard regression:
   - test failure in existing backend tests
   - fallback metadata regression (`fallback_reason` missing when DMS fails)
   - unbounded throughput drop in `routing_metrics`

## 7) Immediate next checkpoints (next 2 sessions)

- [ ] Implement one explicit DMS health/ping result metric and tests.
- [ ] Add one policy constant for fallback reason codes and assertions.
- [ ] Add lightweight runbook section to docs for "enable/disable DMS safely in production-like usage."
- [ ] Add a weekly gate dashboard for route deltas and stop condition thresholds.

## 8) Current sample behavior (already validated)

- DMS should be chosen for:
  - long prompts (`len(prompt) >= DMS_MIN_PROMPT_CHARS`)
  - reasoning task types in `DMS_TASK_TYPES`
- Non-reasoning/short prompts should continue on existing adaptive/parallel/streaming logic with metadata marking.
- Failures should never block request completion because fallback routes to current stable backends.

## 9) Quarterly Architecture Drift Review Plan

Cadence:

- Run a formal architecture drift review at the start of each quarter.
- Record outcomes and follow-up owners in the tracked actions table below.

Checklist baseline:

1. Contract and protocol parity (`contracts/*`, `docs/protocols/*`, operation fixtures).
2. Routing and fallback taxonomy consistency (enum + schema + tests).
3. Optional dependency resilience (local environments without full dependency set).
4. Quality-gate alignment (pre-commit, release checklist, CI contract tests).
5. Incident readiness (API/routing/plugin/research-manager runbook templates current).

Tracked actions:

| Quarter | Action | Owner | Target date | Status |
| --- | --- | --- | --- | --- |
| 2026-Q1 | Validate release checklist + pre-commit contract gates against current env constraints. | merlin-agent | 2026-03-15 | in_progress |
| 2026-Q1 | Complete frontend contract-client drift prevention design pass (typed contract generation). | merlin-agent | 2026-03-31 | pending |
| 2026-Q1 | Publish quarterly incident drill evidence for API/routing/plugins/research-manager paths. | merlin-agent | 2026-03-31 | pending |

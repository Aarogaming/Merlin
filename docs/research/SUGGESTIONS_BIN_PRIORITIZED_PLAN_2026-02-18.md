# Suggestions Bin Prioritized Plan (2026-02-18)

Source sweep: `docs/research/SUGGESTIONS_BIN.md` (`Pass 3 - Repo-Specific Suggestion Sweep (Target 100)`)

## Tier Counts

- Top 15: immediate execution candidates
- Next 35: near-term planned queue
- Later 50: backlog for staged cycles

## Top 15 (Immediate)

- `S001` Add centralized operation-envelope request validation middleware to remove repeated schema checks (targets: `merlin_api_server.py`, `contracts/aas.operation-envelope.v1.schema.json`).
- `S003` Enforce bounded payload-size limits per operation to prevent oversized body abuse (targets: `merlin_api_server.py`, `merlin_settings.py`).
- `S006` Add per-operation latency percentiles (p50/p95/p99) in API status output (targets: `merlin_api_server.py`, `merlin_metrics_dashboard.py`).
- `S007` Split error taxonomy into transport, validation, auth, dependency, and policy classes (targets: `merlin_api_server.py`, `tests/test_operation_error_responses.py`).
- `S014` Add per-operation rate limiting with clear retry hints (targets: `merlin_api_server.py`, `merlin_policy.py`).
- `S020` Add endpoint conformance runner that validates request/response against fixture contracts (targets: `tests/test_operation_expected_responses.py`, `tests/fixtures/contracts`).
- `S024` Move fallback reason strings to a shared enum module to prevent drift (targets: `merlin_routing_contract.py`, `merlin_adaptive_llm.py`).
- `S025` Centralize route-policy logic into one helper used by adaptive/parallel/streaming backends (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`).
- `S026` Make A/B assignment deterministic per conversation or correlation hash (targets: `merlin_ab_testing.py`, `merlin_adaptive_llm.py`).
- `S027` Build explicit SSE parser state machine to handle comments/heartbeat/[DONE] frames (targets: `merlin_streaming_llm.py`, `tests/test_merlin_streaming_llm.py`).
- `S033` Add early-cancel for losing branches in parallel model execution (targets: `merlin_parallel_llm.py`, `tests/test_merlin_parallel_llm.py`).
- `S037` Add automatic DMS disable/enable policy based on rolling error budget (targets: `merlin_adaptive_llm.py`, `merlin_settings.py`).
- `S041` Add session TTL and archival policy for old research-manager sessions (targets: `merlin_research_manager.py`, `merlin_settings.py`).
- `S065` Enforce plugin manifest schema validation before plugin load (targets: `merlin_plugin_manager.py`, `plugins/*/manifest.json`).
- `S093` Add coverage gate for critical modules (API, routing, research manager) (targets: `pytest.ini`, `.github/workflows/ci.yml`).

## Next 35 (Near-Term)

- `S002` Add schema-version negotiation and explicit downgrade errors for incompatible envelopes (targets: `merlin_api_server.py`, `docs/protocols/operation-envelope-v1.md`).
- `S004` Require `correlation_id` for all mutating operations and return deterministic validation errors when absent (targets: `merlin_api_server.py`, `tests/test_merlin_api_server.py`).
- `S005` Add optional `Idempotency-Key` handling for safe retry of create/update style operations (targets: `merlin_api_server.py`, `docs/protocols/operation-envelope-v1.md`).
- `S008` Add startup contract self-check that fails fast when required schemas are missing (targets: `merlin_api_server.py`, `scripts/sync_contract_schemas.py`).
- `S009` Add endpoint to expose active capability flags with source (env/default/runtime) for debugging (targets: `merlin_api_server.py`, `docs/protocols/repo-capabilities-merlin-v1.md`).
- `S010` Add API deprecation headers for operations planned for replacement (targets: `merlin_api_server.py`, `docs/protocols/compatibility-policy.md`).
- `S011` Add OpenAPI-like exported spec snapshot for public Merlin operations (targets: `merlin_api_server.py`, `docs/protocols/README.md`).
- `S012` Add operation replay diagnostics endpoint gated to local debug mode (targets: `merlin_api_server.py`, `merlin_settings.py`).
- `S013` Add strict auth key rotation support with hot reload (targets: `merlin_auth.py`, `merlin_api_server.py`).
- `S015` Add request audit metadata contract (`request_id`, `route`, `decision_version`) (targets: `merlin_api_server.py`, `merlin_audit.py`).
- `S016` Add endpoint-level circuit breaker integration for unstable dependencies (targets: `merlin_api_server.py`, `merlin_self_healing.py`).
- `S017` Add structured access logs with redaction of prompt/content fields (targets: `merlin_logger.py`, `merlin_api_server.py`).
- `S018` Add HTTP timeout and keep-alive tuning defaults for production-like local loads (targets: `merlin_api_server.py`, `docker-compose.yml`).
- `S019` Add operation-level feature flags for safer phased rollouts (targets: `merlin_settings.py`, `merlin_api_server.py`).
- `S021` Replace character-based prompt buckets with optional token-aware buckets (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`).
- `S022` Add DMS cold-start warmup request and expose readiness state (targets: `merlin_llm_backends.py`, `merlin_settings.py`).
- `S023` Add per-model timeout matrix (`short`, `medium`, `long`) (targets: `merlin_settings.py`, `merlin_llm_backends.py`).
- `S028` Capture time-to-first-token and stream completion latency for streamed routes (targets: `merlin_streaming_llm.py`, `merlin_metrics_dashboard.py`).
- `S029` Add quality-scoring hook interface to compare DMS vs control responses (targets: `merlin_adaptive_llm.py`, `merlin_quality_gates.py`).
- `S030` Add cached-prefix prompt construction helper for repeated system prompts (targets: `merlin_llm_backends.py`, `merlin_settings.py`).
- `S031` Add ultra-fast short-prompt lane that bypasses heavy routing checks (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`).
- `S032` Add prompt truncation + warning metadata for near-token-limit requests (targets: `merlin_llm_backends.py`, `merlin_routing_contract.py`).
- `S034` Add shared retry/backoff utility with jitter and retry budget caps (targets: `merlin_utils.py`, `merlin_llm_backends.py`).
- `S035` Add route policy version stamp in every routing metadata payload (targets: `merlin_routing_contract.py`, `merlin_adaptive_llm.py`).
- `S036` Add router regression corpus with expected model selections (targets: `tests/test_merlin_adaptive_llm.py`, `tests/test_merlin_parallel_llm.py`).
- `S038` Normalize usage parsing across OpenAI-compatible providers (`usage`, `cached_tokens`) (targets: `merlin_llm_backends.py`, `tests/test_merlin_llm_backends.py`).
- `S039` Add provider response normalization layer before scoring/metadata emission (targets: `merlin_llm_backends.py`, `merlin_routing_contract.py`).
- `S040` Add safety pre-check stage for high-risk prompts before model dispatch (targets: `merlin_policy.py`, `merlin_adaptive_llm.py`).
- `S042` Add provenance fields (`created_by`, `source_operation`, `policy_version`) on research sessions (targets: `merlin_research_manager.py`, `merlin_api_server.py`).
- `S043` Add confidence calibration helper for signal scoring (targets: `merlin_research_manager.py`, `tests/test_merlin_research_manager.py`).
- `S044` Version brief output templates so brief schema changes stay traceable (targets: `merlin_research_manager.py`, `docs/protocols/operation-envelope-v1.md`).
- `S045` Add explicit audit entries for read-only mode rejections (targets: `merlin_research_manager.py`, `merlin_audit.py`).
- `S046` Add signal deduplication by stable claim hash to reduce noisy evidence (targets: `merlin_research_manager.py`, `merlin_utils.py`).
- `S047` Track contradictory signals and expose conflict counts in briefs (targets: `merlin_research_manager.py`, `tests/test_merlin_research_manager.py`).
- `S053` Expand operation contract fixtures for all research-manager success and error variants (targets: `tests/fixtures/contracts`, `tests/test_operation_expected_responses.py`).

## Later 50 (Backlog)

- `S048` Add causal chain rendering in brief output for hypothesis evidence links (targets: `merlin_research_manager.py`, `merlin_cli.py`).
- `S049` Add export/import CLI for research sessions to JSON snapshots (targets: `merlin_cli.py`, `merlin_research_manager.py`).
- `S050` Add session tagging and topic search filters in API/CLI (targets: `merlin_research_manager.py`, `merlin_cli.py`).
- `S051` Add batch-mode CLI commands for repeated research operations (targets: `merlin_cli.py`, `tests/test_merlin_cli.py`).
- `S052` Add webhook/event emitter for research session updates (targets: `merlin_research_manager.py`, `merlin_hub_client.py`).
- `S054` Add cursor-based pagination for large research session lists (targets: `merlin_research_manager.py`, `merlin_api_server.py`).
- `S055` Add search endpoint for research sessions by objective keyword (targets: `merlin_api_server.py`, `merlin_research_manager.py`).
- `S056` Add optional background summarization queue for expensive brief generation (targets: `merlin_research_manager.py`, `merlin_tasks.py`).
- `S057` Add risk-scoring rubric fields (`impact`, `uncertainty`, `time_horizon`) in session schema (targets: `merlin_research_manager.py`, `docs/research/*`).
- `S058` Link research sessions to task IDs and planner artifacts for traceability (targets: `merlin_tasks.py`, `merlin_research_manager.py`).
- `S059` Ingest planner fallback telemetry as structured research signals automatically (targets: `merlin_quality_gates.py`, `merlin_research_manager.py`).
- `S060` Add CLI command to generate CP packet skeletons from session briefs (targets: `merlin_cli.py`, `docs/research`).
- `S061` Add incremental hashing index updates for resource files to reduce full rescans (targets: `merlin_resource_indexer.py`, `plugins/resource_indexer/plugin.py`).
- `S062` Add debounce/backpressure controls in file watching to prevent thrash (targets: `merlin_watcher.py`, `merlin_resource_indexer.py`).
- `S063` Add retrieval relevance diagnostics (`top_k_hit_rate`, `source_diversity`) for RAG queries (targets: `merlin_rag.py`, `tests/test_merlin_rag.py`).
- `S064` Normalize citation format for RAG responses with deterministic source IDs (targets: `merlin_rag.py`, `merlin_routing_contract.py`).
- `S066` Add plugin permission tiers (`read`, `write`, `network`, `exec`) with policy checks (targets: `merlin_plugin_manager.py`, `merlin_policy.py`).
- `S067` Add plugin execution timeout budgets and cancellation hooks (targets: `merlin_plugin_manager.py`, `merlin_tasks.py`).
- `S068` Add plugin dependency compatibility checker in startup preflight (targets: `merlin_plugin_manager.py`, `scripts/check_secret_hygiene.py`).
- `S069` Add plugin crash isolation and auto-restart with capped retries (targets: `merlin_plugin_manager.py`, `merlin_self_healing.py`).
- `S070` Add plugin catalog API filters by capability and health state (targets: `merlin_plugin_manager.py`, `merlin_api_server.py`).
- `S071` Add vector memory compaction and stale-vector cleanup routine (targets: `merlin_vector_memory.py`, `tests/test_merlin_vector_memory.py`).
- `S072` Add vector-memory integrity checker script for index consistency (targets: `merlin_vector_memory.py`, `scripts/`).
- `S073` Add schema migration utility for Merlin DB with rollback support (targets: `merlin_db.py`, `merlin_backup.py`).
- `S074` Tune SQLite pragmas and WAL settings for better concurrent read/write behavior (targets: `merlin_db.py`, `merlin_settings.py`).
- `S075` Add cache eviction telemetry and hit-rate metrics per cache namespace (targets: `merlin_cache.py`, `merlin_metrics_dashboard.py`).
- `S076` Add backup integrity hash + verify command for archive confidence (targets: `merlin_backup.py`, `merlin_backup_to_drive.py`).
- `S077` Add restore smoke test command to validate backup usability (targets: `merlin_backup.py`, `merlin_cli.py`).
- `S078` Add schema version field in user profile JSON and migration helper (targets: `merlin_user_manager.py`, `merlin_users.json`).
- `S079` Add voice benchmark dataset versioning and provenance fields (targets: `merlin_voice_benchmark.py`, `merlin_voice_sources.json`).
- `S080` Add deterministic fallback-to-text metadata when voice routes fail (targets: `merlin_voice_router.py`, `merlin_voice.py`).
- `S081` Generate typed frontend client contracts from operation fixtures to prevent drift (targets: `frontend/src/services`, `tests/fixtures/contracts`).
- `S082` Add dashboard panel for fallback taxonomy counts and trend lines (targets: `frontend/src/components/AgentAnalytics.tsx`, `frontend/src/components/PluginAnalytics.tsx`).
- `S083` Add research-manager session explorer page in frontend (targets: `frontend/src/pages`, `frontend/src/services/onboarding.ts`).
- `S084` Add command palette for operation discovery and quick execution (targets: `frontend/src/App.tsx`, `frontend/src/components`).
- `S085` Run responsive layout audit and fix overflow issues on narrow widths (targets: `frontend/src/components/*.css`, `frontend/src/index.css`).
- `S086` Add frontend bundle-size budget check in CI (targets: `frontend/scripts/check-dist-size.js`, `.github/workflows/ci.yml`).
- `S087` Add Tauri crash reporting hook with local opt-in upload (targets: `frontend/src-tauri/src/main.rs`, `frontend/src-tauri/tauri.conf.json`).
- `S088` Add user-facing retry guidance for fallback cases in UI responses (targets: `frontend/src/components/SnapshotSummary.tsx`, `frontend/src/components/SystemInfo.tsx`).
- `S089` Add accessibility pass for keyboard nav, labels, and contrast in core components (targets: `frontend/src/components`, `frontend/src/pages/Onboarding.tsx`).
- `S090` Consolidate theme variables and remove duplicated style tokens (targets: `frontend/src/index.css`, `frontend/src/components/*.css`).
- `S091` Add pre-commit tasks for schema sync, lint, and targeted contract tests (targets: `.pre-commit-config.yaml`, `scripts/sync_contract_schemas.py`).
- `S092` Roll out stricter `mypy` config in phases by module criticality (targets: `mypy.ini`, `merlin_api_server.py`, `merlin_llm_backends.py`).
- `S094` Add CI secret-scan policy report artifact and fail conditions (targets: `scripts/check_secret_hygiene.py`, `.github/workflows/ci.yml`).
- `S095` Add dependency vulnerability scan and weekly report generation (targets: `requirements.txt`, `.github/workflows/ci.yml`).
- `S096` Add release checklist automation script for artifacts/contracts/tests (targets: `scripts/`, `docs/AGENT_TRANSITION.md`).
- `S097` Add changelog generation pipeline from tagged commits (targets: `setup.py`, `README.md`, `.github/workflows/ci.yml`).
- `S098` Add standardized benchmark command pack for local performance snapshots (targets: `merlin_benchmark.py`, `scripts/`).
- `S099` Add incident runbook templates per subsystem (API, routing, plugins, research manager) (targets: `RUNBOOK.md`, `docs/research`).
- `S100` Add quarterly architecture drift review checklist with tracked actions (targets: `ARCHITECTURE.md`, `docs/MERLIN_LONG_TERM_ROADMAP.md`).

## Execution Wave Packetization

1. Wave 1 (S001-S020 focus): API contract hardening + error taxonomy + coverage gate (`S001`, `S003`, `S006`, `S007`, `S014`, `S020`, `S093`).
2. Wave 2 (routing core): deterministic routing policy, fallback taxonomy normalization, and streaming reliability (`S024`, `S025`, `S026`, `S027`, `S033`, `S037`).
3. Wave 3 (research manager + platform): session lifecycle, plugin contract enforcement, and backlog indexing (`S041`, `S065`, plus Next 35 carry-ins).

Machine-readable matrix: `docs/research/SUGGESTIONS_BIN_PRIORITY_MATRIX_2026-02-18.json`

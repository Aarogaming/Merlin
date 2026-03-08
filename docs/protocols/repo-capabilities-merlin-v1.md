# Merlin Repo Capabilities v1

This document is the Merlin-facing operation contract baseline for other AAS repos and IDE agents.
It is aligned with `aas-plugin.json` capability names.

## Service Identity

- Repo: `AaroneousAutomationSuite/Merlin`
- Service entry: `merlin_api_server.py`
- Primary interface: HTTP (`http://localhost:8001` in local/dev)
- Capability manifest endpoint: `GET /merlin/operations/capabilities`
- Capability flag diagnostics endpoint: `GET /merlin/operations/capability-flags`
- Replay diagnostics endpoint (debug-gated): `GET /merlin/operations/replay-diagnostics`

## Supported Capability Names

1. `assistant.chat`
2. `assistant.tools`
3. `merlin.rag`
4. `merlin.voice`
5. `merlin.resource_indexer`
6. `merlin.tasks`
7. `merlin.tools`
8. `merlin.user_manager`
9. `merlin.research.manager`

## Operation Naming Convention

Use dot-delimited names: `<capability>.<action>`.

Examples:

- `assistant.chat.request`
- `assistant.tools.execute`
- `merlin.rag.query`
- `merlin.resource_indexer.refresh`

## Minimum Operation Contract

All cross-repo calls to Merlin should use `AAS.OperationEnvelope@1.0.0` and include:

1. Stable operation name + version.
2. Explicit timeout.
3. Idempotency key for writes/mutations.
4. Correlation and trace ids.

## Current Implementation Slice

- Envelope ingress endpoint: `POST /merlin/operations`
- Currently wired operations:
  - `assistant.chat.request`
  - `assistant.tools.execute`
  - `merlin.alerts.list`
  - `merlin.aas.create_task`
  - `merlin.command.execute`
  - `merlin.context.get`
  - `merlin.context.update`
  - `merlin.discovery.run`
  - `merlin.discovery.queue.status`
  - `merlin.discovery.queue.drain`
  - `merlin.discovery.queue.pause`
  - `merlin.discovery.queue.resume`
  - `merlin.discovery.queue.purge_deadletter`
  - `merlin.dynamic_components.list`
  - `merlin.genesis.logs`
  - `merlin.genesis.manifest`
  - `merlin.history.get`
  - `merlin.llm.ab.complete`
  - `merlin.llm.ab.create`
  - `merlin.llm.ab.get`
  - `merlin.llm.ab.list`
  - `merlin.llm.ab.result`
  - `merlin.llm.adaptive.feedback`
  - `merlin.llm.adaptive.metrics`
  - `merlin.llm.adaptive.reset`
  - `merlin.llm.adaptive.status`
  - `merlin.llm.cost.budget.get`
  - `merlin.llm.cost.budget.set`
  - `merlin.llm.cost.optimization.get`
  - `merlin.llm.cost.pricing.set`
  - `merlin.llm.cost.report`
  - `merlin.llm.cost.thresholds.get`
  - `merlin.llm.cost.thresholds.set`
  - `merlin.llm.parallel.status`
  - `merlin.llm.parallel.strategy`
  - `merlin.llm.predictive.export`
  - `merlin.llm.predictive.feedback`
  - `merlin.llm.predictive.models`
  - `merlin.llm.predictive.select`
  - `merlin.llm.predictive.status`
  - `merlin.plugins.list`
  - `merlin.plugins.execute`
  - `merlin.research.manager.session.create`
  - `merlin.research.manager.sessions.list`
  - `merlin.research.manager.session.get`
  - `merlin.research.manager.session.signal.add`
  - `merlin.research.manager.brief.get`
  - `merlin.knowledge.search`
  - `merlin.rag.query`
  - `merlin.search.query`
  - `merlin.system_info.get`
  - `merlin.tasks.create`
  - `merlin.tasks.list`
  - `merlin.user_manager.authenticate`
  - `merlin.user_manager.create`
  - `merlin.voice.status`
  - `merlin.voice.synthesize`
  - `merlin.voice.listen`
  - `merlin.voice.transcribe`
- Current response operation shape: `<operation>.result`

## Response Expectations

- Successful responses return the same `correlation_id`.
- Failures must include structured error payload (`code`, `message`, `retryable`).
- Dependency-backed operations can return `DEPENDENCY_CIRCUIT_OPEN` when endpoint-level
  circuit protection is active after repeated upstream failures.
- Plugin execution operations (`assistant.tools.execute`, `merlin.plugins.execute`)
  enforce manifest permission tiers (`read`, `write`, `network`, `exec`) and can return
  `PLUGIN_PERMISSION_DENIED` in restricted/safe execution modes.
  - Plugin runs also enforce timeout budgets and can return `PLUGIN_TIMEOUT` (`retryable=true`).
  - Plugin crashes are isolated with capped auto-restart attempts; exhausted budgets return
    `PLUGIN_CRASH_ISOLATED` (`retryable=true`).
- Packaged plugins run dependency compatibility preflight at startup/load:
  - optional manifest `dependencies[]` entries support `version` as `*`, exact semver,
    `==semver`, or `>=semver`.
  - incompatible/missing dependencies keep the plugin unloaded.
- Plugin crash auto-restart budget is controlled by `MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS`.
- Plugin catalog queries support filtering by:
  - `capability` (exact capability name match)
  - `health_state` (`healthy`, `degraded`, `isolated`)
- Unknown extra fields in payloads should be ignored by consumers unless explicitly marked required by operation version.
- Research manager mutation operations can return `RESEARCH_MANAGER_READ_ONLY` when write mode is disabled (for example via `MERLIN_RESEARCH_MANAGER_READ_ONLY=1`).
- Research manager operations that accept `session_id` require `[A-Za-z0-9_-]{1,128}`; invalid IDs return `VALIDATION_ERROR`.
- `merlin.research.manager.session.create` accepts optional traceability fields:
  - `linked_task_ids` (positive integer task IDs)
  - `planner_artifacts` (planner packet/document refs)
- `assistant.chat.request` can include `research_session_id` (string); when paired with
  `include_metadata=true`, Merlin attempts automatic planner fallback telemetry ingestion
  into the linked research session and returns `payload.research_signal_ingest`.
- Circuit-breaker behavior is controlled by:
  - `MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED`
  - `MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
  - `MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS`

## Capability Flag Diagnostics

- `GET /merlin/operations/capability-flags` returns runtime capability flags for debugging.
- Operation rollout flags are controlled by `MERLIN_OPERATION_FEATURE_FLAGS` (`operation=enabled|disabled`) and are reflected in diagnostics payloads.
- Response shape:
  - `schema_name`: `AAS.RepoCapabilityFlags`
  - `schema_version`: `1.0.0`
  - `flags[]`: `{ name, value, source, details? }`
- `source` semantics:
  - `env`: value currently driven by an environment variable override.
  - `default`: value is from the built-in default path.
  - `runtime`: value comes from live in-memory state and may change without process restart.

## Replay Diagnostics

- `GET /merlin/operations/replay-diagnostics` exposes current idempotency replay-cache rows for local debugging.
- Endpoint is disabled by default and returns `404` unless `MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED=true`.
- Response includes masked idempotency key previews, status code, and cache entry age.

## Non-Goals

- This doc does not define frontend UI protocol details.
- This doc does not replace per-feature API documentation; it defines baseline inter-repo operation framing.

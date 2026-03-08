# AAS Operation Envelope v1

`schema_name`: `AAS.OperationEnvelope`  
`schema_version`: `1.0.0`

This envelope wraps cross-repo requests and events so Merlin and peers can communicate with shared tracing, retries, and compatibility metadata.

## Required Fields

- `schema_name`: must be `AAS.OperationEnvelope`
- `schema_version`: contract version (`1.0.0`)
- `message_id`: unique message UUID
- `trace_id`: distributed trace UUID
- `timestamp_utc`: ISO-8601 UTC timestamp
- `source`: sender identity
- `target`: intended receiver identity
- `operation`: operation metadata
- `payload`: operation body

## Envelope Shape

```json
{
  "schema_name": "AAS.OperationEnvelope",
  "schema_version": "1.0.0",
  "message_id": "5de2f11e-6ff0-4dc6-b241-3e00edbdfed5",
  "correlation_id": "f2c95520-6e66-4a56-ae9e-5c9497ce2e8b",
  "causation_id": "2fdbf8ca-a620-445f-a6c8-101bdb9b437d",
  "trace_id": "8c25874f-08f3-4948-b031-451de59c151f",
  "timestamp_utc": "2026-02-13T02:30:00Z",
  "source": {
    "repo": "AaroneousAutomationSuite/Merlin",
    "component": "merlin_api_server",
    "agent_runtime": "codex",
    "editor": "vscode"
  },
  "target": {
    "repo": "AaroneousAutomationSuite/Hub",
    "component": "hub_orchestrator"
  },
  "operation": {
    "name": "assistant.chat.request",
    "version": "1.0.0",
    "timeout_ms": 30000,
    "idempotency_key": "chat-req-2026-02-13-0001",
    "expects_ack": true,
    "retry": {
      "max_attempts": 2
    }
  },
  "payload": {
    "user_id": "local-user",
    "prompt": "Summarize latest module health."
  },
  "metadata": {
    "priority": "normal"
  }
}
```

## Field Notes

- `correlation_id`: ties request/response chain together.
- `correlation_id`: required for mutating operations (for example: `*.create`, `*.update`, `*.set`, `*.execute`).
- `causation_id`: parent message id when this is produced by another operation.
- `idempotency_key`: required for mutating operations.
- `expects_ack`: `true` for request/response flows, optional for fire-and-forget events.
- `retry.max_attempts`: must stay bounded to avoid runaway loops.

## Idempotency Handling

- For create/update-style operations, `operation.idempotency_key` is required.
- Merlin caches result envelopes by `(operation.name, idempotency_key)` for bounded safe retry handling.
- Replayed responses include header `X-Merlin-Idempotent-Replay: true`.

## Schema Version Negotiation

- Merlin currently supports envelope schema version `1.0.0`.
- `schema_version` must be semver (`X.Y.Z`).
- When version negotiation fails:
  - Newer-than-supported envelope version -> `SCHEMA_VERSION_DOWNGRADE_REQUIRED`
  - Older-than-supported envelope version -> `SCHEMA_VERSION_UPGRADE_REQUIRED`
  - Non-semver value -> `INVALID_SCHEMA_VERSION`

## Planner Routing Metadata (CP4-A)

When `assistant.chat.result` includes planner/routing telemetry, place it under
`payload.metadata` with the normalized fallback contract keys:

```json
{
  "payload": {
    "reply": "ok",
    "metadata": {
      "selected_model": "m1",
      "prompt_size_bucket": "long",
      "dms_used": false,
      "dms_candidate": true,
      "dms_attempted": true,
      "fallback_reason": "dms_error: connection timeout",
      "fallback_reason_code": "dms_timeout",
      "fallback_detail": "connection timeout",
      "fallback_stage": "dms_primary",
      "fallback_retryable": true,
      "ab_variant": "dms",
      "router_backend": "parallel",
      "router_policy_version": "cp2-2026-02-15",
      "routing_telemetry_schema": "1.0.0"
    }
  }
}
```

If `assistant.chat.request` includes `payload.research_session_id` (string) and
`include_metadata=true`, Merlin attempts to ingest the routing/fallback metadata as a
structured research signal. Response payload includes:

- `research_signal_ingest.ingested`
- `research_signal_ingest.reason` (when not ingested)

## Research Brief Template Versioning

`merlin.research.manager.brief.get.result` payloads include template version fields so
consumers can detect schema/layout drift:

- `brief.brief_template_id`: template identity (`research_manager.default`)
- `brief.brief_template_version`: template/schema version (`1.0.0`)

Example fragment:

```json
{
  "payload": {
    "brief": {
      "session_id": "fixture-session-id",
      "brief_template_id": "research_manager.default",
      "brief_template_version": "1.0.0"
    }
  }
}
```

## Research Session Traceability Fields

`merlin.research.manager.session.create` payloads may include optional traceability links:

- `payload.linked_task_ids`: array of positive integer task IDs.
- `payload.planner_artifacts`: array of planner artifact refs/paths.

Session and brief payloads surface these fields as:

- `session.linked_task_ids`
- `session.planner_artifacts`
- `brief.linked_task_ids`
- `brief.linked_tasks` (resolved local task records when available)
- `brief.planner_artifacts`

## Request Audit Metadata Contract

Merlin emits operation-dispatch audit entries with required metadata keys:

- `request_id`: request-scoped UUID from middleware.
- `route`: HTTP route path (for example `/merlin/operations`).
- `decision_version`: dispatch/audit decision stamp (current: `operation-dispatch-v1`).

## Acknowledgement Pattern

Responses should reuse the same `correlation_id`, generate a new `message_id`, and include `operation.name` suffixed by `.ack` or `.result`.

## Error Pattern

On failure, return a normal envelope with payload:

```json
{
  "error": {
    "code": "TIMEOUT",
    "message": "Hub did not respond before timeout_ms.",
    "retryable": true
  }
}
```

## Dependency Circuit Breaker

For dependency-backed operations, Merlin applies endpoint-level circuit breaking when
`MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED=true`:

- `MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD`: consecutive failures before open.
- `MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS`: open-window before half-open probe.

When open, operation calls return:

- `error.code`: `DEPENDENCY_CIRCUIT_OPEN`
- `error.retryable`: `true`

Plugin execution operations can also return:

- `error.code`: `PLUGIN_PERMISSION_DENIED`
- `error.retryable`: `false`
- `error.code`: `PLUGIN_TIMEOUT`
- `error.retryable`: `true`
- `error.code`: `PLUGIN_CRASH_ISOLATED`
- `error.retryable`: `true`

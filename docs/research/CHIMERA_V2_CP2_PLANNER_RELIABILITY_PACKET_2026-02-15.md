# CHIMERA V2 CP2 Planner Reliability Packet (2026-02-15)

## Cycle Context
- Cycle ID: `CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15`
- Phase: `CP2 Advisory Enforcement`
- Scope: `Merlin/**`
- Focus: composition drift and fallback reliability for planner/routing consumers.

## CP2 Deliverable Summary
This packet is implemented in code and tests, not advisory-only:
- Canonical fallback reason taxonomy for DMS fallback paths.
- Normalized routing telemetry fields across adaptive/parallel/streaming routers.
- Packetizable metadata contract notes for AAS OperationEnvelope consumers.

## Implemented Reliability Controls

### 1) Shared Fallback Contract
A shared routing contract module now centralizes fallback classification and decision metadata shape.

Implemented in:
- `merlin_routing_contract.py`

Controls:
- `classify_dms_fallback_reason(error)` maps free-form errors to stable reason codes.
- `apply_dms_fallback(decision, error, stage)` writes normalized fallback telemetry fields.
- `build_routing_decision(prompt_size_bucket, router_backend)` produces a consistent metadata envelope.

### 2) Router Parity (Composition Drift Reduction)
All three composition routers now emit the same fallback/telemetry field set.

Implemented in:
- `merlin_parallel_llm.py`
- `merlin_streaming_llm.py`
- `merlin_adaptive_llm.py`

Each router now emits:
- `fallback_reason` (legacy compatibility string)
- `fallback_reason_code` (normalized machine code)
- `fallback_detail`
- `fallback_stage`
- `fallback_retryable`
- `dms_candidate`
- `dms_attempted`
- `router_backend`
- `router_policy_version`
- `routing_telemetry_schema`

Compatibility note:
- `fallback_reason` remains present in legacy string form (`dms_error: <detail>`), so existing consumers do not break.

### 3) Non-router Metadata Fallback Path
`merlin_emotion_chat_with_metadata` default/error metadata now uses the same normalized decision skeleton to keep envelope shape stable when router metadata is absent.

Implemented in:
- `merlin_emotion_chat.py`

## Normalized Fallback Taxonomy

| Code | Retryable | Typical Trigger | Consumer Action |
|---|---|---|---|
| `dms_disabled` | No | DMS selected but disabled by config gate | Route to non-DMS lane; flag config drift |
| `dms_timeout` | Yes | Request/read/connect timeout | Safe retry with backoff |
| `dms_transport_error` | Yes | Connection/DNS/network transport failure | Retry or fail over quickly |
| `dms_rate_limited` | Yes | HTTP 429 / rate-limit responses | Retry with budget-aware backoff |
| `dms_http_5xx` | Yes | Provider 5xx/unavailable | Retry within capped attempts |
| `dms_parse_error` | No | Malformed JSON / parser failure | Fail over; inspect provider payload drift |
| `dms_auth_error` | No | 401/403/authentication failures | Stop retry; escalate credential issue |
| `dms_error` | No | Unknown residual class | Fail over + manual triage |

## Packetizable Interface Contract Notes (AAS)

### Envelope Placement
- Location: `AAS.OperationEnvelope.payload.metadata`
- Contract remains additive; unknown keys should be ignored by tolerant readers.

### Recommended Consumer Contract (CP2)
Consumers should read routing metadata in this order:
1. `fallback_reason_code` (primary machine decision)
2. `fallback_retryable` (retry policy)
3. `fallback_stage` (where fallback occurred)
4. `fallback_detail` (diagnostic text)
5. `fallback_reason` (legacy display/backward compatibility)

### OperationEnvelope Notes for AAS Integration
The research-manager lifecycle is now packetizable over the same envelope channel, enabling local orchestration without introducing a side-channel API contract:
- `merlin.research.manager.session.create`
- `merlin.research.manager.sessions.list`
- `merlin.research.manager.session.get`
- `merlin.research.manager.session.signal.add`
- `merlin.research.manager.brief.get`

These operations preserve the standard AAS response envelope and use deterministic machine errors for missing sessions and validation failures.

Write-protection and migration controls:
- Session persistence now stamps `schema_version` (`1.0.0`) and auto-migrates legacy session files that predate versioning.
- Write operations (`session.create`, `session.signal.add`) are policy-gated with a read-only guard (`MERLIN_RESEARCH_MANAGER_READ_ONLY`) and return machine error `RESEARCH_MANAGER_READ_ONLY` when blocked.
- Session IDs are validated to `[A-Za-z0-9_-]{1,128}` at manager/API boundaries to prevent invalid path traversal payloads.
- Session writes now use temp-file replacement for atomic persistence updates.

### Example Metadata Packet
```json
{
  "selected_model": "m1",
  "prompt_size_bucket": "long",
  "dms_used": false,
  "dms_candidate": true,
  "dms_attempted": true,
  "ab_variant": "dms",
  "fallback_reason": "dms_error: connection timeout",
  "fallback_reason_code": "dms_timeout",
  "fallback_detail": "connection timeout",
  "fallback_stage": "dms_primary",
  "fallback_retryable": true,
  "router_backend": "parallel",
  "router_policy_version": "cp2-2026-02-15",
  "routing_telemetry_schema": "1.0.0"
}
```

## Composition Drift/Fallback Analysis Outcome
- Previous drift source: fallback reason values were free-form strings and varied by router implementation.
- CP2 change: all router branches now classify fallback reasons using one shared contract and emit common telemetry fields.
- Outcome: composition consumers can implement deterministic retry/dead-letter/escalation policies without router-specific parsing logic.

## Verification Evidence

### Focused Routing/Fallback Verification
Command:
- `PYTHONPATH=. pytest --capture=no -vv tests/test_merlin_parallel_llm.py::test_routing_prefers_dms_for_long_prompt tests/test_merlin_parallel_llm.py::test_fallback_when_dms_call_fails tests/test_merlin_streaming_llm.py::test_streaming_prefers_dms_for_long_prompt tests/test_merlin_streaming_llm.py::test_streaming_fallback_when_dms_call_fails tests/test_merlin_adaptive_llm.py::test_routing_prefers_dms_for_long_prompt tests/test_merlin_adaptive_llm.py::test_fallback_when_dms_call_fails tests/test_merlin_routing_contract.py::test_classify_dms_fallback_reason_maps_known_errors tests/test_merlin_routing_contract.py::test_apply_dms_fallback_sets_legacy_and_normalized_fields`

Exact outcome:
- Collected: 8 tests
- Result: 8 passed
- Duration: 0.67s

### Broader Targeted Router Suite
Command:
- `PYTHONPATH=. pytest -q --capture=no tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py`

Exact outcome:
- Result: 29 passed
- Duration: 1.69s

### Envelope/Contract Extension Validation
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_contract_schemas.py`

Exact outcome:
- Result: 162 passed, 2 warnings
- Duration: 7.35s

### Envelope/Contract Extension Validation (with specific error fixtures)
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_contract_schemas.py`

Exact outcome:
- Result: 204 passed, 2 warnings
- Duration: 7.72s

### Envelope/Contract + CLI Validation (final)
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_cli.py tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_operation_error_dynamic_responses.py tests/test_contract_schemas.py`

Exact outcome:
- Result: 224 passed, 2 warnings
- Duration: 9.43s

### Targeted Router Re-check (final)
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py`

Exact outcome:
- Result: 45 passed
- Duration: 2.06s

### Envelope/Contract + CLI Validation (latest)
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_cli.py tests/test_merlin_api_server.py tests/test_merlin_research_manager.py tests/test_research_manager_plugin.py tests/test_operation_expected_responses.py tests/test_operation_error_responses.py tests/test_operation_error_specific_responses.py tests/test_operation_error_dynamic_responses.py tests/test_contract_schemas.py`

Exact outcome:
- Result: 229 passed, 2 warnings
- Duration: 8.89s

### Targeted Router Re-check (latest)
Command:
- `PYTHONPATH=. ./.venv/bin/python -m pytest --capture=no -q tests/test_merlin_parallel_llm.py tests/test_merlin_streaming_llm.py tests/test_merlin_adaptive_llm.py tests/test_merlin_routing_contract.py`

Exact outcome:
- Result: 45 passed
- Duration: 2.18s

## Risks and Next Pass
- Risk: classifier still relies on message text heuristics; upstream provider error-format drift can reduce precision.
- Risk: streaming mid-flight parse anomalies still require deeper chunk-level taxonomy if partial output rollback semantics are introduced.
- Next pass:
  1. Promote `fallback_reason_code` to explicit schema fragment in contract fixtures for envelope-level validation.
  2. Add deterministic fixtures for `429`, `5xx`, auth, and parse errors across all router paths.
  3. Add policy-gated retry/backoff controller keyed by `fallback_reason_code` and `fallback_retryable`.
  4. Add cross-repo AAS runbook examples that invoke research-manager envelope operations from Hub orchestration jobs.

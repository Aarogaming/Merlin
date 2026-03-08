# Agent Interop Protocol V1

This repo adopts the AAS inter-repo protocol baseline for synchronous operations.

## Version

- Protocol version: `1.0`
- Repo: `Merlin`

## Core request fields

- `protocol_version`
- `operation_id`
- `request_id`
- `source_repo`
- `target_repo`
- `initiator`
- `intent`
- `constraints`
- `expected_outputs`
- `timeout_sec`
- `created_at_utc`

## Core response fields

- `protocol_version`
- `operation_id`
- `request_id`
- `ack`
- `status`
- `message`
- `artifacts`
- `updated_at_utc`

## Status enum

- `acknowledged`
- `in_progress`
- `blocked`
- `completed`
- `failed`
- `cancelled`

## Compatibility

- Major version changes are breaking.
- Minor changes must be additive.
- Unknown fields should be ignored, not rejected.

## Canonical assets

- Request schema: `protocols/schemas/agent_interop_request_v1.schema.json`
- Response schema: `protocols/schemas/agent_interop_response_v1.schema.json`
- Valid fixture: `protocols/fixtures/request_valid_v1.json`
- Valid fixture: `protocols/fixtures/response_acknowledged_valid_v1.json`
- Valid fixture: `protocols/fixtures/response_completed_valid_v1.json`
- Additive fixture: `protocols/fixtures/request_valid_v1_additive.json`
- Additive fixture: `protocols/fixtures/response_completed_valid_v1_additive.json`

## Synchronous defaults

- ACK within `30` seconds.
- Heartbeat/status update at least every `30` seconds for long operations.
- Retry budget: `2` retries by default.
- Escalate as `blocked` after two missed heartbeat intervals.

## Conformance checks

- `python3 scripts/validate_agent_interop_contract.py`
- `python3 scripts/validate_agent_interop_contract.py --require-additive-fixtures`
- `python3 scripts/validate_agent_interop_contract.py --require-additive-fixtures --require-minor-coverage 0,1`

## Artifact location convention

- Response `artifacts` entries should use safe relative paths with repo prefix (for example `Merlin/docs/repo-alignment/PEER_BASELINE_REPORT.md`).
- `docs/repo-alignment/ARTIFACT_STORAGE_CONVENTIONS.md`

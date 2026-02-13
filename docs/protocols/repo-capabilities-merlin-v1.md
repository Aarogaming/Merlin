# Merlin Repo Capabilities v1

This document is the Merlin-facing operation contract baseline for other AAS repos and IDE agents.
It is aligned with `aas-plugin.json` capability names.

## Service Identity

- Repo: `AaroneousAutomationSuite/Merlin`
- Service entry: `merlin_api_server.py`
- Primary interface: HTTP (`http://localhost:8001` in local/dev)

## Supported Capability Names

1. `assistant.chat`
2. `assistant.tools`
3. `merlin.rag`
4. `merlin.voice`
5. `merlin.resource_indexer`
6. `merlin.tasks`
7. `merlin.tools`
8. `merlin.user_manager`

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

## Response Expectations

- Successful responses return the same `correlation_id`.
- Failures must include structured error payload (`code`, `message`, `retryable`).
- Unknown extra fields in payloads should be ignored by consumers unless explicitly marked required by operation version.

## Non-Goals

- This doc does not define frontend UI protocol details.
- This doc does not replace per-feature API documentation; it defines baseline inter-repo operation framing.

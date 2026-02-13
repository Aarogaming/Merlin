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
- `causation_id`: parent message id when this is produced by another operation.
- `idempotency_key`: required for mutating operations.
- `expects_ack`: `true` for request/response flows, optional for fire-and-forget events.
- `retry.max_attempts`: must stay bounded to avoid runaway loops.

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

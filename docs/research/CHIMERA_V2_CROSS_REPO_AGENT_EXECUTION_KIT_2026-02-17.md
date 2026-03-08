# CHIMERA V2 Cross-Repo Agent Execution Kit (2026-02-17)

Cycle ID: `CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15`
Phase: `CP6 Cross-Repo Orchestration Wave`

Use this kit when running parent/Hub/parallel-consumer agent tasks against Merlin under matching constraints.

## Shared Preconditions

- Merlin API available at `http://localhost:8001`
- Header key: `X-Merlin-Key: merlin-secret-key`
- Envelope schema: `AAS.OperationEnvelope@1.0.0`
- Repo-local execution only in each target repo

## Canonical Operation Set

- `merlin.research.manager.session.create`
- `merlin.research.manager.sessions.list`
- `merlin.research.manager.session.get`
- `merlin.research.manager.session.signal.add`
- `merlin.research.manager.brief.get`

## Canonical Error Codes

- `VALIDATION_ERROR`
- `SESSION_NOT_FOUND`
- `RESEARCH_MANAGER_READ_ONLY`

## Step 1: Capability Discovery

```bash
API=http://localhost:8001
KEY=merlin-secret-key

curl -sS -H "X-Merlin-Key: $KEY" "$API/merlin/operations/capabilities"
```

Pass condition:
- Response contains all five `merlin.research.manager.*` operation names.

## Step 2: Success Flow (Create -> Signal -> Brief)

### 2a) Create session

```bash
MSG_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
CORR_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
TRACE_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

cat > /tmp/merlin-research-create.json <<EOF_JSON
{
  "schema_name": "AAS.OperationEnvelope",
  "schema_version": "1.0.0",
  "message_id": "$MSG_ID",
  "correlation_id": "$CORR_ID",
  "trace_id": "$TRACE_ID",
  "timestamp_utc": "2026-02-17T00:00:00Z",
  "source": {"repo": "AaroneousAutomationSuite/Hub", "component": "hub_orchestrator"},
  "target": {"repo": "AaroneousAutomationSuite/Merlin", "component": "merlin_api_server"},
  "operation": {
    "name": "merlin.research.manager.session.create",
    "version": "1.0.0",
    "timeout_ms": 30000,
    "idempotency_key": "create-session-2026-02-17-0001",
    "expects_ack": true,
    "retry": {"max_attempts": 1}
  },
  "payload": {
    "objective": "Cross-repo adoption validation",
    "constraints": ["repo-local-only"],
    "horizon_days": 14
  }
}
EOF_JSON

curl -sS -H "X-Merlin-Key: $KEY" -H "Content-Type: application/json" \
  -d @/tmp/merlin-research-create.json "$API/merlin/operations"
```

Pass condition:
- `operation.name == "merlin.research.manager.session.create.result"`
- `payload.session.session_id` exists

### 2b) Add signal

```bash
SESSION_ID='<paste session_id from create response>'

MSG_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
CORR_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
TRACE_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

cat > /tmp/merlin-research-signal.json <<EOF_JSON
{
  "schema_name": "AAS.OperationEnvelope",
  "schema_version": "1.0.0",
  "message_id": "$MSG_ID",
  "correlation_id": "$CORR_ID",
  "trace_id": "$TRACE_ID",
  "timestamp_utc": "2026-02-17T00:00:00Z",
  "source": {"repo": "AaroneousAutomationSuite/Hub", "component": "hub_orchestrator"},
  "target": {"repo": "AaroneousAutomationSuite/Merlin", "component": "merlin_api_server"},
  "operation": {
    "name": "merlin.research.manager.session.signal.add",
    "version": "1.0.0",
    "timeout_ms": 30000,
    "idempotency_key": "signal-2026-02-17-0001",
    "expects_ack": true,
    "retry": {"max_attempts": 1}
  },
  "payload": {
    "session_id": "$SESSION_ID",
    "source": "cross-repo-smoke",
    "claim": "Integration path is healthy",
    "confidence": 0.9,
    "supports": ["h_execution_success"]
  }
}
EOF_JSON

curl -sS -H "X-Merlin-Key: $KEY" -H "Content-Type: application/json" \
  -d @/tmp/merlin-research-signal.json "$API/merlin/operations"
```

Pass condition:
- `operation.name == "merlin.research.manager.session.signal.add.result"`
- `payload.session_id == SESSION_ID`

### 2c) Get brief

```bash
MSG_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
CORR_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
TRACE_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

cat > /tmp/merlin-research-brief.json <<EOF_JSON
{
  "schema_name": "AAS.OperationEnvelope",
  "schema_version": "1.0.0",
  "message_id": "$MSG_ID",
  "correlation_id": "$CORR_ID",
  "trace_id": "$TRACE_ID",
  "timestamp_utc": "2026-02-17T00:00:00Z",
  "source": {"repo": "AaroneousAutomationSuite/Hub", "component": "hub_orchestrator"},
  "target": {"repo": "AaroneousAutomationSuite/Merlin", "component": "merlin_api_server"},
  "operation": {
    "name": "merlin.research.manager.brief.get",
    "version": "1.0.0",
    "timeout_ms": 30000,
    "idempotency_key": "brief-2026-02-17-0001",
    "expects_ack": true,
    "retry": {"max_attempts": 1}
  },
  "payload": {"session_id": "$SESSION_ID"}
}
EOF_JSON

curl -sS -H "X-Merlin-Key: $KEY" -H "Content-Type: application/json" \
  -d @/tmp/merlin-research-brief.json "$API/merlin/operations"
```

Pass condition:
- `operation.name == "merlin.research.manager.brief.get.result"`
- `payload.brief.session_id == SESSION_ID`

## Step 3: Deterministic Failure Flow (Invalid Session ID)

```bash
MSG_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
CORR_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)
TRACE_ID=$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)

cat > /tmp/merlin-research-invalid-id.json <<EOF_JSON
{
  "schema_name": "AAS.OperationEnvelope",
  "schema_version": "1.0.0",
  "message_id": "$MSG_ID",
  "correlation_id": "$CORR_ID",
  "trace_id": "$TRACE_ID",
  "timestamp_utc": "2026-02-17T00:00:00Z",
  "source": {"repo": "AaroneousAutomationSuite/Hub", "component": "hub_orchestrator"},
  "target": {"repo": "AaroneousAutomationSuite/Merlin", "component": "merlin_api_server"},
  "operation": {
    "name": "merlin.research.manager.session.get",
    "version": "1.0.0",
    "timeout_ms": 30000,
    "idempotency_key": "invalid-id-2026-02-17-0001",
    "expects_ack": true,
    "retry": {"max_attempts": 1}
  },
  "payload": {"session_id": "../bad"}
}
EOF_JSON

curl -sS -H "X-Merlin-Key: $KEY" -H "Content-Type: application/json" \
  -d @/tmp/merlin-research-invalid-id.json "$API/merlin/operations"
```

Pass condition:
- HTTP status indicates validation failure (422)
- `payload.error.code == "VALIDATION_ERROR"`

## Optional Failure Flow (Read-Only)

If Merlin is configured with `MERLIN_RESEARCH_MANAGER_READ_ONLY=1`, write operations should return:
- `payload.error.code == "RESEARCH_MANAGER_READ_ONLY"`

## Required Agent Return Format

```text
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

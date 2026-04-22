# Critic Loop Implementation Guide

## Overview

The Critic Loop implements the article's "Module A → Module B (Critic) → Module C (Fixer)" pattern for self-correcting agentic systems. It's a complete implementation of automated validation and repair for multi-step task orchestration.

**Status:** ✅ Fully implemented in Phase 1-5

---

## Architecture: Three-Module Pattern

### Module A: Executor (Existing)
- Specialists (Thought, Creation, Intelligence, etc.) execute subtasks
- Emit execution output (status, result, duration)
- Live in: `plugins/thought.py`, `plugins/creation.py`, etc.

### Module B: Critic (NEW - Inline in leadership.py)
- Reviews subtask output against validation criteria
- Uses `audit_strictness` cognitive bias to control review depth
- Location: `leadership.py:_validate_execution()`
- **Checks:** correctness, completeness, safety, efficiency, coherence

### Module C: Repair (NEW - Inline in leadership.py)
- Attempts to fix failed subtasks with retry strategies
- Auto-selects strategy based on failure type
- Location: `leadership.py:_attempt_repair()`
- **Strategies:** faster tier, heavier tier, more context, escalation

---

## Components

### 1. Core Implementation (leadership.py)

**New Pydantic Models:**
```python
ValidationCriteria  # What to check for
ReviewResult        # Critic output
SubtaskExecution    # Complete execution record with review
```

**New Methods in Leadership class:**

| Method | Purpose |
|--------|---------|
| `_execute_dag_with_critic_loop()` | Main orchestrator - runs full 3-module loop |
| `_execute_subtask()` | Module A: Execute single subtask |
| `_validate_execution()` | Module B: Inline critic review |
| `_attempt_repair()` | Module C: Auto-retry with strategy |
| `_repair_faster_tier()` | Retry with lightweight model |
| `_repair_heavier_tier()` | Retry with heavyweight model |
| `_repair_more_context()` | Retry with increased context |
| `_emit_execution_byproduct()` | Store in Knowledge for learning |

**Entry Point:**
When `triage_user_request_advanced` is called, DAG execution now:
1. Parses user request into TaskDAG
2. Calls `_execute_dag_with_critic_loop()`
3. Returns comprehensive results with validation details

### 2. Validation Utilities (plugins/validation_utils.py)

**AdvancedValidationChecks** - Optional enhanced validation:
- `check_response_format()` - Schema validation
- `check_performance()` - Duration/efficiency checks
- `check_error_patterns()` - Detect known failure modes
- `check_coherence()` - Semantic consistency checks
- `compile_validation_report()` - Generate detailed report

**RepairStrategy** - Strategy selection helper:
- `select_strategy()` - Choose best repair approach
- `get_strategy_description()` - Get strategy parameters

### 3. Repair Utilities (plugins/repair_utils.py)

**RepairExecutor** - Orchestrates repair attempts:
- `execute_repair()` - Run single repair attempt
- Tracks attempt history
- Enforces max retry limits
- Provides attempt summary

**ContextAdjustment** - Memory/context management:
- `calculate_optimal_context()` - Compute ideal context window
- `suggest_context_reduction()` - Optimize for failures

**EscalationPath** - Policy violation handling:
- `escalate_to_fortress()` - Route to security for review

---

## Data Flow

### Happy Path (Subtask Passes)
```
1. Execute → status: "success"
2. Validate → passed: true, severity: "none"
3. Store byproduct → Federation learns success
4. Result: ✅ Task complete
```

### Recovery Path (Subtask Fails, Repair Succeeds)
```
1. Execute → status: "error"
2. Validate → passed: false, severity: "error", suggested_fix: "retry_with_heavier_tier"
3. Repair attempt #1 → Execute with heavier tier
4. Re-validate → passed: true
5. Store byproduct → Federation learns anti-pattern + recovery
6. Result: ✅ Task complete after repair
```

### Escalation Path (Policy Violation)
```
1. Execute → status: "success" but contains policy violation
2. Validate → passed: false, severity: "critical", suggested_fix: "escalate_to_fortress"
3. Escalation → Route to Fortress for manual review
4. Store byproduct → Federation learns policy boundary
5. Result: ⚠️ Task escalated, awaiting manual intervention
```

---

## Validation Criteria

### Correctness
- ✅ Output status is "success" or "partial"
- ❌ Output status is "error", "timeout", or missing

### Completeness
- ✅ Output contains "result" field (if strictness high)
- ❌ Output missing result field

### Safety
- ✅ No policy/permission violations (audit_strictness > 75)
- ❌ Permission denied, unauthorized, forbidden

### Efficiency
- ✅ Duration < 120 seconds
- ⚠️ Duration > 120 seconds (warning)
- ❌ Duration > 120 seconds + strictness > 70 (fail)

### Coherence
- ✅ Status and error/result fields are consistent
- ❌ Success claimed but error present, or vice versa

---

## Repair Strategies

### 1. Retry with Faster Tier
- **When:** Timeout or slow execution
- **Action:** Use `tier_1_local` (fast, local model)
- **Settings:** 256 tokens, 30s timeout
- **Max retries:** 1

### 2. Retry with Heavier Tier
- **When:** Incorrect/incomplete output
- **Action:** Use `tier_3_heavy` (GPT-4, Claude)
- **Settings:** 2048 tokens, 90s timeout
- **Max retries:** 2

### 3. Retry with More Context
- **When:** Incomplete output or missing result
- **Action:** Double context window
- **Settings:** 2× tokens, 60s timeout
- **Max retries:** 1

### 4. Escalate to Fortress
- **When:** Policy/permission violation
- **Action:** Route to security domain for review
- **Settings:** No auto-retry
- **Max retries:** 0 (manual only)

---

## Cognitive Bias Integration

The system uses `audit_strictness` to control validation intensity:

| Strictness | Behavior |
|-----------|----------|
| 0-30 | Rubber stamp (trust, don't verify) |
| 40-60 | Balanced (check major issues) |
| 70-85 | Cautious (comprehensive checks) |
| 90-100 | Paranoid (check everything) |

**Example:**
```python
strictness = self.cognitive_biases.get("audit_strictness", 50.0)

if strictness > 75.0:
    # Run deep safety checks
    if execution_output.get("error"):
        issues.append("Safety violation detected")
```

This allows the same critic loop to adapt based on domain expertise and risk tolerance.

---

## Federation Learning Integration

### Success Byproduct (5 params)
```json
{
  "subtask_id": "parse_json",
  "execution_status": "success",
  "review_passed": true,
  "review_issues": [],
  "final_status": "success"
}
```
→ Stored in Knowledge domain as **SOP Candidate**

### Failure Byproduct (15 params)
```json
{
  "subtask_id": "parse_json",
  "execution_status": "error",
  "review_passed": false,
  "review_issues": ["Timeout - slow execution"],
  "repair_attempts": 1,
  "final_status": "success"
}
```
→ Stored in Knowledge domain as **Anti-Pattern Memory**

These byproducts feed into `reflex._adapt()` for federation-wide learning.

---

## Usage Example

### Trigger DAG Execution
```python
# Client sends request to AAS
await nc.request(
    "aaroneousautomationsuite.triage_user_request_advanced",
    json.dumps({
        "request": "Parse JSON file, validate structure, save to database"
    }).encode()
)
```

### Leadership Processes Request
```
1. Thought domain creates TaskDAG with 3 subtasks
2. Leadership calls _execute_dag_with_critic_loop()
3. For each subtask:
   - Execute → get output
   - Validate → review output
   - Repair (if needed) → fix and retry
   - Store → emit byproduct
4. Return summary of all results
```

### Response
```json
{
  "total_subtasks": 3,
  "passed": 3,
  "failed": 0,
  "results": {
    "parse_json": {
      "final_status": "success",
      "repair_attempts": 0,
      "review": { "passed": true, "issues": [] }
    },
    "validate_structure": {
      "final_status": "success",
      "repair_attempts": 1,
      "review": { "passed": true, "issues": ["Initial timeout"] }
    },
    "save_to_database": {
      "final_status": "escalated",
      "repair_attempts": 0,
      "review": { "passed": false, "severity": "critical" }
    }
  }
}
```

---

## Advanced Usage

### Using Enhanced Validation (Optional)
```python
from plugins.validation_utils import AdvancedValidationChecks

# In _validate_execution():
report = AdvancedValidationChecks.compile_validation_report(
    execution_output,
    checks=["format", "performance", "errors", "coherence"]
)
```

### Using Repair Executor (Optional)
```python
from plugins.repair_utils import RepairExecutor

executor = RepairExecutor(max_attempts=3)
repair_result = await executor.execute_repair(
    subtask_id="parse_json",
    execution_output=output,
    validation_issues=issues,
    nc=nc,
    strategy="auto"  # Auto-select strategy
)
```

### Context Management (Optional)
```python
from plugins.repair_utils import ContextAdjustment

optimal_tokens = ContextAdjustment.calculate_optimal_context(
    target_agent="tier_3_heavy",
    complexity_level="complex",
    available_memory_mb=16384
)
```

---

## Testing the Critic Loop

### Manual Test
```python
# In scripts/test_critic_loop.py
import asyncio
from nats.aio.client import Client as NATS

async def test():
    nc = NATS()
    await nc.connect("nats://localhost:4222")
    
    # Trigger DAG with known subtasks
    response = await nc.request(
        "aaroneousautomationsuite.triage_user_request_advanced",
        json.dumps({
            "request": "Execute subtask1, then subtask2, then subtask3"
        }).encode(),
        timeout=120.0
    )
    
    result = json.loads(response.data.decode())
    print(f"Results: {json.dumps(result, indent=2)}")
    
    await nc.close()

asyncio.run(test())
```

### Logging
Enable detailed logging in Leadership:
```python
# Set log level to DEBUG
self.logger.setLevel(logging.DEBUG)
```

Output includes:
```
[CRITIC LOOP] Starting DAG execution with 3 subtasks
[CRITIC LOOP] Processing subtask: parse_json
[CRITIC LOOP] Subtask parse_json validation passed
[CRITIC LOOP] Processing subtask: validate_structure
[CRITIC LOOP] Subtask validate_structure failed validation. Initiating repair...
[REPAIR] Subtask validate_structure repair attempt #1
[REPAIR STRATEGY] Retrying validate_structure with heavier tier
[CRITIC LOOP] Subtask validate_structure repair successful
[CRITIC LOOP] DAG execution complete. Passed: 3/3
```

---

## Next Steps & Enhancements

### Phase 7: Multi-Critic Consensus (Optional)
Use MicroAgent pattern for peer review:
```python
# Route to N micro-agents for independent validation
consensus_result = await self._consensus_review(subtask, nc, num_critics=3)
```

### Phase 8: Few-Shot Learning (Optional)
Store successful repair patterns as in-context examples:
```python
# When repair succeeds, store as training example
await self._store_repair_pattern(subtask, strategy, success=True)
```

### Phase 9: Adaptive Strictness (Optional)
Adjust `audit_strictness` based on historical success rates:
```python
# If domain has high error rate, increase strictness
if historical_failure_rate > 0.3:
    self.cognitive_biases["audit_strictness"] = 80.0
```

### Phase 10: Latency Visualization (Optional)
Emit telemetry during "thinking pause":
```python
# Emit inference latency for UI feedback
await nc.publish(
    "federation.telemetry.inference_latency",
    json.dumps({
        "duration": execution_time,
        "stage": "critic_validation"
    }).encode()
)
```

---

## Summary

✅ **Implemented:**
- DAG execution with inline critic loop
- 5-criteria validation system
- 4 auto-repair strategies
- Cognitive bias integration
- Federation learning via byproducts
- Utility modules for enhancement

✅ **Ready for:**
- Multi-agent consensus (Phase 7)
- Few-shot learning (Phase 8)
- Adaptive control (Phase 9)
- Latency telemetry (Phase 10)

✅ **Integrated with:**
- Leadership domain (orchestration)
- Knowledge domain (memory/learning)
- Fortress domain (policy escalation)
- Reflex base class (cognitive biases)
- NATS event bus (federation communication)

---

## Files Modified/Created

| File | Status | Changes |
|------|--------|---------|
| `plugins/leadership.py` | ✅ Modified | Added Critic Loop methods + Pydantic models |
| `plugins/validation_utils.py` | ✅ Created | Advanced validation checks (optional) |
| `plugins/repair_utils.py` | ✅ Created | Repair orchestration (optional) |
| `mcp-manifest.json` | ⚠️ No changes needed | Already has necessary capabilities |
| `requirements.txt` | ✅ No changes needed | All deps already present |

---

**Implementation Complete!** 🎉

The Critic Loop is now operational and ready to validate, repair, and learn from multi-step task execution.

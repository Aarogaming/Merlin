# Agent Output Packet: CP6 Blocked Repos Recovery (2026-02-18)

Use this packet for currently blocked lanes: `HUB`, `MYFORTRESS`, `WORKBENCH`.

## HUB Recovery Packet

```text
You are the Hub-lane agent for CP6 recovery.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Blocked Recovery

Mission:
Resolve Hub scope ambiguity and deliver the required CP6 Hub artifact.

Scope:
- Allowed: Hub repo only (or canonical Hub scope if confirmed)
- Forbidden: all other repos

Tasks:
1) Determine canonical Hub scope path in your workspace and state it explicitly in output.
2) Add or confirm a Hub binding adapter path for Merlin research-manager operations.
3) Add/confirm fallback mapping for:
   - VALIDATION_ERROR
   - SESSION_NOT_FOUND
   - RESEARCH_MANAGER_READ_ONLY
4) Add/confirm targeted tests for:
   - success envelope operation selection
   - expected failure branch mapping
5) Produce artifact:
   - docs/research/CHIMERA_V2_CP6_HUB_MERLIN_RESEARCH_MANAGER_BINDING_STATUS_2026-02-18.md

Verification:
- targeted Hub tests
- capability probe to http://localhost:8001/merlin/operations/capabilities
- one expected-failure mapping validation

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

## MYFORTRESS Recovery Packet

```text
You are the MyFortress-lane agent for CP6 recovery.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Blocked Recovery

Mission:
Implement minimum viable Merlin research-manager consumer adoption and return full evidence.

Scope:
- Allowed: MyFortress/**
- Forbidden: all other repos

Tasks:
1) Implement capability gate from /merlin/operations/capabilities.
2) Implement envelope builders for:
   - session.create
   - session.get
   - brief.get
   - optional sessions.list / session.signal.add
3) Implement fallback mapping for:
   - VALIDATION_ERROR
   - SESSION_NOT_FOUND
   - RESEARCH_MANAGER_READ_ONLY
4) Add targeted tests for success-path selection and expected-failure fallback branches.
5) Produce artifact:
   - docs/research/CHIMERA_V2_CP6_PARALLEL_CONSUMER_MERLIN_RESEARCH_MANAGER_ADOPTION_STATUS_2026-02-18.md

Verification:
- targeted consumer tests (pass)
- capability probe command + outcome
- fixture or deterministic expected-failure branch validation

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

## WORKBENCH Recovery Packet

```text
You are the Workbench-lane agent for CP6 recovery.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Blocked Recovery

Mission:
Implement minimum viable Merlin research-manager consumer adoption and return full evidence.

Scope:
- Allowed: Workbench/**
- Forbidden: all other repos

Tasks:
1) Implement capability gate from /merlin/operations/capabilities.
2) Implement envelope builders for:
   - session.create
   - session.get
   - brief.get
   - optional sessions.list / session.signal.add
3) Implement fallback mapping for:
   - VALIDATION_ERROR
   - SESSION_NOT_FOUND
   - RESEARCH_MANAGER_READ_ONLY
4) Add targeted tests for success-path selection and expected-failure fallback branches.
5) Produce artifact:
   - docs/research/CHIMERA_V2_CP6_PARALLEL_CONSUMER_MERLIN_RESEARCH_MANAGER_ADOPTION_STATUS_2026-02-18.md

Verification:
- targeted consumer tests (pass)
- capability probe command + outcome
- fixture or deterministic expected-failure branch validation

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

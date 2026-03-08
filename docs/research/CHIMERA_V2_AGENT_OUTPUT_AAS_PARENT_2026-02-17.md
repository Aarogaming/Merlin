# Agent Output Packet: AAS Parent Repo (2026-02-17)

Send the following packet to the agent operating the AAS parent repo.

```text
You are the AAS parent-repo agent.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Cross-Repo Orchestration Wave

Operating conditions (must match Merlin lane):
- Repo-local scope only
- No escalation/approval prompts
- Network enabled
- Execute changes and verify with concrete command outcomes

Mission:
Adopt Merlin research-manager operations into parent-level orchestration metadata and runbook surfaces.

Scope:
- Allowed: current parent repo only
- Forbidden: all other repos

Required Merlin operation set (authoritative):
- merlin.research.manager.session.create
- merlin.research.manager.sessions.list
- merlin.research.manager.session.get
- merlin.research.manager.session.signal.add
- merlin.research.manager.brief.get

Consumer error codes to model:
- VALIDATION_ERROR
- SESSION_NOT_FOUND
- RESEARCH_MANAGER_READ_ONLY

Tasks:
1) Update parent-level capability inventory/runbook references so Merlin research-manager operations are explicitly listed.
2) Add or update parent orchestration examples for request/response envelope flows using the five operations above.
3) Add parent-level verification notes for read-only and invalid-session-id behaviors.
4) Produce a concrete artifact (not suggestions-only):
   - docs/research/CHIMERA_V2_CP6_AAS_PARENT_MERLIN_RESEARCH_MANAGER_ADOPTION_STATUS_2026-02-17.md

Verification (minimum):
- capability discovery against local Merlin
- one successful session create + brief retrieval envelope flow
- one expected failure flow for RESEARCH_MANAGER_READ_ONLY or invalid session_id

Suggested command baseline (adjust as needed for repo tooling):
- curl -sS -H "X-Merlin-Key: merlin-secret-key" http://localhost:8001/merlin/operations/capabilities
- curl -sS -H "X-Merlin-Key: merlin-secret-key" -H "Content-Type: application/json" -d '<operation envelope payload>' http://localhost:8001/merlin/operations
- targeted parent repo tests validating capability/docs/flow artifacts

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

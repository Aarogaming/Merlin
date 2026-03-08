# Agent Output Packet: Hub Repo (2026-02-17)

Send the following packet to the agent operating the Hub repo.

```text
You are the Hub-repo agent.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Cross-Repo Orchestration Wave

Operating conditions (must match Merlin lane):
- Repo-local scope only
- No escalation/approval prompts
- Network enabled
- Implement + verify concrete outcomes

Mission:
Bind Hub orchestration to Merlin research-manager operations with resilient error handling.

Scope:
- Allowed: current Hub repo only
- Forbidden: all other repos

Required Merlin operation set:
- merlin.research.manager.session.create
- merlin.research.manager.sessions.list
- merlin.research.manager.session.get
- merlin.research.manager.session.signal.add
- merlin.research.manager.brief.get

Required error handling behavior:
- VALIDATION_ERROR -> caller/request correction path
- SESSION_NOT_FOUND -> recover or recreate session path
- RESEARCH_MANAGER_READ_ONLY -> non-mutating fallback path

Tasks:
1) Add/extend Hub client adapters for the five Merlin research-manager operations.
2) Add typed request/response mappers for the operation-envelope payloads.
3) Add explicit handling branches for VALIDATION_ERROR, SESSION_NOT_FOUND, RESEARCH_MANAGER_READ_ONLY.
4) Add targeted tests for:
   - success flow: create -> signal -> brief
   - expected failure: read-only write attempt
   - expected failure: invalid session_id
5) Produce concrete artifact:
   - docs/research/CHIMERA_V2_CP6_HUB_MERLIN_RESEARCH_MANAGER_BINDING_STATUS_2026-02-17.md

Verification (minimum):
- targeted Hub tests for adapter behavior and error branching
- one live smoke call to Merlin capabilities endpoint proving operation discoverability
- one deterministic envelope request/response fixture check for create and brief

Suggested command baseline (adjust to Hub tooling):
- rg "merlin.research.manager" -n
- python -m pytest -q <hub-targeted-tests>
- curl -sS -H "X-Merlin-Key: merlin-secret-key" http://localhost:8001/merlin/operations/capabilities

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

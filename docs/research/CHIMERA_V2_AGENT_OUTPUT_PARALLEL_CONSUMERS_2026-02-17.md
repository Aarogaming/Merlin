# Agent Output Packet: Parallel Consumer Repos (2026-02-17)

Send the following packet to agents operating parallel AAS repos that consume Merlin operations.

```text
You are a parallel consumer-repo agent integrating with Merlin.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Cross-Repo Orchestration Wave

Operating conditions (must match Merlin lane):
- Repo-local scope only
- No escalation/approval prompts
- Network enabled
- Apply changes + run targeted verification

Mission:
Enable safe consumption of Merlin research-manager operations with tolerant capability detection and fallback.

Scope:
- Allowed: current repo only
- Forbidden: all other repos

Merlin capability target:
- merlin.research.manager.session.create
- merlin.research.manager.sessions.list
- merlin.research.manager.session.get
- merlin.research.manager.session.signal.add
- merlin.research.manager.brief.get

Tasks:
1) Add capability detection gate:
   - if operations are present in `/merlin/operations/capabilities`, enable research-manager path
   - if absent, continue legacy/non-research path without hard failure
2) Add envelope payload builders for create/get/brief and optional signal/list flows.
3) Add consumer-side fallback mapping for:
   - VALIDATION_ERROR
   - SESSION_NOT_FOUND
   - RESEARCH_MANAGER_READ_ONLY
4) Add targeted tests for:
   - capability present -> research flow selected
   - capability absent -> fallback path selected
   - read-only response -> non-mutating fallback selected
5) Produce concrete artifact:
   - docs/research/CHIMERA_V2_CP6_PARALLEL_CONSUMER_MERLIN_RESEARCH_MANAGER_ADOPTION_STATUS_2026-02-17.md

Verification (minimum):
- local targeted tests covering selection/fallback logic
- one live capabilities probe against local Merlin
- one expected-failure branch validation using mock/fixture error payloads

Suggested command baseline (adjust to repo tooling):
- rg "operations/capabilities|merlin.research.manager" -n
- python -m pytest -q <targeted-consumer-tests>
- curl -sS -H "X-Merlin-Key: merlin-secret-key" http://localhost:8001/merlin/operations/capabilities

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

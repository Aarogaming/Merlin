# Agent Output Packet: CP6 AAS Parent Return Recovery (2026-02-18)

Send this packet to the `AAS parent` repo agent.

```text
You are the AAS parent-lane agent for CP6 return recovery.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Cross-Repo Orchestration Wave - Parent Return Recovery

Operating conditions:
- Repo-local scope only
- No escalation/approval prompts
- Network enabled
- Apply concrete changes and run verification

Mission:
Deliver the missing AAS parent CP6 6-block return with concrete evidence.

Scope:
- Allowed: AAS parent repo only
- Forbidden: all other repos

Tasks:
1) Implement/verify parent-layer binding contract for Merlin research-manager operations:
   - merlin.research.manager.session.create
   - merlin.research.manager.session.get
   - merlin.research.manager.brief.get
   - optional sessions.list / session.signal.add
2) Implement/verify parent fallback taxonomy mapping:
   - VALIDATION_ERROR
   - SESSION_NOT_FOUND
   - RESEARCH_MANAGER_READ_ONLY
3) Add/verify tests covering:
   - capability-present selection path
   - capability-absent fallback path
   - expected failure branch mapping
4) Produce required parent artifact:
   - docs/research/CHIMERA_V2_CP6_PARENT_MERLIN_RESEARCH_MANAGER_BINDING_STATUS_2026-02-18.md

Verification (minimum):
- targeted parent tests
- capability probe command outcome
- one expected-failure mapping command outcome

Output format (exact):
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

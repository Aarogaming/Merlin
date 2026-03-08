# Agent Output Packet: CP6 Conditional-Pass Live Proof Closeout (2026-02-18)

Send this packet to: `ANDROIDAPP`, `LIBRARY`, `MAELSTROM` agents.

```text
You are a repo-local agent closing a CP6 conditional-pass gap.

Cycle ID: CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15
Phase: CP6 Cross-Repo Orchestration Wave - Live Proof Closeout

Operating conditions:
- Repo-local scope only
- No escalation/approval prompts
- Network enabled
- Execute and report exact command strings + pass/fail

Mission:
Convert current CONDITIONAL_PASS to PASS by capturing live Merlin evidence.

Merlin endpoint target:
- API: http://localhost:8001
- Header: X-Merlin-Key: merlin-secret-key

Required closeout tasks:
1) Re-run live capability probe and capture outcome.
2) Execute one live success chain against Merlin:
   - merlin.research.manager.session.create
   - merlin.research.manager.session.signal.add
   - merlin.research.manager.brief.get
3) Execute one deterministic expected-failure branch:
   - invalid session_id for merlin.research.manager.session.get
   - validate error code VALIDATION_ERROR
4) Update or append repo artifact:
   - docs/research/CHIMERA_V2_CP6_PARALLEL_CONSUMER_MERLIN_RESEARCH_MANAGER_ADOPTION_STATUS_2026-02-18.md

Minimum verification commands (adapt only for repo tooling differences):
- curl -sS -H "X-Merlin-Key: merlin-secret-key" http://localhost:8001/merlin/operations/capabilities
- <repo-targeted unit tests for selection/fallback path>
- <repo command executing/validating create->signal->brief live chain>
- <repo command executing invalid-session expected failure>

Success criteria for PASS upgrade:
- live capabilities probe succeeds
- create->signal->brief live chain evidence captured
- expected failure branch returns VALIDATION_ERROR
- artifact updated with exact command strings and results

Output format:
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

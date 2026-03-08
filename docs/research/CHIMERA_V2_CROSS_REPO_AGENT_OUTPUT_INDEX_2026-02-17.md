# CHIMERA V2 Cross-Repo Agent Output Index (2026-02-17)

Cycle ID: `CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15`
Phase: `CP6 Cross-Repo Orchestration Wave`

## Purpose

This index contains ready-to-send execution packets for agents working in non-Merlin repos under the same operating conditions:
- repo-local scope only
- no escalation/approval prompts
- network enabled
- execute, verify, and produce concrete artifacts

## Packet Files

1. `docs/research/CHIMERA_V2_AGENT_OUTPUT_AAS_PARENT_2026-02-17.md`
2. `docs/research/CHIMERA_V2_AGENT_OUTPUT_HUB_2026-02-17.md`
3. `docs/research/CHIMERA_V2_AGENT_OUTPUT_PARALLEL_CONSUMERS_2026-02-17.md`
4. `docs/research/CHIMERA_V2_CROSS_REPO_AGENT_EXECUTION_KIT_2026-02-17.md`
5. `docs/research/CHIMERA_V2_CROSS_REPO_AGENT_RETURN_TEMPLATE_2026-02-17.md`
6. `docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.json`
7. `docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.md`
8. `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_CONDITIONAL_PASS_LIVE_PROOF_2026-02-18.md`
9. `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_BLOCKED_REPOS_RECOVERY_2026-02-18.md`
10. `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_AAS_PARENT_RETURN_RECOVERY_2026-02-18.md`
11. `docs/research/CHIMERA_V2_CP6_GATE_RESCORE_RUNBOOK_2026-02-18.md`
12. `docs/research/CHIMERA_V2_CP6_GATE_RESCORE_INTAKE_EXAMPLE_2026-02-18.json`
13. `docs/research/SUGGESTIONS_BIN_PRIORITIZED_PLAN_2026-02-18.md`
14. `docs/research/SUGGESTIONS_BIN_PRIORITY_MATRIX_2026-02-18.json`
15. `docs/research/SUGGESTIONS_BIN_EXECUTION_TRACKER_2026-02-18.md`
16. `docs/research/CHIMERA_V2_MERLIN_SUGGESTION_EXECUTION_PACKETS_2026-02-18.md`

## Adjudication Tooling

- Script: `scripts/chimera_v2_cp6_gate_rescore.py`
- Targeted tests: `tests/test_chimera_v2_cp6_gate_rescore.py`

## Merlin Contract Snapshot (for all packets)

Research-manager envelope operations now exposed by Merlin:
- `merlin.research.manager.session.create`
- `merlin.research.manager.sessions.list`
- `merlin.research.manager.session.get`
- `merlin.research.manager.session.signal.add`
- `merlin.research.manager.brief.get`

Research-manager machine error codes relevant to consumers:
- `VALIDATION_ERROR`
- `SESSION_NOT_FOUND`
- `RESEARCH_MANAGER_READ_ONLY`

Validation and guard rules relevant to consumers:
- `session_id` must match `[A-Za-z0-9_-]{1,128}`
- write operations may be blocked by read-only policy (`MERLIN_RESEARCH_MANAGER_READ_ONLY=1`)

## Optional Cross-Repo Live Smoke (against local Merlin)

```bash
API=http://localhost:8001
KEY=merlin-secret-key

curl -sS -H "X-Merlin-Key: $KEY" "$API/merlin/operations/capabilities" | jq '.capabilities[] | select(.name | startswith("merlin.research.manager"))'
```

Expected result:
- non-empty capability rows for all five research-manager operations.

## Wave-1 Dispatch Order

1. Send each repo-specific packet (AAS parent, Hub, parallel consumers).
2. Attach the execution kit for exact envelope payload and probe commands.
3. Require responses in the return-template format.

## Wave-2 Closeout Dispatch Order (2026-02-18)

1. Use `docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.json` as source-of-truth adjudication.
2. Send `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_CONDITIONAL_PASS_LIVE_PROOF_2026-02-18.md` to AndroidApp/Library/Maelstrom.
3. Send `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_BLOCKED_REPOS_RECOVERY_2026-02-18.md` to Hub/MyFortress/Workbench.
4. Send `docs/research/CHIMERA_V2_AGENT_OUTPUT_CP6_AAS_PARENT_RETURN_RECOVERY_2026-02-18.md` to AAS parent.
5. Collect 6-block returns and re-score gate verdicts with the same matrix criteria.

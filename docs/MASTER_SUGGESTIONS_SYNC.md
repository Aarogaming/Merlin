# Master Suggestions Synchronization Baseline

Status: Active
Generated UTC: 2026-03-27T14:41:18Z
Workspace root: `C:\Dev library\AaroneousAutomationSuite`

## Purpose

Aggregate repo-side suggestion bins into one orchestrator-level input for
lane planning, delegation prep, and next roadmap drafting cycles.

## Summary

- Suggestion documents discovered: **7**
- Suggestion entries extracted: **1116**
- Repos with suggestions: **5**

### Risk class distribution

- R0: 61
- R1: 705
- R2: 319
- R3: 31

### Lane hint distribution

- A: 3
- B: 8
- C: 18
- D: 13
- E: 29
- F: 25
- G: 8
- H: 6
- I: 1
- unassigned: 1005

### Actionability tier distribution

- high: 68
- medium: 522
- low: 526

### De-duplication summary

- Duplicate groups: 40
- Duplicate entries: 105
- Top duplicate clusters:
  - (6) risk_class: `R1`
  - (5) Hermes Constraint Mesh
  - (5) Janus Web Harbor
  - (5) risk_class: `R0`
  - (4) Atlas Command Outbox

## Source inventory

| Repo | Path | Title | Entries |
|---|---|---|---:|
| AndroidApp | `AndroidApp/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin | 244 |
| Library | `Library/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin | 113 |
| Maelstrom | `Maelstrom/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin | 139 |
| Merlin | `Merlin/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin | 277 |
| MyFortress | `MyFortress/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin | 0 |
| Workbench | `Workbench/docs/research/SUGGESTIONS_BIN.md` | Suggestions Bin (Workbench) | 179 |
| Workbench | `Workbench/docs/SUGGESTIONS_BIN.md` | Workbench Suggestions Bin | 164 |

## Top candidate suggestions (first 30 by priority score)

Feed threshold currently uses actionability score >= 4.

- [R2] [Merlin] [unassigned] [H2] [high:10] [prio:153/#1] [dup:2] Uncertainty-Aware DMS Escalation (`Merlin/docs/research/SUGGESTIONS_BIN.md:987`)
- [R2] [Merlin] [unassigned] [H1] [high:10] [prio:152/#2] [dup:4] Policy-Ledger Version Tag for Routing Decisions (`Merlin/docs/research/SUGGESTIONS_BIN.md:1017`)
- [R2] [AndroidApp] [C] [H1] [high:9] [prio:152/#3] [dup:1] Add "Hermes Relay" canonical websocket URL builder for Merlin endpoints. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:66`)
- [R2] [AndroidApp] [E] [H1] [high:9] [prio:152/#4] [dup:1] Add "Chronos Gate" debounce and dedupe to `MainViewModel.refreshStatus`. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:80`)
- [R2] [AndroidApp] [C] [H1] [high:9] [prio:152/#5] [dup:1] Add "Oracle Spine" backend telemetry reconciliation between simulated and live health sources. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:157`)
- [R2] [AndroidApp] [F] [H2] [high:9] [prio:147/#6] [dup:1] Add "Daemon Mirror" guardrails around OpenCode demo utilities. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:101`)
- [R2] [AndroidApp] [G] [H2] [high:9] [prio:147/#7] [dup:1] Add "Atlas Boundary" manifest transport policy split by build variant. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:108`)
- [R2] [AndroidApp] [B] [H2] [high:9] [prio:147/#8] [dup:1] Add "Cerberus Gate" schema validation for config import/export payloads. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:115`)
- [R2] [AndroidApp] [B] [H2] [high:9] [prio:147/#9] [dup:1] Add "Argos Lattice" protocol-bound artifact envelopes for handoff evidence. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:136`)
- [R2] [AndroidApp] [E] [H2] [high:9] [prio:147/#10] [dup:1] Add "Nightingale Loop" shared refresh scheduler across dashboard/main view layers. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:150`)
- [R1] [AndroidApp] [A] [H1] [high:10] [prio:142/#11] [dup:1] Create a pre-planning "Atlas Phase Map" for AndroidApp that reuses `docs/ANDROIDAPP_LONG_TERM_ROADMAP_2026-02-16.md` and maps Phase 5+ into a ship-ready packet sequence. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:18`)
- [R1] [AndroidApp] [C] [H1] [high:10] [prio:142/#12] [dup:1] Convert the core navigation/command reliability tests into a "Iris Route" suite for offline and reconnect behavior in Merlin command flows. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:34`)
- [R1] [AndroidApp] [H] [H1] [high:10] [prio:142/#13] [dup:1] Replace placeholder guidance in `docs/research/SUGGESTIONS_BIN.md` with a versioned "research-to-packet conversion protocol" template. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:42`)
- [R1] [AndroidApp] [G] [H1] [high:10] [prio:142/#14] [dup:1] Add "Valhalla Release Gate" checklist for release artifact naming and production build determinism. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:58`)
- [R1] [Merlin] [G] [H1] [high:10] [prio:142/#15] [dup:1] Add explicit DMS circuit-breaker + retry/backoff around `merlin_llm_backends._dms_chat` and route-level fallbacks. (`Merlin/docs/research/SUGGESTIONS_BIN.md:18`)
- [R1] [Merlin] [E] [H1] [high:10] [prio:142/#16] [dup:1] Add OpenAI-compatible response-shape normalizer for reasoning providers (strictly parse `usage`, `model`, `id`, `cached_tokens`) in all backends. (`Merlin/docs/research/SUGGESTIONS_BIN.md:40`)
- [R2] [AndroidApp] [unassigned] [none] [high:10] [prio:141/#17] [dup:1] Nyx Audio-Lumen Gate (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:621`)
- [R1] [AndroidApp] [B] [H2] [high:10] [prio:137/#18] [dup:1] Add an interop-preflight "Hermes Gateway Pass" checklist for protocol-driven operations before any cross-repo packet. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:26`)
- [R1] [AndroidApp] [D] [H2] [high:10] [prio:137/#19] [dup:1] Add "Orion Stream Health" acceptance checks for A/B realtime subscriptions and collector churn under rapid detail refresh. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:50`)
- [R1] [Merlin] [E] [H2] [high:10] [prio:137/#20] [dup:1] Track usage-token deltas and prompt bucket economics for DMS experiments using OpenAI-like `usage` fields and `cached_tokens`. (`Merlin/docs/research/SUGGESTIONS_BIN.md:48`)
- [R1] [Merlin] [G] [H2] [high:10] [prio:137/#21] [dup:1] Introduce error-budget controls for DMS rollout (temporary auto-disable on rolling-failure threshold and low-SLO conditions). (`Merlin/docs/research/SUGGESTIONS_BIN.md:56`)
- [R1] [Merlin] [H] [H2] [high:10] [prio:137/#22] [dup:1] Introduce DMS capability matrix and model provenance checks (including non-commercial model license awareness). (`Merlin/docs/research/SUGGESTIONS_BIN.md:85`)
- [R1] [Merlin] [unassigned] [H1] [high:10] [prio:135/#23] [dup:3] Deterministic Conversation-Scoped DMS A/B Assignment (`Merlin/docs/research/SUGGESTIONS_BIN.md:977`)
- [R1] [Merlin] [unassigned] [H1] [high:10] [prio:132/#24] [dup:4] Retry Taxonomy for DMS Transport vs Parser Failures (`Merlin/docs/research/SUGGESTIONS_BIN.md:997`)
- [R1] [Merlin] [unassigned] [H1] [high:10] [prio:132/#25] [dup:4] Streaming Error-Event Grammar for SSE Robustness (`Merlin/docs/research/SUGGESTIONS_BIN.md:1007`)
- [R1] [AndroidApp] [E] [H1] [high:9] [prio:132/#26] [dup:1] Add "Norns Ledger" history dedupe and noise suppression in status persistence. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:87`)
- [R1] [AndroidApp] [F] [H1] [high:9] [prio:132/#27] [dup:1] Add "Iris Lock" permission-safe Wi-Fi and sensor access in Merlin context capture. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:94`)
- [R1] [AndroidApp] [C] [H1] [high:9] [prio:132/#28] [dup:1] Add "Valhalla Streamline" single-stream scheduler for Merlin chat and dashboard collectors. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:122`)
- [R1] [AndroidApp] [F] [H1] [high:9] [prio:132/#29] [dup:1] Add "Prometheus Latch" request guardrails in HTTP repositories. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:129`)
- [R1] [AndroidApp] [F] [H1] [high:9] [prio:132/#30] [dup:1] Add "Mimir Lens" explicit permission gates for context telemetry. (`AndroidApp/docs/research/SUGGESTIONS_BIN.md:143`)

## Usage

Run `python scripts/governance/orchestrator_suggestions_sync_sweep.py`
as needed to refresh this baseline and produce machine-readable feed output.


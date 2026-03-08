# Merlin Native Seed Access

Merlin exposes seed runtime control and telemetry through the operation envelope and CLI, so model-evolution work can be orchestrated from AAS components without ad-hoc scripts.

## Envelope Operations

- `merlin.seed.status`
- `merlin.seed.health`
- `merlin.seed.health.heartbeat`
- `merlin.seed.watchdog.tick`
- `merlin.seed.watchdog.status`
- `merlin.seed.watchdog.control`
- `merlin.seed.control`

Both operations accept `payload.workspace_root` to point at an external seed workspace (for example the AAS root outside this repo).

## CLI Commands

```bash
python merlin_cli.py seed status --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite"
python merlin_cli.py seed health --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite"
python merlin_cli.py seed heartbeat --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite"
python merlin_cli.py seed watchdog --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --no-apply
python merlin_cli.py seed watchdog --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --apply --allow-live-automation
python merlin_cli.py seed watchdog-runtime status --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite"
python merlin_cli.py seed watchdog-runtime control start --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --allow-live-automation --apply --max-iterations 0
python merlin_cli.py seed watchdog-runtime control stop --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --allow-live-automation
python merlin_cli.py seed control start --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --allow-live-automation
python merlin_cli.py seed control restart --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --allow-live-automation
python merlin_cli.py seed control stop --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --allow-live-automation

# Continuous watchdog loop
python scripts/run_merlin_seed_watchdog.py --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --no-apply
python scripts/run_merlin_seed_watchdog.py --workspace-root "/mnt/c/Dev library/AaroneousAutomationSuite" --apply --allow-live-automation --max-iterations 10 --interval-seconds 60
```

## Guidance Payload

`merlin.seed.status` now includes:

- `progress`:
  - `target_rounds`
  - `completed_rounds`
  - `remaining_rounds`
  - `completion_percent`
  - `eta_seconds`
  - `throughput_per_min`
- `guidance`:
  - `state`: `healthy | attention | blocked | complete`
  - `next_action`: `observe | start | restart | stop | unblock_policy`
  - `recommendations[]`: actionable remediations with `id`, `severity`, `message`, and `action`

Seed payload contracts are tracked at:

- `contracts/seed/seed_status.schema.json`
- `contracts/seed/seed_health.schema.json`
- `contracts/seed/seed_health_heartbeat.schema.json`
- `contracts/seed/seed_watchdog_tick.schema.json`
- `contracts/seed/seed_watchdog_runtime_status.schema.json`
- `contracts/seed/seed_watchdog_runtime_control.schema.json`
- `contracts/seed/seed_guidance.schema.json`
- `contracts/registry.json` entries `AAS.Merlin.SeedStatus`, `AAS.Merlin.SeedHealth`, `AAS.Merlin.SeedHealthHeartbeat`, `AAS.Merlin.SeedWatchdogTick`, `AAS.Merlin.SeedWatchdogRuntimeStatus`, `AAS.Merlin.SeedWatchdogRuntimeControl`, and `AAS.Merlin.SeedGuidance`

This keeps policy semantics explicit and gives Merlin a native, machine-readable control loop for "training your next evolution."

## Policy Outcomes

- `ALLOW_LIVE_AUTOMATION=true`: seed control can run (`decision=allowed`)
- `ALLOW_LIVE_AUTOMATION=false`: seed control is blocked/stubbed (`decision=stubbed`, guidance recommends unblocking policy)
- `seed watchdog --no-apply`: deterministic preview (`outcome_status=preview|noop`) with no mutation
- `seed watchdog --apply` + allowed policy: executes recommended `start|restart|stop` action
- `seed watchdog-runtime control` follows the same policy gate, returning `SEED_WATCHDOG_CONTROL_BLOCKED` for blocked starts/restarts.

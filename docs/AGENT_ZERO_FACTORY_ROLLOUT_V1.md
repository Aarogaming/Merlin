# Agent-Zero Factory Rollout v1

This playbook applies the Agent Genome model across existing federation repos
without introducing a dedicated control-plane agent.

## Objective

- Agent-Zero is both factory and operator.
- Every repo can boot solo from birth.
- Every repo can join federation after passing gates.
- All repos can observe control-plane health.
- Only one repo mutates control-plane state at a time through lease control.

## Phase 0: Contract stabilization (immediate)

1. Repair invalid MCP manifests:
   - `Guild/mcp-manifest.json`
   - `Library/mcp-manifest.json`
   - `Merlin/mcp-manifest.json`
2. Add a schema validation gate in each repo CI:
   - fail build on malformed JSON
   - fail build on schema mismatch
3. Normalize protocol references so canonical paths are valid and consistent.

## Phase 1: Genome adoption in Agent-Zero

1. Treat `genome/` as canonical DNA source.
2. Update `scripts/genesis.py` to emit `genome.manifest.json` into new repos.
3. Add lifecycle state file generation at birth (`lifecycle_state.json`).
4. Add runtime profile config (`solo` default, `federated` optional).

## Phase 2: Birth-to-active pipeline for all repos

Each newborn or migrated repo must pass this sequence:

1. Birth:
   - scaffold identity, manifests, plugin shell, lifecycle file
2. Training:
   - run reflex tests and schema conformance tests
3. Stabilization:
   - security hooks + policy checks + health checks
4. Promotion:
   - set status from `quarantine_pending` to `active`

## Phase 3: Control-plane transformer model

1. Enable observer routines in all repos.
2. Require lease for mutating control-plane operations.
3. Enforce single-writer semantics:
   - one active mutator lease
   - all others in observer mode
4. Set lease TTL and renew/release policy.

## Phase 4: Specialization and function shedding

1. Keep core runtime capabilities in all repos.
2. Mark non-essential capabilities as delegated before retirement.
3. Maintain delegation map so ecosystem fallback remains reliable.
4. Track capability state transitions in each repo ledger.

## Repo-by-repo alignment tasks

### AaroneousAutomationSuite (Agent-Zero)

- Own `genome/` schemas, templates, and generation rules.
- Implement schema/compatibility checks in genesis flow.
- Publish canonical release tags for genome versions.

### Guild

- Repair manifest validity.
- Align existing orchestration contracts to genome lifecycle.
- Register observer+lease behavior.

### Library

- Repair manifest validity.
- Host canonical protocol references and compatibility matrix.
- Validate interop schema version drift.

### Maelstrom

- Adopt lifecycle and runtime profile files.
- Register observer-only mode first, then lease-eligible mode.

### Merlin

- Repair manifest validity.
- Add conformance gate before federation promotion.
- Enable capability delegation map for specialization pruning.

### MyFortress

- Enforce promotion gates and lease-policy checks.
- Validate that only lease holders can mutate control-plane state.

### Workbench

- Provide federation conformance test harness.
- Publish scorecards: schema, lifecycle, lease, compatibility compliance.

## Minimal required artifacts per repo

Each repo should contain and validate:

- `mcp-manifest.json`
- `genome.manifest.json`
- `lifecycle_state.json`
- `SOUL.md`
- `AGENTS.md`
- plugin manifest(s)

## Promotion gates (required)

1. JSON validity and schema conformance.
2. Capability ID and entry-point consistency.
3. Health heartbeat and status response checks.
4. Security pre-commit and secret scan pass.
5. Lease policy check for mutator operations.

## Audit commands

- Validate local repo artifacts:
  - `python scripts/validate_agent_artifacts.py --repo-path D:\AaroneousAutomationSuite`
- Validate a sibling repo:
  - `python scripts/validate_agent_artifacts.py --repo Merlin`
- Promote a repo after audit:
  - `python scripts/genesis.py --promote D:\Merlin MyFortress`
- Validate, promote, and revalidate in one command:
  - `python scripts/genesis.py --promote-if-clean D:\Merlin MyFortress`
- Run federation-wide compliance report:
  - `python scripts/audit_federation_compliance.py`

## Suggested adoption order

1. Agent-Zero
2. Workbench
3. Library
4. MyFortress
5. Guild
6. Merlin
7. Maelstrom

This order hardens generation and governance before wider specialization rollout.

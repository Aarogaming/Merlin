You are the next coding agent for `AaroneousAutomationSuite/Merlin`.

Mission:
Close Merlin's highest-impact integration gaps so Discovery becomes a first-class, contract-driven, policy-governed subsystem (not just CLI/local artifacts).

Context you must assume:
- Merlin already has strong operation-envelope infra and robust routing/research systems.
- DiscoveryEngine v1 exists (`merlin_discovery_engine.py`, `plugins/discovery_engine/`, discovery contracts/tests/docs).
- `ALLOW_LIVE_AUTOMATION` default is intentionally `true` now.
- Public profile still blocks network collectors by policy; Experimental profile can allow them when policy permits.

Primary shortcomings to fix:
1. Discovery is not exposed through `/merlin/operations` envelope operations.
2. Live discovery collectors/publishers are still stubs.
3. Queue leasing is not concurrency-safe for true multi-process workers.
4. Packaged plugin runtime has `core.*` import compatibility issues in standalone Merlin.

Deliverables:
1. Add envelope operations and handlers for:
- `merlin.discovery.run`
- `merlin.discovery.queue.status`
- `merlin.discovery.queue.drain`
- `merlin.discovery.queue.pause`
- `merlin.discovery.queue.resume`
- `merlin.discovery.queue.purge_deadletter`
- `merlin.knowledge.search`

2. Add operation fixtures + tests for new discovery operations under `tests/fixtures/contracts` and ensure schema parity tests pass.

3. Implement at least one real live collector behind policy gate:
- `collector.rss` using a safe parser and normalized output contract.
- Ensure behavior matrix is explicit:
- Public profile: blocked.
- Experimental + `ALLOW_LIVE_AUTOMATION` set to `false`: stubbed/blocked.
- Experimental + `ALLOW_LIVE_AUTOMATION=true`: allowed and functional.

4. Implement one publish path beyond stage-only:
- Start with local `git` publisher (policy-gated) or PR publisher stub with explicit actionable refusal metadata if remote credentials are unavailable.

5. Harden queue concurrency:
- Introduce lock discipline for queue file mutation (cross-platform lock strategy or safe lockfile protocol).
- Add two-worker race tests proving no duplicate claim of the same active work item.

6. Fix packaged plugin compatibility:
- Remove/mitigate `core.plugin_manifest` hard dependency path for standalone Merlin runtime.
- Ensure packaged plugins that should load actually load in `python merlin_cli.py plugin list`.

Constraints:
- Preserve existing operation-envelope contracts and backward compatibility.
- Keep policy semantics explicit (`allowed`, `blocked`, `stubbed`) with no hidden live fallback.
- Keep default `ALLOW_LIVE_AUTOMATION=true` intact.
- Add targeted tests for each new behavior branch.

Required verification before handoff:
- `python -m pytest -q`
- Include targeted command outputs for:
- discovery operation call via `/merlin/operations`
- public vs experimental policy behavior
- concurrent queue claim test
- plugin list load health (no unintended packaged-plugin skips)

Output format for your final report:
- Summary of implemented changes.
- File list touched.
- Policy behavior matrix proven by tests.
- Remaining risks and exact next steps.

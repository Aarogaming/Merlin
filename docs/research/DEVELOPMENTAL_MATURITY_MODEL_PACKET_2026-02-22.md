# Developmental Maturity Model Packet (2026-02-22)

## Purpose

Translate the "raise and educate a child" analogy into a practical, non-anthropomorphic system model for Merlin that can improve safety, reliability, and long-run capability growth.

This packet is scoped to repository-local Merlin architecture and is intended to feed next implementation passes.

## Framing (Non-Anthropomorphic)

Useful interpretation:

- "Child development" == staged capability release under supervision.
- "Education" == curriculum, feedback, and promotion gates.
- "Maturity" == proven reliability, policy compliance, and calibrated autonomy.

Avoid:

- Treating the system as conscious or value-aligned by default.
- Replacing explicit governance with intuition.
- Allowing self-modification without hard gates and rollback.

## Current Merlin Baseline (Relevant Strengths)

Merlin already has several maturity-building primitives:

1. Deterministic routing contracts and fallback taxonomy.
2. Operation envelope schemas and fixture-backed contract tests.
3. Optional policy gates (safety checks, rollout flags, DMS controls).
4. A/B and usage economics telemetry.
5. Release/checklist automation and CI quality gates.

These are strong foundations for a staged maturity model rather than a single binary "autonomous/not autonomous" state.

## Developmental Mapping to System Design

| Human Development Lens | System Analog | Existing Merlin Capability | Gap to Close |
| --- | --- | --- | --- |
| Safety and attachment | Stable guardrails and predictable failure behavior | Fallback taxonomy, policy checks, schema validation | Formal maturity tier policy controlling unsafe capability jumps |
| Boundaries and discipline | Explicit permission model and action constraints | Operation feature flags, read-only/restriction branches | Per-tier allowlist for operations/tools and external side effects |
| Guided practice | Supervised execution with audit trail | Envelope audit metadata and error contracts | "Mentor pass" requirement for high-risk operation classes |
| Curriculum | Progressive skill exposure | Router/task heuristics and tests | Tiered curriculum bundles with promotion criteria |
| Reflection | Self-evaluation before acting | Quality scoring and telemetry hooks | Standardized self-critique gate for ambiguous/high-impact tasks |
| Memory maturation | Reliable memory with provenance and confidence | Research session provenance and dedupe | Confidence decay/reinforcement policy and stale-memory demotion |
| Socialization | Multi-agent protocol cooperation | Interop docs and contract baselines | Cross-agent trust contract versioning tied to maturity tier |
| Adolescence to adulthood | Increasing autonomy with accountability | A/B rollout controls and error budgets | Promotion/demotion engine with hard rollback triggers |

## Proposed Merlin Developmental Maturity Model (MDMM)

### Tier M0: Protected

- Goal: deterministic safety and contract correctness.
- Allowed behavior:
  - No external side effects unless explicitly requested.
  - Strict fallback to stable backends.
  - Read-only or constrained operations by default.
- Promotion gate:
  - Contract suites pass.
  - Zero critical policy violations in rolling window.

### Tier M1: Guided

- Goal: supervised execution for bounded tasks.
- Allowed behavior:
  - Selective tool use with strong audit metadata.
  - Mandatory "mentor pass" for high-risk tasks.
- Promotion gate:
  - Stable success/error contract fidelity.
  - Bounded fallback/error rates by operation family.

### Tier M2: Apprenticed

- Goal: limited autonomous decomposition and execution.
- Allowed behavior:
  - Multi-step plans with checkpointed validation.
  - Controlled write operations under policy.
- Promotion gate:
  - Passing scenario/regression corpus.
  - Evidence of controlled rollback behavior during fault injection.

### Tier M3: Operational

- Goal: production-grade autonomy for approved classes.
- Allowed behavior:
  - Wider operation/tool latitude with strict telemetry.
  - Adaptive routing and quality/cost optimization enabled.
- Demotion triggers:
  - Error budget breach.
  - Policy drift or repeated critical regressions.

### Tier M4: Research-Autonomous (Experimental)

- Goal: bounded self-improvement experiments under hard governance.
- Allowed behavior:
  - Controlled experiment proposals.
  - No direct policy/schema mutation without human approval.
- Hard requirement:
  - Fail-closed governance and instant downgrade to M0-M1 path.

## Beneficial Changes for Merlin (Actionable)

1. Add `MERLIN_MATURITY_TIER` and `MERLIN_MATURITY_POLICY_VERSION` in settings.
2. Stamp `maturity_tier` and `maturity_policy_version` into routing/operation metadata.
3. Implement per-tier operation/tool allowlists (deny by default for unmapped operations).
4. Add `mentor_pass_required` policy for high-impact operation categories.
5. Add promotion/demotion evaluator script using existing tests + telemetry thresholds.
6. Add memory-confidence lifecycle:
   - confidence decay over time,
   - reinforcement on corroboration,
   - stale memory de-prioritization.
7. Add incident-to-curriculum pipeline:
   - incident template -> regression fixture scaffold -> tracked learning item.
8. Add maturity dashboard panel:
   - tier, promotion readiness, recent regressions, policy violations.

## Suggested Implementation Packets (Next)

| Suggested ID | Scope | Risk | Outcome |
| --- | --- | --- | --- |
| `S132` | Settings + metadata fields for maturity tier stamping | R1 | Uniform visibility of current maturity policy in responses/status |
| `S133` | Per-tier operation allowlist gate in API dispatch | R1 | Prevents capability jumps and constrains side effects |
| `S134` | Mentor-pass policy hook for high-risk operation classes | R2 | Adds supervised checkpoint before risky actions |
| `S135` | Promotion/demotion evaluator script + JSON report artifact | R2 | Objective lifecycle governance based on evidence |
| `S136` | Memory confidence decay/reinforcement in research manager | R2 | Better long-run memory hygiene and reduced stale influence |
| `S137` | Incident-to-regression scaffold command in scripts | R2 | Converts failures into durable learning tests |
| `S138` | Maturity dashboard status card | R2 | Operational transparency and intervention readiness |

## Risks and Guardrails

Primary risks:

1. Anthropomorphic policy drift ("it seems mature" without evidence).
2. Over-constraining useful behavior with rigid tiers.
3. Metrics gaming if promotion thresholds are shallow.

Guardrails:

1. Evidence-first promotion gates (tests + telemetry + incident-free windows).
2. Explicit demotion path on budget/policy breach.
3. Human approval required for tier policy edits and schema-affecting changes.

## Recommended Immediate Next Pass

Start with `S132` and `S133` (low-blast governance controls), then `S135` to make promotions evidence-based before adding deeper autonomy behaviors.


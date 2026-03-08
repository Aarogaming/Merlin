# Merlin Agent Guide

## Primary Optimization Objective (P0)
- P0 is user time efficiency: maximize useful progress per user interaction.
- Treat repetitive "proceed" requests as a defect; eliminate them by default.
- Use an interruption budget of <= 1 decision request per substantial task.

## Execution Cadence (Autonomy-First)
- Default to autonomous multi-step execution after task receipt.
- Do not pause for repetitive "proceed" confirmations during normal implementation.
- Continue through investigate -> plan -> implement -> validate -> iterate until complete.
- Interrupt only for true blockers, destructive actions, or major strategic forks.

## Decision Threshold
- Default profile is `hands-off`.
- `hands-off` interrupts only on blockers/destructive actions/material strategic forks.
- Use `normal` or `low` only if explicitly requested by the user.

## Scope
This file defines default operating behavior for IDE agents working inside `Merlin` (research manager and CI orchestration module).

## Primary Goals
1. Maintain research manager capabilities and CI orchestration
2. Preserve integration with Library federation contracts
3. Keep autonomous research workflows stable and reproducible
4. Support Chimera V2 consumer integration

## Operating Principles
1. Merlin is the research manager and CI orchestration subsystem within AaroneousAutomationSuite
2. All v1.0.0 governance rules apply (minimal dependencies, type-safe, deterministic)
3. Research workflows must be deterministic and reproducible
4. CI orchestration patterns must be resilient and recoverable

## Module Responsibilities
- Research manager operations and contract validation
- CI orchestration and test execution
- Chimera V2 research-manager consumer integration
- Federation discovery operation
- Integration with Guild and Library through federation contracts

## Validation Requirements
Before committing changes:
1. Verify research manager workflows function correctly
2. Test CI orchestration pipeline integration
3. Confirm Chimera consumer integration works
4. Validate federation contract compatibility
5. Test discovery operations across federation

## Version Control
- Repository: `https://github.com/Aarogaming/Merlin.git`
- Current Version: v1.0.0
- Default Branch: `main`
- Role: Research Manager & CI Orchestration

## Federation Integration
Merlin integrates with federation through:
- Library discovery contracts for artifact discovery
- Chimera V2 research-manager consumer for autonomous operations
- Guild CI triage for test result synchronization
- AaroneousAutomationSuite orchestration

## Research Workflow Constraints
- Research operations must be deterministic and reproducible
- CI workflows must be resilient to transient failures
- Chimera consumer must maintain contract compliance
- Discovery operations must respect federation boundaries

## Support & Escalation
- Research manager issues: Handle locally
- CI orchestration issues: Handle locally
- Chimera integration: Coordinate with Library
- Federation integration: Escalate to Library
- Orchestration issues: Escalate to AaroneousAutomationSuite

---

*This guide was created as part of the v1.0.0 production release.*

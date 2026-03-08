# Merlin Introspective Report

Date: 2026-02-24
Repo: `AaroneousAutomationSuite/Merlin`

## Executive Summary

Merlin is evolving into the reasoning/control-plane service for AAS: policy-gated operation handling, multi-backend model routing, and durable research/discovery memory. The repo has strong momentum on contract-driven API reliability and routing governance, but still has integration and operability gaps that prevent Merlin from fully acting as a first-class cross-repo orchestration node.

## What Merlin Is Trying To Accomplish

- Be AAS's contract-governed assistant service with stable operation envelopes and capability manifests.
- Route requests across multiple LLM backends (including optional DMS) with deterministic fallback and auditable metadata.
- Provide local-first, policy-safe research and discovery pipelines that generate durable knowledge artifacts.
- Serve as a reliable plugin-capable subsystem in a larger multi-repo control-plane (AAS + Library + Guild + Merlin).

## What Is Working Well

- Operation envelope infrastructure is broad and test-backed (`/merlin/operations`, capability/spec/flags endpoints, contract fixtures, error taxonomy).
- LLM routing stack has substantial hardening and telemetry maturity (adaptive/parallel/streaming + DMS governance layers).
- Research manager has robust lifecycle and quality features (signals, briefs, provenance, calibration, archival, API + CLI support).
- DiscoveryEngine v1 exists and is functional for offline-first runs.
- CI/gate posture is strong for core modules (secret hygiene, mypy, pytest matrix, critical module coverage gate, contract sync checks).

## Current Shortcomings / Gaps

### P0 Gaps (block full mission)

- Discovery is not exposed through Merlin's operation-envelope API surface.
- Discovery live paths are still intentional stubs (`collector implementation deferred`, `publisher implementation deferred`) even when policy allows live automation.
- Packaged plugin ecosystem is partially nonfunctional in standalone Merlin runtime due to missing `core.*` imports used by many plugin packages.

### P1 Gaps (high leverage)

- Discovery queue implementation is file-rewrite based and not safe for true multi-process contention (no file locks, optimistic rewrite approach).
- Discovery telemetry is not yet integrated into API-level metrics/status surfaces; run reports are local artifacts only.
- Discovery has tests but is not part of current critical-module coverage gate scope.
- Discovery contracts are present but not yet part of operation-envelope protocol docs/fixtures for cross-repo invocation.

### P2 Gaps (maintainability)

- `merlin_api_server.py` remains very large and dispatch-heavy, creating change-risk concentration.
- Discovery profile docs currently describe behavior accurately, but implementation remains v1 and intentionally incomplete for live collectors/publishers.

## What Must Be True To Meet Merlin's Goal

- Discovery must be remotely invocable via the same contract/envelope model as other core Merlin operations.
- Policy gates must control real live-capability implementations (not just stubs) for at least one network collector and one publish path.
- Plugin packaging/runtime needs a stable local compatibility path so packaged plugins are not skipped in typical Merlin-only runs.
- Discovery queue/work leasing must be concurrency-safe enough for real Guild-like parallel workers.
- Discovery observability must be visible in standard Merlin status/metrics outputs, not only in filesystem artifacts.

## Recommended Next Work (Priority Order)

1. Add discovery operations to `/merlin/operations`.
2. Implement one production-grade live collector behind policy gate (`rss`) and one publish path (`git commit` or PR stub with explicit refusal metadata when unavailable).
3. Add queue locking/atomicity for concurrent workers and lease conflict safety.
4. Add discovery metrics endpoint integration and include discovery KPIs in dashboard/status.
5. Fix packaged plugin local compatibility (`core.plugin_manifest` fallback strategy or bundled shim).
6. Add discovery modules to typed/coverage critical path incrementally.

## Suggested Acceptance Criteria

- Envelope operation examples + fixtures exist for `merlin.discovery.run` and `merlin.knowledge.search` and pass schema tests.
- Public profile offline fixture run and Experimental profile live-gated run both pass in CI.
- At least one live collector succeeds in Experimental mode when `ALLOW_LIVE_AUTOMATION=true`, and reports `blocked/stubbed` deterministically when false.
- Concurrent queue claim test with two workers cannot duplicate processing of the same work item.
- Plugin listing in standalone Merlin no longer emits `No module named 'core'` skips for packaged plugins that should load.

## Strategic Note

Merlin's reliability/governance backbone is already strong. The main remaining challenge is convergence: making Discovery and plugin runtime behavior first-class in the same operational contract surface that the rest of Merlin already uses.

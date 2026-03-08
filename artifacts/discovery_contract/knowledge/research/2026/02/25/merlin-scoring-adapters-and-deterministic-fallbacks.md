---
title: "Merlin scoring adapters and deterministic fallbacks"
date: "2026-02-25"
source: ["fixture:merlin_lab"]
canonical_url: "https://example.org/aas/merlin-adapters"
tags: ["llm"]
confidence: 0.61
run_id: "run_20260225T163156Z_e1691c9f"
---

# Summary
LocalMerlin and NullMerlin adapters for scoring and summarization contracts.

# Why This Matters To AAS
This topic intersects with orchestration, policy gating, and durable knowledge capture for AAS discovery workflows.

# Technical Notes
No secondary technical snippet available.
Canonical URL: https://example.org/aas/merlin-adapters

# Integration Ideas (AAS)
- Route this signal through DiscoveryEngine queue leasing for deterministic retries.
- Use Merlin scoring confidence as a threshold for artifact generation gates.
- Keep indexing in Library-owned JSON index for repo-local portability.

# Risks / Policy Notes
Avoid proprietary feed scraping. Respect profile/capability gating and explicit ALLOW_LIVE_AUTOMATION approval before live collection or PR publishing.

# Action Items
- [ ] Create a follow-up implementation task in AAS task manager.
- [ ] Attach this artifact to the next integration planning cycle.
- [ ] Validate policy posture before enabling live collectors.

# DMS Integration Research Notes (2026-02-15)

## Decision intent
- Keep DMS optional and gated by `DMS_ENABLED` so existing backends remain stable.
- Use DMS primarily for long prompts and reasoning-heavy tasks, not for all requests.
- Keep deterministic, measurable A/B routing so quality and latency tradeoffs can be evaluated.

## Practical findings applied
- OpenAI-compatible routing should treat both `choices[*].message.content` and legacy `choices[*].text`/delta-like forms defensively.
- Streaming providers differ in response shape; collect both OpenAI-style SSE (`choices[...].delta.content`) and non-SSE forms (`message.content` or top-level `content`).
- For API compatibility and security, treat missing `DMS_URL`/`DMS_MODEL` as disable conditions and fail closed to existing routing.
- Record per-request routing metadata (`selected_model`, `prompt_size_bucket`, `dms_used`, `fallback_reason`) and emit AB metrics (requests/success/latency/quality sum) by variant for measurable impact.
- Track throughput with a rolling one-minute window for short-cycle behavior changes and regression detection.

## Roadmap notes
- P0: keep fail-open fallback (`dms -> existing backend`) and robust parser guards in place.
- P1: add explicit quality/latency measurement for each routing decision and expose via existing status endpoints.
- P2: add optional backoff/retry policy around DMS transport failures and per-route request IDs/headers for traceability.
- P2+: add dashboard/charting on `routing_metrics` and periodic health sampling for DMS endpoint.

## Mermaid behavior summary
- DMS route expected when:
  - prompt length threshold crossed (`DMS_MIN_PROMPT_CHARS`)
  - query/task indicates high-complexity reasoning in configured `DMS_TASK_TYPES`
- DMS is never mandatory; if unavailable or disabled, Merlin automatically continues with parallel/adaptive/streaming model pools.

## Research Notes (2026-02-15)
- Source: VentureBeat (published Feb 12, 2026) and linked NVIDIA arXiv summary describe DMS as dynamic KV-cache sparsification that reduces memory bandwidth and can preserve or improve reasoning quality on difficult benchmarks.
- Practical implications for Merlin:
  - Route DMS selectively to long prompts and reasoning-heavy categories (`analysis`, `code`, `planning`) as the current gate, not as a universal default.
  - Preserve short-term stability by keeping fallback into existing backends when DMS request, parsing, or transport fails.
  - Measure DMS impact through A/B metrics: latency/throughput quality deltas, not just single-shot accuracy.
- Adjacent roadmap:
  - `Pay for Hints, Not Answers` (arXiv Jan 2026) suggests staged prompting (LLM hint + SLM completion) as a potential next-level cost gate once DMS routing baseline is stable.

# Suggestions Bin

Repository: Merlin
Status: Active intake

Use this during roadmap downtime to capture research-backed suggestions.

Entry format (recommended):
- [R1] [H1] [lane=A] <suggestion text>
- problem: <what is broken or missing>
- impact: <expected value>
- dependencies: <optional>
- verify: <how to validate>
- rollback: <if applicable>

## Intake

- [R1] [H1] [lane=7] Add explicit DMS circuit-breaker + retry/backoff around `merlin_llm_backends._dms_chat` and route-level fallbacks.
  - problem: transient DMS failures can cascade into user-visible retries without limiting blast radius.
  - impact: bounds dependency blast radius and improves resilience under partial DMS outage while keeping existing backend behavior intact.
  - dependencies: `merlin_llm_backends.py`, `merlin_settings.py` timeout controls, `merlin_adaptive_llm.py`/`merlin_parallel_llm.py`/`merlin_streaming_llm.py` decision paths.
  - verify: inject repeated connection/timeouts in `tests/test_merlin_llm_backends.py` and assert fallback reason + immediate fallback-to-existing path within SLO window.
  - rollback: keep DMS disabled via `DMS_ENABLED=false`; revert to no-op branch if threshold breaches.
  - source: [Circuit breaker pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html), [retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html), [timeouts/retries/backoff with jitter](https://aws.amazon.com/id/builders-library/timeouts-retries-and-backoff-with-jitter/).

- [R1] [H1] [lane=7] Define a canonical fallback reason taxonomy for all DMS paths and include it in `response["metadata"]["fallback_reason"]`.
  - problem: current string reasons can drift and become hard to query in incident analysis.
  - impact: enables machine-sorted postmortems, SLO dashboards, and deterministic AB/kill-switch logic.
  - dependencies: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`, `tests/test_merlin_*`.
  - verify: add tests asserting `dms_unavailable`, `dms_malformed_response`, `dms_timeout`, and `parse_error` reasons.
  - rollback: default unknown failures to `dms_error` to preserve compatibility.

- [R1] [H1] [lane=3] Add low-overhead DMS endpoint health telemetry and health-aware routing gate.
  - problem: routing decision currently lacks freshness/availability signal before invocation.
  - impact: lowers mean fallback latency by avoiding dead-end DMS calls and enables automatic control-plane disable when health degrades.
  - dependencies: new periodic probe in `merlin_llm_backends.health_check` plus read-through cache for latency + status; routing checks via existing `_should_prefer_dms`.
  - verify: add tests/stubs around degraded probe state causing DMS skip and control fallback.
  - rollback: disable health gate via setting; fallback to existing `DMS_ENABLED` boolean behavior.

- [R1] [H1] [lane=5] Add OpenAI-compatible response-shape normalizer for reasoning providers (strictly parse `usage`, `model`, `id`, `cached_tokens`) in all backends.
  - problem: mixed OpenAI-compatible providers return `message.content`, top-level `content`, `text`, and streaming delta variants differently.
  - impact: reduces parser fragility, improves parity for metrics and moderation hooks, and avoids false failures in long-tail provider responses.
  - dependencies: existing `_extract_openai_compatible_content` + streaming chunk parser implementations.
  - verify: table-drive parser tests in `tests/test_merlin_llm_backends.py` + streaming variants.
  - rollback: keep parser compatibility mode and tolerate both raw and normalized paths.
  - source: [OpenAI chat completions response shape](https://platform.openai.com/docs/api-reference/chat/create-chat-completion), [streaming responses](https://platform.openai.com/docs/guides/streaming-responses).

- [R1] [H2] [lane=5] Track usage-token deltas and prompt bucket economics for DMS experiments using OpenAI-like `usage` fields and `cached_tokens`.
  - problem: latency impact alone cannot validate cost/sla tradeoff; throughput claims need token-normalized cost.
  - impact: supports true ROI measurement for DMS routing decisions and budget-aware policies.
  - dependencies: response payload handling + routing metrics schema + status endpoints in adaptive/parallel/streaming.
  - verify: add synthetic payload fixture with `usage.prompt_tokens`, `usage.completion_tokens`, `usage.prompt_tokens_details.cached_tokens`, assert route metrics emit cost proxies.
  - rollback: feature-flag metrics to disable and continue metadata-only flow.
  - source: [OpenAI chat usage fields](https://platform.openai.com/docs/api-reference/chat/create-chat-completion), [prompt caching semantics](https://platform.openai.com/docs/guides/prompt-caching/prompt-caching).

- [R1] [H2] [lane=7] Introduce error-budget controls for DMS rollout (temporary auto-disable on rolling-failure threshold and low-SLO conditions).
  - problem: no automatic protection currently halts experiments when DMS quality/success degrades.
  - impact: supports safe long-running autonomous sessions and protects user experience without manual intervention.
  - dependencies: routing metrics counters + startup config defaults and a periodic policy evaluator.
  - verify: simulate high fallback ratio and assert policy forces control path and emits `DMS_DISABLED_BY_POLICY`.
  - rollback: clear policy override and preserve env-driven control flow.
  - source: [Google SRE error budgets](https://sre.google/workbook/error-budget-policy/).

- [R1] [H1] [lane=6] Add explicit OpenAI compatibility mode for DMS as a first-class backend contract (model token budget, timeout, and idempotent-safe retries).
  - problem: DMS may need specialized per-route settings (timeouts, reasoning effort, max tokens) and request ids to support distributed tracing.
  - impact: increases interoperability with upstream infra, reduces ambiguous failures, and improves auditability.
  - dependencies: `merlin_settings.py` env surface (`DMS_URL`, `DMS_MODEL`, `DMS_API_KEY`, timeout constants), request headers + response metadata.
  - verify: contract test hits DMS payload shape includes model/model metadata and stable timeout budget in `_dms_chat`.
  - rollback: route through existing fallback path if schema contract check fails.

- [R1] [H2] [lane=9] Add a lightweight, deterministic local router benchmark fixture (long/short/complex prompt corpus) and nightly regression job for route policy.
  - problem: policy drift risk across routers (adaptive/parallel/streaming) without a fixed baseline.
  - impact: prevents accidental routing regressions and preserves expected DMS routing behavior across long sessions.
  - dependencies: `tests/test_merlin_*` and CI command for targeted test group.
  - verify: baseline route snapshots for `selected_model`, `prompt_size_bucket`, `dms_used` remain stable unless explicit policy bump committed.
  - rollback: skip benchmark by setting schedule gate off; restore from last known baseline.

- [R1] [H2] [lane=4] Add output quality sampling for DMS paths (lightweight human-grade rubric tags + optional grader script).
  - problem: no direct quality score currently stored in routing telemetry beyond generic feedback.
  - impact: enables DMS/Control AB comparisons with both latency and quality, not only success/latency.
  - dependencies: `routing_metrics.quality_sum` usage, status endpoints, optional grading hook.
  - verify: add synthetic grade fixtures and validate that AB variant quality aggregates are non-decreasing with successful control override.
  - rollback: keep quality aggregation optional in metadata and default to 0.

- [R1] [H2] [lane=8] Introduce DMS capability matrix and model provenance checks (including non-commercial model license awareness).
  - problem: DMS model choices can be incompatible across deployment contexts if legal/runtime constraints differ.
  - impact: reduces compliance risk and prevents unsupported deployment combinations.
  - dependencies: model config docs and startup validation for `DMS_MODEL` compatibility.
  - verify: unit test asserting warning when DMS model uses non-commercial restriction markers.
  - rollback: require explicit `DMS_ENABLED=true` + explicit waiver flag for exceptions.
  - source: [NVIDIA Qwen3-8B-DMS-8x model card](https://huggingface.co/nvidia/Qwen3-8B-DMS-8x).

- [R1] [H2] [lane=5] Extend streaming parser to explicitly handle `[DONE]` and non-JSON SSE anomalies for DMS endpoints.
  - problem: currently stream parsing can be brittle on provider-specific SSE edge cases.
  - impact: stronger resilience for long prompt streaming sessions and cleaner fallback classification.
  - dependencies: `merlin_streaming_llm.py` stream extraction path.
  - verify: add streaming SSE fixtures containing heartbeat/comment frames and ensure content assembly remains deterministic.
  - rollback: return stream error chunk with explicit `fallback_reason` and switch to non-streamed fallback path.

- [R1] [H1] [lane=5] Document routing decision contracts and sample request/response flow (DMS-on / DMS-off / AB-control) in `docs/dms_research_notes.md`.
  - problem: implementation rationale and operational behavior are spread across modules and not centrally documented for 8+ agent handoff.
  - impact: reduces transfer risk, accelerates onboarding, and aligns long-running teams on exact invariants.
  - dependencies: `docs/dms_research_notes.md`, `README.md`, status endpoints.
  - verify: doc review gate in roadmap handoff checklist includes these flows.
  - rollback: preserve existing docs; add append-only extension.

## Research Notes (Curated)

- DMS context: NVIDIA’s Dynamic Memory Sparsification reduces KV cache footprint with adaptive learned eviction + delayed eviction and reports 8x compression with strong benchmark gains on reasoning tasks while preserving or improving accuracy. It is used in `nvidia/Qwen3-8B-DMS-8x` and positioned for inference-time scaling with compatibility claims for Hugging Face/standard stacks.
  - source: [VentureBeat summary](https://venturebeat.com/orchestration/nvidias-new-technique-cuts-llm-reasoning-costs-by-8x-without-losing-accuracy/), [arXiv 2506.05345](https://ar5iv.labs.arxiv.org/html/2506.05345), [HF model card](https://huggingface.co/nvidia/Qwen3-8B-DMS-8x).

- OpenAI-compatible routing reliability: Chat endpoints return chat choice messages; streaming endpoints are SSE chunk streams with delta-style chunk extraction patterns (`choices[...].delta.content` for chat chunks), and non-chat text-only variants still occur in legacy payloads. Prompt caching requires prefixes + `prompt_tokens_details.cached_tokens` and can materially affect observed latency/cost.
  - source: [OpenAI chat completions reference](https://platform.openai.com/docs/api-reference/chat/create-chat-completion), [streaming guide](https://platform.openai.com/docs/guides/streaming-responses), [prompt caching guide](https://platform.openai.com/docs/guides/prompt-caching/prompt-caching).

- Reliability guardrails: standard distributed-systems patterns suggest circuit breakers and capped backoff with jitter for failures, with explicit guidance on timeouts and retry-idempotency tradeoffs.
  - source: [AWS circuit breaker](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html), [AWS retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html), [AWS Builders timeout/retry guidance](https://aws.amazon.com/id/builders-library/timeouts-retries-and-backoff-with-jitter/).

- Measurement and rollout control: operational systems increasingly treat routing reliability as an SLO/economy tradeoff; temporary experiment disablement under threshold breaches is consistent with error-budget control philosophy.
  - source: [Google SRE error budgets](https://sre.google/workbook/error-budget-policy/).

## Cultural + Service Lens

- Repo identity alignment: the name `Merlin` maps well to the project’s strategic routing role if framed as a "counselor model" selecting the right path.
  - problem: team members can under-define DMS as a total replacement instead of an advisory tier.
  - impact: clearer governance and safer rollout language: DMS is the "high-cost oracle" while existing backends remain stable "kingdom core."
  - verify: incorporate this framing in `docs/dms_research_notes.md` and code comments where DMS selection logic is documented.
  - source: [Britannica Merlin legend](https://www.britannica.com/topic/Merlin-legendary-magician), [Wikipedia Merlin overview](https://en.wikipedia.org/wiki/Merlin).

- Service naming collision risk: `Merlin` exists in NVIDIA’s production AI ecosystem (`NVIDIA Merlin`, `Merlin Systems`, `Transformers4Rec`), so architecture docs should disambiguate.
  - problem: confusion in runbooks/integrations when referring to "Merlin API" or "Merlin pipeline".
  - impact: avoids wrong integration assumptions (e.g., assuming recommender-stack semantics when configuring DMS route).
  - verify: add a short glossary in `docs/README.md` or `docs/dms_research_notes.md` for internal Merlin versus NVIDIA Merlin references.
  - source: [NVIDIA Merlin overview](https://developer.nvidia.com/merlin), [Merlin GitHub systems](https://github.com/NVIDIA-Merlin/systems).

- Historical-to-service analogy: Merlin’s advisor archetype suggests an explicit control-plane pattern—small trusted set of policies choosing when to escalate to "deep oracle" paths.
  - problem: routing policy can become a monolith if DMS knobs are merged directly into global defaults.
  - impact: supports incremental, explainable policy evolution and easier policy audits by role (strategy, safety, throughput).
  - verify: add policy ownership notes in a dedicated section and a minimal "policy audit" checklist for high-cost routes.
  - rollback: retain existing environment-driven decision behavior if control-plane refactor is delayed.

- Real-world stability model: systems with high-throughput inference paths typically preserve a stable baseline route and add "reasoning-only" lanes only under explicit conditions.
  - problem: without a proven tiering doctrine, teams may over-assign difficult tasks to expensive backends.
  - impact: better reliability and cost control in production, aligns with the "long prompt / high complexity only" rule.
  - source: [OpenAI-compatible server model](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/) for route abstraction patterns; [AWS circuit breaker guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html).

- Mytho-real naming for long-run planning: use a short mapping legend in docs to maintain consistent communication across agents.
  - problem: 8+ parallel agents can drift on terminology and decision criteria.
  - impact: faster synchronization, fewer semantic conflicts when delegating work across AAS Guild lanes.
  - verify: add a single paragraph in `docs/README.md` under architecture overview: DMS=oracle lane, adaptive/parallel/streaming=stable lanes, fallback=round-table safety.

## Advanced Research Notes

- DMS routing maturity can be strengthened by separating decision signals into two orthogonal gates: prompt-scale and task-complexity. Current NVIDIA Blueprint guidance demonstrates separate task/complexity routers and shows this is the normal production pattern.
  - problem: single-threshold heuristics under-fit conversations where short but highly abstract questions still need reasoning, or long but templated prompts can be solved cheaply.
  - impact: fewer false escalations and better cost control under mixed workload.
  - dependencies: optional classifier output integration in `merlin_adaptive_llm._should_prefer_dms`, adaptive/parallel/streaming parity.
  - verify: add fixture cases where long-plain prompts stay on control and short-reasoning prompts escalate.
  - source: [NVIDIA blueprint router flow](https://developer.nvidia.com/blog/deploying-the-nvidia-ai-blueprint-for-cost-efficient-llm-routing/), [NeMo prompt task/complexity classifier](https://docs.nvidia.com/nemo/curator/0.25.7/curate-text/process-data/quality-assessment/distributed-classifier.html).

- Add DMS-specific request timeout profile with connect/read split and low default retry budget.
  - problem: long-context reasoning can exceed generic timeout envelopes while transient DNS/network failures still need quick failure.
  - impact: lower tail latencies for unavailable endpoints and fewer cascading retries under temporary congestion.
  - dependencies: `merlin_llm_backends._dms_chat`, shared request client wrappers if added, and fallback path telemetry.
  - verify: add timed fault injection test where connect stalls and where read stalls; assert fallback reason and bounded elapsed time.
  - source: [OpenAI chat completion params](https://platform.openai.com/docs/api-reference/chat/create-chat-completion), [OpenAI production timeout note](https://platform.openai.com/docs/actions/production/timeouts), [OpenAI background mode for long tasks](https://platform.openai.com/docs/guides/background).

- Normalize streaming handling around explicit SSE states and optional final usage events.
  - problem: providers may emit heartbeat comments, non-JSON frames, or `usage`-bearing terminal chunks; fragile parsers increase fallback noise.
  - impact: more reliable stream completion for long reasoning responses and cleaner `streaming` path metrics.
  - dependencies: `merlin_streaming_llm.py` stream parser, stream error reporting, route metadata path.
  - verify: add non-JSON and final usage-chunk fixtures to streaming tests.
  - source: [OpenAI streaming responses](https://platform.openai.com/docs/guides/streaming-responses), [OpenAI chat completion object](https://platform.openai.com/docs/api-reference/chat/object), [vLLM OpenAI-compatible stream options](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/).

- Track `reasoning_effort` and reasoning token fields as a control input when available.
  - problem: some reasoning-capable OpenAI-compatible endpoints expose explicit effort knobs and split reasoning token counts, and Merlin ignores this today.
  - impact: makes DMS usage measurable for latency-sensitive tasks and allows policy to lower effort for non-critical routes.
  - dependencies: DMS payload builder in `merlin_llm_backends.py`, response normalization of `usage`.
  - verify: tests with explicit `reasoning_effort` passthrough and prompt-size buckets; assert usage fields still parsed even if absent.
  - source: [OpenAI chat completion response shape](https://platform.openai.com/docs/api-reference/chat/create-chat-completion), [OpenAI usage details](https://platform.openai.com/docs/guides/prompt-caching/prompt-caching).

- Add lightweight "routing reason" trace fields in metadata for explainability: e.g., `router_rule_version`, `decision_confidence`, `prompt_tokens_bucket`.
  - problem: current metadata tracks model and bucket but not policy version/context for auditability.
  - impact: enables deterministic replay and rollback decisions across 8+ agents or after long run windows.
  - dependencies: `merlin_adaptive_llm`, `merlin_parallel_llm`, `merlin_streaming_llm`, status/telemetry endpoints.
  - verify: add contract tests that assert versioned metadata remains stable for unchanged policy.
  - source: [OpenTelemetry genAI metric conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/).

- Consider prompt memoization via template-level prefixes and `prompt_cache_key` style hints on DMS routes first, because OpenAI-style cache semantics can materially reduce input cost in repeated-context workloads.
  - problem: high-throughput systems often re-send nearly identical task headers/system prompts and pay repeated prefill cost.
  - impact: cheaper inference and lower first-token latency under stable context patterns.
  - dependencies: prompt composer layer and DMS route payload config.
  - verify: add synthetic benchmark showing repeated prefix reduces `cached_tokens` and improves median latency.
  - source: [OpenAI prompt caching](https://platform.openai.com/docs/guides/prompt-caching/prompt-caching), [VLLM OpenAI-compatible endpoint docs](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/).

- Historical alignment cue: use "Merlin-as-oracle" language in every operational runbook and status dashboard to avoid role confusion with inference providers.
  - problem: the internal team has inconsistent labels for the router itself versus model endpoints.
  - impact: clearer ownership semantics, safer deployment decisions, lower governance friction.
  - verify: update one operations example in `docs/README.md` and one metrics dashboard label set with oracle/oracle-fallback language.

- Strategic roadmap stretch: evaluate token-level adaptive routing (`Reasoner -> SLM -> Reasoner`) in Merlin as a post-baseline optimization path.
  - problem: full-request routing is coarse; many prompts only need short reasoning phases.
  - impact: potentially large efficiency gains if staged reasoning can be safely delegated.
  - dependencies: control-plane refactor for dual-pass orchestration and streaming checkpointing.
  - verify: isolate as long-horizon experiment in dedicated branch; compare cost/latency/quality against current long-oracle route.
  - source: [When to Reason: Semantic Router for vLLM](https://arxiv.org/abs/2510.08731), [RelayLLM: Efficient Reasoning via Collaborative Decoding](https://arxiv.org/abs/2601.05167).

## Lightweight Normalization Candidates (Addendum)

- Route-gate policy deduplication across adapters
  - repo_fit: adaptive/parallel/streaming and emotion chat each duplicate `max(2000, DMS_MIN_PROMPT_CHARS // 2)`/task-type logic, so a single policy function will prevent drift.
  - source: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`, `merlin_emotion_chat.py`
  - impact: reduced decision inconsistency between modes; easier audits and safer rollback of threshold changes.
  - risk_class: R1

- Rate-limit-aware DMS request caps
  - repo_fit: Long prompt calls plus high `DMS_AB_DMS_PERCENTAGE` can trigger avoidable 429s during bursty usage in this router-centric design.
  - source: https://cookbook.openai.com/examples/how_to_handle_rate_limits
  - impact: lowers chance of hard throttles, keeps fallback paths colder, and improves request completion probability under peak load.
  - risk_class: R2

- Stable fallback taxonomy and test contract
  - repo_fit: routing decisions already carry `fallback_reason` in `merlin_*_llm.py`; codifying a canonical reason set improves existing telemetry.
  - source: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`
  - impact: cleaner policy analysis and faster triage when A/B quality shifts.
  - risk_class: R1

- Request-scoped trace header propagation
  - repo_fit: DMS route calls are already centralized in `merlin_llm_backends.py`; adding request IDs gives end-to-end tracing without changing model providers.
  - source: https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: faster incident correlation across DMS endpoint, Merlin routers, and user-level outcomes.
  - risk_class: R2

- SSE parser contract tests for malformed frames
  - repo_fit: `merlin_streaming_llm.py` streams from multiple backends and must tolerate comment frames/heartbeat-like records in production.
  - source: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - impact: fewer stream parser exceptions and more deterministic fallback transitions.
  - risk_class: R1

- Streaming prompt-bucket experiments in A/B harness
  - repo_fit: existing AB harness already exists for routing; applying the same harness to streamed requests gives parity where user-visible UX risk is highest.
  - source: `tests/test_merlin_adaptive_llm.py`, `tests/test_merlin_streaming_llm.py`, `merlin_ab_testing.py`
  - impact: confidence in DMS decision quality before routing changes hit production traffic.
  - risk_class: R2

## Lightweight Normalization Candidates

- Two-Dimensional DMS Gate
  - repo_fit: Merlin already has length + task-type heuristics; splitting them into orthogonal gates aligns with NVIDIA’s LLM router blueprint and prevents single-threshold over-routing.
  - source: https://developer.nvidia.com/blog/deploying-the-nvidia-ai-blueprint-for-cost-efficient-llm-routing/
  - impact: reduces false positives by routing long but trivial prompts less aggressively, and saves cost on noisy long prompts.
  - risk_class: R1

- DMS Timeout Budgets per Prompt Cohort
  - repo_fit: Merlin’s `DMS_MIN_PROMPT_CHARS` already defines cohorts, so endpoint timeout behavior can be tuned per cohort instead of one global value.
  - source: https://platform.openai.com/docs/guides/latency-optimization, https://platform.openai.com/docs/guides/production-best-practices/model-overview
  - impact: bounds user-facing stall risk while letting larger reasoning prompts use longer budgets.
  - risk_class: R2

- Circuit Breaker + Retry Jitter for DMS Calls
  - repo_fit: DMS is one external dependency in a shared routing path; transient failures should short-circuit quickly and self-heal without destabilizing all users.
  - source: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html, https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html, https://aws.amazon.com/id/builders-library/timeouts-retries-and-backoff-with-jitter/
  - impact: lowers cascading failure risk and protects adaptive/parallel/streaming control planes during endpoint saturation.
  - risk_class: R1

- Deterministic Streaming Ingestion for SSE Edge Cases
  - repo_fit: `merlin_streaming_llm.py` handles real user traffic; `[DONE]`, keep-alive, and usage-in-terminal chunks should be treated deterministically across OpenAI-compatible providers.
  - source: https://platform.openai.com/docs/guides/streaming-responses, https://docs.vllm.ai/en/stable/serving/openai_compatible_server/, https://lmstudio.ai/docs/developer/rest/streaming-events
  - impact: fewer stream parser failures and cleaner fallback transitions from streaming to non-streaming paths.
  - risk_class: R1

- Include Trace Metadata for Routing Decisions
  - repo_fit: Existing Merlin metrics already track `selected_model`; request-scoped metadata can support long run postmortems and deterministic replay when tuning thresholds.
  - source: https://platform.openai.com/docs/api-reference/chat/object
  - impact: easier root-cause and rollback analysis when routing quality regresses under production load.
  - risk_class: R2

- Prompt Cache-Aware Composition
  - repo_fit: Merlin prompts are often repetitive (`system` + tools + policy); stable-prefix structure directly maps to DMS routing ROI.
  - source: https://platform.openai.com/docs/guides/prompt-caching/prompt-caching
  - impact: lower latency and lower prompt-token cost in workloads with stable context scaffolding.
  - risk_class: R2

- Model-Selection Escalation with Quality Floor
  - repo_fit: DMS route should remain a deliberate exception; quality floor from evaluation harness keeps the oracle lane from becoming a default path.
  - source: https://platform.openai.com/docs/guides/model-selection/principles
  - impact: faster serving with small/fast models for routine prompts while preserving accuracy on complex tasks.
  - risk_class: R1

- Coded Identity of Merlin as “Oracle Lane”
  - repo_fit: Multiple teams and agents reference Merlin often; explicit “oracle vs stable lanes” language reduces integration mistakes in parallel development.
  - source: https://developer.nvidia.com/merlin, https://www.britannica.com/topic/Merlin-legendary-magician
  - impact: lowers operational ambiguity in runbooks when deciding when to invoke DMS versus stable backends.
  - risk_class: R3

## Lightweight Normalization Candidates (Transport)

- Centralize outbound request session usage
  - repo_fit: `merlin_llm_backends.py` currently creates new connections per request, while adaptive/parallel/streaming all call into it for high-throughput routing traffic.
  - source: https://requests.readthedocs.io/en/master/user/advanced/
  - impact: fewer connection setup costs and lower tail latency under repeated DMS traffic.
  - risk_class: R2

- Add targeted status-code retry policy for transient failures
  - repo_fit: fallback currently happens on any exception in `_dms_chat`; adding 429/5xx retrying only for transient classes avoids unnecessary failover.
  - source: https://docs.python-requests.org/en/stable/_modules/requests/adapters/, https://cookbook.openai.com/examples/how_to_handle_rate_limits
  - impact: less unnecessary fallback noise and better DMS recoverability during short blips.
  - risk_class: R1

- Separate response parse failures from transport failures
  - repo_fit: DMS parser wraps all exceptions as `dms request failed`, losing visibility when valid HTTP got malformed JSON.
  - source: https://platform.openai.com/docs/api-reference/chat/create-chat-completion, https://docs.python-requests.org/en/stable/user/advanced/
  - impact: deterministic fallback reasons become possible for malformed payloads versus network-level errors.
  - risk_class: R1

- Add DMS request-level cache hints when supported
  - repo_fit: DMS route payload is compatible with OpenAI-style chat fields; adding optional `prompt_cache_key` can improve cache hit behavior on repeated system/policy prompts.
  - source: https://platform.openai.com/docs/guides/prompt-caching/prompt-caching
  - impact: lower `prompt_tokens`, lower latency, and stronger cost predictability on repetitive operations.
  - risk_class: R3

- Router rule version stamping
  - repo_fit: all three routers (`merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`) emit metadata, but no versioned policy identifier, making rerun and rollback analysis harder.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
  - impact: deterministic replay of routing outcomes after policy edits and cleaner rollback of A/B regressions.
  - risk_class: R2
  - notes: Add `router_rule_version` once in a central `DecisionContext`.

- Stream parser handles final data and `[DONE]` explicitly
  - repo_fit: `_stream_model` in `merlin_streaming_llm.py` currently ignores non-JSON SSE frames and has generic `json.JSONDecodeError` handling; this hides protocol edge cases in DMS streams.
  - source: https://platform.openai.com/docs/api-reference/chat/create-chat-completion, https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - impact: less stream parser failure and cleaner fallback path on mixed SSE implementations.
  - risk_class: R1
  - notes: Add explicit skip rules for `data: [DONE]`, empty data, and heartbeat comments.

- Enrich decision reason with route confidence signals
  - repo_fit: routing telemetry already stores `prompt_size_bucket`, `dms_used`, and `fallback_reason`; adding confidence metadata supports governance without changing control logic.
  - source: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`, https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: better operator insight when deciding if DMS thresholds should be raised/lowered.
  - risk_class: R2
  - notes: Derive a simple score from `is_long_prompt`, task-type match, and complexity.

- Propagate request correlation through backend calls
  - repo_fit: `merlin_api_server.py` accepts operation envelopes with `correlation_id`, but DMS calls do not forward that signal into headers/metadata.
  - source: https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: faster incident correlation between API, provider logs, and Merlin status events.
  - risk_class: R2
  - notes: Thread an optional `x-correlation-id` header through `merlin_llm_backends.LLMBackend` request path.

- Capture OpenAI-style rate-limit headers on DMS failures
  - repo_fit: existing fallback metrics count failures but omit quota context; retries can be misinterpreted without `x-ratelimit-*` signals.
  - source: https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff
  - impact: faster tuning of `DMS_AB_DMS_PERCENTAGE` and backoff strategy during throttling events.
  - risk_class: R2
  - notes: Persist observed `x-ratelimit-remaining-*` and `x-ratelimit-reset-*` in optional `fallback_reason`.

- Scope retryable verbs for DMS POST calls
  - repo_fit: router requests are mostly POST with stateless inference, so retry policy should be explicit to avoid duplicate side effects from unknown providers.
  - source: https://urllib3.readthedocs.io/en/2.0.6/reference/urllib3.util.html
  - impact: safer idempotency assumptions for DMS calls and less blind retry churn under transient network faults.
  - risk_class: R2
  - notes: Configure `allowed_methods` (or explicit exception list) with `POST` only when provider side effects are known to be read-only.

- Standardize DMS timeout envelope by request class
  - repo_fit: current timeout plumbing reuses generic values; long-context reasoning calls can require longer waits than simple control prompts.
  - source: https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: better tail-latency control; lower false timeouts on valid long-form reasoning.
  - risk_class: R3
  - notes: Keep one short budget for `short` buckets and one extended for `long` DMS calls.

## Long-Term Research Candidates

- Token-Accurate DMS Routing Signals
  - repo_fit: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, and `merlin_streaming_llm.py` currently gate DMS on character length; token-aware routing would better match OpenAI quota behavior and reasoning cost.
  - source: https://platform.openai.com/docs/guides/prompt-caching/prompt-caching, https://platform.openai.com/docs/api-reference/chat/object
  - impact: reduced misrouting for multibyte-heavy inputs and more stable latency/cost comparisons across buckets.
  - risk_class: R2
  - notes: Start with fast approximate tokenizer in router and compare to char-length in an offline corpus.

- Provider-Resilient Retry Strategy for DMS POST
  - repo_fit: DMS uses OpenAI-compatible POST requests in all three routers; adding explicit retry policy there lowers transient blast-radius.
  - source: https://docs.python-requests.org/en/v1.0.4/user/advanced/, https://urllib3.readthedocs.io/en/2.6.3/reference/urllib3.util.html
  - impact: less noisy fallbacks from brief 429/5xx bursts while preserving quick escape on hard failures.
  - risk_class: R1
  - notes: Configure allowlist `POST` and `status_forcelist` with small retry budgets; keep failure taxonomy unchanged.

- Capture Streaming Usage and Reasoning Tokens
  - repo_fit: existing routing metadata tracks quality/latency but not usage fields from streamed responses, so cost- and throughput-based comparisons under DMS routing are incomplete.
  - source: https://platform.openai.com/docs/guides/streaming-responses, https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: enables DMS A/B control on token economics and reasoning density rather than latency alone.
  - risk_class: R2
  - notes: Persist final usage chunk where available and fallback to aggregate response metadata when absent.

- Gradual DMS Rollout with Canary-Style Controls
  - repo_fit: routing already has experiment toggles (`DMS_AB_ENABLED`/`DMS_AB_DMS_PERCENTAGE`); canary mechanics can be reused for staged release safety.
  - source: https://docs.aws.amazon.com/blogs/machine-learning/take-advantage-of-advanced-deployment-strategies-using-amazon-sagemaker-deployment-guardrails/
  - impact: prevents a hard switch to DMS under unstable endpoints and enables rollback based on model-level SLOs.
  - risk_class: R1

- Correlate Backend Traces with Conversation Lifecycle IDs
  - repo_fit: API request metadata already carries context fields, but DMS calls don't propagate IDs to backend headers or decision logs.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/, https://platform.openai.com/docs/api-reference/chat/create-chat-completion
  - impact: faster triage on cross-model regressions and easier incident reconstruction between adapters.
  - risk_class: R2
  - notes: Add optional `x-correlation-id` and `conversation_id` path through `merlin_api_server.py` and `merlin_llm_backends.py`.

- Structured Rollback Reasoning with Error Taxonomy
  - repo_fit: routers already surface `fallback_reason`; codifying a bounded enum enables policy automation (auto-disable, canary rollback).
  - source: https://platform.openai.com/docs/guides/error-codes/api-errors, https://docs.aws.amazon.com/id/builders-library/timeouts-retries-and-jitter/
  - impact: predictable control-plane automation and faster restoration when DMS quality or SLO drops.
  - risk_class: R1
  - notes: Add explicit reasons for transport, parser, timeout, and rate-limit classes.

- Mythic Oracle Governance for Tier Policy
  - repo_fit: project identity is already Merlin-named; mapping policies to "Oracle" (DMS) and "Common Circle" (stable models) codifies escalation and accountability.
  - source: https://www.britannica.com/topic/Merlin-legendary-magician, https://developer.nvidia.com/merlin
  - impact: reduces role ambiguity for operators during routing policy changes and incident handling.
  - risk_class: R3
  - notes: Use this convention only in runbook language and dashboard labels, no runtime logic changes.

- Hardware and Deployment Compatibility Gate for DMS
  - repo_fit: DMS model cards list supported GPU generations; Merlin should prevent automatic selection in unsupported deployment contexts.
  - source: https://huggingface.co/nvidia/Qwen3-8B-DMS-8x
  - impact: avoids runtime degradation and failed starts from incompatible infrastructure assumptions.
  - risk_class: R3
  - notes: Add a startup/validation check for expected accelerator class when `DMS_ENABLED=true`.

- Reasoning Token Visibility in Quality Scoring
  - repo_fit: DMS routes are meant for harder reasoning tasks; current score path ignores `reasoning_tokens` and conflates quality with latency/final text only.
  - source: https://platform.openai.com/docs/api-reference/chat/object
  - impact: enables policy tuning by “reasoning density” and better separation of expensive-then-fast routing decisions.
  - risk_class: R2
  - notes: Track reasoning token usage where providers return it and normalize metrics when absent.

- Conversation-Scoped DMS AB Assignment
  - repo_fit: adaptive/parallel/streaming now use random DMS assignment per request, which can create split-brain experience within one conversation.
  - source: https://docs.python.org/3/library/random.html#random.Random
  - impact: cleaner experiment interpretation and better user continuity by keeping one stable routing arm per conversation/session.
  - risk_class: R2
  - notes: Derive AB arm from a stable hash of `correlation_id` (or user id + time bucket) before calling `_select_ab_variant`.

- DMS Concurrency Guardrail with Async Semaphore
  - repo_fit: Merlin backends can call DMS across adaptive/parallel/streaming paths in bursts; unbounded DMS concurrency can amplify provider throttling.
  - source: https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore
  - impact: protects low-latency tiers from saturation under traffic spikes and lowers fallback churn from throttling.
  - risk_class: R1
  - notes: Start with a small gate (e.g., 8 concurrent DMS calls) and expose as env-configured setting.

- Token-Bucket Cost Safety for DMS Spend Share
  - repo_fit: `merlin_cost_optimization.py` already records cost and traffic; integrating DMS share can prevent silent budget drift.
  - source: `merlin_cost_optimization.py`
  - impact: avoids surprise monthly spend spikes by enforcing hard policy when DMS cost/volume exceeds thresholds.
  - risk_class: R1
  - notes: Use existing budget alerts and add a DMS-only budget gate before routing attempts.

- Publish DMS Route Capability in Repo Manifest
  - repo_fit: AAS discovery currently advertises capabilities in `/merlin/operations/capabilities` and `docs/protocols`; explicit DMS capability improves orchestration decisions.
  - source: `merlin_api_server.py`; `docs/protocols/repo-capabilities-merlin-v1.md`
  - impact: external agents can explicitly inspect whether Merlin supports adaptive oracle routing before enabling complex workloads.
  - risk_class: R3
  - notes: Add a capability flag for DMS-backed reasoning with env requirements (`DMS_ENABLED`, model, endpoint).

- Add Operation-Envelope Fallback Codes for DMS Path
  - repo_fit: `_operation_error` schema already carries `{code, message, retryable}`, but DMS routing failures are currently collapsed at response layer.
  - source: merlin_api_server.py
  - impact: deterministic triage in AAS orchestration and easier automation for retry, dead-letter, or fallback to control path.
  - risk_class: R1
  - notes: Map specific `dms_*` and parser reasons to stable envelope error codes for assistant/chat operations.

- Stable Prompt-Complexity Proxy from `QueryContext`
  - repo_fit: `_should_prefer_dms` now infers complexity from query/task heuristics; richer context is already available in router `QueryContext`.
  - source: `merlin_adaptive_llm.py`; https://platform.openai.com/docs/guides/rate-limits/usage-limits
  - impact: fewer false DMS escalations and better routing efficiency under long-but-simple templated prompts.
  - risk_class: R2
  - notes: Add lightweight complexity flags (e.g., nested reasoning markers, step chains) and maintain backward-compatible thresholds.

- Deterministic Decision Snapshots for Replays
  - repo_fit: `routing_metrics` and `selected_model` are stateful; reproducible snapshots help extended experiments across 8+ agents.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
  - impact: faster root-cause on regressions by replaying exact input shape, rule-version, and DMS env state.
  - risk_class: R2
  - notes: Persist a minimal JSONL trail per decision containing prompt bucket, task type set, env hash, and AB variant.

- Percentile-Focused DMS Latency Telemetry
  - repo_fit: Merlin status endpoints currently expose average latency, while routing decisions often hinge on tail behavior under load.
  - source: https://opentelemetry.io/docs/specs/semconv/attributes-registry/ and https://sre.google/workbook/sli-slo-error-budget-policy/
  - impact: clearer guardrails for user-visible impact and better rollout thresholds when long-tail latency exceeds control budgets.
  - risk_class: R2
  - notes: Add rolling p50/p95/p99 for `request_latency_seconds` and DMS-fallback latency deltas.

- Structured Prompt-Complexity Corpus for Policy Drift Testing
  - repo_fit: Long-term stability goal needs periodic policy verification across long, short, and mixed-structure prompts from real Merlin workloads.
  - source: `tests/test_merlin_adaptive_llm.py`, `tests/test_merlin_parallel_llm.py`, `tests/test_merlin_streaming_llm.py`
  - impact: catches gate regressions before deployment and keeps routing behavior stable across code churn by parallel agents.
  - risk_class: R1
  - notes: Extend current unit fixtures with a frozen corpus and assert expected model choice for each lane.

- Context-Stable A/B Assignment for DMS
  - repo_fit: `AdaptiveLLMBackend`, `ParallelLLMBackend`, and `StreamingLLMBackend` currently use pseudo-random request-based DMS selection with `random.random`, which can flip variants mid-conversation.
  - source: https://launchdarkly.com/docs/sdk/features/context-config, https://docs.python.org/3/library/hashlib.html, https://launchdarkly.com/docs/home/releases/progressive-rollouts/
  - impact: keeps DMS/control assignment stable per user/session context, reducing split-brain behavior in long interactions and improving experiment validity.
  - risk_class: R2
  - notes: Hash `correlation_id` + optional user token to produce deterministic bucket assignment and compare with current random path in tests.

- Capture Provider Request Identity and Rate Metadata from DMS Calls
  - repo_fit: `merlin_llm_backends._dms_chat` currently logs only local exceptions; it does not preserve request identifiers or provider rate headers for telemetry.
  - source: https://platform.openai.com/docs/api-reference/debugging-requests
  - impact: enables rapid root-cause when DMS latency or quota is the bottleneck by attaching request IDs and ratelimit state into router metadata/fallback reasons.
  - risk_class: R2
  - notes: Store `x-request-id`/`X-Client-Request-Id` and `x-ratelimit-*` fields on success and failure paths when available.

- DMS Transport Pooling + Request Adapter Strategy
  - repo_fit: all DMS posts currently use top-level `requests.post`, missing session reuse and centralized retry/backoff policy while routers already collect throughput.
  - source: https://requests.readthedocs.io/en/master/user/advanced/, https://docs.python-requests.org/en/stable/_modules/requests/adapters/, https://urllib3.readthedocs.io/en/2.6.3/reference/urllib3.util.html
  - impact: reduces connection overhead and centralizes DMS retry controls for DNS/connect/read failures.
  - risk_class: R1
  - notes: Introduce a module-level `requests.Session` for `_dms_chat` with `HTTPAdapter(max_retries=Retry(...))` and conservative `allowed_methods` for retryability.

- Token-Exact Routing Buckets with `tiktoken`
  - repo_fit: `DMS_MIN_PROMPT_CHARS` currently gates by character count while tests already validate char-based behavior across routers.
  - source: https://platform.openai.com/docs/guides/managing-completions, https://platform.openai.com/docs/api-reference/debugging-requests, https://github.com/openai/tiktoken
  - impact: aligns gating with actual token budget behavior, reducing false positives/negatives from multibyte-heavy code/docs prompts.
  - risk_class: R2
  - notes: Start as optional mode (`DMS_TOKEN_BUCKET_ENABLED`) for calibration, with fallback to character count if tokenization unavailable.

- Minimum-Sample Guardrails Before DMS Policy Auto-Shift
  - repo_fit: routing metadata tracks rates per variant, but no explicit minimum-sample or confidence gate before policy changes or auto-disable toggles.
  - source: https://support.launchdarkly.com/hc/en-us/articles/4410284003341-Statistical-significance
  - impact: avoids false routing policy decisions under low traffic and reduces rollout churn from random variance.
  - risk_class: R1
  - notes: Gate auto policy changes behind minimum per-variant request count + confidence threshold, and emit explicit "insufficient sample" status.

- Parse and Persist Reasoning Token Breakdown for DMS Paths
  - repo_fit: Merlin already parses content but not `usage`/`output_tokens_details` fields, limiting cost and reasoning-performance introspection.
  - source: https://platform.openai.com/docs/guides/reasoning/use-case-examples
  - impact: provides concrete signals for quality-vs-latency policy tuning and prevents over-attributing cost spikes to network latency.
  - risk_class: R2
  - notes: Add schema-aware parser path that stores `reasoning_tokens`, `output_tokens`, and `cached_tokens` when present.

- DMS Readiness Probe with Degradation Ladder
  - repo_fit: DMS path can only be validated lazily, so the first live request can absorb readiness and timeout penalties.
  - source: https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/
  - impact: reduces first-request error/fallback spikes by precomputing route eligibility from startup/runtime health checks.
  - risk_class: R1
  - notes: Add a lightweight startup probe for `/models` and mark `dms_available` false when failing.

- Circuit Breaker for DMS Call Failures
  - repo_fit: Adaptive/parallel/streaming backends can continuously retry failed DMS calls and overload fallback pools.
  - source: https://martinfowler.com/bliki/CircuitBreaker.html
  - impact: isolates a degraded DMS dependency quickly and improves overall request success under incident conditions.
  - risk_class: R2
  - notes: Use `failure_count`, `window_secs`, and cooldown timing in memory with a forced short-open before auto-close.

- Retry Strategy Respecting Retry-After
  - repo_fit: DMS and gateway errors can be transient; immediate retries currently risk self-amplification.
  - source: https://www.rfc-editor.org/rfc/rfc9110#name-429-too-many-requests, https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.retry.Retry
  - impact: reduces request storms and preserves latency headroom during soft throttling windows.
  - risk_class: R2
  - notes: Implement bounded retries, exponential backoff + jitter, and obey `Retry-After` when present.

- Typed OpenAI-Compatible Response Contract
  - repo_fit: `merlin_llm_backends._dms_chat` accepts loose payload shapes and may pass malformed responses into routing metrics.
  - source: https://platform.openai.com/docs/api-reference/chat/object
  - impact: catches response format drift early and gives deterministic fallback reasons instead of ambiguous parsing artifacts.
  - risk_class: R2
  - notes: Define a local response parser contract for `choices`, `message.content`, and `usage`.

- Structured Logging Envelope with Correlation IDs
  - repo_fit: Routing paths are complex (decision, fallback, retry); current logs lack consistent IDs for cross-step trace linking.
  - source: https://opentelemetry.io/docs/concepts/context-propagation/
  - impact: improves debugging across adaptive/parallel/streaming modes and enables clean incident timelines.
  - risk_class: R1
  - notes: Add optional `correlation_id` propagation in metadata and include it in fallback_reason payload.

- Rate-Aware DMS Guardrail for Throttle Conditions
  - repo_fit: Merlin can over-assign DMS under sustained 429 patterns even when quality goals are still met by fast models.
  - source: https://platform.openai.com/docs/guides/rate-limits
  - impact: protects throughput by pausing DMS routing during sustained quota pressure.
  - risk_class: R1
  - notes: Track rolling `dms_429` ratio and auto-disable DMS arm when threshold exceeded for N minutes.

- Response Streaming Quality Budget for DMS
  - repo_fit: Streaming path currently validates first token and fallback, but lacks explicit time-to-first-token signals in metadata.
  - source: https://platform.openai.com/docs/api-reference/streaming
  - impact: gives measurable UX-quality signals for DMS vs non-DMS streaming decisions.
  - risk_class: R2
  - notes: Add `ttft_ms`, `stream_duration_ms`, and `first_chunk_ms` fields to decision metadata.

- Request Deduplication and Idempotency Envelope
  - repo_fit: Retry behavior across adaptive and parallel modes can reissue identical DMS calls after transient network failures.
  - source: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Idempotency-Key
  - impact: lowers duplicate spend and improves deterministic retries in noisy networks.
  - risk_class: R2
  - notes: Add `Idempotency-Key` derived from prompt hash for mutability-safe call paths.

- Policy Telemetry Versioning
  - repo_fit: Routing policy evolves quickly with long-term roadmap and multi-agent changes; snapshots should survive refactors.
  - source: https://json-schema.org/understanding-json-schema/
  - impact: makes dashboard metrics and long-run experiments reproducible during strategy changes.
  - risk_class: R1
  - notes: Add `routing_rule_version` and `policy_signature` fields into decision metadata.

- Backend-Specific ThreadPool Isolation
  - repo_fit: adaptive/parallel/streaming backends share global executors; a blocked DMS provider can consume worker capacity and delay fallback paths.
  - source: https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor
  - impact: prevents single-provider stall from starving control models during burst traffic.
  - risk_class: R2
  - notes: Allocate separate pools or bounded queues for DMS candidates vs fallback candidates.

- Request-Scoped Backpressure on Backend Queue Growth
  - repo_fit: there is no hard cap on concurrent in-flight calls, and traffic spikes can increase latency tail before DMS is even tried.
  - source: https://docs.python.org/3/library/collections.html#collections.deque, https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore
  - impact: smooths load, keeps latency SLOs stable, and reduces cascading failures in adaptive routing.
  - risk_class: R1
  - notes: Add a bounded queue and reject/queue with early fallback decision when saturation detected.

- PII-Safe Routing Observability
  - repo_fit: Merlin currently records selected content in metadata for some paths; routing traces can include sensitive text for policy reviews.
  - source: https://owasp.org/www-project-top-ten/2017/A3_2017-Sensitive_Data_Exposure.html
  - impact: avoids accidental prompt leakage while still preserving model/decision telemetry.
  - risk_class: R1
  - notes: Keep only hashes for prompt IDs and omit raw user content from decision logs.

- Deterministic Fallback Reason Taxonomy
  - repo_fit: fallback_reason exists as free-form string; inconsistent labels reduce metric quality and rollout automation.
  - source: https://docs.python.org/3/library/enum.html
  - impact: standardizes error reporting and allows low-effort automated policy actions from orchestration layers.
  - risk_class: R2
  - notes: Introduce enumerated fallbacks (e.g., `dms_unavailable`, `dms_timeout`, `dms_parse_error`) across all three routers.

- Retry Budget Budgeting Per Routing Arm
  - repo_fit: current implementation retries effectively per-backend only through call failures; DMS retry budgets are shared implicitly with normal traffic.
  - source: https://sre.google/workbook/handling-overload/
  - impact: keeps retry storms from turning temporary latency into sustained outage during token spikes.
  - risk_class: R2
  - notes: Add global + per-model retry budget counters; hard-stop non-essential DMS retries under pressure.

- Canonicalize DMS Header Contracts
  - repo_fit: some paths use `Authorization` with bearer token while some may need alternate headers; inconsistent auth adds hard-to-debug failures.
  - source: https://platform.openai.com/docs/api-reference/authentication
  - impact: reduces miswire-induced outages when deploying DMS behind different gateway flavors.
  - risk_class: R1
  - notes: Normalize request headers into reusable helper with explicit key precedence and redacted logging.

- Quality-Weighted Route Metrics
  - repo_fit: routing_metrics tracks latency and success but not quality feedback per route in real time; quality drift can pass latency-only reviews.
  - source: https://sre.google/workbook/sli-slo-error-budget-policy/
  - impact: enables policy shifts based on combined score, not latency alone, for reasoning-heavy workloads.
  - risk_class: R2
  - notes: Emit `quality_score` per request from existing `rate` feedback and include it in control feedback loops.

- Prompt Entropy Gate for DMS Eligibility
  - repo_fit: Long prompts are currently length-threshold-only; low-information verbose prompts can still trigger DMS unnecessarily.
  - source: https://docs.python.org/3/library/collections.html#collections.Counter
  - impact: avoids DMS cost on repetitive/low-information payloads and reduces false positive long-form routing.
  - risk_class: R2
  - notes: Add a simple lexical-entropy check and require both token-length and novelty before DMS preference.

- Cancel-Ahead Fallback for Parallel Streams
  - repo_fit: Parallel backend can keep running non-selected models after a winner is found, wasting latency budget and compute.
  - source: https://aws.amazon.com/builders-library/timeouts-and-retries/?did=ap_card&trk=ap_card
  - impact: lowers tail latency and cost by canceling non-selected parallel calls when winner is stable.
  - risk_class: R1
  - notes: Add cooperative cancellation once best response is locked for both non-streaming and streaming flows.

- Adaptive Timeout Ladder by Model Class
  - repo_fit: All models currently inherit a single timeout input, despite varied response profiles (DMS reasoning vs fast models).
  - source: https://www.ietf.org/rfc/rfc7231.txt
  - impact: fewer false failovers from fixed short timeouts on inherently slower DMS calls while still protecting chat UI responsiveness.
  - risk_class: R1
  - notes: Set per-model timeouts from config (`DMS_TIMEOUT_MS`, etc.) with adaptive defaults and strict global caps.

- Canary Envelope for DMS with Shadow Validation
  - repo_fit: DMS is high-cost and experimental; Merlin already has AB plumbing but only uses one-way response selection.
  - source: https://martinfowler.com/bliki/CanaryRelease.html
  - impact: surfaces regression evidence before full rollout by running DMS as shadow for controlled cohorts.
  - risk_class: R2
  - notes: Add an optional "shadow" mode that records what DMS would have responded with for audit/replay.

- Deterministic Model Warmup Audit
  - repo_fit: DMS and openai-compatible endpoints can have first-use latency spikes that confuse routing and SLO baselines.
  - source: https://platform.openai.com/docs/guides/latency-optimization
  - impact: improves measurement fidelity by isolating cold-start latency from routing policy decisions.
  - risk_class: R2
  - notes: Track first-response warmup time per model and expose `cold_start_ms` metadata.

- Retry Storm Circuit for 429 Bursts
  - repo_fit: parallel/streaming routers can fan out many attempts during upstream throttling, amplifying 429 conditions.
  - source: https://www.rfc-editor.org/rfc/rfc9110#name-429-too-many-requests
  - impact: stabilizes throughput under pressure by pausing retries when 429 ratio exceeds threshold.
  - risk_class: R1
  - notes: Add a soft-stop gate that temporarily disables DMS attempts and forces fallback models only.

- Correlation-Scoped DMS Audit Logs
  - repo_fit: API already carries `correlation_id` and routing decisions could be joined across requests in operations tooling.
  - source: https://opentelemetry.io/docs/concepts/context-propagation/
  - impact: faster postmortems by correlating user request, routing path, provider errors, and fallback outcomes.
  - risk_class: R1
  - notes: Emit compact decision trace rows keyed by correlation ID and decision hash in a rotating local artifact.

- Historical Pattern Replay Suite for Routing Regressions
  - repo_fit: tests already simulate long/short prompts but not full historical workloads from this repo’s run history.
  - source: https://docs.pytest.org/en/stable/how-to/writing_plugins.html
  - impact: catches behavior drift in routing policy during long runs with multi-agent code changes.
  - risk_class: R1
  - notes: Add fixture-backed replay tests using archived anonymized prompt sets and expected DMS decisions.

- Mythic Oracle Gate with Human Review Escalation
  - repo_fit: DMS as "oracle route" aligns with Merlin’s high-level reasoning aspirations, but sensitive decisions should be reviewable.
  - source: https://platform.openai.com/docs/guides/safety-best-practices
  - impact: reduces trust risk by ensuring high-impact operations can force non-DMS or dual-route verification.
  - risk_class: R3
  - notes: Add a task-type exception list for regulated/critical prompts (e.g., finance/security) that bypasses DMS or requires confidence threshold.

- Route Config Integrity Checkpoint
  - repo_fit: DMS-related routing settings can drift across env and runtime changes, yet decisions currently depend on mutable process-level flags.
  - source: https://datatracker.ietf.org/doc/html/rfc6901
  - impact: prevents silent config mismatches that alter traffic split or complexity gates mid-run.
  - risk_class: R1
  - notes: Persist a normalized snapshot of resolved `DMS_*`/routing settings with each routing decision.

- Tenant-Scoped Fairness Caps
  - repo_fit: Single-tenant and internal workloads can share a local Merlin instance; one tenant's long prompts could starve others in DMS-heavy modes.
  - source: https://docs.python.org/3/library/collections.html#collections.defaultdict
  - impact: stabilizes latency SLA by preventing one tenant from monopolizing DMS quota.
  - risk_class: R2
  - notes: Track per-tenant quotas for DMS attempts and enforce token-bucket fairness.

- Replayable Golden Set for Regression Detection
  - repo_fit: Routing decisions are stateful and can shift as AB percentages or model scores evolve.
  - source: https://martinfowler.com/articles/managing-requirements.html
  - impact: catches silent behavior changes before they ship by replaying fixed prompts through all modes.
  - risk_class: R1
  - notes: Store a small fixed prompt corpus with expected selected_model + fallback_reason assertions.

- Provider Error Envelope Contract
  - repo_fit: Existing `fallback_reason` is free-form and some API endpoints need machine-actionable fault classification.
  - source: https://github.com/OAI/OpenAPI-Specification/blob/main/versions/3.0.0.md
  - impact: enables consistent automation in AAS orchestration for retry/dead-letter and incident routing.
  - risk_class: R2
  - notes: Define an enum-like fallback code map and include it in metadata and logs.

- Parallel Response Deduplication by Correlation
  - repo_fit: parallel fallback can receive multiple similar responses from different models for same prompt with no dedupe.
  - source: https://docs.python.org/3/library/hashlib.html
  - impact: prevents duplicate output noise in logs and simplifies voting/consensus post-processing.
  - risk_class: R2
  - notes: Hash normalized response bodies and collapse near-duplicate outputs before strategy scoring.

- Streaming Recovery Path for Partial Chunks
  - repo_fit: streaming mode currently marks fallback on first failure, but may have already emitted partial content to consumer.
  - source: https://platform.openai.com/docs/api-reference/streaming
  - impact: avoids broken UX by defining explicit partial-text failure contract and recovery message format.
  - risk_class: R3
  - notes: Add metadata field signaling truncated stream + fallback provenance when partial emit occurs.

- DMS Call Budget Telemetry in Dashboard
  - repo_fit: API exposes /merlin/llm/* metrics but DMS-specific quota/attempt budget is not first-class in the existing dashboard view.
  - source: merlin_api_server.py
  - impact: gives operators immediate signal when routing is being throttled by budget guardrails rather than raw latency drift.
  - risk_class: R1
  - notes: Add dedicated dashboard panels for dms_attempted/dms_selected/dms_fallback_rate/429 ratio.

- Persist DMS Routing Decisions in Audit Logs
  - repo_fit: Merlin already has `audit_logs` in `merlin_db.py`; routing experiments need durable records for policy review.
  - source: merlin_db.py; merlin_api_server.py
  - impact: supports postmortem reconstruction of model choices and fallback reasons when latency or quality incidents occur.
  - risk_class: R1
  - notes: Log selected_model, fallback_reason, prompt_size_bucket, and correlation_id for each request when DMS is in pool.

- Correlation ID Propagation Across ThreadPool Calls
  - repo_fit: parallel/streaming backends dispatch model calls in threads, where request context can be lost.
  - source: https://docs.python.org/3/library/contextvars.html
  - impact: keeps trace continuity from API request through worker threads and fallback decisions.
  - risk_class: R2
  - notes: Propagate correlation_id via explicit function args or contextvars around `_call_model` and stream functions.

- Dynamic AB Traffic Rebalancing Guard
  - repo_fit: DMS AB split can stall if one arm underperforms but percentage stays static in environment vars.
  - source: `merlin_ab_testing.py`; https://en.wikipedia.org/wiki/Multi-armed_bandit
  - impact: prevents prolonged poor user experience by shifting traffic toward the better arm automatically.
  - risk_class: R2
  - notes: Add a low-risk pilot auto-adjuster that only applies when variant deltas are statistically stable.

- Operation Envelope for DMS Routing Control
  - repo_fit: repo already accepts operation envelopes; DMS enablement changes currently require env reload/restart.
  - source: merlin_api_server.py
  - impact: lets orchestrators toggle DMS/AB behavior at runtime with auditable operations.
  - risk_class: R1
  - notes: Add operations: `merlin.llm.routing.dms.enable|disable`, `merlin.llm.routing.config.set`.

- Deterministic A/B Cohort Hash Key
  - repo_fit: existing A/B uses `random.random`, which can produce unstable cohorts by request sequence.
  - source: https://docs.python.org/3/library/hashlib.html
  - impact: more stable comparisons for multi-request flows in user-facing sessions.
  - risk_class: R2
  - notes: Route all requests for the same conversation through the same DMS/control arm via stable hash.

- Structured `fallback_reason` Contract with Codes
  - repo_fit: `_operation_error` already defines machine-readable response structure; routing fallback messages are unstructured strings.
  - source: merlin_api_server.py
  - impact: improves automatic remediation and dashboard alerts by matching specific codes.
  - risk_class: R2
  - notes: Replace free text reasons with code enum plus optional detail, e.g., `dms.parse_error`, `dms.timeout`.

- Mythic Gate: Apollo-Atreus Retry Discipline
  - repo_fit: This repo embraces long-lived iterative orchestration; repeated retries without caps mirror ancient "do-over loops" that ignore cost.
  - source: https://en.wikipedia.org/wiki/Apollo_11; https://docs.python.org/3/library/itertools.html#itertools.count
  - impact: enforces bounded attempts and explicit stop criteria to avoid runaway compute cycles.
  - risk_class: R2
  - notes: Cap retry attempts per request by route policy and expose count in metadata.

- Canary Warm-Start Before DMS Escalation
  - repo_fit: DMS often arrives with higher warm latency than local models; routing currently doesn't separate cold and hot states.
  - source: https://platform.openai.com/docs/api-reference/chat/object
  - impact: avoids unfairly classifying DMS as slow during initial spikes by warming once per process.
  - risk_class: R1
  - notes: Trigger a lightweight no-op warm call at startup and store `dms_cold_start_complete`.

- Streaming Buffer Flush Contract
  - repo_fit: streaming backend currently concatenates chunks and loses boundary metadata needed for partial-fallback policy.
  - source: https://peps.python.org/pep-3333/
  - impact: enables explicit handoff behavior when stream fails mid-response.
  - risk_class: R3
  - notes: Emit chunk-level metadata events (start, chunk, fallback, done) so clients can detect truncated responses.

- Golden Rule: Keep Routing Decisions Idempotent for Replayability
  - repo_fit: AAS orchestration may replay the same request payload; non-idempotent randomness can drift outcomes across plays.
  - source: https://docs.python.org/3/library/hashlib.html
  - impact: supports deterministic reruns in replay tests and incident reproductions.
  - risk_class: R1
  - notes: Include seed/hash of normalized prompt+settings in fallback/selection path when AB randomness is enabled.

- Operation Schema for DMS Metadata
  - repo_fit: Merlin now has operation-level response schemas; routing metadata is a first-class API value but not standardized in schemas.
  - source: docs/protocols/operation-envelope-v1.md; merlin_api_server.py
  - impact: prevents schema drift between adaptive/parallel/streaming responses and clarifies what AAS/orchestrators can rely on.
  - risk_class: R2
  - notes: Add `llm_routing` metadata fields to the protocol schema and fixture coverage.

- Contract-First DMS Regression Fixtures
  - repo_fit: Existing contract tests are strict for operations and would be ideal for validating DMS on/off behavior.
  - source: tests/test_operation_expected_responses.py; tests/fixtures/contracts
  - impact: locks in stable behavior for `selected_model`, fallback_reason, and prompt_bucket while refactoring routing internals.
  - risk_class: R1
  - notes: Add new fixture pairs for adaptive/parallel/streaming with DMS enabled/disabled outcomes.

- Prompt-Type Auto-Enrichment with Task Classifier
  - repo_fit: `_is_reasoning_query` and `QueryContext` are keyword-based and miss structure hints in multi-part prompts.
  - source: https://huggingface.co/docs/transformers/main/en/index
  - impact: sharper DMS routing on truly reasoning-heavy inputs; fewer misrouted templated long prompts.
  - risk_class: R2
  - notes: Add optional lightweight classifier fallback (or heuristics pass) before DMS decision.

- Rollback-First Runtime Switch for DMS
  - repo_fit: DMS is experimental and should be reversible on incident without full restart.
  - source: merlin_api_server.py
  - impact: faster incident response by disabling route branch to fallback path at runtime while preserving service availability.
  - risk_class: R1
  - notes: Add guarded operation that flips DMS gating and clears in-flight preference cache.

- Dual-Path Canary for "Pay for Hints, Not Answers"
  - repo_fit: notes mention staged prompting as a future cost gate; this can pair with existing two-stage quality scoring.
  - source: docs/dms_research_notes.md
  - impact: lowers average token spend by routing difficult prompts to DMS only for first-pass hints and validating final answer on fast model.
  - risk_class: R2
  - notes: Add optional mode that requests abbreviated reasoning first from DMS and uses a standard model for finalization.

- Merlin-Oracle Incident Runbook
  - repo_fit: repo identity around Merlin suggests operational ritual; routing changes need explicit runbook hooks.
  - source: docs/AGENT_TRANSITION.md
  - impact: reduces recovery time when DMS behavior regresses by defining who flips AB/thresholds and expected metric checks.
  - risk_class: R1
  - notes: Add runbook steps + pre-check commands for DMS disable, metric rollback, and incident close criteria.

- Tenant Safety Envelope for Sensitive Prompts
  - repo_fit: Merlin handles command/task/user flows in multi-user contexts; routing mistakes on sensitive prompts are higher risk.
  - source: docs/README.md
  - impact: reduces chance of routing secrets or safety-critical prompts through experimental model paths.
  - risk_class: R3
  - notes: Introduce denylist task markers that force DMS bypass for policy-defined domains.

## Pass 0 - Capture (2026-02-15)

- Deterministic Conversation-Scoped DMS A/B Assignment
  - repo_fit: Adaptive/parallel/streaming currently use `random.random` each request; long conversations can switch DMS/control mid-thread and confound evaluation.
  - source: https://launchdarkly.com/docs/home/flags/target-rules, https://docs.python.org/3/library/hashlib.html
  - impact: stabilizes user behavior and experiment comparisons by hashing conversation identity into A/B cohorts.
  - risk_class: R1
  - notes: Add `conversation_id`/`correlation_id`-based stable cohorting for `_select_ab_variant` across all routers.

- Uncertainty-Aware DMS Escalation
  - repo_fit: Merlin already tracks `selected_model` and fallback telemetry but has no explicit uncertainty signal before choosing the oracle route.
  - source: https://platform.openai.com/docs/guides/reasoning/use-case-examples, https://arxiv.org/abs/2203.11171
  - impact: routes high-uncertainty prompts to DMS more selectively, reducing unnecessary latency while preserving difficult case quality.
  - risk_class: R2
  - notes: Use proxy uncertainty score from response `reasoning_tokens`, response length variance, or self-consistency check before DMS escalation.

- Retry Taxonomy for DMS Transport vs Parser Failures
  - repo_fit: DMS call failures are all logged as generic errors; route policy cannot auto-react differently for 429/5xx vs malformed payloads.
  - source: https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff, https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html
  - impact: avoids unnecessary failover for transient failures and shortens recovery using targeted retries only for retriable conditions.
  - risk_class: R1
  - notes: Add explicit reason bucket `dms_error_transport`, `dms_error_parse`, `dms_error_http_5xx`, `dms_error_rate_limit`.

- Streaming Error-Event Grammar for SSE Robustness
  - repo_fit: Routing includes streaming backends and can be disrupted by partial/heartbeat frames.
  - source: https://platform.openai.com/docs/guides/streaming-responses
  - impact: prevents brittle parser crashes and gives deterministic fallback metadata when DMS stream degrades.
  - risk_class: R1
  - notes: Treat `data: [DONE]`, comments, empty frames, and malformed JSON as explicit branches with consistent `fallback_reason`.

- Policy-Ledger Version Tag for Routing Decisions
  - repo_fit: Merlin persists `selected_model`/`fallback_reason` but cannot attribute why a given policy revision made that choice.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/, docs/protocols/operation-envelope-v1.md
  - impact: enables deterministic replay and policy rollback at route-reason granularity across long runs.
  - risk_class: R2
  - notes: Add `router_rule_version` and rule fingerprint to metadata for every adaptive/parallel/streaming decision.

- Token-Bucket Throughput Guard for DMS
  - repo_fit: DMS is expensive and single-path heavy bursts can trigger provider throttling, then ripple into fallback storms.
  - source: https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff, https://docs.python.org/3/library/asyncio-sync.html
  - impact: caps concurrent/rapid DMS attempts under pressure while preserving fallback quality.
  - risk_class: R2
  - notes: Add short-window token-bucket or semaphore for DMS-attempt concurrency with dynamic slow-start.

- Usage-Level Route Cost Metric for DMS Decisions
  - repo_fit: Current routing metrics omit per-request output/token decomposition and quality-to-cost tradeoffs.
  - source: https://platform.openai.com/docs/guides/streaming-responses, https://platform.openai.com/docs/api-reference/chat/completions
  - impact: gives measurable ROI for DMS routing by request bucket (`short`/`medium`/`long`) and task class.
  - risk_class: R1
  - notes: Parse `usage.output_tokens_details` and `cached_tokens` into routing analytics and status dashboards.

- Golden Replay Set for Routing Drift
  - repo_fit: Routers already have unit tests but no fixed cross-router corpus that locks stable DMS selection rules.
  - source: https://platform.openai.com/docs/guides/evaluation-best-practices, tests/test_merlin_adaptive_llm.py
  - impact: protects against subtle policy regressions while refactoring routing internals.
  - risk_class: R1
  - notes: Add reproducible fixtures with expected `selected_model`, `prompt_size_bucket`, and quality deltas.

- Token-Aware Routing Buckets
  - repo_fit: Bucketing currently based on character length (`DMS_MIN_PROMPT_CHARS`) while non-English prompts and compact code/text differ materially in token cost.
  - source: https://platform.openai.com/docs/guides/prompt-caching/prompt-caching, https://github.com/openai/tiktoken
  - impact: cleaner DMS policy on actual token economics, reducing over- and under-routing for multibyte or code-heavy prompts.
  - risk_class: R2
  - notes: Add optional tokenized bucket (`short`/`medium`/`long`) with fallback to chars until dependency is installed.

- Sensitive Task Guardrail Layer for DMS
  - repo_fit: Merlin routes generic user/system prompts to oracle candidates; some domains may require strict policy and deterministic low-latency models.
  - source: docs/AGENT_TRANSITION.md, merlin_policy.py
  - impact: reduces risk by forcing high-risk categories through stable non-DMS paths regardless of prompt length.
  - risk_class: R3
  - notes: Add policy denylist/allowlist for `task_type` and domain tags before calling `_should_prefer_dms`.

- Policy-Driven Canary (Shadow) Validation for DMS
  - repo_fit: Existing AB is binary (dms vs control); no non-user-impact mode for measuring output quality before full switch.
  - source: https://launchdarkly.com/docs/home/releases/create-progressive-rollouts, https://platform.openai.com/docs/guides/evaluation-best-practices
  - impact: improves rollout safety by comparing DMS result quality offline or in shadow during stable operation windows.
  - risk_class: R2
  - notes: Run optional shadow path that stores DMS response and quality score without client-facing selection.

- Myth-Informed Routing Governance
  - repo_fit: Merlin branding emphasizes oracle-like routing; governance docs can use that metaphor to reduce ambiguity in on-call decisions.
  - source: https://www.britannica.com/topic/Merlin-legendary-magician
  - impact: better shared language for runbooks and policy ownership between dev/ops teams.
  - risk_class: R3
  - notes: Codify "Oracle Lane" = DMS / "Court Lane" = stable backends in runbooks and status dashboards.

- DMS Quality-First Auto-Pause
  - repo_fit: Routing auto-adjustment can continue through poor quality or unstable windows because signal is weak beyond fallback ratio.
  - source: https://platform.openai.com/docs/guides/evaluation-best-practices, https://sre.google/workbook/error-budget-policy/
  - impact: auto-pauses DMS when confidence/quality drops below threshold and re-enters safe policy automatically.
  - risk_class: R1
  - notes: Gate on minimum sample size plus quality confidence before policy escalation or auto-enable.

## Pass 1 - Top Candidates (upgrade)

- Deterministic Conversation-Scoped DMS A/B Assignment
  - problem: Random A/B selection currently changes per request, which destabilizes multi-turn sessions and makes routing deltas noisy.
  - impact: improves experiment validity and user experience continuity by fixing lane assignment per conversation.
  - verify: add regression test that two calls with same `correlation_id` always pick the same `ab_variant` and `selected_model` when policy inputs unchanged.
  - rollback: disable by setting `DMS_AB_ENABLED=false` or bypassing hash path with runtime flag; preserve short-prompt behavior.
  - risk_class: R1
  - horizon: H1
  - repo_fit: adaptive/parallel/streaming all perform decisioning in `QueryContext` and request handlers.
  - source: https://docs.python.org/3/library/hashlib.html, https://launchdarkly.com/docs/home/flags/target-rules

- Uncertainty-Aware DMS Escalation
  - problem: DMS is currently selected using simple length/task heuristics without explicit uncertainty or confidence signals.
  - impact: prevents overuse of expensive DMS calls on easy prompts and allocates oracle budget to genuinely complex reasoning cases.
  - verify: create fixtures where reasoning-heavy prompts with high uncertainty score prefer DMS while simple prompts stay control despite length.
  - rollback: add feature flag that bypasses uncertainty routing and reverts to threshold-only logic.
  - risk_class: R2
  - horizon: H2
  - repo_fit: `_should_prefer_dms` in `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py` has explicit policy function point.
  - source: https://platform.openai.com/docs/guides/reasoning/use-case-examples, https://arxiv.org/abs/2203.11171

- Retry Taxonomy for DMS Transport vs Parser Failures
  - problem: parser failures and transient transport failures are currently merged; observability and automation cannot distinguish endpoint flaps from malformed responses.
  - impact: improves auto-healing and triage by capturing correct failure class in `fallback_reason`.
  - verify: add tests for 429, 5xx, timeout, malformed JSON each producing distinct `fallback_reason` values.
  - rollback: keep only existing generic reason path until taxonomy is proven stable.
  - risk_class: R1
  - horizon: H1
  - repo_fit: `dms_error` path and `fallback_reason` fields are already part of response metadata.
  - source: https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff, https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html

- Streaming Error-Event Grammar for SSE Robustness
  - problem: SSE edge cases (heartbeat/comment lines, partial payloads, `[DONE]`) can break or misclassify stream routing.
  - impact: predictable streaming behavior improves UX and lowers false fallback spikes during long responses.
  - verify: add stream fixture matrix with normal chunks, `[DONE]`, and malformed frame to `tests/test_merlin_streaming_llm.py`.
  - rollback: keep legacy parsing branch behind compatibility flag if unknown providers regress.
  - risk_class: R1
  - horizon: H1
  - repo_fit: `merlin_streaming_llm.py` has dedicated stream parsing for all routers.
  - source: https://platform.openai.com/docs/guides/streaming-responses

- Policy-Ledger Version Tag for Routing Decisions
  - problem: current routing metadata lacks a machine-anchored policy version, making replay and rollback audits difficult.
  - impact: supports deterministic analysis when A/B or policy rules evolve across long sessions.
  - verify: assert `selected_model` responses include `router_rule_version` and it updates only on policy edits.
  - rollback: ignore new field if legacy consumers fail; keep compatibility in status and operation schema.
  - risk_class: R2
  - horizon: H1
  - repo_fit: metadata dict already passed through responses for adaptive/parallel/streaming.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/, docs/protocols/operation-envelope-v1.md

- Golden Replay Set for Routing Drift
  - problem: behavior drift can appear without direct assertion when rule thresholds or heuristics evolve.
  - impact: catches regressions in DMS routing and fallback policy before they enter production traffic.
  - verify: build fixed prompt corpus with snapshot assertions per backend mode and compare across CI runs.
  - rollback: drop replay enforcement while keeping manual smoke checks, then re-enable once infra is stable.
  - risk_class: R1
  - horizon: H3
  - repo_fit: existing router tests and contract fixtures provide a ready base for stable acceptance sets.
  - source: https://platform.openai.com/docs/guides/evaluation-best-practices, tests/test_merlin_adaptive_llm.py

## Pass 2 - Handoff Quality

## Top 5 candidates

1. Deterministic Conversation-Scoped DMS A/B Assignment (ranked highest actionability)
  - repo_fit: one small change to all three routers, immediate UX/test reliability gain.
  - source: https://docs.python.org/3/library/hashlib.html, https://launchdarkly.com/docs/home/flags/target-rules
  - impact: reduces session-level variance and makes AB outcomes reproducible.
  - notes: highest confidence and low implementation risk; can be delivered behind existing DMS AB switches.
  - risk_class: R1

2. Retry Taxonomy for DMS Transport vs Parser Failures
  - repo_fit: directly improves routing telemetry and safe auto-healing behavior under endpoint instability.
  - source: https://platform.openai.com/docs/guides/rate-limits/retrying-with-exponential-backoff, https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html
  - impact: stronger fault classification and faster incident triage.
  - notes: bounded blast-radius and better rollback automation; should include telemetry assertions.
  - risk_class: R1

3. Streaming Error-Event Grammar for SSE Robustness
  - repo_fit: applies directly to `merlin_streaming_llm.py` parser and user-visible streaming path.
  - source: https://platform.openai.com/docs/guides/streaming-responses
  - impact: fewer mid-stream parser fallbacks and cleaner partial-response contracts.
  - notes: improves resilience without changing routing policy; good first-step hardening.
  - risk_class: R1

4. Policy-Ledger Version Tag for Routing Decisions
  - repo_fit: leverages existing metadata channels in adaptive/parallel/streaming responses.
  - source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/, docs/protocols/operation-envelope-v1.md
  - impact: direct replayability and easier rollback across policy changes.
  - notes: prefer schema-compatible extension to avoid breaking existing dashboards.
  - risk_class: R2

5. Uncertainty-Aware DMS Escalation (research_only)
  - research_only: true
  - repo_fit: aligns with Merlin's goal of routing only truly complex reasoning to DMS.
  - source: https://platform.openai.com/docs/guides/reasoning/use-case-examples, https://arxiv.org/abs/2203.11171
  - impact: higher quality/cost balance, but requires empirical calibration before production.
  - notes: keep off by default; evaluate with replay corpus before policy promotion.
  - risk_class: R2

## Top 5 to Execution Mapping

- Deterministic Conversation-Scoped DMS A/B Assignment
  - files:
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
  - verify:
    - add regression test reusing shared fixture seed to assert same `correlation_id` yields identical `ab_variant` and `selected_model` for same prompt length/task.
  - rollout: low-risk (single-policy-function change in three routers).
  - risk_class: R1
  - notes: include optional bypass flag if deterministic hash needs temporary disable.

- Retry Taxonomy for DMS Transport vs Parser Failures
  - files:
    - `merlin_llm_backends.py`
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
    - `tests/test_merlin_adaptive_llm.py`
    - `tests/test_merlin_parallel_llm.py`
    - `tests/test_merlin_streaming_llm.py`
    - `tests/test_merlin_llm_backends.py`
  - verify:
    - cover 429, 5xx, timeout, malformed JSON path and assert mapped `fallback_reason` taxonomy in metadata.
  - rollout: medium; requires parser+fallback assertion updates.
  - risk_class: R1

- Streaming Error-Event Grammar for SSE Robustness
  - files:
    - `merlin_streaming_llm.py`
    - `tests/test_merlin_streaming_llm.py`
  - verify:
    - add fixture matrix with `[DONE]`, heartbeat/comment, empty frame, malformed json and confirm stream completion contract.
  - rollout: medium-low; parser-only change with clear regression tests.
  - risk_class: R1

- Policy-Ledger Version Tag for Routing Decisions
  - files:
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
  - verify:
    - assert response metadata includes stable `router_rule_version` and that it updates only on policy-change commits.
  - rollout: medium; no behavior changes expected.
  - risk_class: R2

- Golden Replay Set for Routing Drift (research-only dependency path)
  - files:
    - `tests/test_merlin_adaptive_llm.py`
    - `tests/test_merlin_parallel_llm.py`
    - `tests/test_merlin_streaming_llm.py`
    - `tests/test_operation_expected_responses.py` (if contract-backed)
  - verify:
    - snapshot-based regression pass enforces expected `selected_model`, `dms_used`, `prompt_size_bucket` for fixed prompt corpus.
  - rollout: medium; build prompt corpus and freeze expected artifacts.
  - risk_class: R1
  - notes: do not ship without baseline freeze window.

## Top 5 Implementation Tickets

- TKT-1: Add deterministic DMS A/B assignment by conversation
  - files:
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
  - acceptance:
    - two calls with same conversation/correlation context select the same `ab_variant`.
    - non-deterministic routing can be disabled via feature flag for compatibility testing.
    - existing `DMS_MIN_PROMPT_CHARS` / `DMS_TASK_TYPES` behavior remains unchanged for short/simple requests.
  - rollback:
    - gate behind a runtime/setting flag and default to current `random` path when disabled.
  - risk_class: R1

- TKT-2: Implement DMS failure taxonomy with fallback_reason split
  - files:
    - `merlin_llm_backends.py`
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
    - `tests/test_merlin_adaptive_llm.py`
    - `tests/test_merlin_parallel_llm.py`
    - `tests/test_merlin_streaming_llm.py`
    - `tests/test_merlin_llm_backends.py`
  - acceptance:
    - tests cover transport timeout, 429, 5xx, parser error, and success paths.
    - metadata `fallback_reason` uses distinct classes for transport/parse conditions.
    - existing safe fallback behavior to non-DMS path remains intact.
  - rollback:
    - fallback to legacy single string `dms_error:*` path by disabling taxonomy output when needed.
  - risk_class: R1

- TKT-3: Harden SSE stream frame grammar in streaming parser
  - files:
    - `merlin_streaming_llm.py`
    - `tests/test_merlin_streaming_llm.py`
  - acceptance:
    - `[DONE]`, empty lines, comments, and malformed lines are handled deterministically.
    - stream failure sets a consistent `fallback_reason` and continues stable partial-response handling.
  - rollback:
    - add compatibility toggle to retain legacy parser path if provider-specific regressions are found.
  - risk_class: R1

- TKT-4: Add router policy version metadata
  - files:
    - `merlin_adaptive_llm.py`
    - `merlin_parallel_llm.py`
    - `merlin_streaming_llm.py`
  - acceptance:
    - responses include `router_rule_version` in metadata for all routing flows.
    - version changes only with controlled policy edits; default remains stable between releases.
  - rollback:
    - keep metadata optional in downstream contracts and ignore if unknown consumers fail.
  - risk_class: R2

- TKT-5: Build routing drift golden replay set (gated)
  - files:
    - `tests/test_merlin_adaptive_llm.py`
    - `tests/test_merlin_parallel_llm.py`
    - `tests/test_merlin_streaming_llm.py`
    - `tests/test_operation_expected_responses.py` (if contract-backed)
  - acceptance:
    - fixed prompt corpus validates `selected_model`, `dms_used`, and `prompt_size_bucket`.
    - CI catches unintentional routing changes without policy edits.
  - rollback:
    - gate replay checks behind an opt-in target to avoid blocking emergency recovery windows.
  - notes: do not mark as shipping-critical until baseline corpus is finalized.
  - risk_class: R1

## Execution Order (recommended)

- Phase 0 (safety foundation)
  - TKT-2 (failure taxonomy)  
    - Why first: ensures explicit `fallback_reason` observability before routing policy changes.
    - Exit condition: all DMS failure paths map to typed reasons without behavior regression.
  - TKT-4 (policy metadata)
    - Why second: supports audit trails for any subsequent policy experiments.
    - Exit condition: `router_rule_version` appears in adaptive/parallel/streaming metadata and remains stable.

- Phase 1 (routing stability)
  - TKT-1 (deterministic A/B)
    - Why now: removes experiment noise and preserves session continuity.
    - Exit condition: repeated correlation IDs select identical variant and metrics remain coherent.
  - TKT-3 (stream grammar)
    - Why now: hardens most user-visible path once base taxonomy/versioning exists.
    - Exit condition: streaming parser handles `[DONE]` / heartbeat / malformed frames deterministically.

- Phase 2 (evidence lock)
  - TKT-5 (golden replay set)
    - Why now: catches regressions from earlier routing and streaming changes.
    - Exit condition: fixed corpus snapshot checks are green in CI target.

## Execution Risk Envelope

- Residual data-risk: medium (most changes are metadata/routing controls and fallback telemetry).
- Operational risk: low at phase 0-1 due to no policy semantics changes; rises to medium only on full rollout of replay gates.
- Rollback pattern: all tickets remain feature-flagged by env/settings or runtime branch behavior to preserve current stable routing path.

## Handoff Packet (multi-agent assignment)

- Workstream: Reliability / Routing Core
  - Ticket: TKT-2
  - Dependency: none (standalone)
  - Handoff output:
    - distinct fallback reason enums
    - parser/tests demonstrating transport vs parse failure separation
    - behavior proof that fallback path remains non-failing
  - Validation: targeted tests pass in `tests/test_merlin_llm_backends.py`, `tests/test_merlin_*_llm.py`.

- Workstream: Observability / Policy Governance
  - Ticket: TKT-4
  - Dependency: none
  - Handoff output:
    - `router_rule_version` in response metadata
    - change log of policy version source
  - Validation: response schema checks and policy-drift snapshots.

- Workstream: Experiment Design / A/B Stability
  - Ticket: TKT-1
  - Dependency: TKT-4
  - Handoff output:
    - deterministic A/B assignment using conversation key
    - reproducible experiment logs/metrics continuity
  - Validation: same-correlation repeated calls map to same variant.

- Workstream: Streaming Reliability
  - Ticket: TKT-3
  - Dependency: TKT-2
  - Handoff output:
    - deterministic SSE frame handling and fallback mapping
  - Validation: stream fixture matrix (`[DONE]`, heartbeat, malformed) in tests.

- Workstream: Regression Quality / QA
  - Ticket: TKT-5
  - Dependency: TKT-1, TKT-2, TKT-3, TKT-4
  - Handoff output:
    - fixed replay corpus and drift gates
    - evidence of stable routing decisions across routers
  - Validation: CI replay target for `selected_model`, `dms_used`, `prompt_size_bucket`.

## Checkpoint

- completed: Added execution mapping and implementation tickets for Top 5.
- current: Research-to-doc intake complete with ticketized handoff.
- next: Run this packet through your multi-agent queue and assign each workstream lane before implementation starts.
- files changed:
  - docs/research/SUGGESTIONS_BIN.md
- blockers: none for this intake; execution of candidate #5 depends on uncertainty baseline (research_only).


## Pass 3 - Repo-Specific Suggestion Sweep (Target 100)

Date: 2026-02-18
Scope: Merlin repo-local only
Goal: Add 100 concrete advancement/enhancement/optimization recommendations tied to real Merlin modules.

1. [S001] Add centralized operation-envelope request validation middleware to remove repeated schema checks (targets: `merlin_api_server.py`, `contracts/aas.operation-envelope.v1.schema.json`).
2. [S002] Add schema-version negotiation and explicit downgrade errors for incompatible envelopes (targets: `merlin_api_server.py`, `docs/protocols/operation-envelope-v1.md`).
3. [S003] Enforce bounded payload-size limits per operation to prevent oversized body abuse (targets: `merlin_api_server.py`, `merlin_settings.py`).
4. [S004] Require `correlation_id` for all mutating operations and return deterministic validation errors when absent (targets: `merlin_api_server.py`, `tests/test_merlin_api_server.py`).
5. [S005] Add optional `Idempotency-Key` handling for safe retry of create/update style operations (targets: `merlin_api_server.py`, `docs/protocols/operation-envelope-v1.md`).
6. [S006] Add per-operation latency percentiles (p50/p95/p99) in API status output (targets: `merlin_api_server.py`, `merlin_metrics_dashboard.py`).
7. [S007] Split error taxonomy into transport, validation, auth, dependency, and policy classes (targets: `merlin_api_server.py`, `tests/test_operation_error_responses.py`).
8. [S008] Add startup contract self-check that fails fast when required schemas are missing (targets: `merlin_api_server.py`, `scripts/sync_contract_schemas.py`).
9. [S009] Add endpoint to expose active capability flags with source (env/default/runtime) for debugging (targets: `merlin_api_server.py`, `docs/protocols/repo-capabilities-merlin-v1.md`).
10. [S010] Add API deprecation headers for operations planned for replacement (targets: `merlin_api_server.py`, `docs/protocols/compatibility-policy.md`).
11. [S011] Add OpenAPI-like exported spec snapshot for public Merlin operations (targets: `merlin_api_server.py`, `docs/protocols/README.md`).
12. [S012] Add operation replay diagnostics endpoint gated to local debug mode (targets: `merlin_api_server.py`, `merlin_settings.py`).
13. [S013] Add strict auth key rotation support with hot reload (targets: `merlin_auth.py`, `merlin_api_server.py`).
14. [S014] Add per-operation rate limiting with clear retry hints (targets: `merlin_api_server.py`, `merlin_policy.py`).
15. [S015] Add request audit metadata contract (`request_id`, `route`, `decision_version`) (targets: `merlin_api_server.py`, `merlin_audit.py`).
16. [S016] Add endpoint-level circuit breaker integration for unstable dependencies (targets: `merlin_api_server.py`, `merlin_self_healing.py`).
17. [S017] Add structured access logs with redaction of prompt/content fields (targets: `merlin_logger.py`, `merlin_api_server.py`).
18. [S018] Add HTTP timeout and keep-alive tuning defaults for production-like local loads (targets: `merlin_api_server.py`, `docker-compose.yml`).
19. [S019] Add operation-level feature flags for safer phased rollouts (targets: `merlin_settings.py`, `merlin_api_server.py`).
20. [S020] Add endpoint conformance runner that validates request/response against fixture contracts (targets: `tests/test_operation_expected_responses.py`, `tests/fixtures/contracts`).

21. [S021] Replace character-based prompt buckets with optional token-aware buckets (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`).
22. [S022] Add DMS cold-start warmup request and expose readiness state (targets: `merlin_llm_backends.py`, `merlin_settings.py`).
23. [S023] Add per-model timeout matrix (`short`, `medium`, `long`) (targets: `merlin_settings.py`, `merlin_llm_backends.py`).
24. [S024] Move fallback reason strings to a shared enum module to prevent drift (targets: `merlin_routing_contract.py`, `merlin_adaptive_llm.py`).
25. [S025] Centralize route-policy logic into one helper used by adaptive/parallel/streaming backends (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`, `merlin_streaming_llm.py`).
26. [S026] Make A/B assignment deterministic per conversation or correlation hash (targets: `merlin_ab_testing.py`, `merlin_adaptive_llm.py`).
27. [S027] Build explicit SSE parser state machine to handle comments/heartbeat/[DONE] frames (targets: `merlin_streaming_llm.py`, `tests/test_merlin_streaming_llm.py`).
28. [S028] Capture time-to-first-token and stream completion latency for streamed routes (targets: `merlin_streaming_llm.py`, `merlin_metrics_dashboard.py`).
29. [S029] Add quality-scoring hook interface to compare DMS vs control responses (targets: `merlin_adaptive_llm.py`, `merlin_quality_gates.py`).
30. [S030] Add cached-prefix prompt construction helper for repeated system prompts (targets: `merlin_llm_backends.py`, `merlin_settings.py`).
31. [S031] Add ultra-fast short-prompt lane that bypasses heavy routing checks (targets: `merlin_adaptive_llm.py`, `merlin_parallel_llm.py`).
32. [S032] Add prompt truncation + warning metadata for near-token-limit requests (targets: `merlin_llm_backends.py`, `merlin_routing_contract.py`).
33. [S033] Add early-cancel for losing branches in parallel model execution (targets: `merlin_parallel_llm.py`, `tests/test_merlin_parallel_llm.py`).
34. [S034] Add shared retry/backoff utility with jitter and retry budget caps (targets: `merlin_utils.py`, `merlin_llm_backends.py`).
35. [S035] Add route policy version stamp in every routing metadata payload (targets: `merlin_routing_contract.py`, `merlin_adaptive_llm.py`).
36. [S036] Add router regression corpus with expected model selections (targets: `tests/test_merlin_adaptive_llm.py`, `tests/test_merlin_parallel_llm.py`).
37. [S037] Add automatic DMS disable/enable policy based on rolling error budget (targets: `merlin_adaptive_llm.py`, `merlin_settings.py`).
38. [S038] Normalize usage parsing across OpenAI-compatible providers (`usage`, `cached_tokens`) (targets: `merlin_llm_backends.py`, `tests/test_merlin_llm_backends.py`).
39. [S039] Add provider response normalization layer before scoring/metadata emission (targets: `merlin_llm_backends.py`, `merlin_routing_contract.py`).
40. [S040] Add safety pre-check stage for high-risk prompts before model dispatch (targets: `merlin_policy.py`, `merlin_adaptive_llm.py`).

41. [S041] Add session TTL and archival policy for old research-manager sessions (targets: `merlin_research_manager.py`, `merlin_settings.py`).
42. [S042] Add provenance fields (`created_by`, `source_operation`, `policy_version`) on research sessions (targets: `merlin_research_manager.py`, `merlin_api_server.py`).
43. [S043] Add confidence calibration helper for signal scoring (targets: `merlin_research_manager.py`, `tests/test_merlin_research_manager.py`).
44. [S044] Version brief output templates so brief schema changes stay traceable (targets: `merlin_research_manager.py`, `docs/protocols/operation-envelope-v1.md`).
45. [S045] Add explicit audit entries for read-only mode rejections (targets: `merlin_research_manager.py`, `merlin_audit.py`).
46. [S046] Add signal deduplication by stable claim hash to reduce noisy evidence (targets: `merlin_research_manager.py`, `merlin_utils.py`).
47. [S047] Track contradictory signals and expose conflict counts in briefs (targets: `merlin_research_manager.py`, `tests/test_merlin_research_manager.py`).
48. [S048] Add causal chain rendering in brief output for hypothesis evidence links (targets: `merlin_research_manager.py`, `merlin_cli.py`).
49. [S049] Add export/import CLI for research sessions to JSON snapshots (targets: `merlin_cli.py`, `merlin_research_manager.py`).
50. [S050] Add session tagging and topic search filters in API/CLI (targets: `merlin_research_manager.py`, `merlin_cli.py`).
51. [S051] Add batch-mode CLI commands for repeated research operations (targets: `merlin_cli.py`, `tests/test_merlin_cli.py`).
52. [S052] Add webhook/event emitter for research session updates (targets: `merlin_research_manager.py`, `merlin_hub_client.py`).
53. [S053] Expand operation contract fixtures for all research-manager success and error variants (targets: `tests/fixtures/contracts`, `tests/test_operation_expected_responses.py`).
54. [S054] Add cursor-based pagination for large research session lists (targets: `merlin_research_manager.py`, `merlin_api_server.py`).
55. [S055] Add search endpoint for research sessions by objective keyword (targets: `merlin_api_server.py`, `merlin_research_manager.py`).
56. [S056] Add optional background summarization queue for expensive brief generation (targets: `merlin_research_manager.py`, `merlin_tasks.py`).
57. [S057] Add risk-scoring rubric fields (`impact`, `uncertainty`, `time_horizon`) in session schema (targets: `merlin_research_manager.py`, `docs/research/*`).
58. [S058] Link research sessions to task IDs and planner artifacts for traceability (targets: `merlin_tasks.py`, `merlin_research_manager.py`).
59. [S059] Ingest planner fallback telemetry as structured research signals automatically (targets: `merlin_quality_gates.py`, `merlin_research_manager.py`).
60. [S060] Add CLI command to generate CP packet skeletons from session briefs (targets: `merlin_cli.py`, `docs/research`).

61. [S061] Add incremental hashing index updates for resource files to reduce full rescans (targets: `merlin_resource_indexer.py`, `plugins/resource_indexer/plugin.py`).
62. [S062] Add debounce/backpressure controls in file watching to prevent thrash (targets: `merlin_watcher.py`, `merlin_resource_indexer.py`).
63. [S063] Add retrieval relevance diagnostics (`top_k_hit_rate`, `source_diversity`) for RAG queries (targets: `merlin_rag.py`, `tests/test_merlin_rag.py`).
64. [S064] Normalize citation format for RAG responses with deterministic source IDs (targets: `merlin_rag.py`, `merlin_routing_contract.py`).
65. [S065] Enforce plugin manifest schema validation before plugin load (targets: `merlin_plugin_manager.py`, `plugins/*/manifest.json`).
66. [S066] Add plugin permission tiers (`read`, `write`, `network`, `exec`) with policy checks (targets: `merlin_plugin_manager.py`, `merlin_policy.py`).
67. [S067] Add plugin execution timeout budgets and cancellation hooks (targets: `merlin_plugin_manager.py`, `merlin_tasks.py`).
68. [S068] Add plugin dependency compatibility checker in startup preflight (targets: `merlin_plugin_manager.py`, `scripts/check_secret_hygiene.py`).
69. [S069] Add plugin crash isolation and auto-restart with capped retries (targets: `merlin_plugin_manager.py`, `merlin_self_healing.py`).
70. [S070] Add plugin catalog API filters by capability and health state (targets: `merlin_plugin_manager.py`, `merlin_api_server.py`).
71. [S071] Add vector memory compaction and stale-vector cleanup routine (targets: `merlin_vector_memory.py`, `tests/test_merlin_vector_memory.py`).
72. [S072] Add vector-memory integrity checker script for index consistency (targets: `merlin_vector_memory.py`, `scripts/`).
73. [S073] Add schema migration utility for Merlin DB with rollback support (targets: `merlin_db.py`, `merlin_backup.py`).
74. [S074] Tune SQLite pragmas and WAL settings for better concurrent read/write behavior (targets: `merlin_db.py`, `merlin_settings.py`).
75. [S075] Add cache eviction telemetry and hit-rate metrics per cache namespace (targets: `merlin_cache.py`, `merlin_metrics_dashboard.py`).
76. [S076] Add backup integrity hash + verify command for archive confidence (targets: `merlin_backup.py`, `merlin_backup_to_drive.py`).
77. [S077] Add restore smoke test command to validate backup usability (targets: `merlin_backup.py`, `merlin_cli.py`).
78. [S078] Add schema version field in user profile JSON and migration helper (targets: `merlin_user_manager.py`, `merlin_users.json`).
79. [S079] Add voice benchmark dataset versioning and provenance fields (targets: `merlin_voice_benchmark.py`, `merlin_voice_sources.json`).
80. [S080] Add deterministic fallback-to-text metadata when voice routes fail (targets: `merlin_voice_router.py`, `merlin_voice.py`).

81. [S081] Generate typed frontend client contracts from operation fixtures to prevent drift (targets: `frontend/src/services`, `tests/fixtures/contracts`).
82. [S082] Add dashboard panel for fallback taxonomy counts and trend lines (targets: `frontend/src/components/AgentAnalytics.tsx`, `frontend/src/components/PluginAnalytics.tsx`).
83. [S083] Add research-manager session explorer page in frontend (targets: `frontend/src/pages`, `frontend/src/services/onboarding.ts`).
84. [S084] Add command palette for operation discovery and quick execution (targets: `frontend/src/App.tsx`, `frontend/src/components`).
85. [S085] Run responsive layout audit and fix overflow issues on narrow widths (targets: `frontend/src/components/*.css`, `frontend/src/index.css`).
86. [S086] Add frontend bundle-size budget check in CI (targets: `frontend/scripts/check-dist-size.js`, `.github/workflows/ci.yml`).
87. [S087] Add Tauri crash reporting hook with local opt-in upload (targets: `frontend/src-tauri/src/main.rs`, `frontend/src-tauri/tauri.conf.json`).
88. [S088] Add user-facing retry guidance for fallback cases in UI responses (targets: `frontend/src/components/SnapshotSummary.tsx`, `frontend/src/components/SystemInfo.tsx`).
89. [S089] Add accessibility pass for keyboard nav, labels, and contrast in core components (targets: `frontend/src/components`, `frontend/src/pages/Onboarding.tsx`).
90. [S090] Consolidate theme variables and remove duplicated style tokens (targets: `frontend/src/index.css`, `frontend/src/components/*.css`).

91. [S091] Add pre-commit tasks for schema sync, lint, and targeted contract tests (targets: `.pre-commit-config.yaml`, `scripts/sync_contract_schemas.py`).
92. [S092] Roll out stricter `mypy` config in phases by module criticality (targets: `mypy.ini`, `merlin_api_server.py`, `merlin_llm_backends.py`).
93. [S093] Add coverage gate for critical modules (API, routing, research manager) (targets: `pytest.ini`, `.github/workflows/ci.yml`).
94. [S094] Add CI secret-scan policy report artifact and fail conditions (targets: `scripts/check_secret_hygiene.py`, `.github/workflows/ci.yml`).
95. [S095] Add dependency vulnerability scan and weekly report generation (targets: `requirements.txt`, `.github/workflows/ci.yml`).
96. [S096] Add release checklist automation script for artifacts/contracts/tests (targets: `scripts/`, `docs/AGENT_TRANSITION.md`).
97. [S097] Add changelog generation pipeline from tagged commits (targets: `setup.py`, `README.md`, `.github/workflows/ci.yml`).
98. [S098] Add standardized benchmark command pack for local performance snapshots (targets: `merlin_benchmark.py`, `scripts/`).
99. [S099] Add incident runbook templates per subsystem (API, routing, plugins, research manager) (targets: `RUNBOOK.md`, `docs/research`).
100. [S100] Add quarterly architecture drift review checklist with tracked actions (targets: `ARCHITECTURE.md`, `docs/MERLIN_LONG_TERM_ROADMAP.md`).


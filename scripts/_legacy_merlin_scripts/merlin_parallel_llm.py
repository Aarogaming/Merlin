# Merlin Parallel LLM Backend - Multi-Model Orchestration
import os
import asyncio
import requests
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from merlin_logger import merlin_logger
import merlin_settings as settings
from merlin_routing_contract import (
    apply_dms_fallback,
    as_non_negative_int,
    build_routing_decision,
    coerce_usage_normalized,
    enrich_error_with_rate_limit_headers,
    extract_openai_compatible_content,
    fallback_reason_counts_template,
    normalize_openai_usage_payload,
    resolve_query_prompt_bucket,
    select_dms_ab_variant,
    should_prefer_dms_route_from_settings,
)


@dataclass
class ModelResponse:
    model_name: str
    response: str
    latency: float
    success: bool
    error: Optional[str] = None
    usage_normalized: Optional[Dict[str, int]] = None


@dataclass
class ModelConfig:
    name: str
    backend: str
    url: str
    model: str
    api_key: Optional[str] = None


class ParallelLLMBackend:
    _USAGE_BASE_FIELDS = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
    )
    _USAGE_OPTIONAL_FIELDS = ("reasoning_tokens",)

    @staticmethod
    def _extract_openai_compatible_content(data: dict) -> str:
        return extract_openai_compatible_content(data)

    @staticmethod
    def _as_non_negative_int(value: Any) -> int:
        return as_non_negative_int(value)

    @classmethod
    def _normalize_usage(cls, data: dict[str, Any]) -> dict[str, int]:
        return normalize_openai_usage_payload(data)

    @classmethod
    def _coerce_usage_normalized(cls, usage: Any) -> Optional[dict[str, int]]:
        return coerce_usage_normalized(usage)

    def __init__(self):
        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.models = self._load_models()
        self._last_selected_model: Optional[str] = None
        self.dms_ab_enabled = settings.DMS_AB_ENABLED
        self.dms_ab_percentage = settings.DMS_AB_DMS_PERCENTAGE / 100
        self._request_timestamps = deque()
        self.last_decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket="short", router_backend="parallel"
        )
        self.routing_metrics: Dict[str, Any] = {
            "total_requests": 0,
            "dms_attempted": 0,
            "dms_selected": 0,
            "dms_fallbacks": 0,
            "fallback_reason_counts": fallback_reason_counts_template(),
            "throughput_rpm": 0.0,
            "usage_economics": {
                "selected_samples": 0,
                "selected_prompt_tokens": 0,
                "selected_completion_tokens": 0,
                "selected_total_tokens": 0,
                "selected_cached_tokens": 0,
                "selected_reasoning_tokens": 0,
                "by_prompt_bucket": {
                    "short": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                    "medium": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                    "long": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                    "other": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                },
                "by_ab_variant": {
                    "dms": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                    "control": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                    "disabled": {
                        "samples": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                    },
                },
            },
            "ab_variants": {
                "dms": {
                    "requests": 0,
                    "successes": 0,
                    "latency_sum": 0.0,
                    "quality_sum": 0.0,
                },
                "control": {
                    "requests": 0,
                    "successes": 0,
                    "latency_sum": 0.0,
                    "quality_sum": 0.0,
                },
                "disabled": {
                    "requests": 0,
                    "successes": 0,
                    "latency_sum": 0.0,
                    "quality_sum": 0.0,
                },
            },
        }
        merlin_logger.info(
            f"Parallel LLM Backend initialized with {len(self.models)} models, strategy: {self.strategy}"
        )
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))

    def _prompt_size_bucket(self, query: str) -> str:
        prompt_bucket, _ = resolve_query_prompt_bucket(
            query,
            min_prompt_chars=settings.DMS_MIN_PROMPT_CHARS,
            token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
            min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
        )
        return prompt_bucket

    def _should_use_fast_short_lane(self, query: str) -> bool:
        if not settings.MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED:
            return False
        if self.strategy not in {"voting", "auto"}:
            return False
        if len(query) > settings.MERLIN_ROUTER_FAST_SHORT_CHAR_MAX:
            return False
        return self._prompt_size_bucket(query) == "short"

    def _fast_short_lane_model(self) -> Optional[ModelConfig]:
        preferred_order = ("llama3.2", "mistral", "nomic")
        for preferred in preferred_order:
            for model in self.models:
                if model.name == preferred:
                    return model
        for model in self.models:
            if model.name != "dms":
                return model
        return None

    def _get_dms_model(self) -> Optional[ModelConfig]:
        if not settings.DMS_ENABLED:
            return None
        for model in self.models:
            if model.name == "dms":
                return model
        return None

    def _should_prefer_dms(self, query: str) -> bool:
        return should_prefer_dms_route_from_settings(query)

    def _track_request_throughput(self):
        now = time.time()
        self._request_timestamps.append(now)
        cutoff = now - 60
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()
        self.routing_metrics["throughput_rpm"] = len(self._request_timestamps)

    def _record_usage_economics(
        self, prompt_bucket: str, variant: str, usage: Optional[dict[str, int]]
    ) -> None:
        normalized_usage = self._coerce_usage_normalized(usage)
        if not normalized_usage:
            return

        usage_metrics = self.routing_metrics.get("usage_economics")
        if not isinstance(usage_metrics, dict):
            return

        usage_metrics["selected_samples"] = int(usage_metrics.get("selected_samples", 0)) + 1
        usage_metrics["selected_prompt_tokens"] = int(
            usage_metrics.get("selected_prompt_tokens", 0)
        ) + int(normalized_usage.get("prompt_tokens", 0))
        usage_metrics["selected_completion_tokens"] = int(
            usage_metrics.get("selected_completion_tokens", 0)
        ) + int(normalized_usage.get("completion_tokens", 0))
        usage_metrics["selected_total_tokens"] = int(
            usage_metrics.get("selected_total_tokens", 0)
        ) + int(normalized_usage.get("total_tokens", 0))
        usage_metrics["selected_cached_tokens"] = int(
            usage_metrics.get("selected_cached_tokens", 0)
        ) + int(normalized_usage.get("cached_tokens", 0))
        usage_metrics["selected_reasoning_tokens"] = int(
            usage_metrics.get("selected_reasoning_tokens", 0)
        ) + int(normalized_usage.get("reasoning_tokens", 0))

        bucket_key = (
            prompt_bucket
            if prompt_bucket in {"short", "medium", "long"}
            else "other"
        )
        bucket_map = usage_metrics.get("by_prompt_bucket")
        if isinstance(bucket_map, dict):
            bucket_entry = bucket_map.get(bucket_key)
            if not isinstance(bucket_entry, dict):
                bucket_entry = {
                    "samples": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                }
                bucket_map[bucket_key] = bucket_entry
            bucket_entry["samples"] = int(bucket_entry.get("samples", 0)) + 1
            bucket_entry["prompt_tokens"] = int(bucket_entry.get("prompt_tokens", 0)) + int(
                normalized_usage.get("prompt_tokens", 0)
            )
            bucket_entry["completion_tokens"] = int(
                bucket_entry.get("completion_tokens", 0)
            ) + int(normalized_usage.get("completion_tokens", 0))
            bucket_entry["total_tokens"] = int(bucket_entry.get("total_tokens", 0)) + int(
                normalized_usage.get("total_tokens", 0)
            )
            bucket_entry["cached_tokens"] = int(bucket_entry.get("cached_tokens", 0)) + int(
                normalized_usage.get("cached_tokens", 0)
            )
            bucket_entry["reasoning_tokens"] = int(
                bucket_entry.get("reasoning_tokens", 0)
            ) + int(normalized_usage.get("reasoning_tokens", 0))

        variant_key = variant if variant in {"dms", "control", "disabled"} else "disabled"
        variant_map = usage_metrics.get("by_ab_variant")
        if isinstance(variant_map, dict):
            variant_entry = variant_map.get(variant_key)
            if not isinstance(variant_entry, dict):
                variant_entry = {
                    "samples": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                }
                variant_map[variant_key] = variant_entry
            variant_entry["samples"] = int(variant_entry.get("samples", 0)) + 1
            variant_entry["prompt_tokens"] = int(
                variant_entry.get("prompt_tokens", 0)
            ) + int(normalized_usage.get("prompt_tokens", 0))
            variant_entry["completion_tokens"] = int(
                variant_entry.get("completion_tokens", 0)
            ) + int(normalized_usage.get("completion_tokens", 0))
            variant_entry["total_tokens"] = int(variant_entry.get("total_tokens", 0)) + int(
                normalized_usage.get("total_tokens", 0)
            )
            variant_entry["cached_tokens"] = int(variant_entry.get("cached_tokens", 0)) + int(
                normalized_usage.get("cached_tokens", 0)
            )
            variant_entry["reasoning_tokens"] = int(
                variant_entry.get("reasoning_tokens", 0)
            ) + int(normalized_usage.get("reasoning_tokens", 0))

    def _select_ab_variant(
        self, should_prefer_dms: bool, assignment_key: str | None = None
    ) -> str:
        return select_dms_ab_variant(
            should_prefer_dms,
            dms_ab_enabled=self.dms_ab_enabled,
            dms_share_percentage=self.dms_ab_percentage,
            assignment_key=assignment_key,
        )

    def _record_ab_metric(
        self, variant: str, success: bool, latency: float, quality_score: float
    ):
        variant_metrics = self.routing_metrics["ab_variants"].setdefault(
            variant,
            {
                "requests": 0,
                "successes": 0,
                "latency_sum": 0.0,
                "quality_sum": 0.0,
            },
        )
        variant_metrics["requests"] += 1
        if success:
            variant_metrics["successes"] += 1
        variant_metrics["latency_sum"] += latency
        variant_metrics["quality_sum"] += quality_score

    def _usage_economics_status(self) -> Dict[str, Any]:
        usage_metrics = self.routing_metrics.get("usage_economics", {})
        if not isinstance(usage_metrics, dict):
            return {}

        def _avg(total_key: str, samples: int, source: Dict[str, Any]) -> float:
            total = int(source.get(total_key, 0) or 0)
            return float(total / samples) if samples else 0.0

        status: Dict[str, Any] = dict(usage_metrics)
        selected_samples = int(usage_metrics.get("selected_samples", 0) or 0)
        status["selected_avg_prompt_tokens"] = _avg(
            "selected_prompt_tokens", selected_samples, usage_metrics
        )
        status["selected_avg_completion_tokens"] = _avg(
            "selected_completion_tokens", selected_samples, usage_metrics
        )
        status["selected_avg_total_tokens"] = _avg(
            "selected_total_tokens", selected_samples, usage_metrics
        )
        status["selected_avg_cached_tokens"] = _avg(
            "selected_cached_tokens", selected_samples, usage_metrics
        )
        status["selected_avg_reasoning_tokens"] = _avg(
            "selected_reasoning_tokens", selected_samples, usage_metrics
        )

        for map_key in ("by_prompt_bucket", "by_ab_variant"):
            raw_map = usage_metrics.get(map_key)
            if not isinstance(raw_map, dict):
                status[map_key] = {}
                continue

            summarized: Dict[str, Any] = {}
            for key, value in raw_map.items():
                if not isinstance(value, dict):
                    continue
                samples = int(value.get("samples", 0) or 0)
                row: Dict[str, Any] = dict(value)
                row["avg_prompt_tokens"] = _avg("prompt_tokens", samples, value)
                row["avg_completion_tokens"] = _avg("completion_tokens", samples, value)
                row["avg_total_tokens"] = _avg("total_tokens", samples, value)
                row["avg_cached_tokens"] = _avg("cached_tokens", samples, value)
                row["avg_reasoning_tokens"] = _avg("reasoning_tokens", samples, value)
                summarized[key] = row
            status[map_key] = summarized

        return status

    def _ab_status(self) -> Dict[str, Dict[str, float]]:
        metrics = {}
        for variant, values in self.routing_metrics["ab_variants"].items():
            requests = values.get("requests", 0) or 0
            successes = values.get("successes", 0) or 0
            latency_sum = float(values.get("latency_sum", 0.0))
            quality_sum = float(values.get("quality_sum", 0.0))
            metrics[variant] = {
                "requests": requests,
                "success_rate": successes / requests if requests else 0.0,
                "avg_latency": latency_sum / requests if requests else 0.0,
                "avg_quality": quality_sum / requests if requests else 0.0,
            }
        return metrics

    def _load_models(self) -> List[ModelConfig]:
        models = []

        # Mistral via Ollama
        if "mistral" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="mistral",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="mistral",
                )
            )

        # Nomic via Ollama
        if "nomic" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="nomic",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="nomic",
                )
            )

        # GLM (external API)
        if settings.GLM_API_KEY:
            models.append(
                ModelConfig(
                    name="glm4",
                    backend="openai_compat",
                    url=settings.GLM_URL,
                    model=settings.GLM_MODEL,
                    api_key=settings.GLM_API_KEY,
                )
            )

        # Nemotron 3 (external API)
        if settings.NEMOTRON_API_KEY:
            models.append(
                ModelConfig(
                    name="nemotron3",
                    backend="openai_compat",
                    url=settings.NEMOTRON_URL,
                    model=settings.NEMOTRON_MODEL,
                    api_key=settings.NEMOTRON_API_KEY,
                )
            )

        # Llama 3.2 via Ollama
        if "llama3.2" in settings.OLLAMA_MODELS:
            models.append(
                ModelConfig(
                    name="llama3.2",
                    backend="ollama",
                    url=settings.OLLAMA_URL,
                    model="llama3.2",
                )
            )

        if settings.DMS_ENABLED and settings.DMS_URL and settings.DMS_MODEL:
            models.append(
                ModelConfig(
                    name="dms",
                    backend="openai_compat",
                    url=settings.DMS_URL,
                    model=settings.DMS_MODEL,
                    api_key=settings.DMS_API_KEY or None,
                )
            )

        merlin_logger.info(f"Loaded {len(models)} models: {[m.name for m in models]}")
        return models

    def _call_model(
        self, model: ModelConfig, messages: List[Dict], temperature: float, timeout: int
    ) -> ModelResponse:
        import time

        start_time = time.time()

        try:
            payload = {"model": model.model, "messages": messages, "stream": False}

            if temperature is not None and model.backend == "ollama":
                payload["options"] = {"temperature": temperature}
            elif temperature is not None:
                payload["temperature"] = temperature

            headers = {}
            if model.api_key:
                headers["Authorization"] = f"Bearer {model.api_key}"

            response = requests.post(
                model.url, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()

            data = response.json()
            latency = time.time() - start_time

            if model.backend == "ollama":
                content = data.get("message", {}).get("content", "")
            elif model.backend == "openai_compat":
                content = self._extract_openai_compatible_content(data)
            else:
                content = str(data)

            return ModelResponse(
                model_name=model.name,
                response=content,
                latency=latency,
                success=True,
                usage_normalized=self._normalize_usage(data),
            )

        except Exception as e:
            latency = time.time() - start_time
            error_detail = enrich_error_with_rate_limit_headers(e)
            merlin_logger.error(f"Model {model.name} failed: {error_detail}")
            return ModelResponse(
                model_name=model.name,
                response="",
                latency=latency,
                success=False,
                error=error_detail,
                usage_normalized={},
            )

    def _score_response(self, response: str, query: str) -> float:
        try:
            scores = []

            length_score = min(1.0, len(response) / 100)
            scores.append(length_score)

            if "?" in query:
                has_answer = any(char in response for char in ["!", ".", ":"])
                scores.append(1.0 if has_answer else 0.5)
            else:
                scores.append(0.8)

            diversity_score = len(set(response.lower().split())) / max(
                1, len(response.split())
            )
            scores.append(diversity_score)

            return sum(scores) / len(scores)
        except:
            return 0.5

    def _voting_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        scored = [(r, self._score_response(r.response, query)) for r in successful]
        best = max(scored, key=lambda x: x[1])
        self._last_selected_model = best[0].model_name

        merlin_logger.info(
            f"Voting: Selected {best[0].model_name} (score: {best[1]:.2f})"
        )
        return best[0].response

    def _routing_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        selected_model = self._routing_preferred_model(query)

        for response in responses:
            if response.success and response.model_name == selected_model:
                self._last_selected_model = response.model_name
                merlin_logger.info(f"Routing: Selected {response.model_name} for query")
                return response.response

        successful = [r for r in responses if r.success]
        if successful:
            self._last_selected_model = successful[0].model_name
            return successful[0].response

        self._last_selected_model = None
        return "No models available."

    def _routing_preferred_model(self, query: str) -> str:
        query_lower = query.lower()
        routing_rules = {
            "code": [
                "code",
                "program",
                "function",
                "script",
                "debug",
                "fix",
                "nemotron3",
            ],
            "creative": ["story", "creative", "write", "poem", "imagine", "mistral"],
            "fast": ["quick", "short", "brief", "llama3.2"],
            "embedding": ["search", "find", "vector", "semantic", "nomic"],
            "analysis": ["analyze", "compare", "evaluate", "assess", "glm4"],
        }
        for keywords in routing_rules.values():
            if any(kw in query_lower for kw in keywords):
                return keywords[-1]
        return "llama3.2"

    def _should_early_cancel_parallel_futures(
        self,
        strategy_name: str,
        query: str,
        responses: List[ModelResponse],
    ) -> bool:
        if strategy_name != "routing":
            return False
        selected_model = self._routing_preferred_model(query)
        return any(
            response.success and response.model_name == selected_model
            for response in responses
        )

    def _cascade_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        fastest = min(successful, key=lambda r: r.latency)
        best_quality = max(
            successful, key=lambda r: self._score_response(r.response, query)
        )

        if fastest.latency < 2.0:
            refined = f"{fastest.response}\n\n[Refined by {best_quality.model_name}]"
            self._last_selected_model = fastest.model_name
            merlin_logger.info(
                f"Cascade: {fastest.model_name} → {best_quality.model_name}"
            )
            return refined
        else:
            self._last_selected_model = best_quality.model_name
            merlin_logger.info(f"Cascade: Direct to {best_quality.model_name}")
            return best_quality.response

    def _consensus_strategy(self, query: str, responses: List[ModelResponse]) -> str:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        responses_text = [r.response for r in successful]

        from collections import Counter

        words = []
        for resp in responses_text:
            words.extend(resp.lower().split())

        if not words:
            return successful[0].response

        word_counts = Counter(words)
        common_words = [
            word
            for word, count in word_counts.most_common(20)
            if count >= len(successful)
        ]

        if len(common_words) < 5:
            return self._voting_strategy(query, responses)

        consensus = " ".join(common_words[:15])
        self._last_selected_model = "consensus"
        merlin_logger.info(f"Consensus: Built from {len(successful)} models")
        return f"Based on consensus analysis: {consensus}"

    def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int = 30,
    ) -> Dict:
        if stream:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Streaming not supported in parallel mode yet."
                        }
                    }
                ]
            }

        query = messages[-1]["content"] if messages else ""
        self.routing_metrics["total_requests"] += 1
        self._last_selected_model = None
        request_start = time.time()
        self._track_request_throughput()
        decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket=self._prompt_size_bucket(query),
            router_backend="parallel",
            query=query,
        )
        decision["fast_short_lane"] = False

        if self._should_use_fast_short_lane(query):
            fast_model = self._fast_short_lane_model()
            if fast_model is not None:
                fast_response = self._call_model(
                    fast_model, messages, temperature, timeout
                )
                if fast_response.success:
                    self._last_selected_model = fast_response.model_name
                    decision["selected_model"] = fast_response.model_name
                    decision["dms_used"] = False
                    decision["dms_candidate"] = False
                    decision["dms_attempted"] = False
                    decision["ab_variant"] = "disabled"
                    decision["fast_short_lane"] = True
                    decision["fast_short_lane_model"] = fast_response.model_name
                    request_latency = time.time() - request_start
                    quality_score = self._score_response(fast_response.response, query)
                    self._record_ab_metric(
                        "disabled",
                        success=True,
                        latency=request_latency,
                        quality_score=quality_score,
                    )
                    selected_usage = self._coerce_usage_normalized(
                        fast_response.usage_normalized
                    )
                    if selected_usage:
                        decision["usage_normalized"] = selected_usage
                        self._record_usage_economics(
                            decision.get("prompt_size_bucket", "short"),
                            "disabled",
                            selected_usage,
                        )
                    decision["quality_score"] = quality_score
                    decision["request_latency_seconds"] = request_latency
                    self.last_decision = decision
                    return {
                        "choices": [{"message": {"content": fast_response.response}}],
                        "metadata": decision,
                    }

        dms_model = self._get_dms_model()
        should_prefer_dms = dms_model is not None and self._should_prefer_dms(query)
        ab_variant = self._select_ab_variant(
            should_prefer_dms, assignment_key=query if query else None
        )
        decision["ab_variant"] = ab_variant
        include_dms_model = should_prefer_dms and ab_variant == "dms"
        skip_dms_in_pool = not include_dms_model
        decision["dms_candidate"] = should_prefer_dms
        decision["dms_attempted"] = include_dms_model
        decision["parallel_early_cancel_triggered"] = False
        decision["parallel_early_cancelled_branches"] = 0

        if include_dms_model:
            self.routing_metrics["dms_attempted"] += 1
            dms_response = self._call_model(dms_model, messages, temperature, timeout)
            if dms_response.success:
                self._last_selected_model = dms_response.model_name
                decision["selected_model"] = dms_response.model_name
                decision["dms_used"] = True
                self.routing_metrics["dms_selected"] += 1
                request_latency = time.time() - request_start
                quality_score = self._score_response(dms_response.response, query)
                self._record_ab_metric(
                    "dms",
                    success=True,
                    latency=request_latency,
                    quality_score=quality_score,
                )
                selected_usage = self._coerce_usage_normalized(
                    dms_response.usage_normalized
                )
                if selected_usage:
                    decision["usage_normalized"] = selected_usage
                    self._record_usage_economics(
                        decision.get("prompt_size_bucket", "short"),
                        "dms",
                        selected_usage,
                    )
                decision["quality_score"] = quality_score
                decision["request_latency_seconds"] = request_latency
                self.last_decision = decision
                return {
                    "choices": [{"message": {"content": dms_response.response}}],
                    "metadata": decision,
                }

            skip_dms_in_pool = True
            reason_code = apply_dms_fallback(
                decision, dms_response.error, stage="dms_primary"
            )
            self.routing_metrics["fallback_reason_counts"][reason_code] = (
                self.routing_metrics["fallback_reason_counts"].get(reason_code, 0) + 1
            )
            self.routing_metrics["dms_fallbacks"] += 1

        strategies = {
            "voting": self._voting_strategy,
            "routing": self._routing_strategy,
            "cascade": self._cascade_strategy,
            "consensus": self._consensus_strategy,
        }
        strategy_name = self.strategy if self.strategy in strategies else "voting"
        strategy_func = strategies[strategy_name]

        futures = []
        for model in self.models:
            if skip_dms_in_pool and model.name == "dms":
                continue
            future = self.executor.submit(
                self._call_model, model, messages, temperature, timeout
            )
            futures.append(future)

        responses = []
        pending_futures = set(futures)
        for future in as_completed(futures):
            pending_futures.discard(future)
            try:
                response = future.result()
                responses.append(response)
            except Exception as e:
                merlin_logger.error(f"Parallel execution error: {e}")
                continue

            if self._should_early_cancel_parallel_futures(
                strategy_name, query, responses
            ):
                cancelled = 0
                for pending_future in pending_futures:
                    if pending_future.cancel():
                        cancelled += 1
                decision["parallel_early_cancel_triggered"] = cancelled > 0
                decision["parallel_early_cancelled_branches"] = cancelled
                if cancelled > 0:
                    merlin_logger.info(
                        "Parallel routing: early-cancelled %s losing branches",
                        cancelled,
                    )
                break

        final_response = strategy_func(query, responses)
        decision["selected_model"] = self._last_selected_model
        decision["dms_used"] = self._last_selected_model == "dms"
        selected_usage: Optional[dict[str, int]] = None
        if self._last_selected_model is not None:
            for routed_response in responses:
                if routed_response.model_name != self._last_selected_model:
                    continue
                selected_usage = self._coerce_usage_normalized(
                    routed_response.usage_normalized
                )
                if selected_usage:
                    decision["usage_normalized"] = selected_usage
                break
        request_latency = time.time() - request_start
        quality_score = self._score_response(final_response, query)
        metric_variant = ab_variant if should_prefer_dms else "disabled"
        self._record_ab_metric(
            metric_variant,
            success=bool(self._last_selected_model is not None),
            latency=request_latency,
            quality_score=quality_score,
        )
        if selected_usage:
            self._record_usage_economics(
                decision.get("prompt_size_bucket", "short"),
                metric_variant,
                selected_usage,
            )
        decision["quality_score"] = quality_score
        decision["request_latency_seconds"] = request_latency
        self.last_decision = decision

        return {
            "choices": [{"message": {"content": final_response}}],
            "metadata": decision,
        }

    def health_check(self) -> Dict[str, bool]:
        results = {}
        for model in self.models:
            try:
                response = requests.get(
                    (
                        model.url.replace("/chat/completions", "/tags")
                        if "/chat" in model.url
                        else model.url
                    ),
                    timeout=3,
                )
                results[model.name] = response.status_code == 200
            except:
                results[model.name] = False
        return results

    def get_status(self) -> Dict:
        routing_metrics = dict(self.routing_metrics)
        if "ab_variants" in routing_metrics:
            routing_metrics["ab_variants"] = self._ab_status()
        if "usage_economics" in routing_metrics:
            routing_metrics["usage_economics"] = self._usage_economics_status()
        return {
            "strategy": self.strategy,
            "models": [{"name": m.name, "backend": m.backend} for m in self.models],
            "health": self.health_check(),
            "last_decision": self.last_decision,
            "routing_metrics": routing_metrics,
        }


parallel_llm_backend = ParallelLLMBackend()

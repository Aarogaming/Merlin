# Merlin Adaptive LLM Backend - Self-Optimizing Multi-Model Orchestration
import os
import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from merlin_logger import merlin_logger
from merlin_policy import analyze_prompt_safety
from merlin_quality_gates import score_response_quality_with_hook
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
class ModelMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    total_latency: float = 0.0
    user_ratings: List[int] = field(default_factory=list)
    task_successes: Dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency(self) -> float:
        if self.successful_requests == 0:
            return float("inf")
        return self.total_latency / self.successful_requests

    @property
    def avg_rating(self) -> float:
        if not self.user_ratings:
            return 0.0
        return sum(self.user_ratings) / len(self.user_ratings)

    def task_success_rate(self, task_type: str) -> float:
        total = sum(self.task_successes.values())
        if total == 0:
            return 0.0
        return self.task_successes.get(task_type, 0) / total

    def record_request(
        self, success: bool, latency: float, task_type: Optional[str] = None
    ):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_latency += latency
        if task_type:
            self.task_successes[task_type] = self.task_successes.get(task_type, 0) + 1

    def record_rating(self, rating: int):
        self.user_ratings.append(rating)
        if len(self.user_ratings) > 100:
            self.user_ratings = self.user_ratings[-50:]

    def get_score(self, task_type: str = None) -> float:
        base_score = 0.5
        base_score += self.success_rate * 0.3
        base_score += min(1.0, 10.0 / max(1.0, self.avg_latency)) * 0.2
        base_score += self.avg_rating / 5.0 * 0.3

        if task_type and task_type in self.task_successes:
            base_score += self.task_success_rate(task_type) * 0.2

        return min(1.0, max(0.0, base_score))


@dataclass
class QueryContext:
    task_type: str
    complexity: str
    urgency: str
    requires_creativity: bool
    requires_accuracy: bool
    keywords: List[str]

    @classmethod
    def analyze(cls, query: str) -> "QueryContext":
        query_lower = query.lower()

        task_types = {
            "code": [
                "code",
                "function",
                "script",
                "debug",
                "fix",
                "program",
                "implement",
            ],
            "creative": ["story", "write", "poem", "creative", "imagine", "draft"],
            "analysis": [
                "analyze",
                "compare",
                "evaluate",
                "assess",
                "review",
                "explain",
            ],
            "search": ["find", "search", "lookup", "what is", "who is"],
            "fact": ["what", "when", "where", "how many", "how much"],
            "planning": ["plan", "schedule", "organize", "how to", "steps"],
            "translation": ["translate", "convert", "language"],
            "summarize": ["summarize", "brief", "summary", "short"],
        }

        task_type = "general"
        for ttype, keywords in task_types.items():
            if any(kw in query_lower for kw in keywords):
                task_type = ttype
                break

        complexity = "medium"
        if any(kw in query_lower for kw in ["simple", "basic", "quick", "just"]):
            complexity = "low"
        elif any(
            kw in query_lower
            for kw in ["complex", "detailed", "thorough", "comprehensive", "advanced"]
        ):
            complexity = "high"

        urgency = "normal"
        if any(
            kw in query_lower
            for kw in ["urgent", "asap", "now", "immediately", "quick"]
        ):
            urgency = "high"
        elif any(kw in query_lower for kw in ["when you can", "eventually", "later"]):
            urgency = "low"

        requires_creativity = any(
            kw in query_lower
            for kw in ["creative", "story", "imagine", "invent", "innovative"]
        )
        requires_accuracy = any(
            kw in query_lower
            for kw in ["accurate", "precise", "exact", "correct", "factual"]
        )

        keywords = [word for word in query_lower.split() if len(word) > 3][:10]

        return cls(
            task_type=task_type,
            complexity=complexity,
            urgency=urgency,
            requires_creativity=requires_creativity,
            requires_accuracy=requires_accuracy,
            keywords=keywords,
        )


class AdaptiveLLMBackend:
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

    @classmethod
    def _usage_delta(
        cls, dms_usage: dict[str, int], control_usage: dict[str, int]
    ) -> dict[str, int]:
        delta: dict[str, int] = {}
        for key in cls._USAGE_BASE_FIELDS + cls._USAGE_OPTIONAL_FIELDS:
            dms_value = cls._as_non_negative_int(dms_usage.get(key))
            control_value = cls._as_non_negative_int(control_usage.get(key))
            delta_value = dms_value - control_value
            if delta_value != 0:
                delta[key] = delta_value
        return delta

    def __init__(self):
        self.metrics_file = "artifacts/adaptive_metrics.json"
        self.model_metrics: Dict[str, ModelMetrics] = {}
        self.load_metrics()

        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.learning_mode = os.getenv("LEARNING_MODE", "enabled").lower() == "enabled"
        self.min_samples = int(os.getenv("MIN_LEARNING_SAMPLES", "5"))
        self.dms_ab_enabled = settings.DMS_AB_ENABLED
        self.dms_ab_percentage = settings.DMS_AB_DMS_PERCENTAGE / 100
        self._request_timestamps = deque()
        self._dms_quality_autopause_enabled = settings.DMS_QUALITY_AUTOPAUSE_ENABLED
        self._dms_quality_window = max(1, settings.DMS_QUALITY_AUTOPAUSE_WINDOW)
        self._dms_quality_min_samples = max(
            1,
            min(
                settings.DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES,
                self._dms_quality_window,
            ),
        )
        self._dms_quality_min_avg_score = settings.DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE
        self._dms_quality_cooldown_seconds = max(
            1, settings.DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS
        )
        self._dms_quality_scores: deque[float] = deque(maxlen=self._dms_quality_window)
        self._dms_error_budget_enabled = settings.DMS_ERROR_BUDGET_ENABLED
        self._dms_error_budget_window = max(1, settings.DMS_ERROR_BUDGET_WINDOW)
        self._dms_error_budget_min_attempts = max(
            1,
            min(
                settings.DMS_ERROR_BUDGET_MIN_ATTEMPTS,
                self._dms_error_budget_window,
            ),
        )
        self._dms_error_budget_max_failure_rate = (
            settings.DMS_ERROR_BUDGET_MAX_FAILURE_RATE
        )
        self._dms_error_budget_cooldown_seconds = max(
            1, settings.DMS_ERROR_BUDGET_COOLDOWN_SECONDS
        )
        self._dms_attempt_outcomes: deque[int] = deque(
            maxlen=self._dms_error_budget_window
        )
        self._dms_disabled_until_ts = 0.0
        self._dms_last_budget_trip_reason: Optional[str] = None

        self.models = self._load_models()
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))
        self._last_selected_model: Optional[str] = None
        self.last_decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket="short", router_backend="adaptive"
        )
        self.routing_metrics: Dict[str, Any] = {
            "total_requests": 0,
            "dms_attempted": 0,
            "dms_selected": 0,
            "dms_fallbacks": 0,
            "dms_shadow_attempted": 0,
            "dms_shadow_successes": 0,
            "dms_shadow_failures": 0,
            "dms_shadow_quality_sum": 0.0,
            "dms_quality_budget_trips": 0,
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
                "shadow_delta_samples": 0,
                "shadow_dms_minus_control_prompt_tokens_sum": 0,
                "shadow_dms_minus_control_completion_tokens_sum": 0,
                "shadow_dms_minus_control_total_tokens_sum": 0,
                "shadow_dms_minus_control_cached_tokens_sum": 0,
                "shadow_dms_minus_control_reasoning_tokens_sum": 0,
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

        self.strategies = {
            "voting": self._voting_strategy,
            "routing": self._adaptive_routing_strategy,
            "cascade": self._adaptive_cascade_strategy,
            "consensus": self._consensus_strategy,
            "auto": self._auto_strategy,
        }

        merlin_logger.info(
            f"Adaptive LLM Backend: {len(self.models)} models, learning: {self.learning_mode}"
        )

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

    def _fast_short_lane_model(self) -> Optional[Dict[str, Any]]:
        preferred_order = ("llama3.2", "mistral", "nomic")
        for preferred in preferred_order:
            for model in self.models:
                if model.get("name") == preferred:
                    return model
        for model in self.models:
            if model.get("name") != "dms":
                return model
        return None

    def _track_request_throughput(self):
        now = time.time()
        self._request_timestamps.append(now)
        cutoff = now - 60
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()
        self.routing_metrics["throughput_rpm"] = len(self._request_timestamps)

    def _record_usage_economics(
        self, prompt_bucket: str, usage: Optional[dict[str, int]]
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
        if not isinstance(bucket_map, dict):
            return
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

    def _record_shadow_usage_delta(self, delta: dict[str, int]) -> None:
        if not delta:
            return

        usage_metrics = self.routing_metrics.get("usage_economics")
        if not isinstance(usage_metrics, dict):
            return

        usage_metrics["shadow_delta_samples"] = int(
            usage_metrics.get("shadow_delta_samples", 0)
        ) + 1
        usage_metrics["shadow_dms_minus_control_prompt_tokens_sum"] = int(
            usage_metrics.get("shadow_dms_minus_control_prompt_tokens_sum", 0)
        ) + int(delta.get("prompt_tokens", 0))
        usage_metrics["shadow_dms_minus_control_completion_tokens_sum"] = int(
            usage_metrics.get("shadow_dms_minus_control_completion_tokens_sum", 0)
        ) + int(delta.get("completion_tokens", 0))
        usage_metrics["shadow_dms_minus_control_total_tokens_sum"] = int(
            usage_metrics.get("shadow_dms_minus_control_total_tokens_sum", 0)
        ) + int(delta.get("total_tokens", 0))
        usage_metrics["shadow_dms_minus_control_cached_tokens_sum"] = int(
            usage_metrics.get("shadow_dms_minus_control_cached_tokens_sum", 0)
        ) + int(delta.get("cached_tokens", 0))
        usage_metrics["shadow_dms_minus_control_reasoning_tokens_sum"] = int(
            usage_metrics.get("shadow_dms_minus_control_reasoning_tokens_sum", 0)
        ) + int(delta.get("reasoning_tokens", 0))

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
        self,
        variant: str,
        success: bool,
        latency: float,
        quality_score: float,
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

    def _is_dms_budget_temporarily_disabled(self, now: Optional[float] = None) -> bool:
        current_time = time.time() if now is None else now
        if self._dms_disabled_until_ts <= 0:
            return False
        if current_time >= self._dms_disabled_until_ts:
            self._dms_disabled_until_ts = 0.0
            self._dms_attempt_outcomes.clear()
            self._dms_quality_scores.clear()
            self._dms_last_budget_trip_reason = None
            return False
        return True

    def _record_dms_attempt_outcome(
        self,
        success: bool,
        failure_reason: Optional[str] = None,
    ):
        if not self._dms_error_budget_enabled:
            return

        current_time = time.time()
        if self._is_dms_budget_temporarily_disabled(now=current_time):
            return

        self._dms_attempt_outcomes.append(1 if success else 0)
        attempts = len(self._dms_attempt_outcomes)
        if attempts < self._dms_error_budget_min_attempts:
            return

        failures = attempts - sum(self._dms_attempt_outcomes)
        failure_rate = failures / attempts if attempts else 0.0
        if failure_rate >= self._dms_error_budget_max_failure_rate:
            self._dms_disabled_until_ts = (
                current_time + self._dms_error_budget_cooldown_seconds
            )
            self._dms_last_budget_trip_reason = failure_reason
            merlin_logger.warning(
                "Adaptive DMS budget opened: failure_rate=%s attempts=%s cooldown=%ss",
                round(failure_rate, 4),
                attempts,
                self._dms_error_budget_cooldown_seconds,
            )

    def _record_dms_quality_score(self, quality_score: float):
        if not self._dms_quality_autopause_enabled:
            return

        current_time = time.time()
        if self._is_dms_budget_temporarily_disabled(now=current_time):
            return

        self._dms_quality_scores.append(float(quality_score))
        sample_count = len(self._dms_quality_scores)
        if sample_count < self._dms_quality_min_samples:
            return

        avg_quality = (
            sum(self._dms_quality_scores) / sample_count if sample_count else 0.0
        )
        if avg_quality < self._dms_quality_min_avg_score:
            self._dms_disabled_until_ts = (
                current_time + self._dms_quality_cooldown_seconds
            )
            self._dms_last_budget_trip_reason = "quality_score_below_threshold"
            self.routing_metrics["dms_quality_budget_trips"] += 1
            merlin_logger.warning(
                "Adaptive DMS quality budget opened: avg_quality=%s samples=%s cooldown=%ss",
                round(avg_quality, 4),
                sample_count,
                self._dms_quality_cooldown_seconds,
            )

    def _dms_budget_status(self, now: Optional[float] = None) -> Dict[str, Any]:
        current_time = time.time() if now is None else now
        temporarily_disabled = self._is_dms_budget_temporarily_disabled(now=current_time)
        attempts = len(self._dms_attempt_outcomes)
        failures = attempts - sum(self._dms_attempt_outcomes)
        failure_rate = failures / attempts if attempts else 0.0
        quality_samples = len(self._dms_quality_scores)
        avg_quality = (
            sum(self._dms_quality_scores) / quality_samples if quality_samples else 0.0
        )
        return {
            "enabled": self._dms_error_budget_enabled,
            "window_size": self._dms_error_budget_window,
            "min_attempts": self._dms_error_budget_min_attempts,
            "max_failure_rate": self._dms_error_budget_max_failure_rate,
            "cooldown_seconds": self._dms_error_budget_cooldown_seconds,
            "attempts": attempts,
            "failures": failures,
            "failure_rate": failure_rate,
            "quality_autopause_enabled": self._dms_quality_autopause_enabled,
            "quality_window_size": self._dms_quality_window,
            "quality_min_samples": self._dms_quality_min_samples,
            "quality_min_avg_score": self._dms_quality_min_avg_score,
            "quality_cooldown_seconds": self._dms_quality_cooldown_seconds,
            "quality_samples": quality_samples,
            "avg_quality": avg_quality,
            "temporarily_disabled": temporarily_disabled,
            "disabled_until_unix": (
                self._dms_disabled_until_ts if temporarily_disabled else None
            ),
            "last_trip_reason": self._dms_last_budget_trip_reason,
        }

    def _get_dms_model(self) -> Optional[Dict[str, Any]]:
        if not settings.DMS_ENABLED:
            return None
        for model in self.models:
            if model["name"] == "dms":
                return model
        return None

    def _should_prefer_dms(self, query: str, context: QueryContext) -> bool:
        return should_prefer_dms_route_from_settings(
            query,
            context_task_type=context.task_type,
            context_complexity=context.complexity,
            enforce_context_task_allowlist=settings.DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED,
        )

    def _load_models(self) -> List[Dict[str, Any]]:
        models = []

        for model_name in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": model_name,
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": model_name,
                }
            )

        if settings.NEMOTRON_API_KEY:
            models.append(
                {
                    "name": "nemotron3",
                    "backend": "openai_compat",
                    "url": settings.NEMOTRON_URL,
                    "model": settings.NEMOTRON_MODEL,
                    "api_key": settings.NEMOTRON_API_KEY,
                }
            )

        if settings.GLM_API_KEY:
            models.append(
                {
                    "name": "glm4",
                    "backend": "openai_compat",
                    "url": settings.GLM_URL,
                    "model": settings.GLM_MODEL,
                    "api_key": settings.GLM_API_KEY,
                }
            )

        if settings.DMS_ENABLED and settings.DMS_URL and settings.DMS_MODEL:
            models.append(
                {
                    "name": "dms",
                    "backend": "openai_compat",
                    "url": settings.DMS_URL,
                    "model": settings.DMS_MODEL,
                    "api_key": settings.DMS_API_KEY or None,
                }
            )

        return models

    def load_metrics(self):
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                for name, metrics in data.items():
                    self.model_metrics[name] = ModelMetrics(
                        total_requests=metrics.get("total_requests", 0),
                        successful_requests=metrics.get("successful_requests", 0),
                        total_latency=metrics.get("total_latency", 0.0),
                        user_ratings=metrics.get("user_ratings", []),
                        task_successes=metrics.get("task_successes", {}),
                    )
                merlin_logger.info(
                    f"Loaded metrics for {len(self.model_metrics)} models"
                )
            except Exception as e:
                merlin_logger.error(f"Failed to load metrics: {e}")

    def save_metrics(self):
        try:
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            data = {}
            for name, metrics in self.model_metrics.items():
                data[name] = {
                    "total_requests": metrics.total_requests,
                    "successful_requests": metrics.successful_requests,
                    "total_latency": metrics.total_latency,
                    "user_ratings": metrics.user_ratings,
                    "task_successes": metrics.task_successes,
                }
            with open(self.metrics_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save metrics: {e}")

    def _call_model(
        self,
        model: Dict[str, Any],
        messages: List[Dict[str, Any]],
        temperature: float,
        timeout: int,
    ) -> Dict[str, Any]:
        start_time = time.time()

        try:
            payload = {"model": model["model"], "messages": messages, "stream": False}

            if temperature is not None and model["backend"] == "ollama":
                payload["options"] = {"temperature": temperature}
            elif temperature is not None:
                payload["temperature"] = temperature

            headers = {}
            if model.get("api_key"):
                headers["Authorization"] = f"Bearer {model['api_key']}"

            response = requests.post(
                model["url"], json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()

            data = response.json()
            latency = time.time() - start_time

            if model["backend"] == "ollama":
                content = data.get("message", {}).get("content", "")
            elif model["backend"] == "openai_compat":
                content = self._extract_openai_compatible_content(data)
            else:
                content = str(data)

            return {
                "model_name": model["name"],
                "response": content,
                "latency": latency,
                "success": True,
                "usage_normalized": self._normalize_usage(data),
            }

        except Exception as e:
            latency = time.time() - start_time
            error_detail = enrich_error_with_rate_limit_headers(e)
            return {
                "model_name": model["name"],
                "response": "",
                "latency": latency,
                "success": False,
                "error": error_detail,
                "usage_normalized": {},
            }

    def _score_response(self, response: str, context: QueryContext) -> float:
        scores = []

        length_score = min(1.0, len(response) / 150)
        scores.append(length_score)

        if context.task_type == "code":
            code_keywords = [
                "def",
                "function",
                "class",
                "import",
                "return",
                "if",
                "for",
                "while",
            ]
            code_score = sum(1 for kw in code_keywords if kw in response) / len(
                code_keywords
            )
            scores.append(min(1.0, code_score * 2))

        if context.requires_creativity:
            creative_words = response.lower().split()
            diversity = len(set(creative_words)) / max(1, len(creative_words))
            scores.append(diversity)

        if context.requires_accuracy:
            has_structure = any(char in response for char in [".", ";", ":"])
            scores.append(1.0 if has_structure else 0.5)

        return sum(scores) / len(scores)

    def _score_with_quality_hook(
        self,
        *,
        query: str,
        variant: str,
        response: str,
        context: QueryContext,
        decision: Dict[str, Any],
        fallback_quality_score: float,
    ) -> float:
        hook_result = score_response_quality_with_hook(
            query=query,
            variant=variant,
            response=response,
            context={
                "task_type": context.task_type,
                "complexity": context.complexity,
                "urgency": context.urgency,
                "strategy": self.strategy,
            },
        )
        if hook_result.get("error"):
            decision["quality_hook_error"] = hook_result["error"]
        if hook_result.get("applied"):
            hook_score = float(hook_result["score"])
            decision["quality_hook_applied"] = True
            decision["quality_hook_source"] = hook_result.get("source", "custom")
            decision["quality_hook_score"] = hook_score
            return hook_score
        decision["quality_hook_applied"] = False
        return fallback_quality_score

    def _auto_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        if context.urgency == "high":
            return self._adaptive_routing_strategy(context, responses)
        elif context.complexity == "high":
            return self._voting_strategy(context, responses)
        elif context.requires_accuracy:
            return self._consensus_strategy(context, responses)
        else:
            return self._adaptive_routing_strategy(context, responses)

    def _adaptive_routing_strategy(
        self, context: QueryContext, responses: List[Dict]
    ) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        for model in self.models:
            model_name = model["name"]
            if model_name in self.model_metrics:
                self.model_metrics[model_name].record_request(
                    success=False, latency=0, task_type=context.task_type
                )

        best_model = None
        best_score = -1.0

        for response in successful:
            model_name = response["model_name"]
            metrics = self.model_metrics.get(model_name, ModelMetrics())

            model_score = metrics.get_score(context.task_type)

            if self.learning_mode and metrics.total_requests >= self.min_samples:
                if best_score < model_score:
                    best_score = model_score
                    best_model = response
            else:
                if not best_model or response["latency"] < best_model["latency"]:
                    best_model = response

        if best_model:
            self._last_selected_model = best_model["model_name"]
            merlin_logger.info(
                f"Adaptive routing: Selected {best_model['model_name']} (score: {best_score:.2f})"
            )
            return best_model["response"]

        self._last_selected_model = successful[0]["model_name"]
        return successful[0]["response"]

    def _voting_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        scored = [(r, self._score_response(r["response"], context)) for r in successful]
        best = max(scored, key=lambda x: x[1])
        self._last_selected_model = best[0]["model_name"]

        if self.learning_mode:
            for response, score in scored:
                model_name = response["model_name"]
                if model_name not in self.model_metrics:
                    self.model_metrics[model_name] = ModelMetrics()
                self.model_metrics[model_name].record_request(
                    success=response["success"],
                    latency=response["latency"],
                    task_type=context.task_type,
                )

        merlin_logger.info(
            f"Adaptive voting: Selected {best[0]['model_name']} (score: {best[1]:.2f})"
        )
        return best[0]["response"]

    def _adaptive_cascade_strategy(
        self, context: QueryContext, responses: List[Dict]
    ) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        fastest = min(successful, key=lambda r: r["latency"])

        if self.learning_mode and context.urgency != "high":
            best_quality = max(
                successful, key=lambda r: self._score_response(r["response"], context)
            )

            if fastest["latency"] < 2.0:
                refined = f"{fastest['response']}\n\n[Verified by {best_quality['model_name']}]"
                self._last_selected_model = fastest["model_name"]
                merlin_logger.info(
                    f"Adaptive cascade: {fastest['model_name']} → {best_quality['model_name']}"
                )

                for model_name in [fastest["model_name"], best_quality["model_name"]]:
                    if model_name not in self.model_metrics:
                        self.model_metrics[model_name] = ModelMetrics()
                    response_data = next(
                        r for r in successful if r["model_name"] == model_name
                    )
                    self.model_metrics[model_name].record_request(
                        success=response_data["success"],
                        latency=response_data["latency"],
                        task_type=context.task_type,
                    )

                return refined

        self._last_selected_model = fastest["model_name"]
        return fastest["response"]

    def _consensus_strategy(self, context: QueryContext, responses: List[Dict]) -> str:
        successful = [r for r in responses if r["success"]]
        if not successful:
            self._last_selected_model = None
            return "All models failed to respond."

        responses_text = [r["response"] for r in successful]

        word_counter: Counter[str] = Counter()
        for resp in responses_text:
            words = resp.lower().split()
            word_counter.update(words)

        common_words = [
            word
            for word, count in word_counter.most_common(30)
            if count >= len(successful) // 2
        ]

        if len(common_words) < 5:
            return self._voting_strategy(context, responses)

        consensus = " ".join(common_words[:20])
        self._last_selected_model = "consensus"

        if self.learning_mode:
            for response in successful:
                model_name = response["model_name"]
                if model_name not in self.model_metrics:
                    self.model_metrics[model_name] = ModelMetrics()
                self.model_metrics[model_name].record_request(
                    success=response["success"],
                    latency=response["latency"],
                    task_type=context.task_type,
                )

        merlin_logger.info(f"Adaptive consensus: Built from {len(successful)} models")
        return f"Based on consensus analysis: {consensus}"

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int = 30,
    ) -> Dict:
        if stream:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Streaming not supported in adaptive mode yet."
                        }
                    }
                ]
            }

        request_start = time.time()
        query = messages[-1]["content"] if messages else ""
        context = QueryContext.analyze(query)
        self._track_request_throughput()
        self.routing_metrics["total_requests"] += 1
        self._last_selected_model = None
        decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket=self._prompt_size_bucket(query),
            router_backend="adaptive",
            query=query,
        )
        decision["fast_short_lane"] = False
        decision["dms_shadow_validation_enabled"] = (
            settings.DMS_SHADOW_VALIDATION_ENABLED
        )
        decision["dms_shadow_executed"] = False
        safety = analyze_prompt_safety(query)
        decision["safety_risk_level"] = safety["risk_level"]
        decision["safety_mode"] = safety["mode"]
        decision["safety_matched_keywords"] = safety["matched_keywords"]
        decision["policy_blocked"] = safety["blocked"]

        if safety["blocked"]:
            decision["ab_variant"] = "disabled"
            decision["policy_block_reason"] = "high_risk_prompt"
            request_latency = time.time() - request_start
            decision["request_latency_seconds"] = request_latency
            self._record_ab_metric(
                "disabled",
                success=False,
                latency=request_latency,
                quality_score=0.0,
            )
            self.last_decision = decision
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Request blocked by Merlin safety policy in safe mode."
                        }
                    }
                ],
                "metadata": decision,
            }

        if self._should_use_fast_short_lane(query):
            fast_model = self._fast_short_lane_model()
            if fast_model is not None:
                fast_response = self._call_model(
                    fast_model, messages, temperature, timeout
                )
                if fast_response["success"]:
                    self._last_selected_model = fast_response["model_name"]
                    decision["selected_model"] = fast_response["model_name"]
                    decision["dms_used"] = False
                    decision["dms_candidate"] = False
                    decision["dms_attempted"] = False
                    decision["ab_variant"] = "disabled"
                    decision["fast_short_lane"] = True
                    decision["fast_short_lane_model"] = fast_response["model_name"]
                    request_latency = time.time() - request_start
                    quality_score = self._score_with_quality_hook(
                        query=query,
                        variant="disabled",
                        response=fast_response["response"],
                        context=context,
                        decision=decision,
                        fallback_quality_score=self._score_response(
                            fast_response["response"], context
                        ),
                    )
                    self._record_ab_metric(
                        "disabled",
                        success=True,
                        latency=request_latency,
                        quality_score=quality_score,
                    )
                    selected_usage = self._coerce_usage_normalized(
                        fast_response.get("usage_normalized")
                    )
                    if selected_usage:
                        decision["usage_normalized"] = selected_usage
                        self._record_usage_economics(
                            decision.get("prompt_size_bucket", "short"),
                            selected_usage,
                        )
                    self.last_decision = decision
                    decision["quality_score"] = quality_score
                    decision["request_latency_seconds"] = request_latency
                    decision["dms_budget"] = self._dms_budget_status()
                    self.save_metrics()
                    return {
                        "choices": [
                            {"message": {"content": fast_response["response"]}}
                        ],
                        "metadata": decision,
                    }

        dms_model = self._get_dms_model()
        dms_candidate = dms_model is not None and self._should_prefer_dms(query, context)
        dms_budget_blocked = (
            dms_candidate and self._is_dms_budget_temporarily_disabled(now=request_start)
        )
        should_prefer_dms = dms_candidate and not dms_budget_blocked
        ab_variant = self._select_ab_variant(
            should_prefer_dms, assignment_key=query if query else None
        )
        decision["ab_variant"] = ab_variant
        include_dms_model = should_prefer_dms and ab_variant == "dms"
        skip_dms_in_pool = not include_dms_model
        decision["dms_candidate"] = dms_candidate
        decision["dms_attempted"] = include_dms_model
        decision["dms_budget_blocked"] = dms_budget_blocked
        decision["dms_budget"] = self._dms_budget_status(now=request_start)

        if include_dms_model and dms_model is not None:
            self.routing_metrics["dms_attempted"] += 1
            dms_response = self._call_model(dms_model, messages, temperature, timeout)
            if dms_response["success"]:
                self._record_dms_attempt_outcome(success=True)
                self._last_selected_model = dms_response["model_name"]
                decision["selected_model"] = dms_response["model_name"]
                decision["dms_used"] = True
                self.routing_metrics["dms_selected"] += 1
                request_latency = time.time() - request_start
                quality_score = self._score_with_quality_hook(
                    query=query,
                    variant="dms",
                    response=dms_response["response"],
                    context=context,
                    decision=decision,
                    fallback_quality_score=self._score_response(
                        dms_response["response"], context
                    ),
                )
                self._record_ab_metric(
                    "dms",
                    success=True,
                    latency=request_latency,
                    quality_score=quality_score,
                )
                self._record_dms_quality_score(quality_score)
                selected_usage = self._coerce_usage_normalized(
                    dms_response.get("usage_normalized")
                )
                if selected_usage:
                    decision["usage_normalized"] = selected_usage
                    self._record_usage_economics(
                        decision.get("prompt_size_bucket", "short"),
                        selected_usage,
                    )
                self.last_decision = decision
                decision["quality_score"] = quality_score
                decision["request_latency_seconds"] = request_latency
                decision["dms_budget"] = self._dms_budget_status()
                self.save_metrics()
                return {
                    "choices": [{"message": {"content": dms_response["response"]}}],
                    "metadata": decision,
                }

            skip_dms_in_pool = True
            reason_code = apply_dms_fallback(
                decision, dms_response.get("error"), stage="dms_primary"
            )
            self.routing_metrics["fallback_reason_counts"][reason_code] = (
                self.routing_metrics["fallback_reason_counts"].get(reason_code, 0) + 1
            )
            self.routing_metrics["dms_fallbacks"] += 1
            self._record_dms_attempt_outcome(success=False, failure_reason=reason_code)
            decision["dms_budget"] = self._dms_budget_status()

        futures = []
        for model in self.models:
            if skip_dms_in_pool and model["name"] == "dms":
                continue
            future = self.executor.submit(
                self._call_model, model, messages, temperature, timeout
            )
            futures.append(future)

        responses = []
        for future in as_completed(futures):
            try:
                response = future.result()
                responses.append(response)
            except Exception as e:
                merlin_logger.error(f"Adaptive execution error: {e}")

        strategy_func = self.strategies.get(self.strategy, self._auto_strategy)
        final_response = strategy_func(context, responses)
        decision["selected_model"] = self._last_selected_model
        decision["dms_used"] = self._last_selected_model == "dms"
        selected_usage: Optional[dict[str, int]] = None
        if self._last_selected_model is not None:
            for routed_response in responses:
                if routed_response.get("model_name") != self._last_selected_model:
                    continue
                selected_usage = self._coerce_usage_normalized(
                    routed_response.get("usage_normalized")
                )
                if selected_usage:
                    decision["usage_normalized"] = selected_usage
                    self._record_usage_economics(
                        decision.get("prompt_size_bucket", "short"),
                        selected_usage,
                    )
                break

        run_shadow_validation = (
            settings.DMS_SHADOW_VALIDATION_ENABLED
            and dms_model is not None
            and should_prefer_dms
            and ab_variant == "control"
        )
        if run_shadow_validation:
            decision["dms_shadow_executed"] = True
            self.routing_metrics["dms_shadow_attempted"] += 1
            shadow_response = self._call_model(dms_model, messages, temperature, timeout)
            decision["dms_shadow_model"] = dms_model.get("name", "dms")
            decision["dms_shadow_latency_seconds"] = float(
                shadow_response.get("latency", 0.0)
            )
            if shadow_response.get("success"):
                shadow_quality = self._score_response(
                    str(shadow_response.get("response", "")), context
                )
                decision["dms_shadow_success"] = True
                decision["dms_shadow_quality_score"] = shadow_quality
                self.routing_metrics["dms_shadow_successes"] += 1
                self.routing_metrics["dms_shadow_quality_sum"] += shadow_quality
                shadow_usage = self._coerce_usage_normalized(
                    shadow_response.get("usage_normalized")
                )
                if shadow_usage:
                    decision["dms_shadow_usage_normalized"] = shadow_usage
                if selected_usage and shadow_usage:
                    shadow_delta = self._usage_delta(shadow_usage, selected_usage)
                    if shadow_delta:
                        decision["dms_shadow_usage_delta"] = shadow_delta
                        self._record_shadow_usage_delta(shadow_delta)
            else:
                decision["dms_shadow_success"] = False
                decision["dms_shadow_error"] = str(
                    shadow_response.get("error") or "shadow_validation_failed"
                )
                self.routing_metrics["dms_shadow_failures"] += 1

        request_latency = time.time() - request_start
        metric_variant = ab_variant if should_prefer_dms else "disabled"
        quality_score = self._score_with_quality_hook(
            query=query,
            variant=metric_variant,
            response=final_response,
            context=context,
            decision=decision,
            fallback_quality_score=self._score_response(final_response, context),
        )
        selected_model = self._last_selected_model
        self._record_ab_metric(
            metric_variant,
            success=selected_model is not None,
            latency=request_latency,
            quality_score=quality_score,
        )
        self.last_decision = decision
        decision["quality_score"] = quality_score
        decision["request_latency_seconds"] = request_latency
        decision["dms_budget"] = self._dms_budget_status()

        self.save_metrics()

        return {
            "choices": [{"message": {"content": final_response}}],
            "metadata": decision,
        }

    def provide_feedback(self, model_name: str, rating: int, task_type: str = None):
        if self.learning_mode:
            if model_name not in self.model_metrics:
                self.model_metrics[model_name] = ModelMetrics()
            self.model_metrics[model_name].record_rating(rating)
            self.save_metrics()
            merlin_logger.info(f"Feedback recorded for {model_name}: {rating}/5")

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

        bucket_map = usage_metrics.get("by_prompt_bucket")
        if isinstance(bucket_map, dict):
            summarized_buckets: Dict[str, Any] = {}
            for key, value in bucket_map.items():
                if not isinstance(value, dict):
                    continue
                samples = int(value.get("samples", 0) or 0)
                row: Dict[str, Any] = dict(value)
                row["avg_prompt_tokens"] = _avg("prompt_tokens", samples, value)
                row["avg_completion_tokens"] = _avg("completion_tokens", samples, value)
                row["avg_total_tokens"] = _avg("total_tokens", samples, value)
                row["avg_cached_tokens"] = _avg("cached_tokens", samples, value)
                row["avg_reasoning_tokens"] = _avg("reasoning_tokens", samples, value)
                summarized_buckets[key] = row
            status["by_prompt_bucket"] = summarized_buckets
        else:
            status["by_prompt_bucket"] = {}

        shadow_samples = int(usage_metrics.get("shadow_delta_samples", 0) or 0)
        status["shadow_dms_minus_control_avg_prompt_tokens"] = _avg(
            "shadow_dms_minus_control_prompt_tokens_sum", shadow_samples, usage_metrics
        )
        status["shadow_dms_minus_control_avg_completion_tokens"] = _avg(
            "shadow_dms_minus_control_completion_tokens_sum", shadow_samples, usage_metrics
        )
        status["shadow_dms_minus_control_avg_total_tokens"] = _avg(
            "shadow_dms_minus_control_total_tokens_sum", shadow_samples, usage_metrics
        )
        status["shadow_dms_minus_control_avg_cached_tokens"] = _avg(
            "shadow_dms_minus_control_cached_tokens_sum", shadow_samples, usage_metrics
        )
        status["shadow_dms_minus_control_avg_reasoning_tokens"] = _avg(
            "shadow_dms_minus_control_reasoning_tokens_sum", shadow_samples, usage_metrics
        )

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

    def get_status(self) -> Dict:
        routing_metrics = dict(self.routing_metrics)
        if "ab_variants" in routing_metrics:
            routing_metrics["ab_variants"] = self._ab_status()
        if "usage_economics" in routing_metrics:
            routing_metrics["usage_economics"] = self._usage_economics_status()
        return {
            "strategy": self.strategy,
            "learning_mode": self.learning_mode,
            "min_samples": self.min_samples,
            "models": [
                {"name": m["name"], "backend": m["backend"]} for m in self.models
            ],
            "metrics": {
                name: {
                    "total_requests": m.total_requests,
                    "success_rate": m.success_rate,
                    "avg_latency": m.avg_latency,
                    "avg_rating": m.avg_rating,
                }
                for name, m in self.model_metrics.items()
            },
            "last_decision": self.last_decision,
            "routing_metrics": routing_metrics,
            "dms_error_budget": self._dms_budget_status(),
        }

    def health_check(self) -> Dict[str, bool]:
        results = {}
        for model in self.models:
            try:
                response = requests.get(
                    (
                        model["url"].replace("/chat/completions", "/tags")
                        if "/chat" in model["url"]
                        else model["url"]
                    ),
                    timeout=3,
                )
                results[model["name"]] = response.status_code == 200
            except:
                results[model["name"]] = False
        return results

    def reset_metrics(self, model_name: str = None):
        if model_name:
            if model_name in self.model_metrics:
                self.model_metrics[model_name] = ModelMetrics()
        else:
            self.model_metrics = {name: ModelMetrics() for name in self.model_metrics}
        self.save_metrics()


adaptive_llm_backend = AdaptiveLLMBackend()

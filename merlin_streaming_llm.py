# Streaming LLM Backend - Real-time Multi-Model Orchestration with Streaming
import os
import json
import time
import asyncio
from collections import deque
from typing import Any, Dict, List, Optional, AsyncGenerator, Iterable, Iterator
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import requests
from merlin_logger import merlin_logger
import merlin_settings as settings
from merlin_routing_contract import (
    apply_dms_fallback,
    as_non_negative_int,
    build_routing_decision,
    coerce_usage_normalized,
    enrich_error_with_rate_limit_headers,
    fallback_reason_counts_template,
    normalize_openai_usage_payload,
    resolve_query_prompt_bucket,
    select_dms_ab_variant,
    should_prefer_dms_route_from_settings,
)


@dataclass
class StreamingModelResponse:
    model_name: str
    response_generator: AsyncGenerator[str, None]
    latency: float
    success: bool
    error: Optional[str] = None
    usage_normalized: Optional[Dict[str, int]] = None


class StreamingLLMBackend:
    SSE_CONTROL_FIELDS = {"data", "event", "id", "retry"}
    SSE_ERROR_EVENTS = {"error", "response.error", "response.failed", "completion.error"}

    @staticmethod
    def _as_non_negative_int(value: Any) -> int:
        return as_non_negative_int(value)

    @classmethod
    def _normalize_stream_usage(cls, data: dict) -> Dict[str, int]:
        return normalize_openai_usage_payload(data)

    @classmethod
    def _coerce_usage_normalized(cls, usage: Any) -> Optional[dict[str, int]]:
        return coerce_usage_normalized(usage)

    @staticmethod
    def _merge_stream_usage_totals(
        target: Dict[str, int], usage: Dict[str, int]
    ) -> None:
        for key, value in usage.items():
            if not isinstance(value, int):
                continue
            if value <= 0 and key != "cached_tokens":
                continue
            existing = target.get(key)
            if not isinstance(existing, int):
                target[key] = value
                continue
            target[key] = max(existing, value)

    @staticmethod
    def _extract_openai_compatible_stream_chunk(data: dict) -> str:
        if not isinstance(data, dict):
            return str(data) if data else ""

        if "message" in data and isinstance(data.get("message"), dict):
            return str(data["message"].get("content", ""))

        if "text" in data and data.get("text") is not None:
            return str(data.get("text"))

        if "done" in data:
            return ""

        if "content" in data:
            content = data.get("content")
            return content if isinstance(content, str) else str(content or "")

        choices = data.get("choices", [])
        chunks: list[str] = []
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    delta_content = delta.get("content")
                else:
                    delta_content = delta
                if delta_content is not None:
                    chunks.append(str(delta_content))
        return "".join(chunks)

    @staticmethod
    def _decode_stream_line(line: bytes | str | None) -> str:
        if line is None:
            return ""
        if isinstance(line, bytes):
            return line.decode("utf-8", errors="replace")
        return str(line)

    @classmethod
    def _iter_sse_frames(
        cls, lines: Iterable[bytes | str]
    ) -> Iterator[tuple[str, str]]:
        data_lines: list[str] = []
        event_name = "message"
        for raw_line in lines:
            line = cls._decode_stream_line(raw_line)
            stripped = line.strip()

            if not stripped:
                if data_lines:
                    payload = "\n".join(data_lines).strip()
                    data_lines = []
                    if payload:
                        normalized_event = event_name.strip().lower() or "message"
                        yield (normalized_event, payload)
                event_name = "message"
                continue

            if stripped.startswith(":"):
                continue

            if stripped == "[DONE]":
                yield ("message", stripped)
                continue

            if stripped[0] in "[{":
                yield ("message", stripped)
                continue

            if ":" not in line:
                continue

            field, value = line.split(":", 1)
            field = field.strip().lower()
            if field not in cls.SSE_CONTROL_FIELDS:
                continue
            if field == "event":
                event_name = value.strip() or "message"
            if field == "data":
                data_lines.append(value.lstrip(" "))

        if data_lines:
            payload = "\n".join(data_lines).strip()
            if payload:
                normalized_event = event_name.strip().lower() or "message"
                yield (normalized_event, payload)

    @classmethod
    def _iter_sse_payloads(cls, lines: Iterable[bytes | str]) -> Iterator[str]:
        for _event_name, payload in cls._iter_sse_frames(lines):
            yield payload

    @classmethod
    def _is_sse_error_event(cls, event_name: str, data: Any) -> bool:
        normalized_event = str(event_name or "message").strip().lower()
        if normalized_event in cls.SSE_ERROR_EVENTS or normalized_event.endswith(
            ".error"
        ):
            return True

        if not isinstance(data, dict):
            return False

        if "error" in data:
            return True

        payload_type = data.get("type")
        if isinstance(payload_type, str) and "error" in payload_type.lower():
            return True

        return False

    @classmethod
    def _extract_stream_error_detail(
        cls, event_name: str, data: Any, payload_text: str
    ) -> str:
        parts: list[str] = []
        if isinstance(data, dict):
            raw_error = data.get("error")
            if isinstance(raw_error, dict):
                for key in ("status", "status_code", "code", "type", "message", "detail"):
                    value = raw_error.get(key)
                    if value is not None:
                        text = str(value).strip()
                        if text:
                            parts.append(text)
            elif isinstance(raw_error, str):
                text = raw_error.strip()
                if text:
                    parts.append(text)

            if not parts:
                for key in ("status", "status_code", "code", "type", "message", "detail"):
                    value = data.get(key)
                    if value is not None:
                        text = str(value).strip()
                        if text:
                            parts.append(text)

        detail = " ".join(dict.fromkeys(parts)).strip()
        if not detail:
            detail = str(payload_text).strip() or "request_failed"

        normalized_event = str(event_name or "message").strip().lower()
        if (
            normalized_event
            and normalized_event != "message"
            and normalized_event not in detail.lower()
        ):
            return f"{normalized_event}: {detail}"
        return detail

    @staticmethod
    def _extract_error_marker(chunk: str) -> str | None:
        text = str(chunk or "").strip()
        prefix = "[Error: "
        if text.startswith(prefix) and text.endswith("]"):
            detail = text[len(prefix) : -1].strip()
            return detail or "request_failed"
        return None

    def __init__(self):
        self.strategy = settings.PARALLEL_STRATEGY.lower()
        self.models = self._load_models()
        self.executor = ThreadPoolExecutor(max_workers=min(10, len(self.models) * 2))
        self._last_selected_model: Optional[str] = None
        self.dms_ab_enabled = settings.DMS_AB_ENABLED
        self.dms_ab_percentage = settings.DMS_AB_DMS_PERCENTAGE / 100
        self._request_timestamps = deque()
        self.last_decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket="short", router_backend="streaming"
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
            "stream_latency": {
                "requests": 0,
                "ttft_sum_seconds": 0.0,
                "completion_sum_seconds": 0.0,
                "ttft_samples": 0,
                "completion_samples": 0,
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
            f"Streaming LLM Backend: {len(self.models)} models, strategy: {self.strategy}"
        )

    def _prompt_size_bucket(self, query: str) -> str:
        prompt_bucket, _ = resolve_query_prompt_bucket(
            query,
            min_prompt_chars=settings.DMS_MIN_PROMPT_CHARS,
            token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
            min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
        )
        return prompt_bucket

    def _get_dms_model(self) -> Optional[Dict]:
        if not settings.DMS_ENABLED:
            return None
        for model in self.models:
            if model["name"] == "dms":
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

    def _select_ab_variant(
        self, should_prefer_dms: bool, assignment_key: str | None = None
    ) -> str:
        return select_dms_ab_variant(
            should_prefer_dms,
            dms_ab_enabled=self.dms_ab_enabled,
            dms_share_percentage=self.dms_ab_percentage,
            assignment_key=assignment_key,
        )

    def _record_usage_economics(
        self, prompt_bucket: str, variant: str, usage: Optional[dict[str, int]]
    ) -> None:
        normalized_usage = self._coerce_usage_normalized(usage)
        if not normalized_usage:
            return

        usage_metrics = self.routing_metrics.get("usage_economics")
        if not isinstance(usage_metrics, dict):
            return

        usage_metrics["selected_samples"] = (
            self._as_non_negative_int(usage_metrics.get("selected_samples")) + 1
        )
        usage_metrics["selected_prompt_tokens"] = self._as_non_negative_int(
            usage_metrics.get("selected_prompt_tokens")
        ) + self._as_non_negative_int(normalized_usage.get("prompt_tokens"))
        usage_metrics["selected_completion_tokens"] = self._as_non_negative_int(
            usage_metrics.get("selected_completion_tokens")
        ) + self._as_non_negative_int(normalized_usage.get("completion_tokens"))
        usage_metrics["selected_total_tokens"] = self._as_non_negative_int(
            usage_metrics.get("selected_total_tokens")
        ) + self._as_non_negative_int(normalized_usage.get("total_tokens"))
        usage_metrics["selected_cached_tokens"] = self._as_non_negative_int(
            usage_metrics.get("selected_cached_tokens")
        ) + self._as_non_negative_int(normalized_usage.get("cached_tokens"))
        usage_metrics["selected_reasoning_tokens"] = self._as_non_negative_int(
            usage_metrics.get("selected_reasoning_tokens")
        ) + self._as_non_negative_int(normalized_usage.get("reasoning_tokens"))

        bucket_key = (
            prompt_bucket if prompt_bucket in {"short", "medium", "long"} else "other"
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
            bucket_entry["samples"] = self._as_non_negative_int(
                bucket_entry.get("samples")
            ) + 1
            bucket_entry["prompt_tokens"] = self._as_non_negative_int(
                bucket_entry.get("prompt_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("prompt_tokens"))
            bucket_entry["completion_tokens"] = self._as_non_negative_int(
                bucket_entry.get("completion_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("completion_tokens"))
            bucket_entry["total_tokens"] = self._as_non_negative_int(
                bucket_entry.get("total_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("total_tokens"))
            bucket_entry["cached_tokens"] = self._as_non_negative_int(
                bucket_entry.get("cached_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("cached_tokens"))
            bucket_entry["reasoning_tokens"] = self._as_non_negative_int(
                bucket_entry.get("reasoning_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("reasoning_tokens"))

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
            variant_entry["samples"] = self._as_non_negative_int(
                variant_entry.get("samples")
            ) + 1
            variant_entry["prompt_tokens"] = self._as_non_negative_int(
                variant_entry.get("prompt_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("prompt_tokens"))
            variant_entry["completion_tokens"] = self._as_non_negative_int(
                variant_entry.get("completion_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("completion_tokens"))
            variant_entry["total_tokens"] = self._as_non_negative_int(
                variant_entry.get("total_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("total_tokens"))
            variant_entry["cached_tokens"] = self._as_non_negative_int(
                variant_entry.get("cached_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("cached_tokens"))
            variant_entry["reasoning_tokens"] = self._as_non_negative_int(
                variant_entry.get("reasoning_tokens")
            ) + self._as_non_negative_int(normalized_usage.get("reasoning_tokens"))

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

    def _record_stream_latency(
        self, *, ttft_seconds: float, completion_seconds: float
    ) -> None:
        latency_metrics = self.routing_metrics.setdefault(
            "stream_latency",
            {
                "requests": 0,
                "ttft_sum_seconds": 0.0,
                "completion_sum_seconds": 0.0,
                "ttft_samples": 0,
                "completion_samples": 0,
            },
        )
        latency_metrics["requests"] += 1
        latency_metrics["ttft_sum_seconds"] += max(0.0, float(ttft_seconds))
        latency_metrics["completion_sum_seconds"] += max(0.0, float(completion_seconds))
        latency_metrics["ttft_samples"] += 1
        latency_metrics["completion_samples"] += 1

    def _stream_latency_status(self) -> Dict[str, float]:
        latency_metrics = self.routing_metrics.get("stream_latency", {})
        requests = int(latency_metrics.get("requests", 0) or 0)
        ttft_sum = float(latency_metrics.get("ttft_sum_seconds", 0.0) or 0.0)
        completion_sum = float(
            latency_metrics.get("completion_sum_seconds", 0.0) or 0.0
        )
        ttft_samples = int(latency_metrics.get("ttft_samples", 0) or 0)
        completion_samples = int(latency_metrics.get("completion_samples", 0) or 0)
        return {
            "requests": requests,
            "ttft_samples": ttft_samples,
            "completion_samples": completion_samples,
            "avg_ttft_seconds": ttft_sum / ttft_samples if ttft_samples else 0.0,
            "avg_completion_seconds": (
                completion_sum / completion_samples if completion_samples else 0.0
            ),
        }

    def _usage_economics_status(self) -> Dict[str, Any]:
        usage_metrics = self.routing_metrics.get("usage_economics", {})
        if not isinstance(usage_metrics, dict):
            return {}

        def _avg(total_key: str, samples: int, source: dict[str, Any]) -> float:
            total = self._as_non_negative_int(source.get(total_key))
            return float(total / samples) if samples else 0.0

        status: Dict[str, Any] = dict(usage_metrics)
        selected_samples = self._as_non_negative_int(usage_metrics.get("selected_samples"))
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
                samples = self._as_non_negative_int(value.get("samples"))
                row: Dict[str, Any] = dict(value)
                row["avg_prompt_tokens"] = _avg("prompt_tokens", samples, value)
                row["avg_completion_tokens"] = _avg("completion_tokens", samples, value)
                row["avg_total_tokens"] = _avg("total_tokens", samples, value)
                row["avg_cached_tokens"] = _avg("cached_tokens", samples, value)
                row["avg_reasoning_tokens"] = _avg("reasoning_tokens", samples, value)
                summarized[key] = row

            status[map_key] = summarized

        return status

    def _load_models(self) -> List[Dict]:
        models = []

        if "mistral" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "mistral",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "mistral",
                }
            )

        if "nomic" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "nomic",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "nomic",
                }
            )

        if "llama3.2" in settings.OLLAMA_MODELS:
            models.append(
                {
                    "name": "llama3.2",
                    "backend": "ollama",
                    "url": settings.OLLAMA_URL,
                    "model": "llama3.2",
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

    async def _stream_model(
        self, model: Dict, messages: List[Dict], temperature: float
    ) -> StreamingModelResponse:
        start_time = time.time()

        try:
            payload = {"model": model["model"], "messages": messages, "stream": True}
            usage_normalized: Dict[str, int] = {}

            if temperature is not None and model["backend"] == "ollama":
                payload["options"] = {"temperature": temperature}
            elif temperature is not None:
                payload["temperature"] = temperature

            headers = {}
            if model.get("api_key"):
                headers["Authorization"] = f"Bearer {model['api_key']}"

            async def stream_generator():
                try:
                    response = requests.post(
                        model["url"],
                        json=payload,
                        headers=headers,
                        stream=True,
                        timeout=30,
                    )
                    response.raise_for_status()

                    for event_name, payload_text in self._iter_sse_frames(
                        response.iter_lines()
                    ):
                        if payload_text == "[DONE]":
                            break
                        try:
                            data = json.loads(payload_text)
                        except json.JSONDecodeError as exc:
                            if event_name in self.SSE_ERROR_EVENTS or event_name.endswith(
                                ".error"
                            ):
                                raise RuntimeError(
                                    f"{event_name}: JSONDecodeError: {payload_text}"
                                ) from exc
                            continue

                        if self._is_sse_error_event(event_name, data):
                            raise RuntimeError(
                                self._extract_stream_error_detail(
                                    event_name, data, payload_text
                                )
                            )

                        usage = self._normalize_stream_usage(data)
                        if usage:
                            self._merge_stream_usage_totals(usage_normalized, usage)

                        if model["backend"] == "ollama":
                            if "message" in data and isinstance(
                                data.get("message"), dict
                            ):
                                message = data["message"].get("content", "")
                                if message:
                                    yield str(message)
                            continue

                        chunk = self._extract_openai_compatible_stream_chunk(data)
                        if chunk:
                            yield chunk
                except Exception as e:
                    error_detail = enrich_error_with_rate_limit_headers(e)
                    merlin_logger.error(
                        f"Streaming error for {model['name']}: {error_detail}"
                    )
                    yield f"[Error: {error_detail}]"

            latency = time.time() - start_time

            return StreamingModelResponse(
                model_name=model["name"],
                response_generator=stream_generator(),
                latency=latency,
                success=True,
                usage_normalized=usage_normalized,
            )

        except Exception as e:
            latency = time.time() - start_time
            error_detail = enrich_error_with_rate_limit_headers(e)
            merlin_logger.error(f"Model {model['name']} failed: {error_detail}")

            async def error_generator():
                yield f"[Error: {error_detail}]"

            return StreamingModelResponse(
                model_name=model["name"],
                response_generator=error_generator(),
                latency=latency,
                success=False,
                error=error_detail,
                usage_normalized={},
            )

    def _score_chunk(self, chunk: str, query: str) -> float:
        scores = []

        length_score = min(1.0, len(chunk) / 50)
        scores.append(length_score)

        if "?" in query:
            has_answer = any(char in chunk for char in ["!", ".", ":"])
            scores.append(1.0 if has_answer else 0.5)
        else:
            scores.append(0.8)

        diversity_score = len(set(chunk.lower().split())) / max(1, len(chunk.split()))
        scores.append(diversity_score)

        return sum(scores) / len(scores)

    async def _voting_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            yield "All models failed to respond."
            return

        accumulated_responses = {}

        async def collect_responses():
            tasks = [
                asyncio.create_task(self._collect_full_response(r)) for r in successful
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            for i, task in enumerate(tasks):
                if not task.exception():
                    accumulated_responses[i] = task.result()

        await collect_responses()

        scored = [
            (i, self._score_response_text(accumulated_responses.get(i, ""), query))
            for i in range(len(successful))
        ]
        best_idx = max(scored, key=lambda x: x[1])[0]

        best_response = accumulated_responses.get(best_idx, "")
        self._last_selected_model = successful[best_idx].model_name
        merlin_logger.info(
            f"Streaming voting: Selected {successful[best_idx].model_name} (score: {scored[best_idx][1]:.2f})"
        )

        for word in best_response.split():
            yield word + " "
            await asyncio.sleep(0.01)

    async def _routing_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
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

        selected_model = "llama3.2"
        for category, keywords in routing_rules.items():
            if any(kw in query_lower for kw in keywords):
                selected_model = keywords[-1]
                break

        for response in responses:
            if response.success and response.model_name == selected_model:
                self._last_selected_model = response.model_name
                merlin_logger.info(f"Streaming routing: Selected {response.model_name}")
                async for chunk in response.response_generator:
                    yield chunk
                return

        for response in responses:
            if response.success:
                self._last_selected_model = response.model_name
                async for chunk in response.response_generator:
                    yield chunk
                return

        self._last_selected_model = None
        yield "No models available."

    async def _cascade_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            yield "All models failed to respond."
            return

        fastest = min(successful, key=lambda r: r.latency)

        if fastest.latency < 2.0:
            self._last_selected_model = fastest.model_name
            merlin_logger.info(f"Streaming cascade: {fastest.model_name} (fast)")
            async for chunk in fastest.response_generator:
                yield chunk

            yield "\n\n[Verifying with other models...]"
            await asyncio.sleep(0.5)
        else:
            best_quality = max(successful, key=lambda r: r.latency)
            self._last_selected_model = best_quality.model_name
            merlin_logger.info(f"Streaming cascade: {best_quality.model_name}")
            async for chunk in best_quality.response_generator:
                yield chunk

    async def _consensus_strategy_stream(
        self, query: str, responses: List[StreamingModelResponse]
    ) -> AsyncGenerator[str, None]:
        successful = [r for r in responses if r.success]
        if not successful:
            self._last_selected_model = None
            yield "All models failed to respond."
            return

        async def collect_all():
            tasks = [
                asyncio.create_task(self._collect_full_response(r)) for r in successful
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            all_responses = []
            for i, task in enumerate(tasks):
                if not task.exception():
                    all_responses.append(task.result())

            return all_responses

        responses_text = await collect_all()

        from collections import Counter

        words = []
        for resp in responses_text:
            words.extend(resp.lower().split())

        if not words:
            async for chunk in responses[0].response_generator:
                yield chunk
            return

        word_counts = Counter(words)
        common_words = [
            word
            for word, count in word_counts.most_common(20)
            if count >= len(successful) // 2
        ]

        if len(common_words) < 5:
            async for chunk in responses[0].response_generator:
                yield chunk
            return

        consensus = " ".join(common_words[:15])
        self._last_selected_model = "consensus"
        merlin_logger.info(f"Streaming consensus: Built from {len(successful)} models")
        yield f"Based on consensus analysis: {consensus}"

    async def _collect_full_response(self, response: StreamingModelResponse) -> str:
        chunks = []
        async for chunk in response.response_generator:
            chunks.append(chunk)
        return "".join(chunks)

    def _score_response_text(self, response: str, query: str) -> float:
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

    async def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        stream: bool = True,
        timeout: int = 30,
    ) -> AsyncGenerator[str, None]:
        if not stream:
            yield "Streaming not disabled in streaming backend."
            return

        query = messages[-1]["content"] if messages else ""
        self.routing_metrics["total_requests"] += 1
        self._last_selected_model = None
        prompt_bucket = self._prompt_size_bucket(query)
        decision: Dict[str, Any] = build_routing_decision(
            prompt_size_bucket=prompt_bucket,
            router_backend="streaming",
            query=query,
        )
        request_start = time.time()
        self._track_request_throughput()

        dms_model = self._get_dms_model()
        should_prefer_dms = dms_model is not None and self._should_prefer_dms(query)
        ab_variant = self._select_ab_variant(
            should_prefer_dms, assignment_key=query if query else None
        )
        decision["ab_variant"] = ab_variant
        include_dms_model = should_prefer_dms and ab_variant == "dms"
        skip_dms_in_fallback = not include_dms_model
        decision["dms_candidate"] = should_prefer_dms
        decision["dms_attempted"] = include_dms_model

        if include_dms_model:
            self.routing_metrics["dms_attempted"] += 1
            dms_response = await self._stream_model(dms_model, messages, temperature)
            if dms_response.success:
                self._last_selected_model = dms_response.model_name
                decision["selected_model"] = dms_response.model_name
                decision["dms_used"] = True
                self.routing_metrics["dms_selected"] += 1

                dms_chunks = []
                first_chunk_elapsed: float | None = None
                dms_stream_error: str | None = None
                async for chunk in dms_response.response_generator:
                    error_detail = self._extract_error_marker(chunk)
                    if error_detail is not None:
                        if not dms_chunks:
                            dms_stream_error = error_detail
                            break
                        merlin_logger.warning(
                            "DMS stream error after partial output; keeping partial response: %s",
                            error_detail,
                        )
                        break
                    dms_chunks.append(chunk)
                    if first_chunk_elapsed is None:
                        first_chunk_elapsed = time.time() - request_start
                    yield chunk

                if dms_stream_error is not None:
                    skip_dms_in_fallback = True
                    reason_code = apply_dms_fallback(
                        decision, dms_stream_error, stage="dms_stream"
                    )
                    self.routing_metrics["fallback_reason_counts"][reason_code] = (
                        self.routing_metrics["fallback_reason_counts"].get(reason_code, 0)
                        + 1
                    )
                    self.routing_metrics["dms_fallbacks"] += 1
                else:
                    final_response = "".join(dms_chunks)
                    request_latency = time.time() - request_start
                    stream_ttft = (
                        first_chunk_elapsed
                        if first_chunk_elapsed is not None
                        else request_latency
                    )
                    self._record_stream_latency(
                        ttft_seconds=stream_ttft, completion_seconds=request_latency
                    )
                    quality_score = self._score_response_text(final_response, query)
                    self._record_ab_metric(
                        "dms",
                        success=True,
                        latency=request_latency,
                        quality_score=quality_score,
                    )
                    decision["quality_score"] = quality_score
                    decision["request_latency_seconds"] = request_latency
                    decision["stream_ttft_seconds"] = stream_ttft
                    decision["stream_completion_seconds"] = request_latency
                    selected_usage = self._coerce_usage_normalized(
                        dms_response.usage_normalized
                    )
                    if selected_usage:
                        decision["stream_usage_normalized"] = dict(selected_usage)
                        self._record_usage_economics(prompt_bucket, "dms", selected_usage)
                    self.last_decision = decision
                    return

            else:
                skip_dms_in_fallback = True
                reason_code = apply_dms_fallback(
                    decision, dms_response.error, stage="dms_primary"
                )
                self.routing_metrics["fallback_reason_counts"][reason_code] = (
                    self.routing_metrics["fallback_reason_counts"].get(reason_code, 0)
                    + 1
                )
                self.routing_metrics["dms_fallbacks"] += 1

        strategies = {
            "voting": self._voting_strategy_stream,
            "routing": self._routing_strategy_stream,
            "cascade": self._cascade_strategy_stream,
            "consensus": self._consensus_strategy_stream,
        }

        strategy_func = strategies.get(self.strategy, self._voting_strategy_stream)

        stream_tasks = [
            asyncio.create_task(self._stream_model(model, messages, temperature))
            for model in self.models
            if not (skip_dms_in_fallback and model["name"] == "dms")
        ]

        completed_responses = []
        for future in asyncio.as_completed(stream_tasks):
            try:
                response = await future
                completed_responses.append(response)
            except Exception as e:
                merlin_logger.error(f"Stream execution error: {e}")

        collected_chunks = []
        first_chunk_elapsed: float | None = None
        async for chunk in strategy_func(query, completed_responses):
            collected_chunks.append(chunk)
            if first_chunk_elapsed is None:
                first_chunk_elapsed = time.time() - request_start
            yield chunk

        final_response = "".join(collected_chunks)
        request_latency = time.time() - request_start
        stream_ttft = (
            first_chunk_elapsed if first_chunk_elapsed is not None else request_latency
        )
        self._record_stream_latency(
            ttft_seconds=stream_ttft, completion_seconds=request_latency
        )
        decision["selected_model"] = self._last_selected_model
        decision["dms_used"] = self._last_selected_model == "dms"
        quality_score = self._score_response_text(final_response, query)
        self._record_ab_metric(
            ab_variant if should_prefer_dms else "disabled",
            success=bool(self._last_selected_model is not None),
            latency=request_latency,
            quality_score=quality_score,
        )
        decision["quality_score"] = quality_score
        decision["request_latency_seconds"] = request_latency
        decision["stream_ttft_seconds"] = stream_ttft
        decision["stream_completion_seconds"] = request_latency
        selected_usage: Optional[dict[str, int]] = None
        for response in completed_responses:
            if response.model_name == self._last_selected_model and response.usage_normalized:
                selected_usage = self._coerce_usage_normalized(response.usage_normalized)
                if selected_usage:
                    decision["stream_usage_normalized"] = dict(selected_usage)
                break
        metric_variant = ab_variant if should_prefer_dms else "disabled"
        if selected_usage:
            self._record_usage_economics(prompt_bucket, metric_variant, selected_usage)
        self.last_decision = decision

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

    def get_status(self) -> Dict:
        routing_metrics = dict(self.routing_metrics)
        if "ab_variants" in routing_metrics:
            routing_metrics["ab_variants"] = self._ab_status()
        if "usage_economics" in routing_metrics:
            routing_metrics["usage_economics"] = self._usage_economics_status()
        routing_metrics["stream_latency"] = self._stream_latency_status()
        return {
            "strategy": self.strategy,
            "models": [
                {"name": m["name"], "backend": m["backend"]} for m in self.models
            ],
            "health": self.health_check(),
            "last_decision": self.last_decision,
            "routing_metrics": routing_metrics,
        }


streaming_llm_backend = StreamingLLMBackend()

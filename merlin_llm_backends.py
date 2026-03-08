# Merlin LLM Backend Abstraction
import hashlib
import time
import uuid
from collections import OrderedDict, deque
import requests
from typing import Any
from merlin_logger import merlin_logger
import merlin_settings as settings
from merlin_utils import RetryBackoffPolicy, retry_with_backoff
from merlin_routing_contract import (
    estimate_prompt_tokens,
    extract_openai_compatible_content,
    normalize_openai_usage_payload,
    normalize_provider_chat_payload,
    preflight_prompt_messages,
    prompt_size_bucket,
)

_REQUEST_EXCEPTIONS = requests.exceptions
_DMS_MODEL_CAPABILITY_MATRIX: dict[str, dict[str, Any]] = {
    "nvidia/qwen3-8b-dms-8x": {
        "provider": "nvidia",
        "capability_tier": "reasoning_oracle",
        "provenance_source": "huggingface_model_card",
        "license_class": "non-commercial",
        "commercial_use_allowed": False,
    },
}


class LLMBackend:
    _dms_warmup_checked_unix: float | None

    @staticmethod
    def _build_dms_model_provenance(model_name: str) -> dict[str, Any]:
        normalized_model = str(model_name or "").strip()
        matrix_key = normalized_model.lower()
        matrix_profile = _DMS_MODEL_CAPABILITY_MATRIX.get(matrix_key)

        if isinstance(matrix_profile, dict):
            profile: dict[str, Any] = dict(matrix_profile)
            profile["matrix_match"] = True
        else:
            profile = {
                "provider": "unknown",
                "capability_tier": "unknown",
                "provenance_source": "unmapped",
                "license_class": "unknown",
                "commercial_use_allowed": True,
                "matrix_match": False,
            }

        profile["model"] = normalized_model
        license_class = str(profile.get("license_class", "")).strip().lower()
        non_commercial = (
            profile.get("commercial_use_allowed") is False
            or license_class in {"non-commercial", "research-only", "cc-by-nc"}
        )
        waiver_applied = bool(settings.DMS_NON_COMMERCIAL_MODEL_WAIVER and non_commercial)

        if (
            non_commercial
            and settings.DMS_MODEL_PROVENANCE_ENFORCEMENT
            and not waiver_applied
        ):
            policy_action = "block"
        elif non_commercial and not waiver_applied:
            policy_action = "warn"
        else:
            policy_action = "allow"

        profile["non_commercial"] = non_commercial
        profile["waiver_applied"] = waiver_applied
        profile["policy_action"] = policy_action
        return profile

    @staticmethod
    def _llm_retry_policy() -> RetryBackoffPolicy:
        initial_backoff_s = max(0.0, settings.MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS / 1000.0)
        max_backoff_s = max(0.0, settings.MERLIN_LLM_RETRY_MAX_BACKOFF_MS / 1000.0)
        retry_budget_s = max(0.0, settings.MERLIN_LLM_RETRY_BUDGET_MS / 1000.0)
        return RetryBackoffPolicy(
            max_attempts=settings.MERLIN_LLM_RETRY_MAX_ATTEMPTS,
            initial_backoff_seconds=initial_backoff_s,
            max_backoff_seconds=max_backoff_s,
            jitter_ratio=settings.MERLIN_LLM_RETRY_JITTER_RATIO,
            retry_budget_seconds=retry_budget_s,
        )

    @staticmethod
    def _is_retryable_request_error(error: Exception) -> bool:
        if isinstance(error, _REQUEST_EXCEPTIONS.Timeout):
            return True
        if isinstance(error, _REQUEST_EXCEPTIONS.ConnectionError):
            return True
        if isinstance(error, _REQUEST_EXCEPTIONS.HTTPError):
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
            if isinstance(status_code, int):
                return status_code in {429, 500, 502, 503, 504}
        return False

    def _post_json_with_retry(
        self,
        url: str,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: int | tuple[int, int],
        retry_max_attempts: int | None = None,
    ) -> requests.Response:
        def _operation():
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response

        if (
            not settings.MERLIN_LLM_RETRY_ENABLED
            or settings.MERLIN_LLM_RETRY_MAX_ATTEMPTS <= 1
        ):
            return _operation()

        policy = self._llm_retry_policy()
        if retry_max_attempts is not None:
            capped_attempts = min(policy.max_attempts, max(1, int(retry_max_attempts)))
            policy = RetryBackoffPolicy(
                max_attempts=capped_attempts,
                initial_backoff_seconds=policy.initial_backoff_seconds,
                max_backoff_seconds=policy.max_backoff_seconds,
                jitter_ratio=policy.jitter_ratio,
                retry_budget_seconds=policy.retry_budget_seconds,
            )
        if policy.max_attempts <= 1:
            return _operation()

        def _on_retry(next_attempt: int, delay: float, error: Exception) -> None:
            merlin_logger.warning(
                "LLM request transient failure; retrying %s attempt %s/%s in %.3fs: %s",
                url,
                next_attempt,
                policy.max_attempts,
                delay,
                error,
            )

        return retry_with_backoff(
            _operation,
            policy=policy,
            should_retry=self._is_retryable_request_error,
            on_retry=_on_retry,
        )

    @staticmethod
    def _dms_timeout_profile(timeout: int) -> int | tuple[int, int]:
        if not settings.DMS_TIMEOUT_SPLIT_ENABLED:
            return timeout
        connect_timeout = max(1, settings.DMS_CONNECT_TIMEOUT_S)
        read_timeout = max(
            1,
            timeout if isinstance(timeout, int) and timeout > 0 else settings.DMS_READ_TIMEOUT_S,
        )
        return (connect_timeout, read_timeout)

    @classmethod
    def _normalize_usage(cls, data: dict[str, Any]) -> dict[str, int]:
        return normalize_openai_usage_payload(
            data,
            require_usage_map=False,
            prompt_fallback_fields=("prompt_eval_count", "prompt_tokens"),
            completion_fallback_fields=("eval_count", "completion_tokens"),
            include_zero_fields=True,
        )

    @classmethod
    def _with_normalized_usage(cls, data: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_provider_chat_payload(data)
        payload["usage_normalized"] = cls._normalize_usage(data)
        return payload

    @staticmethod
    def _extract_openai_compatible_content(data: dict[str, Any]) -> str:
        return extract_openai_compatible_content(data)

    @staticmethod
    def _messages_to_prompt_text(messages: list[Any]) -> str:
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if content is None:
                continue
            parts.append(str(content))
        return "\n".join(parts)

    @classmethod
    def _build_dms_prompt_cache_key(cls, messages: list[Any]) -> str:
        prompt_text = cls._messages_to_prompt_text(messages)
        prefix = str(settings.DMS_PROMPT_CACHE_KEY_PREFIX).strip() or "merlin:dms"
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        return f"{prefix}:{prompt_hash}"

    @staticmethod
    def _messages_to_system_prompt_key(messages: list[Any]) -> tuple[str, ...]:
        parts: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            if str(message.get("role", "")).lower() != "system":
                continue
            content = message.get("content")
            if content is None:
                continue
            parts.append(str(content))
        return tuple(parts)

    def _cached_system_prompt_prefix(self, messages: list[Any]) -> str:
        key = self._messages_to_system_prompt_key(messages)
        if not key:
            return ""

        if not settings.MERLIN_SYSTEM_PROMPT_CACHE_ENABLED:
            return "\n\n".join(key)

        cached_value = self._system_prompt_cache.get(key)
        if isinstance(cached_value, str):
            self._system_prompt_cache.move_to_end(key)
            return cached_value

        prefix = "\n\n".join(key)
        self._system_prompt_cache[key] = prefix
        self._system_prompt_cache.move_to_end(key)
        max_entries = max(1, settings.MERLIN_SYSTEM_PROMPT_CACHE_MAX_ENTRIES)
        while len(self._system_prompt_cache) > max_entries:
            self._system_prompt_cache.popitem(last=False)
        return prefix

    def _build_cached_prefix_prompt(self, messages: list[Any]) -> str:
        prefix = self._cached_system_prompt_prefix(messages)
        content_lines: list[str] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            if str(message.get("role", "")).lower() == "system":
                continue
            content = message.get("content")
            if content is None:
                continue
            content_lines.append(str(content))

        content_text = "\n".join(content_lines).strip()
        if prefix and content_text:
            return f"{prefix}\n\n{content_text}"
        if prefix:
            return prefix
        return content_text

    def _prompt_size_bucket(self, messages: list[Any]) -> str:
        prompt_text = self._messages_to_prompt_text(messages)
        prompt_tokens = (
            estimate_prompt_tokens(prompt_text)
            if settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE
            else None
        )
        return prompt_size_bucket(
            len(prompt_text),
            settings.DMS_MIN_PROMPT_CHARS,
            token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
            prompt_tokens=prompt_tokens,
            min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
        )

    @staticmethod
    def _merge_prompt_preflight_metadata(
        response_payload: dict[str, Any], prompt_preflight: dict[str, Any]
    ) -> dict[str, Any]:
        payload = dict(response_payload)
        payload["prompt_preflight"] = dict(prompt_preflight)
        warnings = prompt_preflight.get("warnings")
        if isinstance(warnings, list) and warnings:
            existing_warnings = payload.get("warnings")
            merged_warnings = (
                list(existing_warnings)
                if isinstance(existing_warnings, list)
                else []
            )
            for warning in warnings:
                if warning not in merged_warnings:
                    merged_warnings.append(warning)
            payload["warnings"] = merged_warnings
        return payload

    def _timeout_from_matrix(self, prompt_bucket: str) -> int:
        timeout_matrix = settings.MERLIN_MODEL_TIMEOUT_MATRIX
        backend_key = self.backend.lower()
        backend_profile = timeout_matrix.get(backend_key)
        if not isinstance(backend_profile, dict):
            backend_profile = {}
        timeout_value = backend_profile.get(prompt_bucket)
        if isinstance(timeout_value, int) and timeout_value > 0:
            return timeout_value

        default_profile = timeout_matrix.get("default")
        if isinstance(default_profile, dict):
            timeout_value = default_profile.get(prompt_bucket)
            if isinstance(timeout_value, int) and timeout_value > 0:
                return timeout_value

        if prompt_bucket == "short":
            return settings.MERLIN_MODEL_TIMEOUT_SHORT_S
        if prompt_bucket == "long":
            return settings.MERLIN_MODEL_TIMEOUT_LONG_S
        return settings.MERLIN_MODEL_TIMEOUT_MEDIUM_S

    def _resolve_timeout(self, messages: list[Any], timeout: int | None) -> int:
        if isinstance(timeout, int) and timeout > 0:
            return timeout
        prompt_bucket = self._prompt_size_bucket(messages)
        return self._timeout_from_matrix(prompt_bucket)

    @staticmethod
    def _dms_timeout_for_prompt_bucket(prompt_bucket: str) -> int:
        if prompt_bucket == "short":
            return settings.DMS_TIMEOUT_SHORT_S
        if prompt_bucket == "long":
            return settings.DMS_TIMEOUT_LONG_S
        return settings.DMS_TIMEOUT_MEDIUM_S

    def _consume_dms_rate_limit_slot(self) -> bool:
        if not settings.DMS_REQUEST_RATE_LIMIT_ENABLED:
            return True

        per_minute = max(1, int(settings.DMS_REQUEST_RATE_LIMIT_PER_MINUTE))
        now = time.time()
        cutoff = now - 60.0
        while self._dms_request_timestamps and self._dms_request_timestamps[0] < cutoff:
            self._dms_request_timestamps.popleft()

        if len(self._dms_request_timestamps) >= per_minute:
            return False

        self._dms_request_timestamps.append(now)
        return True

    def _dms_warmup_payload(self) -> dict[str, Any]:
        return {
            "model": settings.DMS_MODEL,
            "messages": [{"role": "system", "content": settings.DMS_WARMUP_PROMPT}],
            "temperature": 0.0,
            "stream": False,
            "max_tokens": 1,
        }

    def _ensure_dms_warmup(self, *, force: bool = False) -> bool:
        if not settings.DMS_ENABLED:
            self._dms_warmup_checked = False
            self._dms_warmup_ready = False
            self._dms_warmup_detail = "dms_disabled"
            return False

        if self._dms_provenance_blocked:
            self._dms_warmup_checked = True
            self._dms_warmup_ready = False
            self._dms_warmup_detail = "provenance_blocked"
            return False

        if not settings.DMS_WARMUP_ENABLED:
            self._dms_warmup_checked = False
            self._dms_warmup_ready = True
            self._dms_warmup_detail = "warmup_disabled"
            return True

        if self._dms_warmup_checked and not force:
            return self._dms_warmup_ready

        headers = {}
        if settings.DMS_API_KEY:
            headers["Authorization"] = f"Bearer {settings.DMS_API_KEY}"

        self._dms_warmup_checked = True
        self._dms_warmup_checked_unix = time.time()
        try:
            self._post_json_with_retry(
                settings.DMS_URL,
                payload=self._dms_warmup_payload(),
                headers=headers,
                timeout=self._dms_timeout_profile(settings.DMS_WARMUP_TIMEOUT_S),
                retry_max_attempts=settings.DMS_RETRY_MAX_ATTEMPTS,
            )
            self._dms_warmup_ready = True
            self._dms_warmup_detail = "warmup_ok"
            return True
        except Exception as e:
            self._dms_warmup_ready = False
            self._dms_warmup_detail = f"warmup_failed: {e}"
            merlin_logger.warning("DMS warmup probe failed: %s", e)
            return False

    def get_dms_readiness(self) -> dict[str, Any]:
        if (
            settings.DMS_ENABLED
            and settings.DMS_WARMUP_ENABLED
            and not self._dms_warmup_checked
        ):
            self._ensure_dms_warmup()
        return {
            "dms_enabled": settings.DMS_ENABLED,
            "warmup_enabled": settings.DMS_WARMUP_ENABLED,
            "ready": self._dms_warmup_ready,
            "checked": self._dms_warmup_checked,
            "last_checked_unix": self._dms_warmup_checked_unix,
            "detail": self._dms_warmup_detail,
            "model_provenance": dict(self._dms_model_provenance),
        }

    def __init__(self) -> None:
        self.backend = settings.LLM_BACKEND.lower()
        self._system_prompt_cache: OrderedDict[tuple[str, ...], str] = OrderedDict()
        self._dms_request_timestamps: deque[float] = deque()
        self._dms_model_provenance = self._build_dms_model_provenance(settings.DMS_MODEL)
        self._dms_provenance_blocked = (
            settings.DMS_ENABLED
            and self._dms_model_provenance.get("policy_action") == "block"
        )
        self._dms_warmup_checked = False
        self._dms_warmup_ready = not settings.DMS_ENABLED
        if not settings.DMS_ENABLED:
            self._dms_warmup_detail = "dms_disabled"
        elif self._dms_provenance_blocked:
            self._dms_warmup_detail = "provenance_blocked"
        else:
            self._dms_warmup_detail = "warmup_not_checked"
        self._dms_warmup_checked_unix = None
        if settings.DMS_ENABLED and self._dms_model_provenance.get(
            "policy_action"
        ) in {"warn", "block"}:
            merlin_logger.warning(
                "DMS model provenance policy_action=%s model=%s license_class=%s waiver=%s",
                self._dms_model_provenance.get("policy_action"),
                self._dms_model_provenance.get("model"),
                self._dms_model_provenance.get("license_class"),
                self._dms_model_provenance.get("waiver_applied"),
            )
        if (
            self.backend == "dms"
            and settings.DMS_ENABLED
            and settings.DMS_WARMUP_ENABLED
            and not self._dms_provenance_blocked
        ):
            self._ensure_dms_warmup(force=True)
        merlin_logger.info(f"LLM Backend initialized: {self.backend}")

    def chat_completion(
        self,
        messages: list[Any],
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        prepared_messages, prompt_preflight = preflight_prompt_messages(
            messages,
            token_limit=settings.MERLIN_PROMPT_TOKEN_SOFT_LIMIT,
            truncate_target_tokens=settings.MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET,
            near_limit_ratio=settings.MERLIN_PROMPT_NEAR_LIMIT_RATIO,
        )
        timeout_was_explicit = isinstance(timeout, int) and timeout > 0
        resolved_timeout = self._resolve_timeout(prepared_messages, timeout)
        if self.backend == "ollama":
            response = self._ollama_chat(
                prepared_messages, temperature, stream, resolved_timeout
            )
            return self._merge_prompt_preflight_metadata(response, prompt_preflight)
        elif self.backend == "openai":
            response = self._openai_chat(
                prepared_messages, temperature, stream, resolved_timeout
            )
            return self._merge_prompt_preflight_metadata(response, prompt_preflight)
        elif self.backend == "huggingface":
            response = self._huggingface_chat(
                prepared_messages, temperature, stream, resolved_timeout
            )
            return self._merge_prompt_preflight_metadata(response, prompt_preflight)
        elif self.backend == "dms":
            response = self._dms_chat(
                prepared_messages,
                temperature,
                stream,
                resolved_timeout,
                allow_prompt_bucket_timeout_override=not timeout_was_explicit,
            )
            return self._merge_prompt_preflight_metadata(response, prompt_preflight)
        else:  # lmstudio (default)
            response = self._lmstudio_chat(
                prepared_messages, temperature, stream, resolved_timeout
            )
            return self._merge_prompt_preflight_metadata(response, prompt_preflight)

    def _lmstudio_chat(
        self, messages: list[Any], temperature: float, stream: bool, timeout: int
    ) -> dict[str, Any]:
        try:
            payload = {
                "model": settings.OPENAI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            response = self._post_json_with_retry(
                settings.LM_STUDIO_URL,
                payload=payload,
                timeout=timeout,
            )
            return self._with_normalized_usage(response.json())
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"LM Studio request failed: {e}")
            raise

    def _ollama_chat(
        self, messages: list[Any], temperature: float, stream: bool, timeout: int
    ) -> dict[str, Any]:
        try:
            default_model = (
                settings.OLLAMA_MODELS[0] if settings.OLLAMA_MODELS else "llama3.2"
            )
            payload = {"model": default_model, "messages": messages, "stream": stream}
            if temperature is not None:
                payload["options"] = {"temperature": temperature}
            response = self._post_json_with_retry(
                settings.OLLAMA_URL,
                payload=payload,
                timeout=timeout,
            )
            data = response.json()
            return self._with_normalized_usage(data)
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"Ollama request failed: {e}")
            raise

    def _openai_chat(
        self, messages: list[Any], temperature: float, stream: bool, timeout: int
    ) -> dict[str, Any]:
        try:
            payload = {
                "model": settings.OPENAI_MODEL,
                "messages": messages,
                "temperature": temperature,
                "stream": stream,
            }
            headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            response = self._post_json_with_retry(
                settings.OPENAI_URL,
                payload=payload,
                headers=headers,
                timeout=timeout,
            )
            return self._with_normalized_usage(response.json())
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"OpenAI request failed: {e}")
            raise

    def _huggingface_chat(
        self, messages: list[Any], temperature: float, stream: bool, timeout: int
    ) -> dict[str, Any]:
        try:
            prompt_text = self._build_cached_prefix_prompt(messages)
            payload = {
                "inputs": prompt_text,
                "parameters": {"temperature": temperature, "max_new_tokens": 500},
            }
            headers = {"Authorization": f"Bearer {settings.HF_API_KEY}"}
            response = self._post_json_with_retry(
                settings.HF_API_URL,
                payload=payload,
                headers=headers,
                timeout=timeout,
            )
            data = response.json()
            return self._with_normalized_usage(data)
        except requests.exceptions.RequestException as e:
            merlin_logger.error(f"HuggingFace request failed: {e}")
            raise

    def _dms_chat(
        self,
        messages: list[Any],
        temperature: float,
        stream: bool,
        timeout: int,
        *,
        allow_prompt_bucket_timeout_override: bool = True,
    ) -> dict[str, Any]:
        if not settings.DMS_ENABLED:
            merlin_logger.warning(
                "DMS backend selected but DMS_ENABLED is false; falling back to LM Studio."
            )
            return self._lmstudio_chat(messages, temperature, stream, timeout)
        if self._dms_provenance_blocked:
            merlin_logger.warning(
                "DMS model provenance policy blocks model %s; falling back to LM Studio.",
                settings.DMS_MODEL,
            )
            return self._lmstudio_chat(messages, temperature, stream, timeout)
        if not self._ensure_dms_warmup():
            merlin_logger.warning(
                "DMS warmup readiness is false; falling back to LM Studio."
            )
            return self._lmstudio_chat(messages, temperature, stream, timeout)
        if not self._consume_dms_rate_limit_slot():
            merlin_logger.warning(
                "DMS request cap exceeded (%s/min); falling back to LM Studio.",
                settings.DMS_REQUEST_RATE_LIMIT_PER_MINUTE,
            )
            return self._lmstudio_chat(messages, temperature, stream, timeout)

        payload = {
            "model": settings.DMS_MODEL,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if settings.DMS_REASONING_EFFORT:
            payload["reasoning_effort"] = settings.DMS_REASONING_EFFORT
        if settings.DMS_PROMPT_CACHE_KEY_ENABLED:
            payload["prompt_cache_key"] = self._build_dms_prompt_cache_key(messages)
        headers = {}
        if settings.DMS_API_KEY:
            headers["Authorization"] = f"Bearer {settings.DMS_API_KEY}"
        if settings.DMS_TRACE_HEADER_ENABLED:
            header_name = (
                str(settings.DMS_TRACE_HEADER_NAME).strip() or "X-Merlin-Request-Id"
            )
            headers[header_name] = uuid.uuid4().hex
        effective_timeout = timeout
        if (
            allow_prompt_bucket_timeout_override
            and settings.DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED
        ):
            prompt_bucket = self._prompt_size_bucket(messages)
            effective_timeout = self._dms_timeout_for_prompt_bucket(prompt_bucket)

        try:
            response = self._post_json_with_retry(
                settings.DMS_URL,
                payload=payload,
                headers=headers,
                timeout=self._dms_timeout_profile(effective_timeout),
                retry_max_attempts=settings.DMS_RETRY_MAX_ATTEMPTS,
            )
            data = response.json()
            return self._with_normalized_usage(data)
        except Exception as e:
            merlin_logger.warning(f"DMS request failed, falling back to LM Studio: {e}")
            return self._lmstudio_chat(messages, temperature, stream, timeout)

    def health_check(self) -> bool:
        try:
            if self.backend == "ollama":
                response = requests.get(
                    settings.OLLAMA_URL.replace("/api/chat", "/api/tags"), timeout=5
                )
            elif self.backend == "lmstudio":
                response = requests.get(
                    settings.LM_STUDIO_URL.replace("/chat/completions", "/models"),
                    timeout=5,
                )
            elif self.backend == "openai":
                response = requests.get(
                    settings.OPENAI_URL.replace("/chat/completions", "/models"),
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    timeout=5,
                )
            elif self.backend == "huggingface":
                if not settings.HF_API_KEY:
                    return False
                response = requests.get(
                    "https://api-inference.huggingface.co/models",
                    headers={"Authorization": f"Bearer {settings.HF_API_KEY}"},
                    timeout=5,
                )
            elif self.backend == "dms":
                if not settings.DMS_ENABLED:
                    return False
                health_url = settings.DMS_URL.replace("/chat/completions", "/models")
                headers = {}
                if settings.DMS_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.DMS_API_KEY}"
                response = requests.get(health_url, headers=headers, timeout=5)
            else:
                return False
            return response.status_code == 200
        except Exception as e:
            merlin_logger.warning(f"Health check failed for {self.backend}: {e}")
            return False


llm_backend = LLMBackend()

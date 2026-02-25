from __future__ import annotations

from enum import StrEnum
import hashlib
import random
from typing import Any, Iterable, Mapping

import merlin_settings as settings

ROUTER_POLICY_VERSION = "cp2-2026-02-15"
ROUTING_TELEMETRY_SCHEMA_VERSION = "1.0.0"
ROUTING_TRACE_SCHEME = "sha256-v1"
MATURITY_TIERS = frozenset({"M0", "M1", "M2", "M3", "M4"})
DEFAULT_MATURITY_TIER = "M0"
DEFAULT_MATURITY_POLICY_VERSION = "mdmm-2026-02-22"

class RoutingFallbackReasonCode(StrEnum):
    DMS_AUTH_ERROR = "dms_auth_error"
    DMS_DISABLED = "dms_disabled"
    DMS_ERROR = "dms_error"
    DMS_HTTP_5XX = "dms_http_5xx"
    DMS_PARSE_ERROR = "dms_parse_error"
    DMS_RATE_LIMITED = "dms_rate_limited"
    DMS_TIMEOUT = "dms_timeout"
    DMS_TRANSPORT_ERROR = "dms_transport_error"


FALLBACK_REASON_CODES = frozenset(code.value for code in RoutingFallbackReasonCode)
RETRYABLE_FALLBACK_CODES = frozenset(
    {
        RoutingFallbackReasonCode.DMS_TIMEOUT.value,
        RoutingFallbackReasonCode.DMS_TRANSPORT_ERROR.value,
        RoutingFallbackReasonCode.DMS_RATE_LIMITED.value,
        RoutingFallbackReasonCode.DMS_HTTP_5XX.value,
    }
)

RATE_LIMIT_SIGNAL_HEADER_KEYS: tuple[str, ...] = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "retry-after",
)

ROUTING_DECISION_FIELDS = (
    "selected_model",
    "prompt_size_bucket",
    "dms_used",
    "dms_candidate",
    "dms_attempted",
    "fallback_reason",
    "fallback_reason_code",
    "fallback_detail",
    "fallback_stage",
    "fallback_retryable",
    "ab_variant",
    "router_backend",
    "router_policy_version",
    "router_rule_version",
    "routing_telemetry_schema",
    "maturity_tier",
    "maturity_policy_version",
    "routing_trace_id",
    "routing_trace_fingerprint",
    "routing_trace_scheme",
)

ROUTING_REASONING_KEYWORDS: dict[str, tuple[str, ...]] = {
    "analysis": ("analyze", "compare", "evaluate", "assess", "review", "reason"),
    "code": ("code", "debug", "implement", "function", "algorithm"),
    "planning": ("plan", "roadmap", "steps", "schedule", "strategy"),
}

ROUTING_HIGH_COMPLEXITY_MARKERS: tuple[str, ...] = (
    "complex",
    "detailed",
    "thorough",
    "comprehensive",
    "advanced",
    "multi-step",
)

ROUTING_UNCERTAINTY_MARKERS: tuple[str, ...] = (
    "uncertain",
    "not sure",
    "unknown",
    "ambiguous",
    "trade-off",
    "tradeoff",
    "probability",
    "confidence",
    "assumption",
    "hypothesis",
    "risk",
)

ROUTING_REASONING_QUESTION_MARKERS: tuple[str, ...] = (
    "why",
    "how",
    "what if",
    "explain",
    "analyze",
    "evaluate",
)
ROUTING_UNCERTAINTY_COMPARE_EPSILON = 1e-9

PROMPT_WARNING_NEAR_TOKEN_LIMIT = "prompt_near_token_limit"
PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT = "prompt_truncated_for_token_limit"


def _normalize_trace_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _build_routing_trace(
    query: str,
    *,
    router_backend: str,
    prompt_size_bucket: str,
) -> dict[str, str]:
    normalized_query = _normalize_trace_query(query)
    trace_seed = f"{router_backend}|{prompt_size_bucket}|{normalized_query}"
    trace_fingerprint = hashlib.sha256(trace_seed.encode("utf-8")).hexdigest()
    return {
        "routing_trace_id": f"rt_{trace_fingerprint[:16]}",
        "routing_trace_fingerprint": trace_fingerprint,
        "routing_trace_scheme": ROUTING_TRACE_SCHEME,
    }


def _coerce_maturity_tier(value: object | None) -> str:
    if value is None:
        return DEFAULT_MATURITY_TIER
    candidate = str(value).strip().upper()
    if candidate in MATURITY_TIERS:
        return candidate
    return DEFAULT_MATURITY_TIER


def _coerce_maturity_policy_version(value: object | None) -> str:
    if value is None:
        return DEFAULT_MATURITY_POLICY_VERSION
    candidate = str(value).strip()
    return candidate or DEFAULT_MATURITY_POLICY_VERSION


def build_routing_decision(
    prompt_size_bucket: str, router_backend: str, *, query: str = ""
) -> dict[str, Any]:
    maturity_tier = _coerce_maturity_tier(
        getattr(settings, "MERLIN_MATURITY_TIER", DEFAULT_MATURITY_TIER)
    )
    maturity_policy_version = _coerce_maturity_policy_version(
        getattr(
            settings,
            "MERLIN_MATURITY_POLICY_VERSION",
            DEFAULT_MATURITY_POLICY_VERSION,
        )
    )
    decision = {
        "selected_model": None,
        "prompt_size_bucket": prompt_size_bucket,
        "dms_used": False,
        "dms_candidate": False,
        "dms_attempted": False,
        "fallback_reason": None,
        "fallback_reason_code": None,
        "fallback_detail": None,
        "fallback_stage": None,
        "fallback_retryable": None,
        "ab_variant": "disabled",
        "router_backend": router_backend,
        "router_policy_version": ROUTER_POLICY_VERSION,
        "router_rule_version": ROUTER_POLICY_VERSION,
        "routing_telemetry_schema": ROUTING_TELEMETRY_SCHEMA_VERSION,
        "maturity_tier": maturity_tier,
        "maturity_policy_version": maturity_policy_version,
    }
    decision.update(
        _build_routing_trace(
            query,
            router_backend=router_backend,
            prompt_size_bucket=prompt_size_bucket,
        )
    )
    return decision


def _normalize_error_detail(error: object | None) -> str:
    if error is None:
        return "request_failed"
    detail = str(error).strip()
    return detail if detail else "request_failed"


def enrich_error_with_rate_limit_headers(error: object | None) -> str:
    detail = _normalize_error_detail(error)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return detail

    normalized_headers: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key).strip().lower()
        value_text = str(value).strip()
        if not key_text or not value_text:
            continue
        normalized_headers[key_text] = value_text

    header_parts = []
    for header_key in RATE_LIMIT_SIGNAL_HEADER_KEYS:
        if header_key in normalized_headers:
            header_parts.append(f"{header_key}={normalized_headers[header_key]}")

    if not header_parts:
        return detail

    return f"{detail} | rate_limit_headers: {', '.join(header_parts)}"


def as_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def normalize_openai_usage_payload(
    data: Any,
    *,
    require_usage_map: bool = True,
    prompt_fallback_fields: Iterable[str] = ("prompt_tokens",),
    completion_fallback_fields: Iterable[str] = ("completion_tokens",),
    include_zero_fields: bool = False,
) -> dict[str, int]:
    if not isinstance(data, Mapping):
        if not include_zero_fields:
            return {}
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

    usage = data.get("usage")
    usage_map = usage if isinstance(usage, Mapping) else {}
    if require_usage_map and not usage_map:
        if not include_zero_fields:
            return {}
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

    prompt_fallback_value = None
    for field in prompt_fallback_fields:
        value = data.get(field)
        if value is not None:
            prompt_fallback_value = value
            break

    completion_fallback_value = None
    for field in completion_fallback_fields:
        value = data.get(field)
        if value is not None:
            completion_fallback_value = value
            break

    prompt_tokens = as_non_negative_int(
        usage_map.get("prompt_tokens")
        or usage_map.get("input_tokens")
        or prompt_fallback_value
    )
    completion_tokens = as_non_negative_int(
        usage_map.get("completion_tokens")
        or usage_map.get("output_tokens")
        or completion_fallback_value
    )
    total_tokens = as_non_negative_int(
        usage_map.get("total_tokens")
        or data.get("total_tokens")
        or (prompt_tokens + completion_tokens)
    )

    prompt_details = usage_map.get("prompt_tokens_details")
    cached_detail_tokens = (
        prompt_details.get("cached_tokens") if isinstance(prompt_details, Mapping) else None
    )
    completion_details = usage_map.get("completion_tokens_details")
    reasoning_detail_tokens = (
        completion_details.get("reasoning_tokens")
        if isinstance(completion_details, Mapping)
        else None
    )

    cached_tokens = as_non_negative_int(
        usage_map.get("cached_tokens")
        or cached_detail_tokens
        or usage_map.get("cache_read_input_tokens")
        or data.get("cache_read_input_tokens")
    )
    reasoning_tokens = as_non_negative_int(
        usage_map.get("reasoning_tokens")
        or reasoning_detail_tokens
        or data.get("reasoning_tokens")
    )

    if (
        prompt_tokens <= 0
        and completion_tokens <= 0
        and total_tokens <= 0
        and cached_tokens <= 0
        and reasoning_tokens <= 0
    ):
        if not include_zero_fields:
            return {}
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

    normalized: dict[str, int] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
    }
    if reasoning_tokens > 0:
        normalized["reasoning_tokens"] = reasoning_tokens
    return normalized


def coerce_usage_normalized(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, Mapping):
        return None

    prompt_tokens = as_non_negative_int(usage.get("prompt_tokens"))
    completion_tokens = as_non_negative_int(usage.get("completion_tokens"))
    total_tokens = as_non_negative_int(
        usage.get("total_tokens") or (prompt_tokens + completion_tokens)
    )
    cached_tokens = as_non_negative_int(usage.get("cached_tokens"))
    reasoning_tokens = as_non_negative_int(usage.get("reasoning_tokens"))

    if (
        prompt_tokens <= 0
        and completion_tokens <= 0
        and total_tokens <= 0
        and cached_tokens <= 0
        and reasoning_tokens <= 0
    ):
        return None

    normalized: dict[str, int] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
    }
    if reasoning_tokens > 0:
        normalized["reasoning_tokens"] = reasoning_tokens
    return normalized


def extract_openai_compatible_content(data: Any) -> str:
    if not isinstance(data, Mapping):
        return str(data)

    message = data.get("message")
    if isinstance(message, Mapping):
        message_content = message.get("content")
        return str(message_content) if message_content is not None else ""

    if "text" in data and data.get("text") is not None:
        return str(data.get("text"))

    if "content" in data and data.get("content") is not None:
        return str(data.get("content"))

    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if isinstance(first_choice, Mapping):
        choice_message = first_choice.get("message")
        if isinstance(choice_message, Mapping):
            choice_content = choice_message.get("content")
            return str(choice_content) if choice_content is not None else ""

        choice_text = first_choice.get("text")
        if choice_text is not None:
            return str(choice_text)

        if choice_message is not None:
            return str(choice_message)

    return ""


def _extract_provider_content(payload: Any) -> str:
    if isinstance(payload, Mapping):
        message = payload.get("message")
        if isinstance(message, Mapping):
            message_content = message.get("content")
            if message_content is not None:
                return str(message_content)

        top_level_content = payload.get("content")
        if top_level_content is not None:
            return str(top_level_content)

        top_level_text = payload.get("text")
        if top_level_text is not None:
            return str(top_level_text)

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                choice_message = first_choice.get("message")
                if isinstance(choice_message, Mapping):
                    choice_content = choice_message.get("content")
                    if choice_content is not None:
                        return str(choice_content)
                choice_text = first_choice.get("text")
                if choice_text is not None:
                    return str(choice_text)

    if isinstance(payload, list) and payload:
        first_item = payload[0]
        if isinstance(first_item, Mapping):
            generated_text = first_item.get("generated_text")
            if generated_text is not None:
                return str(generated_text)
            top_level_content = first_item.get("content")
            if top_level_content is not None:
                return str(top_level_content)
            top_level_text = first_item.get("text")
            if top_level_text is not None:
                return str(top_level_text)

    if payload is None:
        return ""
    return str(payload)


def _provider_payload_shape(payload: Any) -> str:
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                if isinstance(first_choice.get("message"), Mapping):
                    return "choices_message"
                if first_choice.get("text") is not None:
                    return "choices_text"
            return "choices_other"
        if isinstance(payload.get("message"), Mapping):
            return "top_level_message"
        if payload.get("content") is not None:
            return "top_level_content"
        if payload.get("text") is not None:
            return "top_level_text"
        return "mapping_other"
    if isinstance(payload, list):
        if payload and isinstance(payload[0], Mapping):
            if payload[0].get("generated_text") is not None:
                return "list_generated_text"
            return "list_mapping_other"
        return "list_other"
    return "scalar_other"


def normalize_provider_chat_payload(payload: Any) -> dict[str, Any]:
    normalized_payload: dict[str, Any] = (
        dict(payload) if isinstance(payload, Mapping) else {}
    )
    choices = normalized_payload.get("choices")
    shape = _provider_payload_shape(payload)

    if (
        isinstance(choices, list)
        and choices
        and isinstance(choices[0], Mapping)
        and isinstance(choices[0].get("message"), Mapping)
        and choices[0]["message"].get("content") is not None
    ):
        normalized_choices = list(choices)
        first_choice = dict(normalized_choices[0])
        first_message = dict(first_choice.get("message", {}))
        first_message["content"] = str(first_message.get("content"))
        first_choice["message"] = first_message
        normalized_choices[0] = first_choice
        normalized_payload["choices"] = normalized_choices
        normalized_payload["provider_payload_normalized"] = False
    else:
        normalized_payload["choices"] = [
            {"message": {"content": _extract_provider_content(payload)}}
        ]
        normalized_payload["provider_payload_normalized"] = True

    normalized_payload["provider_payload_shape"] = shape
    return normalized_payload


def deterministic_source_id(source_path: str) -> str:
    normalized = source_path.strip().replace("\\", "/").lower()
    if not normalized:
        normalized = "unknown"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"src_{digest}"


def normalize_rag_citations(matches: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for match in matches:
        if not isinstance(match, Mapping):
            continue
        metadata = match.get("metadata")
        if not isinstance(metadata, Mapping):
            continue

        raw_path = metadata.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = raw_path.strip().replace("\\", "/")

        raw_source_id = metadata.get("source_id")
        if isinstance(raw_source_id, str) and raw_source_id.strip():
            source_id = raw_source_id.strip()
        else:
            source_id = deterministic_source_id(path)

        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        citations.append({"source_id": source_id, "path": path})

    return citations


def estimate_prompt_tokens(prompt_text: str) -> int:
    text = str(prompt_text or "").strip()
    if not text:
        return 0

    # Approximate token usage without model-specific tokenizers.
    char_estimate = max(1, len(text) // 4)
    word_estimate = max(1, int(len(text.split()) * 1.3))
    return max(char_estimate, word_estimate)


def _messages_to_prompt_text(messages: list[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if content is None:
            continue
        parts.append(str(content))
    return "\n".join(parts)


def estimate_message_tokens(messages: list[Mapping[str, Any]]) -> int:
    return estimate_prompt_tokens(_messages_to_prompt_text(messages))


def preflight_prompt_messages(
    messages: list[Mapping[str, Any]],
    *,
    token_limit: int,
    truncate_target_tokens: int,
    near_limit_ratio: float = 0.9,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prepared_messages: list[dict[str, Any]] = [
        dict(message) if isinstance(message, Mapping) else {"content": str(message)}
        for message in messages
    ]
    estimated_before = estimate_message_tokens(prepared_messages)

    clamped_ratio = max(0.1, min(1.0, float(near_limit_ratio)))
    effective_token_limit = max(1, int(token_limit))
    effective_truncate_target = max(
        1, min(int(truncate_target_tokens), effective_token_limit)
    )
    near_limit_threshold = max(1, int(effective_token_limit * clamped_ratio))

    warning_codes: list[str] = []
    near_limit = estimated_before >= near_limit_threshold
    if near_limit:
        warning_codes.append(PROMPT_WARNING_NEAR_TOKEN_LIMIT)

    dropped_message_count = 0
    trimmed_last_message = False

    if estimated_before > effective_token_limit and prepared_messages:
        preserved_indexes: set[int] = {len(prepared_messages) - 1}
        for index, message in enumerate(prepared_messages):
            role_value = str(message.get("role", "")).lower()
            if role_value == "system":
                preserved_indexes.add(index)

        dropped_indexes: set[int] = set()
        for index, _message in enumerate(prepared_messages):
            if index in preserved_indexes:
                continue
            current_messages = [
                message
                for msg_index, message in enumerate(prepared_messages)
                if msg_index not in dropped_indexes
            ]
            if estimate_message_tokens(current_messages) <= effective_truncate_target:
                break
            dropped_indexes.add(index)

        if dropped_indexes:
            dropped_message_count = len(dropped_indexes)
            prepared_messages = [
                message
                for index, message in enumerate(prepared_messages)
                if index not in dropped_indexes
            ]

        estimated_after_drop = estimate_message_tokens(prepared_messages)
        if estimated_after_drop > effective_truncate_target and prepared_messages:
            last_message = dict(prepared_messages[-1])
            last_content = str(last_message.get("content", ""))
            if last_content:
                ratio = effective_truncate_target / max(1, estimated_after_drop)
                keep_chars = max(32, int(len(last_content) * ratio))
                if keep_chars < len(last_content):
                    last_message["content"] = last_content[-keep_chars:]
                    prepared_messages[-1] = last_message
                    trimmed_last_message = True

        warning_codes.append(PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT)

    estimated_after = estimate_message_tokens(prepared_messages)
    metadata: dict[str, Any] = {
        "token_limit": effective_token_limit,
        "truncate_target_tokens": effective_truncate_target,
        "near_limit_ratio": clamped_ratio,
        "estimated_tokens_before": estimated_before,
        "estimated_tokens_after": estimated_after,
        "near_token_limit": near_limit,
        "truncated": estimated_after < estimated_before,
        "dropped_message_count": dropped_message_count,
        "trimmed_last_message": trimmed_last_message,
        "warnings": warning_codes,
    }
    return prepared_messages, metadata


def prompt_size_bucket(
    prompt_length: int,
    min_prompt_chars: int,
    *,
    token_aware: bool = False,
    prompt_tokens: int | None = None,
    min_prompt_tokens: int | None = None,
) -> str:
    if (
        token_aware
        and min_prompt_tokens is not None
        and min_prompt_tokens > 0
        and prompt_tokens is not None
    ):
        if prompt_tokens >= min_prompt_tokens:
            return "long"
        if prompt_tokens >= max(512, min_prompt_tokens // 2):
            return "medium"
        return "short"

    if prompt_length >= min_prompt_chars:
        return "long"
    if prompt_length >= max(2000, min_prompt_chars // 2):
        return "medium"
    return "short"


def resolve_query_prompt_bucket(
    query: str,
    *,
    min_prompt_chars: int,
    token_aware: bool = False,
    min_prompt_tokens: int | None = None,
) -> tuple[str, int | None]:
    query_text = str(query or "")
    prompt_tokens = estimate_prompt_tokens(query_text) if token_aware else None
    bucket = prompt_size_bucket(
        len(query_text),
        min_prompt_chars,
        token_aware=token_aware,
        prompt_tokens=prompt_tokens,
        min_prompt_tokens=min_prompt_tokens,
    )
    return bucket, prompt_tokens


def reasoning_query_match(query: str, allowed_task_types: set[str]) -> bool:
    query_lower = query.lower()
    keywords: list[str] = []
    for task_name, task_values in ROUTING_REASONING_KEYWORDS.items():
        if task_name in allowed_task_types:
            keywords.extend(task_values)
    return any(keyword in query_lower for keyword in keywords)


def normalize_task_type_allowlist(task_types: Iterable[object]) -> set[str]:
    normalized: set[str] = set()
    for task in task_types:
        if task is None:
            continue
        task_text = str(task).strip().lower()
        if task_text:
            normalized.add(task_text)
    return normalized


def _estimate_uncertainty_score(
    query: str,
    *,
    allowed_task_types: set[str],
    context_task_type: str | None = None,
    context_complexity: str | None = None,
    reasoning_candidate: bool | None = None,
) -> float:
    query_lower = query.lower()
    score = 0.0

    if any(marker in query_lower for marker in ROUTING_UNCERTAINTY_MARKERS):
        score += 0.35

    question_mark_count = query.count("?")
    if question_mark_count > 0:
        score += min(0.15, question_mark_count * 0.05)

    if any(marker in query_lower for marker in ROUTING_REASONING_QUESTION_MARKERS):
        score += 0.15

    if any(marker in query_lower for marker in ROUTING_HIGH_COMPLEXITY_MARKERS):
        score += 0.2

    if reasoning_candidate is None:
        reasoning_candidate = reasoning_query_match(query, allowed_task_types)
    if reasoning_candidate:
        score += 0.15

    if context_complexity is not None and context_complexity.lower() == "high":
        score += 0.2

    if (
        context_task_type is not None
        and context_task_type.lower() in allowed_task_types
        and context_complexity is not None
        and context_complexity.lower() == "high"
    ):
        score += 0.1

    return max(0.0, min(1.0, score))


def should_prefer_dms_route(
    query: str,
    *,
    dms_enabled: bool,
    min_prompt_chars: int,
    allowed_task_types: set[str],
    context_task_type: str | None = None,
    context_complexity: str | None = None,
    token_aware: bool = False,
    min_prompt_tokens: int | None = None,
    prompt_tokens: int | None = None,
    uncertainty_routing_enabled: bool = False,
    uncertainty_threshold: float = 0.55,
    enforce_context_task_allowlist: bool = False,
) -> bool:
    if not dms_enabled:
        return False

    normalized_context_task_type = (
        context_task_type.strip().lower() if context_task_type is not None else None
    )
    if (
        enforce_context_task_allowlist
        and normalized_context_task_type is not None
        and normalized_context_task_type not in allowed_task_types
    ):
        return False

    long_prompt_candidate = False
    if token_aware and min_prompt_tokens is not None and min_prompt_tokens > 0:
        effective_prompt_tokens = (
            prompt_tokens if prompt_tokens is not None else estimate_prompt_tokens(query)
        )
        if effective_prompt_tokens >= min_prompt_tokens:
            long_prompt_candidate = True
    elif len(query) >= min_prompt_chars:
        long_prompt_candidate = True

    context_candidate = False
    if context_task_type is not None and context_complexity is not None:
        context_candidate = (
            context_complexity.lower() == "high"
            and normalized_context_task_type in allowed_task_types
        )
        if context_candidate and not uncertainty_routing_enabled:
            return True

    query_lower = query.lower()
    high_complexity = any(
        keyword in query_lower for keyword in ROUTING_HIGH_COMPLEXITY_MARKERS
    )
    reasoning_candidate = reasoning_query_match(query, allowed_task_types)
    query_candidate = high_complexity and reasoning_candidate

    if not uncertainty_routing_enabled:
        return long_prompt_candidate or query_candidate

    if not (long_prompt_candidate or context_candidate or reasoning_candidate):
        return False

    effective_threshold = max(0.0, min(1.0, float(uncertainty_threshold)))
    uncertainty_score = _estimate_uncertainty_score(
        query,
        allowed_task_types=allowed_task_types,
        context_task_type=normalized_context_task_type,
        context_complexity=context_complexity,
        reasoning_candidate=reasoning_candidate,
    )
    return (
        uncertainty_score + ROUTING_UNCERTAINTY_COMPARE_EPSILON
    ) >= effective_threshold


def should_prefer_dms_route_from_settings(
    query: str,
    *,
    context_task_type: str | None = None,
    context_complexity: str | None = None,
    enforce_context_task_allowlist: bool = False,
) -> bool:
    _, prompt_tokens = resolve_query_prompt_bucket(
        query,
        min_prompt_chars=settings.DMS_MIN_PROMPT_CHARS,
        token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
        min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
    )
    return should_prefer_dms_route(
        query,
        dms_enabled=settings.DMS_ENABLED,
        min_prompt_chars=settings.DMS_MIN_PROMPT_CHARS,
        allowed_task_types=normalize_task_type_allowlist(settings.DMS_TASK_TYPES),
        context_task_type=context_task_type,
        context_complexity=context_complexity,
        token_aware=settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE,
        min_prompt_tokens=settings.DMS_MIN_PROMPT_TOKENS,
        prompt_tokens=prompt_tokens,
        uncertainty_routing_enabled=settings.DMS_UNCERTAINTY_ROUTING_ENABLED,
        uncertainty_threshold=settings.DMS_UNCERTAINTY_SCORE_THRESHOLD,
        enforce_context_task_allowlist=enforce_context_task_allowlist,
    )


def _normalized_dms_share(raw_percentage: float) -> float:
    return max(0.0, min(1.0, float(raw_percentage)))


def deterministic_ab_bucket(assignment_key: str) -> float:
    digest = hashlib.sha256(assignment_key.encode("utf-8")).digest()
    # Use 8 bytes for stable 64-bit bucket precision.
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    max_value = (1 << 64) - 1
    return value / max_value


def select_dms_ab_variant(
    should_prefer_dms: bool,
    *,
    dms_ab_enabled: bool,
    dms_share_percentage: float,
    assignment_key: str | None = None,
) -> str:
    if not should_prefer_dms:
        return "disabled"
    if not dms_ab_enabled:
        return "dms"

    threshold = _normalized_dms_share(dms_share_percentage)
    if assignment_key:
        sample = deterministic_ab_bucket(assignment_key)
    else:
        sample = random.random()

    return "dms" if sample < threshold else "control"


def fallback_reason_counts_template() -> dict[str, int]:
    return {code: 0 for code in sorted(FALLBACK_REASON_CODES)}


def is_retryable_fallback_reason(reason_code: str) -> bool:
    return reason_code in RETRYABLE_FALLBACK_CODES


def classify_dms_fallback_reason(error: object | None) -> tuple[str, str]:
    detail = _normalize_error_detail(error)
    error_text = detail.lower()

    if (
        "429" in error_text
        or "rate limit" in error_text
        or "too many requests" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_RATE_LIMITED.value, detail

    if (
        "timeout" in error_text
        or "timed out" in error_text
        or "read timed out" in error_text
        or "connect timeout" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_TIMEOUT.value, detail

    if (
        "jsondecodeerror" in error_text
        or "json decode" in error_text
        or "invalid json" in error_text
        or "malformed json" in error_text
        or "parse" in error_text
        or "expecting value" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_PARSE_ERROR.value, detail

    if (
        "500" in error_text
        or "502" in error_text
        or "503" in error_text
        or "504" in error_text
        or "bad gateway" in error_text
        or "service unavailable" in error_text
        or "internal server error" in error_text
        or "gateway timeout" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_HTTP_5XX.value, detail

    if (
        "401" in error_text
        or "403" in error_text
        or "unauthorized" in error_text
        or "forbidden" in error_text
        or "invalid api key" in error_text
        or "authentication" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_AUTH_ERROR.value, detail

    if (
        "connection" in error_text
        or "dns" in error_text
        or "name resolution" in error_text
        or "newconnectionerror" in error_text
        or "max retries exceeded" in error_text
        or "network is unreachable" in error_text
        or "connection reset" in error_text
    ):
        return RoutingFallbackReasonCode.DMS_TRANSPORT_ERROR.value, detail

    return RoutingFallbackReasonCode.DMS_ERROR.value, detail


def apply_dms_fallback(
    decision: dict[str, Any], error: object | None, stage: str = "dms_primary"
) -> str:
    reason_code, detail = classify_dms_fallback_reason(error)
    decision["fallback_reason"] = f"dms_error: {detail}"
    decision["fallback_reason_code"] = reason_code
    decision["fallback_detail"] = detail
    decision["fallback_stage"] = stage
    decision["fallback_retryable"] = is_retryable_fallback_reason(reason_code)
    return reason_code


def validate_routing_decision_metadata(
    metadata: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    for field in ROUTING_DECISION_FIELDS:
        if field not in metadata:
            errors.append(f"missing field: {field}")

    reason_code = metadata.get("fallback_reason_code")
    if reason_code is not None and reason_code not in FALLBACK_REASON_CODES:
        errors.append(f"invalid fallback_reason_code: {reason_code}")

    fallback_retryable = metadata.get("fallback_retryable")
    if fallback_retryable is not None and not isinstance(fallback_retryable, bool):
        errors.append("fallback_retryable must be a boolean or null")

    router_rule_version = metadata.get("router_rule_version")
    if router_rule_version is not None and not isinstance(router_rule_version, str):
        errors.append("router_rule_version must be a string")

    routing_schema = metadata.get("routing_telemetry_schema")
    if routing_schema is not None and not isinstance(routing_schema, str):
        errors.append("routing_telemetry_schema must be a string")

    maturity_tier = metadata.get("maturity_tier")
    if maturity_tier is not None:
        if not isinstance(maturity_tier, str):
            errors.append("maturity_tier must be a string")
        elif maturity_tier not in MATURITY_TIERS:
            allowed = ", ".join(sorted(MATURITY_TIERS))
            errors.append(f"maturity_tier must be one of: {allowed}")

    maturity_policy_version = metadata.get("maturity_policy_version")
    if maturity_policy_version is not None:
        if not isinstance(maturity_policy_version, str):
            errors.append("maturity_policy_version must be a string")
        elif not maturity_policy_version.strip():
            errors.append("maturity_policy_version must be a non-empty string")

    routing_trace_id = metadata.get("routing_trace_id")
    if routing_trace_id is not None:
        if not isinstance(routing_trace_id, str):
            errors.append("routing_trace_id must be a string")
        else:
            suffix = routing_trace_id[3:] if routing_trace_id.startswith("rt_") else ""
            if len(suffix) != 16 or any(
                char not in "0123456789abcdef" for char in suffix
            ):
                errors.append("routing_trace_id must match rt_<16 lowercase hex chars>")

    routing_trace_fingerprint = metadata.get("routing_trace_fingerprint")
    if routing_trace_fingerprint is not None:
        if not isinstance(routing_trace_fingerprint, str):
            errors.append("routing_trace_fingerprint must be a string")
        elif len(routing_trace_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in routing_trace_fingerprint
        ):
            errors.append(
                "routing_trace_fingerprint must be 64 lowercase hex characters"
            )

    routing_trace_scheme = metadata.get("routing_trace_scheme")
    if routing_trace_scheme is not None and not isinstance(routing_trace_scheme, str):
        errors.append("routing_trace_scheme must be a string")
    elif routing_trace_scheme is not None and routing_trace_scheme != ROUTING_TRACE_SCHEME:
        errors.append(
            f"routing_trace_scheme must equal {ROUTING_TRACE_SCHEME}"
        )

    router_policy_version = metadata.get("router_policy_version")
    if (
        isinstance(router_policy_version, str)
        and isinstance(router_rule_version, str)
        and router_rule_version != router_policy_version
    ):
        errors.append("router_rule_version must match router_policy_version")

    return (len(errors) == 0, errors)

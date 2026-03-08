from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from jsonschema import Draft202012Validator

from merlin_routing_contract import (
    FALLBACK_REASON_CODES,
    PROMPT_WARNING_NEAR_TOKEN_LIMIT,
    PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT,
    RETRYABLE_FALLBACK_CODES,
    ROUTING_TRACE_SCHEME,
    RoutingFallbackReasonCode,
    apply_dms_fallback,
    build_routing_decision,
    classify_dms_fallback_reason,
    coerce_usage_normalized,
    deterministic_ab_bucket,
    deterministic_source_id,
    enrich_error_with_rate_limit_headers,
    estimate_prompt_tokens,
    extract_openai_compatible_content,
    fallback_reason_counts_template,
    is_retryable_fallback_reason,
    normalize_openai_usage_payload,
    normalize_rag_citations,
    normalize_provider_chat_payload,
    preflight_prompt_messages,
    prompt_size_bucket,
    reasoning_query_match,
    normalize_task_type_allowlist,
    resolve_query_prompt_bucket,
    select_dms_ab_variant,
    should_prefer_dms_route,
    should_prefer_dms_route_from_settings,
    validate_routing_decision_metadata,
)

pytestmark = pytest.mark.critical_coverage

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "contracts"

ROUTING_METADATA_VALIDATOR = Draft202012Validator(
    json.loads(
        (CONTRACTS_DIR / "assistant.chat.routing-metadata.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
)


def _schema_errors(validator: Draft202012Validator, data: dict) -> list[str]:
    return sorted(error.message for error in validator.iter_errors(data))


def _load_contract_fixture(filename: str) -> dict:
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_build_routing_decision_has_normalized_fields():
    decision = build_routing_decision("short", "parallel")

    assert decision["prompt_size_bucket"] == "short"
    assert decision["router_backend"] == "parallel"
    assert decision["router_policy_version"] == "cp2-2026-02-15"
    assert decision["router_rule_version"] == "cp2-2026-02-15"
    assert decision["maturity_tier"] == "M0"
    assert decision["maturity_policy_version"] == "mdmm-2026-02-22"
    assert decision["fallback_reason"] is None
    assert decision["fallback_reason_code"] is None
    assert decision["routing_trace_id"].startswith("rt_")
    assert len(decision["routing_trace_id"]) == 19
    assert len(decision["routing_trace_fingerprint"]) == 64
    assert decision["routing_trace_scheme"] == ROUTING_TRACE_SCHEME


def test_build_routing_decision_trace_fields_are_deterministic_for_normalized_query():
    first = build_routing_decision(
        "long",
        "adaptive",
        query="   Explain   fallback behavior   ",
    )
    second = build_routing_decision(
        "long",
        "adaptive",
        query="explain fallback behavior",
    )
    different_query = build_routing_decision(
        "long",
        "adaptive",
        query="explain routing behavior",
    )

    assert first["routing_trace_id"] == second["routing_trace_id"]
    assert (
        first["routing_trace_fingerprint"] == second["routing_trace_fingerprint"]
    )
    assert first["routing_trace_id"] != different_query["routing_trace_id"]


def test_build_routing_decision_uses_runtime_maturity_settings(monkeypatch):
    monkeypatch.setattr(
        "merlin_routing_contract.settings.MERLIN_MATURITY_TIER",
        "M2",
    )
    monkeypatch.setattr(
        "merlin_routing_contract.settings.MERLIN_MATURITY_POLICY_VERSION",
        "mdmm-fixture-policy-v1",
    )

    decision = build_routing_decision("medium", "adaptive")
    assert decision["maturity_tier"] == "M2"
    assert decision["maturity_policy_version"] == "mdmm-fixture-policy-v1"


@pytest.mark.parametrize(
    "error_text,expected_code",
    [
        ("connection timeout", "dms_timeout"),
        ("HTTP 429 too many requests", "dms_rate_limited"),
        ("503 service unavailable", "dms_http_5xx"),
        ("JSONDecodeError: expecting value", "dms_parse_error"),
        ("401 unauthorized", "dms_auth_error"),
        ("403 forbidden", "dms_auth_error"),
        ("connection reset by peer", "dms_transport_error"),
        ("max retries exceeded", "dms_transport_error"),
        ("unexpected payload structure", "dms_error"),
    ],
)
def test_classify_dms_fallback_reason_maps_known_errors(
    error_text: str, expected_code: str
):
    assert classify_dms_fallback_reason(error_text)[0] == expected_code


def test_apply_dms_fallback_sets_legacy_and_normalized_fields():
    decision = build_routing_decision("long", "adaptive")
    reason_code = apply_dms_fallback(decision, "connection reset by peer")

    assert reason_code == "dms_transport_error"
    assert decision["fallback_reason"] == "dms_error: connection reset by peer"
    assert decision["fallback_reason_code"] == "dms_transport_error"
    assert decision["fallback_detail"] == "connection reset by peer"
    assert decision["fallback_retryable"] is True


def test_enrich_error_with_rate_limit_headers_appends_known_headers():
    class _Response:
        headers = {
            "X-RateLimit-Remaining-Requests": "0",
            "x-ratelimit-reset-requests": "12ms",
            "Retry-After": "2",
            "content-type": "application/json",
        }

    error = requests.exceptions.HTTPError("HTTP 429", response=_Response())

    detail = enrich_error_with_rate_limit_headers(error)

    assert detail.startswith("HTTP 429 | rate_limit_headers: ")
    assert "x-ratelimit-remaining-requests=0" in detail
    assert "x-ratelimit-reset-requests=12ms" in detail
    assert "retry-after=2" in detail
    assert "content-type" not in detail


def test_enrich_error_with_rate_limit_headers_noop_when_headers_missing():
    error = requests.exceptions.RequestException("connection timeout")
    assert enrich_error_with_rate_limit_headers(error) == "connection timeout"


def test_fallback_reason_enum_matches_public_sets():
    enum_values = {code.value for code in RoutingFallbackReasonCode}
    assert enum_values == FALLBACK_REASON_CODES
    assert RETRYABLE_FALLBACK_CODES.issubset(FALLBACK_REASON_CODES)


def test_fallback_reason_count_template_contains_all_codes():
    counts = fallback_reason_counts_template()
    assert set(counts.keys()) == FALLBACK_REASON_CODES
    assert all(value == 0 for value in counts.values())


def test_is_retryable_fallback_reason_matches_known_partition():
    assert is_retryable_fallback_reason("dms_timeout") is True
    assert is_retryable_fallback_reason("dms_auth_error") is False


def test_prompt_size_bucket_uses_shared_threshold_policy():
    assert prompt_size_bucket(100, 6000) == "short"
    assert prompt_size_bucket(3500, 6000) == "medium"
    assert prompt_size_bucket(7000, 6000) == "long"


def test_prompt_size_bucket_token_aware_mode():
    assert (
        prompt_size_bucket(
            100,
            6000,
            token_aware=True,
            prompt_tokens=200,
            min_prompt_tokens=1500,
        )
        == "short"
    )
    assert (
        prompt_size_bucket(
            100,
            6000,
            token_aware=True,
            prompt_tokens=900,
            min_prompt_tokens=1500,
        )
        == "medium"
    )
    assert (
        prompt_size_bucket(
            100,
            6000,
            token_aware=True,
            prompt_tokens=1800,
            min_prompt_tokens=1500,
        )
        == "long"
    )


def test_resolve_query_prompt_bucket_returns_bucket_and_optional_tokens():
    query = "word " * 120

    token_bucket, token_count = resolve_query_prompt_bucket(
        query,
        min_prompt_chars=6000,
        token_aware=True,
        min_prompt_tokens=100,
    )
    assert token_bucket == "long"
    assert isinstance(token_count, int)
    assert token_count >= 100

    char_bucket, char_count = resolve_query_prompt_bucket(
        query,
        min_prompt_chars=6000,
        token_aware=False,
        min_prompt_tokens=100,
    )
    assert char_bucket == "short"
    assert char_count is None


def test_normalize_task_type_allowlist_normalizes_and_filters_values():
    allowlist = normalize_task_type_allowlist(
        ["Analysis", "  CODE ", "", "analysis", None, "   ", "planning"]
    )
    assert allowlist == {"analysis", "code", "planning"}


def test_normalize_openai_usage_payload_normalizes_supported_fields():
    normalized = normalize_openai_usage_payload(
        {
            "usage": {
                "input_tokens": 25,
                "output_tokens": 9,
                "cache_read_input_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 3},
            }
        }
    )
    assert normalized == {
        "prompt_tokens": 25,
        "completion_tokens": 9,
        "total_tokens": 34,
        "cached_tokens": 7,
        "reasoning_tokens": 3,
    }


def test_normalize_openai_usage_payload_returns_empty_when_missing_or_zero():
    assert normalize_openai_usage_payload({"choices": [{"message": {"content": "ok"}}]}) == {}
    assert normalize_openai_usage_payload({"usage": {"prompt_tokens": 0, "completion_tokens": 0}}) == {}


def test_coerce_usage_normalized_filters_invalid_payloads_and_recomputes_totals():
    assert coerce_usage_normalized(None) is None
    assert coerce_usage_normalized({"prompt_tokens": 0, "completion_tokens": 0}) is None

    normalized = coerce_usage_normalized(
        {"prompt_tokens": 15, "completion_tokens": 5, "cached_tokens": 2}
    )
    assert normalized == {
        "prompt_tokens": 15,
        "completion_tokens": 5,
        "total_tokens": 20,
        "cached_tokens": 2,
    }


def test_normalize_openai_usage_payload_supports_optional_top_level_fallbacks():
    normalized = normalize_openai_usage_payload(
        {"prompt_eval_count": 11, "eval_count": 4},
        require_usage_map=False,
        prompt_fallback_fields=("prompt_eval_count", "prompt_tokens"),
        completion_fallback_fields=("eval_count", "completion_tokens"),
        include_zero_fields=True,
    )
    assert normalized == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
        "cached_tokens": 0,
    }


def test_normalize_openai_usage_payload_can_return_zero_fields_when_requested():
    normalized = normalize_openai_usage_payload(
        {},
        require_usage_map=False,
        include_zero_fields=True,
    )
    assert normalized == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
    }


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"message": {"content": "msg"}}, "msg"),
        ({"text": "top-text"}, "top-text"),
        ({"content": "top-content"}, "top-content"),
        ({"choices": [{"message": {"content": "choice-msg"}}]}, "choice-msg"),
        ({"choices": [{"text": "choice-text"}]}, "choice-text"),
        ({"choices": [{"message": 42}]}, "42"),
        ({"choices": []}, ""),
        ("scalar", "scalar"),
    ],
)
def test_extract_openai_compatible_content_handles_supported_payload_shapes(
    payload, expected
):
    assert extract_openai_compatible_content(payload) == expected


def test_should_prefer_dms_route_from_settings_respects_context_allowlist(monkeypatch):
    monkeypatch.setattr("merlin_routing_contract.settings.DMS_ENABLED", True)
    monkeypatch.setattr("merlin_routing_contract.settings.DMS_MIN_PROMPT_CHARS", 32)
    monkeypatch.setattr("merlin_routing_contract.settings.DMS_TASK_TYPES", ["analysis"])
    monkeypatch.setattr(
        "merlin_routing_contract.settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE",
        False,
    )
    monkeypatch.setattr("merlin_routing_contract.settings.DMS_MIN_PROMPT_TOKENS", 1500)
    monkeypatch.setattr(
        "merlin_routing_contract.settings.DMS_UNCERTAINTY_ROUTING_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "merlin_routing_contract.settings.DMS_UNCERTAINTY_SCORE_THRESHOLD",
        0.55,
    )

    query = "x" * 64
    assert should_prefer_dms_route_from_settings(query) is True
    assert (
        should_prefer_dms_route_from_settings(
            query,
            context_task_type="general",
            context_complexity="high",
            enforce_context_task_allowlist=True,
        )
        is False
    )


def test_estimate_prompt_tokens_returns_non_zero_for_non_empty_text():
    assert estimate_prompt_tokens("hello world") > 0
    assert estimate_prompt_tokens("") == 0


def test_normalize_provider_chat_payload_preserves_choice_message_shape():
    payload = {"choices": [{"message": {"content": "hello"}}]}
    normalized = normalize_provider_chat_payload(payload)

    assert normalized["choices"][0]["message"]["content"] == "hello"
    assert normalized["provider_payload_shape"] == "choices_message"
    assert normalized["provider_payload_normalized"] is False


@pytest.mark.parametrize(
    "payload,expected_content,expected_shape",
    [
        ({"text": "legacy"}, "legacy", "top_level_text"),
        ({"content": "top"}, "top", "top_level_content"),
        ({"choices": [{"text": "choice text"}]}, "choice text", "choices_text"),
        ([{"generated_text": "hf output"}], "hf output", "list_generated_text"),
    ],
)
def test_normalize_provider_chat_payload_coerces_noncanonical_shapes(
    payload, expected_content, expected_shape
):
    normalized = normalize_provider_chat_payload(payload)

    assert normalized["choices"][0]["message"]["content"] == expected_content
    assert normalized["provider_payload_shape"] == expected_shape
    assert normalized["provider_payload_normalized"] is True


def test_deterministic_source_id_is_stable_for_same_path():
    first = deterministic_source_id("Docs/Readme.md")
    second = deterministic_source_id("docs/readme.md")
    third = deterministic_source_id("docs/other.md")

    assert first == second
    assert first.startswith("src_")
    assert first != third


def test_normalize_rag_citations_builds_deterministic_source_ids():
    citations = normalize_rag_citations(
        [
            {"text": "a", "metadata": {"path": "docs/readme.md"}},
            {"text": "b", "metadata": {"path": "docs/readme.md"}},
            {"text": "c", "metadata": {"path": "docs/guide.md", "source_id": "guide_src"}},
            {"text": "d", "metadata": {}},
        ]
    )

    assert len(citations) == 2
    assert citations[0]["path"] == "docs/readme.md"
    assert citations[0]["source_id"].startswith("src_")
    assert citations[1] == {"source_id": "guide_src", "path": "docs/guide.md"}


def test_preflight_prompt_messages_warns_when_near_token_limit():
    messages = [{"role": "user", "content": "x" * 360}]

    prepared, metadata = preflight_prompt_messages(
        messages,
        token_limit=100,
        truncate_target_tokens=90,
        near_limit_ratio=0.9,
    )

    assert prepared == messages
    assert metadata["near_token_limit"] is True
    assert metadata["truncated"] is False
    assert metadata["warnings"] == [PROMPT_WARNING_NEAR_TOKEN_LIMIT]


def test_preflight_prompt_messages_truncates_when_over_limit():
    messages = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "a" * 400},
        {"role": "assistant", "content": "b" * 300},
        {"role": "user", "content": "c" * 400},
    ]

    prepared, metadata = preflight_prompt_messages(
        messages,
        token_limit=160,
        truncate_target_tokens=120,
        near_limit_ratio=0.9,
    )

    assert metadata["truncated"] is True
    assert metadata["estimated_tokens_after"] <= metadata["estimated_tokens_before"]
    assert PROMPT_WARNING_NEAR_TOKEN_LIMIT in metadata["warnings"]
    assert PROMPT_WARNING_TRUNCATED_FOR_TOKEN_LIMIT in metadata["warnings"]
    assert prepared[0]["role"] == "system"
    assert prepared[-1]["role"] == "user"


def test_reasoning_query_match_respects_allowed_task_types():
    assert reasoning_query_match("please analyze this", {"analysis"}) is True
    assert reasoning_query_match("plan migration steps", {"planning"}) is True
    assert reasoning_query_match("analyze this", {"code"}) is False


def test_should_prefer_dms_route_supports_context_and_query_modes():
    assert (
        should_prefer_dms_route(
            "tiny",
            dms_enabled=False,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
        )
        is False
    )
    assert (
        should_prefer_dms_route(
            "x" * 7000,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
        )
        is True
    )
    assert (
        should_prefer_dms_route(
            "complex plan for migration",
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"planning"},
        )
        is True
    )
    assert (
        should_prefer_dms_route(
            "short prompt",
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            context_task_type="analysis",
            context_complexity="high",
        )
        is True
    )


def test_should_prefer_dms_route_context_allowlist_guardrail_blocks_disallowed_type():
    assert (
        should_prefer_dms_route(
            "x" * 7000,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            context_task_type="general",
            context_complexity="high",
            enforce_context_task_allowlist=True,
        )
        is False
    )


def test_should_prefer_dms_route_context_allowlist_guardrail_allows_matching_type():
    assert (
        should_prefer_dms_route(
            "x" * 7000,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            context_task_type="analysis",
            context_complexity="high",
            enforce_context_task_allowlist=True,
        )
        is True
    )


def test_should_prefer_dms_route_supports_token_aware_mode():
    assert (
        should_prefer_dms_route(
            "short prompt",
            dms_enabled=True,
            min_prompt_chars=10000,
            allowed_task_types={"analysis"},
            token_aware=True,
            min_prompt_tokens=1500,
            prompt_tokens=1700,
        )
        is True
    )
    assert (
        should_prefer_dms_route(
            "short prompt",
            dms_enabled=True,
            min_prompt_chars=10000,
            allowed_task_types={"analysis"},
            token_aware=True,
            min_prompt_tokens=1500,
            prompt_tokens=200,
        )
        is False
    )


def test_should_prefer_dms_route_uncertainty_mode_blocks_simple_long_prompt():
    assert (
        should_prefer_dms_route(
            "hello " * 2000,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.55,
        )
        is False
    )


def test_should_prefer_dms_route_uncertainty_mode_prefers_uncertain_reasoning():
    assert (
        should_prefer_dms_route(
            (
                "I am not sure how to evaluate the probability and trade-off risk "
                "for this migration plan?"
            ),
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis", "planning"},
            context_task_type="analysis",
            context_complexity="high",
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.55,
        )
        is True
    )


def test_should_prefer_dms_route_uncertainty_threshold_clamps_lower_bound():
    assert (
        should_prefer_dms_route(
            "hello " * 2000,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            uncertainty_routing_enabled=True,
            uncertainty_threshold=-1.0,
        )
        is True
    )


def test_should_prefer_dms_route_uncertainty_threshold_clamps_upper_bound():
    assert (
        should_prefer_dms_route(
            "uncertain " * 1200,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            uncertainty_routing_enabled=True,
            uncertainty_threshold=1.4,
        )
        is False
    )


def test_should_prefer_dms_route_uncertainty_mode_context_high_only_is_not_enough():
    assert (
        should_prefer_dms_route(
            "short prompt",
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            context_task_type="analysis",
            context_complexity="high",
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.55,
        )
        is False
    )


def test_should_prefer_dms_route_uncertainty_mode_context_plus_reasoning_can_pass():
    assert (
        should_prefer_dms_route(
            "please analyze this migration plan",
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis", "planning"},
            context_task_type="analysis",
            context_complexity="high",
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.55,
        )
        is True
    )


def test_should_prefer_dms_route_uncertainty_threshold_is_inclusive_at_boundary():
    boundary_query = ("uncertain context " * 500) + " how?"
    assert (
        should_prefer_dms_route(
            boundary_query,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.55,
        )
        is True
    )


def test_should_prefer_dms_route_uncertainty_threshold_rejects_above_boundary():
    boundary_query = ("uncertain context " * 500) + " how?"
    assert (
        should_prefer_dms_route(
            boundary_query,
            dms_enabled=True,
            min_prompt_chars=6000,
            allowed_task_types={"analysis"},
            uncertainty_routing_enabled=True,
            uncertainty_threshold=0.56,
        )
        is False
    )


def test_select_dms_ab_variant_deterministic_with_assignment_key():
    variant_one = select_dms_ab_variant(
        True,
        dms_ab_enabled=True,
        dms_share_percentage=0.5,
        assignment_key="session-123",
    )
    variant_two = select_dms_ab_variant(
        True,
        dms_ab_enabled=True,
        dms_share_percentage=0.5,
        assignment_key="session-123",
    )
    assert variant_one == variant_two
    assert variant_one in {"dms", "control"}


def test_select_dms_ab_variant_handles_disabled_and_bounds():
    assert (
        select_dms_ab_variant(
            False, dms_ab_enabled=True, dms_share_percentage=0.5, assignment_key="k"
        )
        == "disabled"
    )
    assert (
        select_dms_ab_variant(
            True, dms_ab_enabled=False, dms_share_percentage=0.5, assignment_key="k"
        )
        == "dms"
    )
    assert (
        select_dms_ab_variant(
            True, dms_ab_enabled=True, dms_share_percentage=0.0, assignment_key="k"
        )
        == "control"
    )
    assert (
        select_dms_ab_variant(
            True, dms_ab_enabled=True, dms_share_percentage=1.0, assignment_key="k"
        )
        == "dms"
    )


def test_deterministic_ab_bucket_is_stable():
    first = deterministic_ab_bucket("stable-key")
    second = deterministic_ab_bucket("stable-key")
    assert first == second
    assert 0.0 <= first <= 1.0


def test_validate_routing_decision_metadata_passes_for_contract_shape():
    decision = build_routing_decision("medium", "streaming")
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is True
    assert errors == []


def test_validate_routing_decision_metadata_rejects_invalid_reason_code():
    decision = build_routing_decision("medium", "parallel")
    decision["fallback_reason_code"] = "invalid_code"
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert errors == ["invalid fallback_reason_code: invalid_code"]


def test_validate_routing_decision_metadata_rejects_missing_required_fields():
    decision = build_routing_decision("short", "adaptive")
    decision.pop("router_policy_version")
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert errors == ["missing field: router_policy_version"]


def test_validate_routing_decision_metadata_rejects_wrong_types():
    decision = build_routing_decision("short", "parallel")
    decision["fallback_retryable"] = "yes"
    decision["router_rule_version"] = 1
    decision["routing_telemetry_schema"] = 1
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert "fallback_retryable must be a boolean or null" in errors
    assert "router_rule_version must be a string" in errors
    assert "routing_telemetry_schema must be a string" in errors


def test_validate_routing_decision_metadata_rejects_invalid_maturity_fields():
    decision = build_routing_decision("short", "adaptive")
    decision["maturity_tier"] = "M9"
    decision["maturity_policy_version"] = "   "
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert "maturity_tier must be one of: M0, M1, M2, M3, M4" in errors
    assert "maturity_policy_version must be a non-empty string" in errors


def test_validate_routing_decision_metadata_rejects_version_mismatch():
    decision = build_routing_decision("short", "adaptive")
    decision["router_rule_version"] = "cp2-2026-02-16"
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert "router_rule_version must match router_policy_version" in errors


def test_validate_routing_decision_metadata_rejects_invalid_trace_fields():
    decision = build_routing_decision("short", "adaptive")
    decision["routing_trace_id"] = "trace-123"
    decision["routing_trace_fingerprint"] = "not-hex"
    decision["routing_trace_scheme"] = "legacy"
    valid, errors = validate_routing_decision_metadata(decision)

    assert valid is False
    assert "routing_trace_id must match rt_<16 lowercase hex chars>" in errors
    assert "routing_trace_fingerprint must be 64 lowercase hex characters" in errors
    assert "routing_trace_scheme must equal sha256-v1" in errors


def test_routing_metadata_fixture_matches_schema_fragment():
    metadata = _load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    errors = _schema_errors(ROUTING_METADATA_VALIDATOR, metadata)

    assert errors == []


def test_routing_metadata_in_expected_response_matches_schema_fragment():
    expected = _load_contract_fixture(
        "assistant.chat.request.with_metadata.expected_response.json"
    )
    metadata = expected["payload"]["metadata"]
    errors = _schema_errors(ROUTING_METADATA_VALIDATOR, metadata)

    assert errors == []


def test_routing_metadata_schema_rejects_invalid_fallback_reason_code():
    metadata = _load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    metadata["fallback_reason_code"] = "invalid_reason"
    metadata["fallback_retryable"] = False
    errors = _schema_errors(ROUTING_METADATA_VALIDATOR, metadata)

    assert errors
    assert any("invalid_reason" in error for error in errors)


def test_routing_metadata_schema_requires_full_contract_shape():
    metadata = _load_contract_fixture("assistant.chat.routing_metadata.contract.json")
    metadata.pop("router_policy_version")
    errors = _schema_errors(ROUTING_METADATA_VALIDATOR, metadata)

    assert any("router_policy_version" in error for error in errors)

# Merlin Settings: Emulation Mode
import os
import json
from pathlib import Path


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_list(value: str | None) -> list[str]:
    if value is None:
        return []
    parsed = []
    for item in value.split(","):
        stripped = item.strip()
        if stripped:
            parsed.append(stripped)
    return parsed


def _parse_lower_list(value: str | None) -> list[str]:
    return [item.lower() for item in _parse_list(value)]


def _parse_operation_payload_limits(value: str | None) -> dict[str, int]:
    """
    Parse `operation=max_bytes` pairs from a comma-separated string.

    Example:
      "assistant.chat.request=65536,merlin.rag.query=262144"
    """
    limits: dict[str, int] = {}
    if value is None:
        return limits

    for token in value.split(","):
        item = token.strip()
        if not item or "=" not in item:
            continue
        operation_name, raw_limit = item.split("=", 1)
        operation_name = operation_name.strip()
        raw_limit = raw_limit.strip()
        if not operation_name:
            continue
        try:
            parsed_limit = int(raw_limit)
        except ValueError:
            continue
        if parsed_limit <= 0:
            continue
        limits[operation_name] = parsed_limit
    return limits


def _parse_operation_feature_flags(value: str | None) -> dict[str, bool]:
    """
    Parse operation enable/disable flags from `operation=state` pairs.

    Supported states:
      enabled/on/true/1
      disabled/off/false/0
    """
    flags: dict[str, bool] = {}
    if value is None:
        return flags

    for token in value.split(","):
        item = token.strip()
        if not item or "=" not in item:
            continue
        operation_name, raw_state = item.split("=", 1)
        operation_name = operation_name.strip()
        state = raw_state.strip().lower()
        if not operation_name:
            continue
        if state in {"1", "true", "enabled", "on"}:
            flags[operation_name] = True
        elif state in {"0", "false", "disabled", "off"}:
            flags[operation_name] = False
    return flags


def _parse_model_timeout_matrix(
    value: str | None,
    *,
    default_short: int,
    default_medium: int,
    default_long: int,
) -> dict[str, dict[str, int]]:
    """
    Parse timeout overrides from `backend.bucket=seconds` pairs.

    Example:
      "openai.short=20,dms.medium=45,dms.long=90"
    """
    matrix: dict[str, dict[str, int]] = {
        "default": {
            "short": default_short,
            "medium": default_medium,
            "long": default_long,
        }
    }
    known_backends = ("lmstudio", "ollama", "openai", "huggingface", "dms")
    for backend_name in known_backends:
        matrix[backend_name] = dict(matrix["default"])

    if value is None:
        return matrix

    for token in value.split(","):
        item = token.strip()
        if not item or "=" not in item:
            continue
        scope_bucket, raw_timeout = item.split("=", 1)
        scope_bucket = scope_bucket.strip().lower()
        raw_timeout = raw_timeout.strip()
        if "." not in scope_bucket:
            continue
        backend_name, bucket = scope_bucket.rsplit(".", 1)
        backend_name = backend_name.strip()
        bucket = bucket.strip()
        if not backend_name or bucket not in {"short", "medium", "long"}:
            continue
        parsed_timeout = _optional_int(raw_timeout)
        if parsed_timeout is None or parsed_timeout <= 0:
            continue
        matrix.setdefault(backend_name, dict(matrix["default"]))[
            bucket
        ] = parsed_timeout

    return matrix


def _coerce_positive_int(value: str | None, default: int) -> int:
    parsed = _optional_int(value)
    if parsed is None or parsed <= 0:
        return default
    return parsed


def _parse_upper_choice(
    value: str | None,
    *,
    allowed: set[str],
    default: str,
) -> str:
    if value is None:
        return default
    candidate = value.strip().upper()
    if candidate in allowed:
        return candidate
    return default


MERLIN_ALLOWED_MATURITY_TIERS = frozenset({"M0", "M1", "M2", "M3", "M4"})
MERLIN_MATURITY_ALLOWLIST_ALL_OPERATIONS = "*"


def _parse_maturity_tier(value: str | None, *, default: str = "M0") -> str:
    fallback = default if default in MERLIN_ALLOWED_MATURITY_TIERS else "M0"
    if value is None:
        return fallback
    candidate = value.strip().upper()
    if candidate in MERLIN_ALLOWED_MATURITY_TIERS:
        return candidate
    return fallback


def _default_maturity_operation_allowlists() -> dict[str, frozenset[str]]:
    return {
        tier: frozenset({MERLIN_MATURITY_ALLOWLIST_ALL_OPERATIONS})
        for tier in MERLIN_ALLOWED_MATURITY_TIERS
    }


def _parse_maturity_operation_allowlists(
    value: str | None,
) -> dict[str, frozenset[str]]:
    parsed_allowlists = _default_maturity_operation_allowlists()
    if value is None or not value.strip():
        return parsed_allowlists

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return parsed_allowlists
    if not isinstance(decoded, dict):
        return parsed_allowlists

    normalized_overrides: dict[str, frozenset[str]] = {}
    for raw_tier, raw_operations in decoded.items():
        if not isinstance(raw_tier, str):
            continue
        tier = raw_tier.strip().upper()
        if tier not in MERLIN_ALLOWED_MATURITY_TIERS:
            continue

        operations: set[str] = set()
        if isinstance(raw_operations, str):
            for token in raw_operations.split(","):
                normalized = token.strip()
                if normalized:
                    operations.add(normalized)
        elif isinstance(raw_operations, list):
            for item in raw_operations:
                if not isinstance(item, str):
                    continue
                normalized = item.strip()
                if normalized:
                    operations.add(normalized)
        else:
            continue

        if MERLIN_MATURITY_ALLOWLIST_ALL_OPERATIONS in operations:
            normalized_overrides[tier] = frozenset(
                {MERLIN_MATURITY_ALLOWLIST_ALL_OPERATIONS}
            )
            continue
        normalized_overrides[tier] = frozenset(operations)

    parsed_allowlists.update(normalized_overrides)
    return parsed_allowlists


# API Connectivity
MERLIN_API_HOST = os.getenv("MERLIN_API_HOST", "0.0.0.0")
MERLIN_API_PORT = _coerce_positive_int(os.getenv("MERLIN_API_PORT"), 8000)
MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S = _coerce_positive_int(
    os.getenv("MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S"), 15
)
MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S = _coerce_positive_int(
    os.getenv("MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S"), 30
)
_raw_http_limit_concurrency = _optional_int(os.getenv("MERLIN_HTTP_LIMIT_CONCURRENCY"))
MERLIN_HTTP_LIMIT_CONCURRENCY = (
    _raw_http_limit_concurrency
    if _raw_http_limit_concurrency is not None and _raw_http_limit_concurrency > 0
    else None
)
MERLIN_MATURITY_TIER = _parse_maturity_tier(
    os.getenv("MERLIN_MATURITY_TIER"),
    default="M0",
)
_raw_merlin_maturity_policy_version = os.getenv(
    "MERLIN_MATURITY_POLICY_VERSION",
    "mdmm-2026-02-22",
)
MERLIN_MATURITY_POLICY_VERSION = (
    _raw_merlin_maturity_policy_version.strip() or "mdmm-2026-02-22"
)
MERLIN_MATURITY_OPERATION_ALLOWLISTS = _parse_maturity_operation_allowlists(
    os.getenv("MERLIN_MATURITY_OPERATION_ALLOWLISTS")
)

# LLM Backend Selection: "lmstudio", "ollama", "openai", "huggingface", "parallel", "adaptive", "dms"
LLM_BACKEND = os.getenv("LLM_BACKEND", "lmstudio")

# Parallel LLM Strategy: "voting", "routing", "cascade", "consensus", "auto"
PARALLEL_STRATEGY = os.getenv("PARALLEL_STRATEGY", "voting")

# Adaptive LLM Settings
LEARNING_MODE = os.getenv("LEARNING_MODE", "enabled")
MIN_LEARNING_SAMPLES = int(os.getenv("MIN_LEARNING_SAMPLES", "5"))
MERLIN_SYSTEM_PROMPT_CACHE_ENABLED = (
    os.getenv("MERLIN_SYSTEM_PROMPT_CACHE_ENABLED", "true").lower() == "true"
)
MERLIN_SYSTEM_PROMPT_CACHE_MAX_ENTRIES = _coerce_positive_int(
    os.getenv("MERLIN_SYSTEM_PROMPT_CACHE_MAX_ENTRIES"), 128
)

# LM Studio Configuration
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")

# Ollama Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODELS = json.loads(
    os.getenv("OLLAMA_MODELS", '["llama3.2", "mistral", "nomic", "glm4"]')
)
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_URL = os.getenv("OPENAI_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# DMS (Dynamic Memory Sparsification) endpoint configuration
DMS_ENABLED = os.getenv("DMS_ENABLED", "false").lower() == "true"
DMS_URL = os.getenv("DMS_URL", "http://localhost:8002/v1/chat/completions")
DMS_MODEL = os.getenv("DMS_MODEL", "nvidia/Qwen3-8B-DMS-8x")
DMS_API_KEY = os.getenv("DMS_API_KEY", "")
DMS_MODEL_PROVENANCE_ENFORCEMENT = (
    os.getenv("DMS_MODEL_PROVENANCE_ENFORCEMENT", "false").lower() == "true"
)
DMS_NON_COMMERCIAL_MODEL_WAIVER = (
    os.getenv("DMS_NON_COMMERCIAL_MODEL_WAIVER", "false").lower() == "true"
)
_raw_dms_reasoning_effort = os.getenv("DMS_REASONING_EFFORT", "").strip().lower()
DMS_REASONING_EFFORT = (
    _raw_dms_reasoning_effort
    if _raw_dms_reasoning_effort in {"low", "medium", "high"}
    else ""
)
DMS_PROMPT_CACHE_KEY_ENABLED = (
    os.getenv("DMS_PROMPT_CACHE_KEY_ENABLED", "false").lower() == "true"
)
_raw_dms_prompt_cache_key_prefix = os.getenv(
    "DMS_PROMPT_CACHE_KEY_PREFIX", "merlin:dms"
)
DMS_PROMPT_CACHE_KEY_PREFIX = _raw_dms_prompt_cache_key_prefix.strip() or "merlin:dms"
DMS_TRACE_HEADER_ENABLED = (
    os.getenv("DMS_TRACE_HEADER_ENABLED", "false").lower() == "true"
)
_raw_dms_trace_header_name = os.getenv("DMS_TRACE_HEADER_NAME", "X-Merlin-Request-Id")
DMS_TRACE_HEADER_NAME = _raw_dms_trace_header_name.strip() or "X-Merlin-Request-Id"
DMS_TIMEOUT_SPLIT_ENABLED = (
    os.getenv("DMS_TIMEOUT_SPLIT_ENABLED", "false").lower() == "true"
)
DMS_CONNECT_TIMEOUT_S = _coerce_positive_int(os.getenv("DMS_CONNECT_TIMEOUT_S"), 3)
DMS_READ_TIMEOUT_S = _coerce_positive_int(os.getenv("DMS_READ_TIMEOUT_S"), 45)
DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED = (
    os.getenv("DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED", "false").lower() == "true"
)
DMS_TIMEOUT_SHORT_S = _coerce_positive_int(
    os.getenv("DMS_TIMEOUT_SHORT_S"), DMS_READ_TIMEOUT_S
)
DMS_TIMEOUT_MEDIUM_S = _coerce_positive_int(
    os.getenv("DMS_TIMEOUT_MEDIUM_S"), DMS_READ_TIMEOUT_S
)
DMS_TIMEOUT_LONG_S = _coerce_positive_int(
    os.getenv("DMS_TIMEOUT_LONG_S"), DMS_READ_TIMEOUT_S
)
DMS_REQUEST_RATE_LIMIT_ENABLED = (
    os.getenv("DMS_REQUEST_RATE_LIMIT_ENABLED", "false").lower() == "true"
)
DMS_REQUEST_RATE_LIMIT_PER_MINUTE = _coerce_positive_int(
    os.getenv("DMS_REQUEST_RATE_LIMIT_PER_MINUTE"), 60
)
DMS_RETRY_MAX_ATTEMPTS = _coerce_positive_int(os.getenv("DMS_RETRY_MAX_ATTEMPTS"), 1)
DMS_MIN_PROMPT_CHARS = _coerce_positive_int(os.getenv("DMS_MIN_PROMPT_CHARS"), 6000)
DMS_MIN_PROMPT_TOKENS = _coerce_positive_int(os.getenv("DMS_MIN_PROMPT_TOKENS"), 1500)
DMS_TASK_TYPES = _parse_lower_list(
    os.getenv("DMS_TASK_TYPES", "analysis,code,planning")
)
DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED = (
    os.getenv("DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED", "false").lower() == "true"
)
DMS_UNCERTAINTY_ROUTING_ENABLED = (
    os.getenv("DMS_UNCERTAINTY_ROUTING_ENABLED", "false").lower() == "true"
)
_raw_dms_uncertainty_score_threshold = _optional_float(
    os.getenv("DMS_UNCERTAINTY_SCORE_THRESHOLD")
)
DMS_UNCERTAINTY_SCORE_THRESHOLD = max(
    0.0,
    min(
        1.0,
        (
            _raw_dms_uncertainty_score_threshold
            if _raw_dms_uncertainty_score_threshold is not None
            else 0.55
        ),
    ),
)
MERLIN_PROMPT_BUCKET_TOKEN_AWARE = (
    os.getenv("MERLIN_PROMPT_BUCKET_TOKEN_AWARE", "false").lower() == "true"
)
MERLIN_MODEL_TIMEOUT_SHORT_S = _coerce_positive_int(
    os.getenv("MERLIN_MODEL_TIMEOUT_SHORT_S"), 15
)
MERLIN_MODEL_TIMEOUT_MEDIUM_S = _coerce_positive_int(
    os.getenv("MERLIN_MODEL_TIMEOUT_MEDIUM_S"), 30
)
MERLIN_MODEL_TIMEOUT_LONG_S = _coerce_positive_int(
    os.getenv("MERLIN_MODEL_TIMEOUT_LONG_S"), 60
)
MERLIN_MODEL_TIMEOUT_MATRIX = _parse_model_timeout_matrix(
    os.getenv("MERLIN_MODEL_TIMEOUT_MATRIX"),
    default_short=MERLIN_MODEL_TIMEOUT_SHORT_S,
    default_medium=MERLIN_MODEL_TIMEOUT_MEDIUM_S,
    default_long=MERLIN_MODEL_TIMEOUT_LONG_S,
)
MERLIN_PROMPT_TOKEN_SOFT_LIMIT = _coerce_positive_int(
    os.getenv("MERLIN_PROMPT_TOKEN_SOFT_LIMIT"), 8192
)
MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET = _coerce_positive_int(
    os.getenv("MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET"), 7168
)
_raw_merlin_prompt_near_limit_ratio = _optional_float(
    os.getenv("MERLIN_PROMPT_NEAR_LIMIT_RATIO")
)
MERLIN_PROMPT_NEAR_LIMIT_RATIO = max(
    0.1,
    min(
        1.0,
        (
            _raw_merlin_prompt_near_limit_ratio
            if _raw_merlin_prompt_near_limit_ratio is not None
            else 0.9
        ),
    ),
)
MERLIN_LLM_RETRY_ENABLED = (
    os.getenv("MERLIN_LLM_RETRY_ENABLED", "false").lower() == "true"
)
MERLIN_LLM_RETRY_MAX_ATTEMPTS = _coerce_positive_int(
    os.getenv("MERLIN_LLM_RETRY_MAX_ATTEMPTS"), 2
)
MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS = _coerce_positive_int(
    os.getenv("MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS"), 100
)
MERLIN_LLM_RETRY_MAX_BACKOFF_MS = _coerce_positive_int(
    os.getenv("MERLIN_LLM_RETRY_MAX_BACKOFF_MS"), 1000
)
_raw_merlin_llm_retry_jitter_ratio = _optional_float(
    os.getenv("MERLIN_LLM_RETRY_JITTER_RATIO")
)
MERLIN_LLM_RETRY_JITTER_RATIO = max(
    0.0,
    min(
        1.0,
        (
            _raw_merlin_llm_retry_jitter_ratio
            if _raw_merlin_llm_retry_jitter_ratio is not None
            else 0.2
        ),
    ),
)
MERLIN_LLM_RETRY_BUDGET_MS = _coerce_positive_int(
    os.getenv("MERLIN_LLM_RETRY_BUDGET_MS"), 1500
)
MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED = (
    os.getenv("MERLIN_ROUTER_FAST_SHORT_LANE_ENABLED", "true").lower() == "true"
)
MERLIN_ROUTER_FAST_SHORT_CHAR_MAX = _coerce_positive_int(
    os.getenv("MERLIN_ROUTER_FAST_SHORT_CHAR_MAX"), 160
)
DMS_WARMUP_ENABLED = os.getenv("DMS_WARMUP_ENABLED", "false").lower() == "true"
DMS_WARMUP_TIMEOUT_S = _coerce_positive_int(os.getenv("DMS_WARMUP_TIMEOUT_S"), 5)
DMS_WARMUP_PROMPT = os.getenv("DMS_WARMUP_PROMPT", "Merlin DMS warmup probe.")
# DMS A/B control experiment: compare DMS routing against existing routing
DMS_AB_ENABLED = os.getenv("DMS_AB_ENABLED", "false").lower() == "true"
DMS_AB_DMS_PERCENTAGE = max(
    0,
    min(100, _optional_int(os.getenv("DMS_AB_DMS_PERCENTAGE", "50")) or 50),
)
DMS_SHADOW_VALIDATION_ENABLED = (
    os.getenv("DMS_SHADOW_VALIDATION_ENABLED", "false").lower() == "true"
)
DMS_QUALITY_AUTOPAUSE_ENABLED = (
    os.getenv("DMS_QUALITY_AUTOPAUSE_ENABLED", "false").lower() == "true"
)
DMS_QUALITY_AUTOPAUSE_WINDOW = _coerce_positive_int(
    os.getenv("DMS_QUALITY_AUTOPAUSE_WINDOW"), 10
)
DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES = _coerce_positive_int(
    os.getenv("DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES"), 5
)
_raw_dms_quality_autopause_min_avg_score = _optional_float(
    os.getenv("DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE")
)
DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE = max(
    0.0,
    min(
        1.0,
        (
            _raw_dms_quality_autopause_min_avg_score
            if _raw_dms_quality_autopause_min_avg_score is not None
            else 0.35
        ),
    ),
)
DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS = _coerce_positive_int(
    os.getenv("DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS"), 300
)
DMS_ERROR_BUDGET_ENABLED = (
    os.getenv("DMS_ERROR_BUDGET_ENABLED", "true").lower() == "true"
)
DMS_ERROR_BUDGET_WINDOW = _coerce_positive_int(os.getenv("DMS_ERROR_BUDGET_WINDOW"), 20)
DMS_ERROR_BUDGET_MIN_ATTEMPTS = _coerce_positive_int(
    os.getenv("DMS_ERROR_BUDGET_MIN_ATTEMPTS"), 5
)
_raw_dms_error_budget_max_failure_rate = _optional_float(
    os.getenv("DMS_ERROR_BUDGET_MAX_FAILURE_RATE")
)
DMS_ERROR_BUDGET_MAX_FAILURE_RATE = max(
    0.0,
    min(
        1.0,
        (
            _raw_dms_error_budget_max_failure_rate
            if _raw_dms_error_budget_max_failure_rate is not None
            else 0.5
        ),
    ),
)
DMS_ERROR_BUDGET_COOLDOWN_SECONDS = _coerce_positive_int(
    os.getenv("DMS_ERROR_BUDGET_COOLDOWN_SECONDS"), 300
)

# Research manager retention/archival policy
MERLIN_RESEARCH_SESSION_TTL_DAYS = _coerce_positive_int(
    os.getenv("MERLIN_RESEARCH_SESSION_TTL_DAYS"), 90
)
MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED = (
    os.getenv("MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED", "true").lower() == "true"
)

# Nemotron 3 Configuration
NEMOTRON_API_KEY = os.getenv("NEMOTRON_API_KEY", "")
NEMOTRON_URL = os.getenv("NEMOTRON_URL", "http://localhost:8001/v1/chat/completions")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3")

# GLM Configuration
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_URL = os.getenv("GLM_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-4")

# Nomic Configuration
NOMIC_URL = os.getenv("NOMIC_URL", "http://localhost:11434/api/chat")
NOMIC_MODEL = os.getenv("NOMIC_MODEL", "nomic-embed-text")

# HuggingFace Configuration
HF_API_KEY = os.getenv("HF_API_KEY", "")
HF_API_URL = os.getenv(
    "HF_API_URL",
    "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
)
HF_TIMEOUT = int(os.getenv("HF_TIMEOUT", "60"))

# Voice Configuration
MERLIN_VOICE_PRIMARY_ENGINE = os.getenv("MERLIN_VOICE_PRIMARY_ENGINE", "xtts")
MERLIN_VOICE_FALLBACK_ENGINE = os.getenv("MERLIN_VOICE_FALLBACK_ENGINE", "pyttsx3")
MERLIN_VOICE_XTTS_MODEL = os.getenv("MERLIN_VOICE_XTTS_MODEL", "")
MERLIN_VOICE_XTTS_DEVICE = os.getenv("MERLIN_VOICE_XTTS_DEVICE", "cuda")
MERLIN_VOICE_XTTS_LANGUAGE = os.getenv("MERLIN_VOICE_XTTS_LANGUAGE", "en")
MERLIN_VOICE_REFERENCE_WAV = os.getenv("MERLIN_VOICE_REFERENCE_WAV", "")
MERLIN_VOICE_PIPER_PATH = os.getenv("MERLIN_VOICE_PIPER_PATH", "piper")
MERLIN_VOICE_PIPER_MODEL = os.getenv("MERLIN_VOICE_PIPER_MODEL", "")
MERLIN_VOICE_PIPER_SPEAKER_ID = _optional_int(
    os.getenv("MERLIN_VOICE_PIPER_SPEAKER_ID")
)
MERLIN_VOICE_PIPER_LENGTH_SCALE = _optional_float(
    os.getenv("MERLIN_VOICE_PIPER_LENGTH_SCALE")
)
MERLIN_VOICE_PIPER_NOISE_SCALE = _optional_float(
    os.getenv("MERLIN_VOICE_PIPER_NOISE_SCALE")
)
MERLIN_VOICE_PIPER_NOISE_W = _optional_float(os.getenv("MERLIN_VOICE_PIPER_NOISE_W"))
MERLIN_VOICE_PLAYBACK = os.getenv("MERLIN_VOICE_PLAYBACK", "true").lower() == "true"
MERLIN_VOICE_PLAYBACK_COMMAND = os.getenv("MERLIN_VOICE_PLAYBACK_COMMAND", "")
MERLIN_VOICE_CACHE_DIR = os.getenv("MERLIN_VOICE_CACHE_DIR", "artifacts/voice")
MERLIN_VOICE_KEEP_TEMP_AUDIO = (
    os.getenv("MERLIN_VOICE_KEEP_TEMP_AUDIO", "false").lower() == "true"
)

# Speech-to-Text Configuration
MERLIN_STT_PRIMARY_ENGINE = os.getenv("MERLIN_STT_PRIMARY_ENGINE", "google")
MERLIN_STT_FALLBACK_ENGINE = os.getenv("MERLIN_STT_FALLBACK_ENGINE", "whisper")
MERLIN_STT_GOOGLE_LANGUAGE = os.getenv("MERLIN_STT_GOOGLE_LANGUAGE", "en-US")
MERLIN_STT_WHISPER_MODEL = os.getenv("MERLIN_STT_WHISPER_MODEL", "whisper-1")
MERLIN_STT_WHISPER_LANGUAGE = os.getenv("MERLIN_STT_WHISPER_LANGUAGE", "")
MERLIN_STT_WHISPER_BASE_URL = os.getenv(
    "MERLIN_STT_WHISPER_BASE_URL", "https://api.openai.com/v1"
)
MERLIN_STT_WHISPER_TIMEOUT_S = _optional_float(
    os.getenv("MERLIN_STT_WHISPER_TIMEOUT_S", "60")
)
MERLIN_STT_TIMEOUT_S = _optional_float(os.getenv("MERLIN_STT_TIMEOUT_S", "5"))
MERLIN_STT_PHRASE_TIME_LIMIT_S = _optional_float(
    os.getenv("MERLIN_STT_PHRASE_TIME_LIMIT_S", "12")
)
MERLIN_STT_DYNAMIC_ENERGY = (
    os.getenv("MERLIN_STT_DYNAMIC_ENERGY", "true").lower() == "true"
)
MERLIN_STT_ENERGY_THRESHOLD = _optional_int(os.getenv("MERLIN_STT_ENERGY_THRESHOLD"))

# Security
MERLIN_API_KEY = os.getenv("MERLIN_API_KEY", "merlin-secret-key")

# Operation envelope payload-size controls
MERLIN_OPERATION_PAYLOAD_MAX_BYTES = _coerce_positive_int(
    os.getenv("MERLIN_OPERATION_PAYLOAD_MAX_BYTES"), 262144
)
MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION = _parse_operation_payload_limits(
    os.getenv("MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION")
)
MERLIN_OPERATION_METRICS_MAX_SAMPLES = _coerce_positive_int(
    os.getenv("MERLIN_OPERATION_METRICS_MAX_SAMPLES"), 512
)
MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE = max(
    0, _optional_int(os.getenv("MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", "0")) or 0
)
MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION = _parse_operation_payload_limits(
    os.getenv("MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION")
)
MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED = (
    os.getenv("MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED", "false").lower() == "true"
)
MERLIN_OPERATION_FEATURE_FLAGS = _parse_operation_feature_flags(
    os.getenv("MERLIN_OPERATION_FEATURE_FLAGS")
)
MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED = (
    os.getenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"
)
MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD = _coerce_positive_int(
    os.getenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD"), 3
)
MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS = _coerce_positive_int(
    os.getenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS"), 30
)
MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS = max(
    0, _optional_int(os.getenv("MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS", "2")) or 2
)
_raw_plugin_execution_mode = (
    str(os.getenv("MERLIN_PLUGIN_EXECUTION_MODE", "process")).strip().lower()
)
MERLIN_PLUGIN_EXECUTION_MODE = (
    _raw_plugin_execution_mode
    if _raw_plugin_execution_mode in {"process", "thread"}
    else "process"
)
MERLIN_PLUGIN_PROCESS_POOL_SIZE = _coerce_positive_int(
    os.getenv("MERLIN_PLUGIN_PROCESS_POOL_SIZE"),
    2,
)
MERLIN_SQLITE_JOURNAL_MODE = _parse_upper_choice(
    os.getenv("MERLIN_SQLITE_JOURNAL_MODE"),
    allowed={"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"},
    default="WAL",
)
MERLIN_SQLITE_SYNCHRONOUS = _parse_upper_choice(
    os.getenv("MERLIN_SQLITE_SYNCHRONOUS"),
    allowed={"OFF", "NORMAL", "FULL", "EXTRA"},
    default="NORMAL",
)
MERLIN_SQLITE_BUSY_TIMEOUT_MS = _coerce_positive_int(
    os.getenv("MERLIN_SQLITE_BUSY_TIMEOUT_MS"),
    5000,
)
MERLIN_SQLITE_WAL_AUTOCHECKPOINT = _coerce_positive_int(
    os.getenv("MERLIN_SQLITE_WAL_AUTOCHECKPOINT"),
    1000,
)
MERLIN_SQLITE_CACHE_SIZE_KB = _coerce_positive_int(
    os.getenv("MERLIN_SQLITE_CACHE_SIZE_KB"),
    8192,
)
MERLIN_SQLITE_TEMP_STORE = _parse_upper_choice(
    os.getenv("MERLIN_SQLITE_TEMP_STORE"),
    allowed={"DEFAULT", "FILE", "MEMORY"},
    default="MEMORY",
)

# Path to Dev Library
DEV_LIBRARY_PATH = "D:/Dev library/AaroneousAutomationSuite"

# Runtime directories
MERLIN_CHAT_HISTORY_DIR = Path(
    os.getenv("MERLIN_CHAT_HISTORY_DIR", "merlin_chat_history")
)
MERLIN_CHAT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

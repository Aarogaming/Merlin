import importlib
from pathlib import Path


def test_parse_list_and_env_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings._parse_list("a, b, ,c") == ["a", "b", "c"]
    assert settings._parse_list("") == []
    assert settings._parse_list(None) == []

    assert settings.MERLIN_CHAT_HISTORY_DIR == Path(tmp_path / "history")
    assert settings.MERLIN_CHAT_HISTORY_DIR.exists()


def test_operation_payload_limit_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_OPERATION_PAYLOAD_MAX_BYTES", "2048")
    monkeypatch.setenv("MERLIN_OPERATION_METRICS_MAX_SAMPLES", "321")
    monkeypatch.setenv("MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE", "99")
    monkeypatch.setenv(
        "MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION",
        "assistant.chat.request=256, merlin.rag.query=4096, bad-token,=123,x=-1",
    )
    monkeypatch.setenv(
        "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION",
        "assistant.chat.request=3, merlin.rag.query=7, bad-token, nope=-1",
    )
    monkeypatch.setenv("MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setenv(
        "MERLIN_OPERATION_FEATURE_FLAGS",
        "merlin.plugins.execute=disabled,merlin.tasks.create=enabled,invalid-token",
    )
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_OPERATION_PAYLOAD_MAX_BYTES == 2048
    assert settings.MERLIN_OPERATION_METRICS_MAX_SAMPLES == 321
    assert settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE == 99
    assert settings.MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION == {
        "assistant.chat.request": 256,
        "merlin.rag.query": 4096,
    }
    assert settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION == {
        "assistant.chat.request": 3,
        "merlin.rag.query": 7,
    }
    assert settings.MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED is True
    assert settings.MERLIN_OPERATION_FEATURE_FLAGS == {
        "merlin.plugins.execute": False,
        "merlin.tasks.create": True,
    }


def test_dependency_circuit_breaker_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "7")
    monkeypatch.setenv("MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS", "45")
    monkeypatch.setenv("MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS", "4")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED is False
    assert settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD == 7
    assert settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS == 45
    assert settings.MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS == 4


def test_plugin_execution_mode_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_PLUGIN_EXECUTION_MODE", "thread")
    monkeypatch.setenv("MERLIN_PLUGIN_PROCESS_POOL_SIZE", "5")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_PLUGIN_EXECUTION_MODE == "thread"
    assert settings.MERLIN_PLUGIN_PROCESS_POOL_SIZE == 5

    monkeypatch.setenv("MERLIN_PLUGIN_EXECUTION_MODE", "invalid")
    monkeypatch.setenv("MERLIN_PLUGIN_PROCESS_POOL_SIZE", "0")
    settings = importlib.reload(settings)
    assert settings.MERLIN_PLUGIN_EXECUTION_MODE == "process"
    assert settings.MERLIN_PLUGIN_PROCESS_POOL_SIZE == 2


def test_sqlite_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_SQLITE_JOURNAL_MODE", "wal")
    monkeypatch.setenv("MERLIN_SQLITE_SYNCHRONOUS", "normal")
    monkeypatch.setenv("MERLIN_SQLITE_BUSY_TIMEOUT_MS", "6400")
    monkeypatch.setenv("MERLIN_SQLITE_WAL_AUTOCHECKPOINT", "444")
    monkeypatch.setenv("MERLIN_SQLITE_CACHE_SIZE_KB", "3072")
    monkeypatch.setenv("MERLIN_SQLITE_TEMP_STORE", "memory")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_SQLITE_JOURNAL_MODE == "WAL"
    assert settings.MERLIN_SQLITE_SYNCHRONOUS == "NORMAL"
    assert settings.MERLIN_SQLITE_BUSY_TIMEOUT_MS == 6400
    assert settings.MERLIN_SQLITE_WAL_AUTOCHECKPOINT == 444
    assert settings.MERLIN_SQLITE_CACHE_SIZE_KB == 3072
    assert settings.MERLIN_SQLITE_TEMP_STORE == "MEMORY"


def test_http_runtime_tuning_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_API_HOST", "127.0.0.1")
    monkeypatch.setenv("MERLIN_API_PORT", "8100")
    monkeypatch.setenv("MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S", "21")
    monkeypatch.setenv("MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S", "45")
    monkeypatch.setenv("MERLIN_HTTP_LIMIT_CONCURRENCY", "128")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_API_HOST == "127.0.0.1"
    assert settings.MERLIN_API_PORT == 8100
    assert settings.MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S == 21
    assert settings.MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S == 45
    assert settings.MERLIN_HTTP_LIMIT_CONCURRENCY == 128


def test_maturity_tier_and_policy_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_MATURITY_TIER", "m3")
    monkeypatch.setenv("MERLIN_MATURITY_POLICY_VERSION", "  mdmm-policy-v2  ")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_MATURITY_TIER == "M3"
    assert settings.MERLIN_MATURITY_POLICY_VERSION == "mdmm-policy-v2"

    monkeypatch.setenv("MERLIN_MATURITY_TIER", "invalid-tier")
    monkeypatch.setenv("MERLIN_MATURITY_POLICY_VERSION", "   ")
    settings = importlib.reload(settings)
    assert settings.MERLIN_MATURITY_TIER == "M0"
    assert settings.MERLIN_MATURITY_POLICY_VERSION == "mdmm-2026-02-22"


def test_maturity_operation_allowlist_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv(
        "MERLIN_MATURITY_OPERATION_ALLOWLISTS",
        (
            '{"M0":["assistant.chat.request"," merlin.tasks.list "],'
            '"m1":"*",'
            '"M2":[],'
            '"M3":["merlin.alerts.list", 7],'
            '"M9":["ignored.operation"]}'
        ),
    )
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS["M0"] == frozenset(
        {"assistant.chat.request", "merlin.tasks.list"}
    )
    assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS["M1"] == frozenset({"*"})
    assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS["M2"] == frozenset()
    assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS["M3"] == frozenset(
        {"merlin.alerts.list"}
    )
    assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS["M4"] == frozenset({"*"})

    monkeypatch.setenv("MERLIN_MATURITY_OPERATION_ALLOWLISTS", "not-json")
    settings = importlib.reload(settings)
    for tier in settings.MERLIN_ALLOWED_MATURITY_TIERS:
        assert settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS[tier] == frozenset({"*"})


def test_dms_error_budget_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_ERROR_BUDGET_ENABLED", "true")
    monkeypatch.setenv("DMS_ERROR_BUDGET_WINDOW", "11")
    monkeypatch.setenv("DMS_ERROR_BUDGET_MIN_ATTEMPTS", "4")
    monkeypatch.setenv("DMS_ERROR_BUDGET_MAX_FAILURE_RATE", "1.4")
    monkeypatch.setenv("DMS_ERROR_BUDGET_COOLDOWN_SECONDS", "45")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_ERROR_BUDGET_ENABLED is True
    assert settings.DMS_ERROR_BUDGET_WINDOW == 11
    assert settings.DMS_ERROR_BUDGET_MIN_ATTEMPTS == 4
    assert settings.DMS_ERROR_BUDGET_MAX_FAILURE_RATE == 1.0
    assert settings.DMS_ERROR_BUDGET_COOLDOWN_SECONDS == 45


def test_dms_uncertainty_routing_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_UNCERTAINTY_ROUTING_ENABLED", "true")
    monkeypatch.setenv("DMS_UNCERTAINTY_SCORE_THRESHOLD", "1.4")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_UNCERTAINTY_ROUTING_ENABLED is True
    assert settings.DMS_UNCERTAINTY_SCORE_THRESHOLD == 1.0

    monkeypatch.setenv("DMS_UNCERTAINTY_SCORE_THRESHOLD", "-0.2")
    settings = importlib.reload(settings)
    assert settings.DMS_UNCERTAINTY_SCORE_THRESHOLD == 0.0


def test_dms_sensitive_task_guardrail_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED", "true")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_SENSITIVE_TASK_GUARDRAIL_ENABLED is True


def test_dms_model_provenance_policy_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_MODEL_PROVENANCE_ENFORCEMENT", "true")
    monkeypatch.setenv("DMS_NON_COMMERCIAL_MODEL_WAIVER", "true")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_MODEL_PROVENANCE_ENFORCEMENT is True
    assert settings.DMS_NON_COMMERCIAL_MODEL_WAIVER is True


def test_dms_reasoning_effort_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_REASONING_EFFORT", "HIGH")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_REASONING_EFFORT == "high"

    monkeypatch.setenv("DMS_REASONING_EFFORT", "invalid-value")
    settings = importlib.reload(settings)
    assert settings.DMS_REASONING_EFFORT == ""


def test_dms_prompt_cache_key_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_PROMPT_CACHE_KEY_ENABLED", "true")
    monkeypatch.setenv("DMS_PROMPT_CACHE_KEY_PREFIX", "  merlin:route-cache  ")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_PROMPT_CACHE_KEY_ENABLED is True
    assert settings.DMS_PROMPT_CACHE_KEY_PREFIX == "merlin:route-cache"

    monkeypatch.setenv("DMS_PROMPT_CACHE_KEY_PREFIX", "   ")
    settings = importlib.reload(settings)
    assert settings.DMS_PROMPT_CACHE_KEY_PREFIX == "merlin:dms"


def test_dms_trace_header_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_TRACE_HEADER_ENABLED", "true")
    monkeypatch.setenv("DMS_TRACE_HEADER_NAME", "  X-Trace-Request  ")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_TRACE_HEADER_ENABLED is True
    assert settings.DMS_TRACE_HEADER_NAME == "X-Trace-Request"

    monkeypatch.setenv("DMS_TRACE_HEADER_NAME", "   ")
    settings = importlib.reload(settings)
    assert settings.DMS_TRACE_HEADER_NAME == "X-Merlin-Request-Id"


def test_dms_timeout_and_retry_profile_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_TIMEOUT_SPLIT_ENABLED", "true")
    monkeypatch.setenv("DMS_CONNECT_TIMEOUT_S", "2")
    monkeypatch.setenv("DMS_READ_TIMEOUT_S", "40")
    monkeypatch.setenv("DMS_RETRY_MAX_ATTEMPTS", "3")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_TIMEOUT_SPLIT_ENABLED is True
    assert settings.DMS_CONNECT_TIMEOUT_S == 2
    assert settings.DMS_READ_TIMEOUT_S == 40
    assert settings.DMS_RETRY_MAX_ATTEMPTS == 3


def test_dms_prompt_bucket_timeout_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED", "true")
    monkeypatch.setenv("DMS_READ_TIMEOUT_S", "41")
    monkeypatch.setenv("DMS_TIMEOUT_SHORT_S", "5")
    monkeypatch.setenv("DMS_TIMEOUT_MEDIUM_S", "9")
    monkeypatch.setenv("DMS_TIMEOUT_LONG_S", "13")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_PROMPT_BUCKET_TIMEOUTS_ENABLED is True
    assert settings.DMS_TIMEOUT_SHORT_S == 5
    assert settings.DMS_TIMEOUT_MEDIUM_S == 9
    assert settings.DMS_TIMEOUT_LONG_S == 13

    monkeypatch.setenv("DMS_TIMEOUT_SHORT_S", "0")
    monkeypatch.setenv("DMS_TIMEOUT_MEDIUM_S", "-3")
    monkeypatch.setenv("DMS_TIMEOUT_LONG_S", "bad")
    settings = importlib.reload(settings)
    assert settings.DMS_TIMEOUT_SHORT_S == 41
    assert settings.DMS_TIMEOUT_MEDIUM_S == 41
    assert settings.DMS_TIMEOUT_LONG_S == 41


def test_dms_request_rate_limit_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_REQUEST_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DMS_REQUEST_RATE_LIMIT_PER_MINUTE", "7")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_REQUEST_RATE_LIMIT_ENABLED is True
    assert settings.DMS_REQUEST_RATE_LIMIT_PER_MINUTE == 7

    monkeypatch.setenv("DMS_REQUEST_RATE_LIMIT_PER_MINUTE", "-1")
    settings = importlib.reload(settings)
    assert settings.DMS_REQUEST_RATE_LIMIT_PER_MINUTE == 60


def test_dms_shadow_validation_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_SHADOW_VALIDATION_ENABLED", "true")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_SHADOW_VALIDATION_ENABLED is True


def test_dms_quality_autopause_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_ENABLED", "true")
    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_WINDOW", "7")
    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES", "3")
    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE", "1.4")
    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS", "42")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.DMS_QUALITY_AUTOPAUSE_ENABLED is True
    assert settings.DMS_QUALITY_AUTOPAUSE_WINDOW == 7
    assert settings.DMS_QUALITY_AUTOPAUSE_MIN_SAMPLES == 3
    assert settings.DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE == 1.0
    assert settings.DMS_QUALITY_AUTOPAUSE_COOLDOWN_SECONDS == 42

    monkeypatch.setenv("DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE", "-0.5")
    settings = importlib.reload(settings)
    assert settings.DMS_QUALITY_AUTOPAUSE_MIN_AVG_SCORE == 0.0


def test_research_archive_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_RESEARCH_SESSION_TTL_DAYS", "30")
    monkeypatch.setenv("MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED", "false")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_RESEARCH_SESSION_TTL_DAYS == 30
    assert settings.MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED is False


def test_prompt_bucket_and_timeout_matrix_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_PROMPT_BUCKET_TOKEN_AWARE", "true")
    monkeypatch.setenv("DMS_MIN_PROMPT_TOKENS", "2048")
    monkeypatch.setenv("MERLIN_MODEL_TIMEOUT_SHORT_S", "12")
    monkeypatch.setenv("MERLIN_MODEL_TIMEOUT_MEDIUM_S", "34")
    monkeypatch.setenv("MERLIN_MODEL_TIMEOUT_LONG_S", "56")
    monkeypatch.setenv(
        "MERLIN_MODEL_TIMEOUT_MATRIX",
        "dms.short=20,dms.long=90,openai.medium=40,bad-token,dms.invalid=7,foo.short=-1",
    )
    monkeypatch.setenv("DMS_WARMUP_ENABLED", "true")
    monkeypatch.setenv("DMS_WARMUP_TIMEOUT_S", "9")
    monkeypatch.setenv("DMS_WARMUP_PROMPT", "probe")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_PROMPT_BUCKET_TOKEN_AWARE is True
    assert settings.DMS_MIN_PROMPT_TOKENS == 2048
    assert settings.MERLIN_MODEL_TIMEOUT_SHORT_S == 12
    assert settings.MERLIN_MODEL_TIMEOUT_MEDIUM_S == 34
    assert settings.MERLIN_MODEL_TIMEOUT_LONG_S == 56
    assert settings.MERLIN_MODEL_TIMEOUT_MATRIX["default"] == {
        "short": 12,
        "medium": 34,
        "long": 56,
    }
    assert settings.MERLIN_MODEL_TIMEOUT_MATRIX["dms"] == {
        "short": 20,
        "medium": 34,
        "long": 90,
    }
    assert settings.MERLIN_MODEL_TIMEOUT_MATRIX["openai"] == {
        "short": 12,
        "medium": 40,
        "long": 56,
    }
    assert settings.DMS_WARMUP_ENABLED is True
    assert settings.DMS_WARMUP_TIMEOUT_S == 9
    assert settings.DMS_WARMUP_PROMPT == "probe"


def test_prompt_preflight_token_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_PROMPT_TOKEN_SOFT_LIMIT", "4096")
    monkeypatch.setenv("MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET", "2048")
    monkeypatch.setenv("MERLIN_PROMPT_NEAR_LIMIT_RATIO", "1.5")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_PROMPT_TOKEN_SOFT_LIMIT == 4096
    assert settings.MERLIN_PROMPT_TOKEN_TRUNCATE_TARGET == 2048
    assert settings.MERLIN_PROMPT_NEAR_LIMIT_RATIO == 1.0

    monkeypatch.setenv("MERLIN_PROMPT_NEAR_LIMIT_RATIO", "0.01")
    settings = importlib.reload(settings)
    assert settings.MERLIN_PROMPT_NEAR_LIMIT_RATIO == 0.1


def test_llm_retry_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_LLM_RETRY_ENABLED", "true")
    monkeypatch.setenv("MERLIN_LLM_RETRY_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS", "250")
    monkeypatch.setenv("MERLIN_LLM_RETRY_MAX_BACKOFF_MS", "2000")
    monkeypatch.setenv("MERLIN_LLM_RETRY_JITTER_RATIO", "1.5")
    monkeypatch.setenv("MERLIN_LLM_RETRY_BUDGET_MS", "3200")
    settings = importlib.import_module("merlin_settings")
    settings = importlib.reload(settings)

    assert settings.MERLIN_LLM_RETRY_ENABLED is True
    assert settings.MERLIN_LLM_RETRY_MAX_ATTEMPTS == 5
    assert settings.MERLIN_LLM_RETRY_INITIAL_BACKOFF_MS == 250
    assert settings.MERLIN_LLM_RETRY_MAX_BACKOFF_MS == 2000
    assert settings.MERLIN_LLM_RETRY_JITTER_RATIO == 1.0
    assert settings.MERLIN_LLM_RETRY_BUDGET_MS == 3200

    monkeypatch.setenv("MERLIN_LLM_RETRY_JITTER_RATIO", "-0.1")
    settings = importlib.reload(settings)
    assert settings.MERLIN_LLM_RETRY_JITTER_RATIO == 0.0

import subprocess
import sys
import os
from datetime import datetime, timezone
from typing import Any, Callable


def run_step(name: str, command: list):
    print(f"\n>>> Running {name}...")
    try:
        subprocess.run(command, check=True)
        print(f"✅ {name} passed!")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {name} failed!")
        return False
    except FileNotFoundError:
        print(f"⚠️ {name} skipped (tool not found)")
        return True


QualityScoringHook = Callable[[str, str, str, dict[str, Any]], float | dict[str, Any] | None]
_quality_scoring_hook: QualityScoringHook | None = None
PlannerFallbackTelemetrySink = Callable[[dict[str, Any]], dict[str, Any] | None]
_planner_fallback_telemetry_sink: PlannerFallbackTelemetrySink | None = None


def register_quality_scoring_hook(hook: QualityScoringHook | None) -> None:
    global _quality_scoring_hook
    _quality_scoring_hook = hook


def clear_quality_scoring_hook() -> None:
    register_quality_scoring_hook(None)


def register_planner_fallback_telemetry_sink(
    sink: PlannerFallbackTelemetrySink | None,
) -> None:
    global _planner_fallback_telemetry_sink
    _planner_fallback_telemetry_sink = sink


def clear_planner_fallback_telemetry_sink() -> None:
    register_planner_fallback_telemetry_sink(None)


def _normalize_planner_fallback_telemetry(
    *,
    session_id: str,
    metadata: dict[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})

    fallback_reason_code_raw = payload.get("fallback_reason_code")
    if isinstance(fallback_reason_code_raw, str) and fallback_reason_code_raw.strip():
        fallback_reason_code = fallback_reason_code_raw.strip().lower()
    else:
        fallback_reason_code = "none"

    fallback_reason_raw = payload.get("fallback_reason")
    fallback_reason = (
        fallback_reason_raw.strip()
        if isinstance(fallback_reason_raw, str) and fallback_reason_raw.strip()
        else ""
    )

    fallback_detail_raw = payload.get("fallback_detail")
    fallback_detail = (
        fallback_detail_raw.strip()
        if isinstance(fallback_detail_raw, str) and fallback_detail_raw.strip()
        else ""
    )

    fallback_stage_raw = payload.get("fallback_stage")
    fallback_stage = (
        fallback_stage_raw.strip().lower()
        if isinstance(fallback_stage_raw, str) and fallback_stage_raw.strip()
        else "unspecified"
    )

    selected_model_raw = payload.get("selected_model")
    selected_model = (
        selected_model_raw.strip()
        if isinstance(selected_model_raw, str) and selected_model_raw.strip()
        else "unknown"
    )

    router_backend_raw = payload.get("router_backend")
    router_backend = (
        router_backend_raw.strip()
        if isinstance(router_backend_raw, str) and router_backend_raw.strip()
        else "unknown"
    )

    router_policy_version_raw = payload.get("router_policy_version")
    router_policy_version = (
        router_policy_version_raw.strip()
        if isinstance(router_policy_version_raw, str) and router_policy_version_raw.strip()
        else "unknown"
    )

    routing_schema_raw = payload.get("routing_telemetry_schema")
    routing_schema = (
        routing_schema_raw.strip()
        if isinstance(routing_schema_raw, str) and routing_schema_raw.strip()
        else "unknown"
    )

    return {
        "session_id": session_id,
        "source": source.strip() if source.strip() else "assistant.chat.request",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_model": selected_model,
        "dms_used": bool(payload.get("dms_used", False)),
        "dms_candidate": bool(payload.get("dms_candidate", False)),
        "dms_attempted": bool(payload.get("dms_attempted", False)),
        "fallback_reason_code": fallback_reason_code,
        "fallback_reason": fallback_reason,
        "fallback_detail": fallback_detail,
        "fallback_stage": fallback_stage,
        "fallback_retryable": bool(payload.get("fallback_retryable", False)),
        "router_backend": router_backend,
        "router_policy_version": router_policy_version,
        "routing_telemetry_schema": routing_schema,
    }


def ingest_planner_fallback_telemetry(
    *,
    session_id: str,
    metadata: dict[str, Any] | None,
    source: str = "assistant.chat.request",
) -> dict[str, Any]:
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        return {
            "ingested": False,
            "reason": "missing_session_id",
            "telemetry": None,
        }

    telemetry = _normalize_planner_fallback_telemetry(
        session_id=normalized_session_id,
        metadata=metadata,
        source=source,
    )

    if _planner_fallback_telemetry_sink is None:
        return {
            "ingested": False,
            "reason": "no_sink",
            "telemetry": telemetry,
        }

    try:
        sink_result = _planner_fallback_telemetry_sink(dict(telemetry))
    except Exception as error:
        return {
            "ingested": False,
            "reason": "sink_error",
            "error": str(error),
            "telemetry": telemetry,
        }

    result: dict[str, Any] = {
        "ingested": True,
        "telemetry": telemetry,
    }
    if sink_result is not None:
        result["sink_result"] = sink_result
    return result


def score_response_quality_with_hook(
    *,
    query: str,
    variant: str,
    response: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _quality_scoring_hook is None:
        return {
            "applied": False,
            "score": None,
            "source": "none",
            "error": None,
        }

    hook_context = dict(context or {})
    try:
        hook_result = _quality_scoring_hook(query, variant, response, hook_context)
        if isinstance(hook_result, dict):
            raw_score = hook_result.get("score")
            source = str(hook_result.get("source", "custom"))
        else:
            raw_score = hook_result
            source = "custom"
        if raw_score is None:
            return {
                "applied": False,
                "score": None,
                "source": source,
                "error": None,
            }
        return {
            "applied": True,
            "score": float(raw_score),
            "source": source,
            "error": None,
        }
    except Exception as error:
        return {
            "applied": False,
            "score": None,
            "source": "error",
            "error": str(error),
        }


def main():
    print("=" * 40)
    print("Merlin Merlin - Quality Gates")
    print("=" * 40)

    # Determine python path (prefer venv if active)
    python_exe = sys.executable

    steps = [
        ("Formatting Check (Black)", [python_exe, "-m", "black", "--check", "."]),
        ("Type Check (Mypy)", [python_exe, "-m", "mypy", "."]),
        ("Unit Tests (Pytest)", [python_exe, "-m", "pytest"]),
    ]

    all_passed = True
    for name, cmd in steps:
        if not run_step(name, cmd):
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 All quality gates passed!")
        sys.exit(0)
    else:
        print("🚫 Some quality gates failed. Please fix the issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()

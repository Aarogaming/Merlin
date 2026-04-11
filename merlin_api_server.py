# Merlin REST API server for Unity/Unreal integration
import os
import sys
from pathlib import Path

# Ensure shared core modules are importable
_MERLIN_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _MERLIN_ROOT.parent
_CORE_PATH = _REPO_ROOT / "core"
if str(_CORE_PATH) not in sys.path:
    sys.path.insert(0, str(_CORE_PATH))
if str(_MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_MERLIN_ROOT))

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
)
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from typing import Any, Callable, List, cast

_slowapi_limiter: Any | None = None
_slowapi_error_handler: Any | None = None
_slowapi_get_remote_address: Callable[[Request], str] | None = None
_slowapi_rate_limit_exceeded: type[Exception] | None = None

try:
    from slowapi import Limiter as _SlowapiLimiter
    from slowapi import _rate_limit_exceeded_handler as _slowapi_handler
    from slowapi.util import get_remote_address as _slowapi_remote_address
    from slowapi.errors import RateLimitExceeded as _SlowapiRateLimitExceeded

    _slowapi_limiter = _SlowapiLimiter
    _slowapi_error_handler = _slowapi_handler
    _slowapi_get_remote_address = _slowapi_remote_address
    _slowapi_rate_limit_exceeded = _SlowapiRateLimitExceeded
except ModuleNotFoundError:
    pass

_SLOWAPI_AVAILABLE = (
    _slowapi_limiter is not None
    and _slowapi_error_handler is not None
    and _slowapi_get_remote_address is not None
    and _slowapi_rate_limit_exceeded is not None
)

if _SLOWAPI_AVAILABLE:
    RateLimitExceeded = cast(type[Exception], _slowapi_rate_limit_exceeded)
    Limiter = cast(Any, _slowapi_limiter)

    def get_remote_address(request: Request) -> str:
        key_func = cast(Callable[[Request], str], _slowapi_get_remote_address)
        return key_func(request)

    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        handler = cast(Callable[[Request, Exception], Any], _slowapi_error_handler)
        return cast(JSONResponse, handler(request, exc))

else:

    class _FallbackRateLimitExceeded(Exception):
        pass

    class _FallbackLimiter:
        def __init__(self, key_func: Any = None, *args: Any, **kwargs: Any) -> None:
            self.key_func = key_func

        def limit(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                return func

            return decorator

    RateLimitExceeded = _FallbackRateLimitExceeded
    Limiter = _FallbackLimiter

    def get_remote_address(request: Request) -> str:
        client = getattr(request, "client", None)
        host = getattr(client, "host", None)
        return host if isinstance(host, str) and host else "unknown"

    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded; slowapi is not installed in this environment."
            },
        )


_prometheus_instrumentator: type[Any] | None = None
try:
    from prometheus_fastapi_instrumentator import (
        Instrumentator as _PrometheusInstrumentator,
    )

    _prometheus_instrumentator = _PrometheusInstrumentator
except ModuleNotFoundError:
    pass

if _prometheus_instrumentator is None:

    class _FallbackInstrumentator:
        def instrument(self, app: FastAPI) -> "_FallbackInstrumentator":
            return self

        def expose(self, app: FastAPI) -> "_FallbackInstrumentator":
            return self

    Instrumentator: type[Any] = _FallbackInstrumentator
else:
    Instrumentator = _prometheus_instrumentator


from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
from threading import Lock
import uvicorn
import importlib
from merlin_system_info import get_system_info
from merlin_file_manager import list_files, delete_file, move_file, open_file
from merlin_command_executor import execute_command
from merlin_logger import merlin_logger, get_recent_logs, log_with_context

try:
    from merlin_policy import policy_manager, evaluate_operation_mentor_pass
except ImportError:
    from merlin_policy import policy_manager

    _FALLBACK_VALID_MATURITY_TIERS: frozenset[str] = frozenset(
        {"M0", "M1", "M2", "M3", "M4"}
    )
    _FALLBACK_DEFAULT_REQUIRED_TIERS: frozenset[str] = frozenset({"M1"})
    _FALLBACK_HIGH_RISK_OPERATION_CLASSES: dict[str, frozenset[str]] = {
        "command_execution": frozenset({"merlin.command.execute"}),
        "tool_execution": frozenset(
            {
                "assistant.tools.execute",
                "merlin.plugins.execute",
            }
        ),
        "state_mutation": frozenset(
            {
                "merlin.context.update",
                "merlin.discovery.run",
                "merlin.discovery.queue.drain",
                "merlin.discovery.queue.pause",
                "merlin.discovery.queue.resume",
                "merlin.discovery.queue.purge_deadletter",
                "merlin.seed.control",
                "merlin.tasks.create",
                "merlin.user_manager.create",
                "merlin.genesis.manifest",
                "merlin.aas.create_task",
                "merlin.research.manager.session.create",
                "merlin.research.manager.session.signal.add",
            }
        ),
    }

    def _fallback_parse_required_tiers() -> frozenset[str]:
        raw_value = os.environ.get("MERLIN_MENTOR_PASS_REQUIRED_TIERS")
        if raw_value is None:
            return _FALLBACK_DEFAULT_REQUIRED_TIERS
        normalized_tokens = [
            token.strip().upper() for token in raw_value.split(",") if token.strip()
        ]
        if not normalized_tokens:
            return frozenset()
        if "*" in normalized_tokens:
            return _FALLBACK_VALID_MATURITY_TIERS
        return frozenset(
            token
            for token in normalized_tokens
            if token in _FALLBACK_VALID_MATURITY_TIERS
        )

    def _fallback_mentor_pass_approved(metadata: Any) -> bool:
        if not isinstance(metadata, dict):
            return False
        mentor_pass = metadata.get("mentor_pass")
        if isinstance(mentor_pass, dict):
            approved = mentor_pass.get("approved")
            if isinstance(approved, bool):
                return approved
            if isinstance(approved, str):
                if approved.strip().lower() in {"1", "true", "yes", "on", "approved"}:
                    return True
            passed = mentor_pass.get("passed")
            if isinstance(passed, bool):
                return passed
            if isinstance(passed, str):
                if passed.strip().lower() in {"1", "true", "yes", "on", "passed"}:
                    return True
            status = mentor_pass.get("status")
            if isinstance(status, str):
                if status.strip().lower() in {"approved", "pass", "passed", "granted"}:
                    return True
            return False
        if isinstance(mentor_pass, bool):
            return mentor_pass
        if isinstance(mentor_pass, str):
            return mentor_pass.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
                "approved",
                "pass",
                "passed",
            }
        return False

    def _fallback_classify_operation(operation_name: str) -> list[str]:
        normalized = str(operation_name or "").strip()
        if not normalized:
            return []
        return sorted(
            class_name
            for class_name, operations in _FALLBACK_HIGH_RISK_OPERATION_CLASSES.items()
            if normalized in operations
        )

    def evaluate_operation_mentor_pass(
        operation_name: str,
        metadata: Any,
        *,
        maturity_tier: str,
    ) -> dict[str, Any]:
        active_tier = str(maturity_tier or "").strip().upper() or "M0"
        operation_classes = _fallback_classify_operation(operation_name)
        required_tiers = _fallback_parse_required_tiers()
        required = bool(operation_classes) and active_tier in required_tiers
        approved = _fallback_mentor_pass_approved(metadata)
        return {
            "required": required,
            "approved": approved,
            "blocked": required and not approved,
            "operation_classes": operation_classes,
            "maturity_tier": active_tier,
            "required_tiers": sorted(required_tiers),
        }


try:
    from merlin_self_healing import EndpointCircuitBreaker
except ImportError:

    class EndpointCircuitBreaker:
        def __init__(
            self,
            failure_threshold: int = 3,
            recovery_timeout_seconds: float = 30.0,
            *,
            time_fn: Callable[[], float] | None = None,
        ):
            self.failure_threshold = max(1, int(failure_threshold))
            self.recovery_timeout_seconds = max(0.0, float(recovery_timeout_seconds))
            self._time_fn = time_fn or time.time
            self._lock = Lock()
            self._state: dict[str, dict[str, Any]] = {}

        def allow_request(self, dependency_key: str) -> bool:
            key = str(dependency_key or "").strip()
            if not key:
                return True
            now = float(self._time_fn())
            with self._lock:
                state = self._state.setdefault(
                    key,
                    {
                        "state": "closed",
                        "failure_count": 0,
                        "opened_at": None,
                        "last_failure_reason": None,
                    },
                )
                if state["state"] != "open":
                    return True
                opened_at = state.get("opened_at")
                if not isinstance(opened_at, (int, float)):
                    opened_at = now
                    state["opened_at"] = opened_at
                if (now - float(opened_at)) >= self.recovery_timeout_seconds:
                    state["state"] = "half_open"
                    return True
                return False

        def record_success(self, dependency_key: str) -> None:
            key = str(dependency_key or "").strip()
            if not key:
                return
            with self._lock:
                state = self._state.setdefault(
                    key,
                    {
                        "state": "closed",
                        "failure_count": 0,
                        "opened_at": None,
                        "last_failure_reason": None,
                    },
                )
                state["state"] = "closed"
                state["failure_count"] = 0
                state["opened_at"] = None
                state["last_failure_reason"] = None

        def record_failure(
            self, dependency_key: str, reason: str | None = None
        ) -> None:
            key = str(dependency_key or "").strip()
            if not key:
                return
            now = float(self._time_fn())
            with self._lock:
                state = self._state.setdefault(
                    key,
                    {
                        "state": "closed",
                        "failure_count": 0,
                        "opened_at": None,
                        "last_failure_reason": None,
                    },
                )
                if state["state"] == "half_open":
                    state["failure_count"] = self.failure_threshold
                else:
                    state["failure_count"] = int(state.get("failure_count", 0)) + 1
                state["last_failure_reason"] = reason
                if int(state["failure_count"]) >= self.failure_threshold:
                    state["state"] = "open"
                    state["opened_at"] = now

        def get_state(self, dependency_key: str) -> dict[str, Any]:
            key = str(dependency_key or "").strip()
            if not key:
                return {
                    "state": "closed",
                    "failure_count": 0,
                    "opened_at": None,
                    "last_failure_reason": None,
                }
            with self._lock:
                state = self._state.get(key)
                if state is None:
                    return {
                        "state": "closed",
                        "failure_count": 0,
                        "opened_at": None,
                        "last_failure_reason": None,
                    }
                return {
                    "state": str(state.get("state", "closed")),
                    "failure_count": int(state.get("failure_count", 0)),
                    "opened_at": state.get("opened_at"),
                    "last_failure_reason": state.get("last_failure_reason"),
                }


from merlin_tasks import task_manager

try:
    from merlin_quality_gates import (
        ingest_planner_fallback_telemetry,
        register_planner_fallback_telemetry_sink,
    )
except ImportError:
    _planner_fallback_sinks: list[Callable[[dict[str, Any]], dict[str, Any]]] = []

    def register_planner_fallback_telemetry_sink(
        sink: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        if callable(sink):
            _planner_fallback_sinks.append(sink)

    def ingest_planner_fallback_telemetry(
        *,
        session_id: str,
        metadata: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
        payload["session_id"] = session_id
        payload["source"] = source

        if not _planner_fallback_sinks:
            return {
                "ingested": False,
                "reason": "quality_gate_unavailable",
                "session_id": session_id,
            }

        result: dict[str, Any] = {
            "ingested": False,
            "reason": "fallback_sink_no_ingest",
            "session_id": session_id,
        }
        for sink in list(_planner_fallback_sinks):
            try:
                sink_result = sink(dict(payload))
            except Exception as error:
                result = {
                    "ingested": False,
                    "reason": "fallback_sink_error",
                    "error": str(error),
                    "session_id": session_id,
                }
                continue
            if isinstance(sink_result, dict):
                sink_result.setdefault("session_id", session_id)
                result = sink_result
                if sink_result.get("ingested") is True:
                    return sink_result
            else:
                result = {
                    "ingested": False,
                    "reason": "fallback_sink_invalid_result",
                    "session_id": session_id,
                }
        return result


try:
    from merlin_routing_contract import normalize_rag_citations
except ImportError:

    def normalize_rag_citations(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for index, item in enumerate(matches, start=1):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {})
            metadata = metadata if isinstance(metadata, dict) else {}
            citation: dict[str, Any] = {
                "source_id": str(metadata.get("source_id") or f"src_{index}"),
            }
            path = metadata.get("path")
            if isinstance(path, str) and path.strip():
                citation["path"] = path
            text = str(item.get("text", "")).strip()
            if text:
                citation["excerpt"] = text[:280]
            citations.append(citation)
        return citations


try:
    from merlin_audit import log_audit_event, build_request_audit_metadata
except ImportError:
    from merlin_audit import log_audit_event

    def build_request_audit_metadata(
        *,
        request: Any,
        body_bytes: bytes,
        operation_name: str | None = None,
        response_status: int | None = None,
    ) -> dict[str, Any]:
        _ = (request, body_bytes)
        metadata: dict[str, Any] = {}
        if operation_name:
            metadata["operation_name"] = str(operation_name)
        if response_status is not None:
            metadata["response_status"] = int(response_status)
        return metadata


from merlin_auth import (
    create_access_token,
    verify_password,
    ALGORITHM,
    SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

try:
    from merlin_auth import parse_api_key_collection, load_api_key_collection_from_file
except ImportError:

    def parse_api_key_collection(raw_value: Any) -> set[str]:
        if raw_value is None:
            return set()
        text = str(raw_value).replace("\n", ",")
        return {token.strip() for token in text.split(",") if token.strip()}

    def load_api_key_collection_from_file(path_value: Any) -> set[str]:
        if path_value is None:
            return set()
        path = Path(str(path_value).strip())
        if not path.exists() or not path.is_file():
            return set()
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return set()
        return parse_api_key_collection(content)


from merlin_user_manager import user_manager
import merlin_settings as settings

try:
    from merlin_seed_access import build_seed_access
except ImportError:

    class _FallbackSeedAccessController:
        def __init__(self, workspace_root: str | None = None):
            self.workspace_root = workspace_root

        def status(self, **kwargs: Any) -> dict[str, Any]:
            _ = kwargs
            return {
                "schema_name": "AAS.Merlin.SeedStatus",
                "schema_version": "1.0.0",
                "state": "unavailable",
                "reason": "seed_access_unavailable",
                "workspace_root": self.workspace_root,
            }

        def control(self, **kwargs: Any) -> dict[str, Any]:
            action = str(kwargs.get("action", "")).strip().lower()
            return {
                "schema_name": "AAS.Merlin.SeedControlResult",
                "schema_version": "1.0.0",
                "action": action,
                "decision": "blocked",
                "status": "blocked",
                "reason": "seed_access_unavailable",
            }

    def build_seed_access(*, workspace_root: str | None = None) -> Any:
        return _FallbackSeedAccessController(workspace_root=workspace_root)


from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta, datetime, timezone
import shutil
import tempfile
import os
import platform
import ssl
import json
import hashlib
import uuid
import re
import time

# Required contract schemas must exist before serving operation traffic.
CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"
REQUIRED_CONTRACT_SCHEMA_PATHS: tuple[Path, ...] = (
    CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json",
    CONTRACTS_DIR / "aas.repo-capability-manifest.v1.schema.json",
    CONTRACTS_DIR / "assistant.chat.routing-metadata.v1.schema.json",
)

# Import UAF endpoints
uaf_router: Any = None
try:
    from merlin_uaf_endpoints import uaf_router as imported_uaf_router

    uaf_router = imported_uaf_router
    UAF_ENDPOINTS_AVAILABLE = True
except ImportError:
    UAF_ENDPOINTS_AVAILABLE = False


class _LazyAttr:
    def __init__(self, module_name: str, attr_name: str):
        self._module_name = module_name
        self._attr_name = attr_name
        self._resolved: Any | None = None

    def _get(self) -> Any:
        if self._resolved is None:
            module = importlib.import_module(self._module_name)
            self._resolved = getattr(module, self._attr_name)
        return self._resolved

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._get()(*args, **kwargs)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get(), item)


class _LazySingleton:
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._instance: Any | None = None

    def _get_instance(self) -> Any:
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_instance(), item)


def _build_plugin_manager() -> Any:
    module = importlib.import_module("merlin_plugin_manager")
    manager = module.PluginManager()
    manager.load_plugins()
    return manager


def _build_hub_client() -> Any:
    module = importlib.import_module("merlin_hub_client")
    return module.MerlinHubClient()


def _build_research_manager() -> Any:
    module = importlib.import_module("merlin_research_manager")
    manager = module.ResearchManager()
    emit_event = getattr(hub_client, "emit_research_session_event", None)
    if callable(emit_event) and hasattr(manager, "set_event_emitter"):
        manager.set_event_emitter(
            lambda payload: hub_client.emit_research_session_event(payload)
        )

    def _fallback_signal_sink(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ingested": False, "reason": "invalid_payload"}
        raw_session_id = payload.get("session_id")
        session_id = raw_session_id.strip() if isinstance(raw_session_id, str) else ""
        if not session_id:
            return {"ingested": False, "reason": "missing_session_id"}
        telemetry = dict(payload)
        telemetry.pop("session_id", None)
        raw_source = telemetry.pop("source", "assistant.chat.request")
        source = raw_source if isinstance(raw_source, str) else "assistant.chat.request"
        try:
            return manager.ingest_planner_fallback_telemetry(
                session_id=session_id,
                telemetry=telemetry,
                source=source,
            )
        except Exception as error:
            return {
                "ingested": False,
                "reason": "research_ingest_error",
                "error": str(error),
            }

    register_planner_fallback_telemetry_sink(_fallback_signal_sink)
    return manager


merlin_emotion_chat = _LazyAttr("merlin_emotion_chat", "merlin_emotion_chat")
merlin_emotion_chat_with_metadata = _LazyAttr(
    "merlin_emotion_chat", "merlin_emotion_chat_with_metadata"
)
load_chat = _LazyAttr("merlin_emotion_chat", "load_chat")
merlin_emotion_chat_stream = _LazyAttr(
    "merlin_emotion_chat", "merlin_emotion_chat_stream"
)
merlin_rag = _LazyAttr("merlin_rag", "merlin_rag")
parallel_llm_backend = _LazyAttr("merlin_parallel_llm", "parallel_llm_backend")
adaptive_llm_backend = _LazyAttr("merlin_adaptive_llm", "adaptive_llm_backend")
ab_testing_manager = _LazyAttr("merlin_ab_testing", "ab_testing_manager")
predictive_model_selector = _LazyAttr(
    "merlin_predictive_selection", "predictive_model_selector"
)
cost_optimization_manager = _LazyAttr(
    "merlin_cost_optimization", "cost_optimization_manager"
)
build_discovery_engine = _LazyAttr("merlin_discovery_engine", "build_engine")
handle_dashboard_websocket = _LazyAttr(
    "merlin_metrics_dashboard", "handle_dashboard_websocket"
)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


_ACCESS_LOG_REDACT_KEYS = {"user_input", "prompt", "content", "text", "code"}


def _is_access_log_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _ACCESS_LOG_REDACT_KEYS:
        return True
    return "prompt" in lowered or "content" in lowered


def _redact_access_log_payload(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _is_access_log_sensitive_key(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_access_log_payload(item, depth + 1)
        return redacted
    if isinstance(value, list):
        items = [_redact_access_log_payload(item, depth + 1) for item in value[:8]]
        if len(value) > 8:
            items.append("[TRUNCATED]")
        return items
    if isinstance(value, str) and len(value) > 240:
        return value[:240] + "...[TRUNCATED]"
    return value


def _validate_required_contract_schemas() -> None:
    missing = [
        str(schema_path)
        for schema_path in REQUIRED_CONTRACT_SCHEMA_PATHS
        if not schema_path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Missing required contract schema file(s): "
            + ", ".join(missing)
            + " (run scripts/sync_contract_schemas.py --write to restore drifted/missing schemas)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not getattr(app.state, "bootstrap_ready", False):
        _validate_required_contract_schemas()
        importlib.import_module("merlin_dashboard").setup_dashboard(app)
        metrics_disabled = _coerce_bool(
            os.environ.get("MERLIN_DISABLE_PROMETHEUS_METRICS")
        )
        if not metrics_disabled:
            try:
                Instrumentator().instrument(app).expose(app)
            except RuntimeError as exc:
                merlin_logger.warning(
                    "Skipping Prometheus instrumentation at startup: %s", exc
                )
        app.state.bootstrap_ready = True
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, cast(Callable[..., Any], _rate_limit_exceeded_handler)
)

# Register UAF router if available
if UAF_ENDPOINTS_AVAILABLE and uaf_router is not None:
    app.include_router(uaf_router)

# --- Retrieval Profile ABTest creation endpoint ---
_ab_manager: Any | None = None


class RetrievalProfileABTestRequest(BaseModel):
    profile_a: str
    profile_b: str
    test_name: str = "retrieval_profile_abtest"


def _get_ab_manager() -> Any:
    global _ab_manager
    if _ab_manager is None:
        from merlin_ab_testing import ABTestingManager

        _ab_manager = ABTestingManager()
    return _ab_manager


@app.post("/abtest/retrieval-profile/create")
async def create_retrieval_profile_abtest(request: RetrievalProfileABTestRequest):
    if not request.profile_a or not request.profile_b:
        raise HTTPException(
            status_code=400,
            detail="Both profile_a and profile_b are required.",
        )
    try:
        ab_manager = _get_ab_manager()
        test_id = ab_manager.create_retrieval_profile_test(
            profile_a=request.profile_a,
            profile_b=request.profile_b,
            test_name=request.test_name,
        )
        test = ab_manager.active_tests[test_id]
        return {
            "status": "success",
            "test_id": test_id,
            "variants": test.variants,
            "test_name": test.name,
        }
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"A/B testing subsystem unavailable: {exc}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# UAF Dashboard endpoint
@app.get("/uaf/dashboard")
async def serve_uaf_dashboard():
    """Serve the UAF web dashboard."""
    from pathlib import Path

    dashboard_path = Path(__file__).parent.parent / "uaf" / "dashboard" / "index.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    else:
        raise HTTPException(status_code=404, detail="Dashboard not found")


# --- UNIVERSAL CONTEXT (Cross-Platform Sync) ---
class UniversalContext:
    def __init__(self):
        self.state = {
            "last_active_platform": platform.system(),
            "current_task": "Resting",
            "perception_data": {},
            "divine_guidance": [],
        }

    def update(self, data: dict):
        self.state.update(data)
        merlin_logger.info(
            f"Universal Context Sync: {self.state['last_active_platform']}"
        )


global_context = UniversalContext()

# --- END CONTEXT ---


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    merlin_logger.error(f"Global Error: {exc} | Path: {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": (
                str(exc) if os.getenv("DEBUG") else "An unexpected error occurred."
            ),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    merlin_logger.warning(
        f"HTTP Error: {exc.detail} | Status: {exc.status_code} | Path: {request.url.path}"
    )
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


plugin_manager = _LazySingleton(_build_plugin_manager)
hub_client = _LazySingleton(_build_hub_client)
research_manager = _LazySingleton(_build_research_manager)
voice = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

API_KEY_NAME = "X-Merlin-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def _active_api_keys() -> set[str]:
    strict_rotation = _coerce_bool(
        os.environ.get("MERLIN_API_KEY_ROTATION_STRICT", "false")
    )

    keys: set[str] = set()
    keys.update(parse_api_key_collection(os.environ.get("MERLIN_API_KEYS")))
    keys.update(
        load_api_key_collection_from_file(
            os.environ.get("MERLIN_API_KEY_ROTATION_FILE")
        )
    )

    explicit_primary = os.environ.get("MERLIN_API_KEY")
    if explicit_primary is not None:
        keys.update(parse_api_key_collection(explicit_primary))
    elif not strict_rotation:
        keys.add("merlin-secret-key")

    return {key for key in keys if key}


def is_valid_api_key(api_key: str | None) -> bool:
    if api_key is None:
        return False
    return api_key in _active_api_keys()


def get_api_key(api_key: str = Depends(api_key_header)) -> str:
    if not is_valid_api_key(api_key):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key


MANIFEST_PATH = Path(
    os.environ.get("MERLIN_MANIFEST_PATH", "merlin_genesis_manifest.json")
)


def load_manifest_entries() -> list[dict[str, Any]]:
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            merlin_logger.error(f"Failed to read manifest queue: {exc}")
    return []


def append_manifest_entry(entry: dict[str, Any]) -> None:
    entries = load_manifest_entries()
    entries.append(entry)
    try:
        with MANIFEST_PATH.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except Exception as exc:
        merlin_logger.error(f"Failed to write manifest queue: {exc}")


def ws_requires_api_key() -> bool:
    return os.environ.get("MERLIN_WS_REQUIRE_API_KEY", "true").lower() == "true"


def get_voice() -> Any:
    global voice
    if voice is None:
        try:
            voice_cls = importlib.import_module("merlin_voice").MerlinVoice
            voice = voice_cls()
        except Exception as exc:
            merlin_logger.error(f"Voice init failed: {exc}")
            return None
    return voice


def _install_request_body_replay(request: Request, body: bytes) -> None:
    # Starlette request body caching semantics differ between versions.
    # Replaying once through `request._receive` keeps downstream handlers
    # deterministic for both older and newer stacks.
    replay_body = body if isinstance(body, (bytes, bytearray)) else b""
    original_receive = getattr(request, "_receive", None)
    first_message_sent = False

    async def _fallback_receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    downstream_receive = (
        cast(Callable[[], Any], original_receive)
        if callable(original_receive)
        else _fallback_receive
    )

    async def _replay_receive() -> dict[str, Any]:
        nonlocal first_message_sent
        if not first_message_sent:
            first_message_sent = True
            return {
                "type": "http.request",
                "body": bytes(replay_body),
                "more_body": False,
            }
        return cast(dict[str, Any], await downstream_receive())

    setattr(request, "_receive", _replay_receive)


def _requires_legacy_request_body_replay(starlette_version: str | None = None) -> bool:
    version_text = starlette_version
    if version_text is None:
        try:
            import starlette as _starlette  # type: ignore

            version_text = getattr(_starlette, "__version__", "0")
        except Exception:
            version_text = "0"

    tokens = re.findall(r"\d+", str(version_text))
    if not tokens:
        return False
    major = int(tokens[0])
    minor = int(tokens[1]) if len(tokens) > 1 else 0
    patch = int(tokens[2]) if len(tokens) > 2 else 0
    return (major, minor, patch) < (0, 36, 0)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    import time
    import uuid

    operation_name: str | None = None
    operation_request_payload: dict[str, Any] | None = None
    body_bytes: bytes = b""
    is_operation_request = (
        request.method == "POST" and request.url.path == "/merlin/operations"
    )

    if is_operation_request:
        try:
            body = await request.body()
            body_bytes = body
            if _requires_legacy_request_body_replay():
                _install_request_body_replay(request, body)
            if body:
                parsed = json.loads(body.decode("utf-8"))
                if isinstance(parsed, dict):
                    operation = parsed.get("operation")
                    if isinstance(operation, dict):
                        raw_name = operation.get("name")
                        if isinstance(raw_name, str) and raw_name.strip():
                            operation_name = raw_name.strip()
                    operation_request_payload = {
                        "operation": parsed.get("operation"),
                        "payload": parsed.get("payload"),
                    }
        except (UnicodeDecodeError, json.JSONDecodeError):
            operation_name = "__parse_error__"

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id

    if is_operation_request:
        _record_operation_metric(
            operation_name=operation_name,
            status_code=response.status_code,
            latency_ms=process_time * 1000.0,
        )
        try:
            audit_details = build_request_audit_metadata(
                route=request.url.path,
                decision_version=OPERATION_AUDIT_DECISION_VERSION,
                request_id=request_id,
                operation_name=operation_name or "__unknown__",
            )
        except TypeError:
            audit_details = build_request_audit_metadata(
                request=request,
                body_bytes=body_bytes,
                operation_name=operation_name or "__unknown__",
                response_status=response.status_code,
            )
            audit_details.setdefault("route", request.url.path)
            audit_details.setdefault(
                "decision_version", OPERATION_AUDIT_DECISION_VERSION
            )
            audit_details.setdefault("request_id", request_id)
        audit_details["status_code"] = response.status_code
        try:
            log_audit_event(
                action="operation.dispatch",
                details=audit_details,
                user="api_server",
                request_id=request_id,
            )
        except TypeError:
            legacy_details = dict(audit_details)
            legacy_details.pop("request_id", None)
            log_audit_event(
                action="operation.dispatch",
                details=legacy_details,
                user="api_server",
                request_id=request_id,
            )

    client = getattr(request, "client", None)
    client_ip = getattr(client, "host", "unknown")
    if not isinstance(client_ip, str):
        client_ip = "unknown"

    access_log_fields: dict[str, Any] = {
        "event": "http_access",
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "latency_ms": round(process_time * 1000.0, 3),
        "client_ip": client_ip,
    }
    if operation_name:
        access_log_fields["operation_name"] = operation_name
    if operation_request_payload is not None:
        access_log_fields["request_payload"] = _redact_access_log_payload(
            operation_request_payload
        )

    log_with_context(
        "INFO",
        "HTTP access",
        request_id=request_id,
        **access_log_fields,
    )

    return response


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "platform": platform.system(),
        "execution_mode": policy_manager.mode.value,
    }


@app.get("/merlin/llm/parallel/status")
async def parallel_llm_status(api_key: str = Depends(get_api_key)):
    return parallel_llm_backend.get_status()


@app.post("/merlin/llm/parallel/strategy")
async def set_parallel_strategy(strategy: str, api_key: str = Depends(get_api_key)):
    from merlin_parallel_llm import ParallelLLMBackend

    if strategy not in ["voting", "routing", "cascade", "consensus"]:
        raise HTTPException(status_code=400, detail="Invalid strategy")
    os.environ["PARALLEL_STRATEGY"] = strategy
    return {"status": "updated", "strategy": strategy}


class FeedbackRequest(BaseModel):
    model_name: str
    rating: int
    task_type: str | None = None


@app.post("/merlin/llm/adaptive/feedback")
async def provide_adaptive_feedback(
    feedback: FeedbackRequest, api_key: str = Depends(get_api_key)
):
    if feedback.rating < 1 or feedback.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")
    adaptive_llm_backend.provide_feedback(
        feedback.model_name, feedback.rating, feedback.task_type
    )
    return {
        "status": "feedback recorded",
        "model": feedback.model_name,
        "rating": feedback.rating,
    }


@app.get("/merlin/llm/adaptive/status")
async def adaptive_llm_status(api_key: str = Depends(get_api_key)):
    return adaptive_llm_backend.get_status()


@app.get("/merlin/llm/adaptive/metrics")
async def adaptive_llm_metrics(api_key: str = Depends(get_api_key)):
    status = adaptive_llm_backend.get_status()
    return {"metrics": status["metrics"]}


@app.post("/merlin/llm/adaptive/reset")
async def reset_adaptive_metrics(
    model_name: str | None = None, api_key: str = Depends(get_api_key)
):
    adaptive_llm_backend.reset_metrics(model_name)
    return {"status": "metrics reset", "model": model_name or "all"}


class CreateABTestRequest(BaseModel):
    name: str
    variants: List[str]
    weights: List[float] | None = None
    duration_hours: int = 24


@app.post("/merlin/llm/ab/create")
async def create_ab_test(
    request: CreateABTestRequest, api_key: str = Depends(get_api_key)
):
    test_id = ab_testing_manager.create_test(
        name=request.name,
        variants=request.variants,
        weights=request.weights,
        duration_hours=request.duration_hours,
    )
    return {"test_id": test_id, "status": "created", "name": request.name}


@app.get("/merlin/llm/ab/tests")
async def list_ab_tests(api_key: str = Depends(get_api_key)):
    return {"tests": ab_testing_manager.list_active_tests()}


@app.get("/merlin/llm/ab/test/{test_id}")
async def get_ab_test_status(test_id: str, api_key: str = Depends(get_api_key)):
    status = ab_testing_manager.get_test_status(test_id)
    if not status:
        raise HTTPException(status_code=404, detail="Test not found")
    return status


class RecordABTestResultRequest(BaseModel):
    test_id: str
    variant: str
    user_rating: int | None = None
    latency: float | None = None
    success: bool = True


@app.post("/merlin/llm/ab/result")
async def record_ab_test_result(
    request: RecordABTestResultRequest, api_key: str = Depends(get_api_key)
):
    ab_testing_manager.record_result(
        test_id=request.test_id,
        variant=request.variant,
        user_rating=request.user_rating,
        latency=request.latency,
        success=request.success,
    )
    return {
        "status": "recorded",
        "test_id": request.test_id,
        "variant": request.variant,
    }


@app.post("/merlin/llm/ab/complete/{test_id}")
async def complete_ab_test(test_id: str, api_key: str = Depends(get_api_key)):
    winner = ab_testing_manager.complete_test(test_id)
    return {"status": "completed", "winner": winner}


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await handle_dashboard_websocket(websocket)


# --- PREDICTIVE MODEL SELECTION ENDPOINTS ---


class SelectModelRequest(BaseModel):
    query: str


@app.post("/merlin/llm/predictive/select")
async def select_predictive_model(
    request: SelectModelRequest, api_key: str = Depends(get_api_key)
):
    selected_model = predictive_model_selector.select_model(request.query)
    explanation = predictive_model_selector.get_model_explanation(
        selected_model, request.query
    )

    merlin_logger.info(
        f"Predictive selection: {selected_model} for query: {request.query[:50]}"
    )

    return {
        "selected_model": selected_model,
        "explanation": explanation,
        "query_preview": request.query[:100],
    }


class RecordPredictionFeedbackRequest(BaseModel):
    model_name: str
    was_successful: bool
    latency: float | None = None
    task_type: str | None = None
    rating: int | None = None


@app.post("/merlin/llm/predictive/feedback")
async def record_prediction_feedback(
    request: RecordPredictionFeedbackRequest, api_key: str = Depends(get_api_key)
):
    predictive_model_selector.record_feedback(
        model_name=request.model_name,
        was_successful=request.was_successful,
        latency=request.latency,
        task_type=request.task_type,
        rating=request.rating,
    )

    return {
        "status": "recorded",
        "model_name": request.model_name,
        "updated_weights": predictive_model_selector.model_weights.get(
            request.model_name, {}
        ),
    }


@app.get("/merlin/llm/predictive/status")
async def get_predictive_status(api_key: str = Depends(get_api_key)):
    return predictive_model_selector.get_status()


@app.get("/merlin/llm/predictive/models")
async def list_predictive_models(api_key: str = Depends(get_api_key)):
    return {
        "models": list(predictive_model_selector.model_weights.keys()),
        "weights": predictive_model_selector.model_weights,
        "feature_importance": predictive_model_selector.feature_importance,
    }


@app.post("/merlin/llm/predictive/export")
async def export_prediction_data(api_key: str = Depends(get_api_key)):
    return predictive_model_selector.export_model_data()


# --- COST OPTIMIZATION ENDPOINTS ---


class CostReportRequest(BaseModel):
    days: int = 30


class SetBudgetRequest(BaseModel):
    budget_limit: float


class SetCostThresholdsRequest(BaseModel):
    warning_threshold: float | None = None
    critical_threshold: float | None = None


class ModelPricingData(BaseModel):
    input_cost_per_1k: float
    output_cost_per_1k: float
    currency: str = "USD"
    free_tier_limit: int | None = None
    tier_name: str | None = None


class ResearchSessionCreateRequest(BaseModel):
    objective: str
    constraints: list[str] | None = None
    horizon_days: int = 14
    tags: list[str] | None = None
    impact: float | None = None
    uncertainty: float | None = None
    time_horizon: str | None = None
    linked_task_ids: list[int] | None = None
    planner_artifacts: list[str] | None = None


class ResearchSignalRequest(BaseModel):
    source: str
    claim: str
    confidence: float = 0.6
    novelty: float = 0.5
    risk: float = 0.2
    supports: list[str] | None = None
    contradicts: list[str] | None = None


def _cost_manager() -> Any:
    return cast(Any, cost_optimization_manager)


@app.post("/merlin/llm/cost/report")
async def get_cost_report(
    request: CostReportRequest, api_key: str = Depends(get_api_key)
):
    manager = _cost_manager()
    report = manager.get_cost_report(request.days)
    return report


@app.post("/merlin/llm/cost/budget")
async def set_monthly_budget(
    request: SetBudgetRequest, api_key: str = Depends(get_api_key)
):
    manager = _cost_manager()
    manager.budget_limit = request.budget_limit
    return {"status": "updated", "new_budget_limit": request.budget_limit}


@app.get("/merlin/llm/cost/budget")
async def get_monthly_budget(api_key: str = Depends(get_api_key)):
    manager = _cost_manager()
    return {
        "budget_limit": manager.budget_limit,
        "current_month_spend": sum(
            sum(
                u.total_cost
                for u in usage_list
                if u.date.startswith(datetime.now().strftime("%Y-%m-"))
            )
            for usage_list in manager.daily_usage.values()
        ),
        "percentage_used": (
            sum(
                sum(
                    u.total_cost
                    for u in usage_list
                    if u.date.startswith(datetime.now().strftime("%Y-%m-"))
                )
                for usage_list in manager.daily_usage.values()
            )
            / manager.budget_limit
            * 100
            if manager.budget_limit > 0
            else 0
        ),
    }


@app.post("/merlin/llm/cost/thresholds")
async def set_cost_thresholds(
    request: SetCostThresholdsRequest, api_key: str = Depends(get_api_key)
):
    manager = _cost_manager()
    if request.warning_threshold is not None:
        manager.cost_thresholds["warning"] = request.warning_threshold
    if request.critical_threshold is not None:
        manager.cost_thresholds["critical"] = request.critical_threshold
    return {
        "status": "updated",
        "warning_threshold": manager.cost_thresholds["warning"],
        "critical_threshold": manager.cost_thresholds["critical"],
    }


@app.get("/merlin/llm/cost/thresholds")
async def get_cost_thresholds(api_key: str = Depends(get_api_key)):
    manager = _cost_manager()
    return manager.cost_thresholds


@app.get("/merlin/llm/cost/optimization")
async def get_cost_optimization(api_key: str = Depends(get_api_key)):
    manager = _cost_manager()
    return manager.get_cost_optimization_recommendation()


@app.post("/merlin/llm/cost/pricing")
async def set_model_pricing(
    request: ModelPricingData, api_key: str = Depends(get_api_key)
):
    pricing = {
        "input_cost_per_1k": request.input_cost_per_1k,
        "output_cost_per_1k": request.output_cost_per_1k,
        "currency": request.currency,
        "free_tier_limit": request.free_tier_limit,
        "tier_name": request.tier_name,
    }

    return {"status": "pricing_updated", "pricing": pricing}


@app.post("/merlin/research/manager/session")
async def create_research_manager_session(
    request: ResearchSessionCreateRequest, api_key: str = Depends(get_api_key)
):
    try:
        session = research_manager.create_session(
            objective=request.objective,
            constraints=request.constraints,
            horizon_days=request.horizon_days,
            tags=request.tags,
            impact=request.impact,
            uncertainty=request.uncertainty,
            time_horizon=request.time_horizon,
            linked_task_ids=request.linked_task_ids,
            planner_artifacts=request.planner_artifacts,
            created_by="AaroneousAutomationSuite/Merlin:merlin_api_server",
            source_operation="http.post:/merlin/research/manager/session",
            policy_version=RESEARCH_SESSION_PROVENANCE_POLICY_VERSION,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "session": session,
        "next_actions": research_manager.next_actions(session["session_id"]),
    }


@app.get("/merlin/research/manager/sessions")
async def list_research_manager_sessions(
    limit: int = 20,
    tag: str | None = None,
    topic: str | None = None,
    cursor: str | None = None,
    api_key: str = Depends(get_api_key),
):
    normalized_limit = max(1, min(limit, 200))
    try:
        page = research_manager.list_sessions_page(
            limit=normalized_limit,
            cursor=cursor,
            tag=tag,
            topic_query=topic,
        )
        return {
            "sessions": page.get("sessions", []),
            "next_cursor": page.get("next_cursor"),
        }
    except AttributeError:
        return {
            "sessions": research_manager.list_sessions(
                limit=normalized_limit,
                tag=tag,
                topic_query=topic,
            ),
            "next_cursor": None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/merlin/research/manager/search")
async def search_research_manager_sessions(
    q: str,
    limit: int = 20,
    tag: str | None = None,
    cursor: str | None = None,
    api_key: str = Depends(get_api_key),
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must be non-empty")
    normalized_limit = max(1, min(limit, 200))
    try:
        page = research_manager.search_sessions(
            query=query,
            limit=normalized_limit,
            cursor=cursor,
            tag=tag,
        )
    except AttributeError:
        page = {
            "sessions": research_manager.list_sessions(
                limit=normalized_limit,
                tag=tag,
                topic_query=query,
            ),
            "next_cursor": None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "query": query,
        "sessions": page.get("sessions", []),
        "next_cursor": page.get("next_cursor"),
    }


@app.get("/merlin/research/manager/session/{session_id}")
async def get_research_manager_session(
    session_id: str, api_key: str = Depends(get_api_key)
):
    try:
        session = research_manager.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"session": session}


@app.post("/merlin/research/manager/session/{session_id}/signal")
async def add_research_manager_signal(
    session_id: str,
    request: ResearchSignalRequest,
    api_key: str = Depends(get_api_key),
):
    try:
        return research_manager.add_signal(
            session_id=session_id,
            source=request.source,
            claim=request.claim,
            confidence=request.confidence,
            novelty=request.novelty,
            risk=request.risk,
            supports=request.supports,
            contradicts=request.contradicts,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research session not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/merlin/research/manager/session/{session_id}/brief")
async def get_research_manager_brief(
    session_id: str, api_key: str = Depends(get_api_key)
):
    try:
        brief = research_manager.get_brief(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"brief": brief}


@app.get("/metrics/dashboard", response_class=HTMLResponse)
async def metrics_dashboard_page():
    from fastapi.responses import FileResponse

    dashboard_path = Path(
        os.environ.get("MERLIN_DASHBOARD_PATH", "metrics_dashboard.html")
    )
    return FileResponse(dashboard_path)


# --- GENESIS & CONTEXT ENDPOINTS ---


@app.get("/merlin/genesis/dna")
async def get_merlin_dna(api_key: str = Depends(get_api_key)):
    dna = {}
    core_files = [
        "merlin_api_server.py",
        "merlin_policy.py",
        "merlin_agents.py",
        "merlin_emotion_chat.py",
        "merlin_watcher.py",
    ]
    for f in core_files:
        if os.path.exists(f):
            with open(f, "r") as file:
                dna[f] = file.read()
    return JSONResponse(content={"dna": dna})


@app.get("/merlin/context")
async def get_context(api_key: str = Depends(get_api_key)):
    return JSONResponse(content=global_context.state)


@app.post("/merlin/context")
async def update_context(request: Request, api_key: str = Depends(get_api_key)):
    data = await request.json()
    global_context.update(data)
    return {"status": "Context Synchronized"}


# --- CHAT & WEBSOCKETS ---


class ChatRequest(BaseModel):
    user_input: str
    user_id: str = "default"


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "Medium"


class ExecuteRequest(BaseModel):
    command: str


class SpeakRequest(BaseModel):
    text: str
    engine: str | None = None


class VoiceSynthesizeRequest(BaseModel):
    text: str
    engine: str | None = None


class SearchRequest(BaseModel):
    query: str


class ManifestRequest(BaseModel):
    filename: str
    code: str


class OperationEndpoint(BaseModel):
    repo: str
    component: str
    agent_runtime: str | None = None
    editor: str | None = None


class OperationRetry(BaseModel):
    max_attempts: int = 0


class OperationSpec(BaseModel):
    name: str
    version: str
    timeout_ms: int
    idempotency_key: str | None = None
    expects_ack: bool | None = None
    retry: OperationRetry | None = None


class OperationEnvelopeRequest(BaseModel):
    schema_name: str
    schema_version: str
    message_id: str
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str
    timestamp_utc: datetime
    source: OperationEndpoint
    target: OperationEndpoint
    operation: OperationSpec
    payload: Any
    metadata: dict[str, Any] | None = None


OPERATION_ENVELOPE_SCHEMA_NAME = "AAS.OperationEnvelope"
OPERATION_ENVELOPE_SCHEMA_VERSION = "1.0.0"
OPERATION_AUDIT_DECISION_VERSION = "operation-dispatch-v1"
RESEARCH_SESSION_PROVENANCE_POLICY_VERSION = "research-session-provenance-v1"
DEPRECATED_OPERATION_POLICIES: dict[str, dict[str, str]] = {
    "merlin.voice.listen": {
        "replacement_operation": "merlin.voice.transcribe",
        "sunset": "2026-06-30T00:00:00Z",
        "policy_link": "docs/protocols/compatibility-policy.md",
    }
}


def _operation_source_actor(source: OperationEndpoint) -> str:
    repo = source.repo.strip()
    component = source.component.strip()
    if repo and component:
        return f"{repo}:{component}"
    if repo:
        return repo
    if component:
        return component
    return "unknown"


def _is_semver(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", value))


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    if not _is_semver(value):
        return None
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _negotiate_operation_envelope_schema_version(
    schema_version: str,
) -> tuple[bool, str | None, str | None]:
    requested = _parse_semver(schema_version)
    if requested is None:
        return (
            False,
            "INVALID_SCHEMA_VERSION",
            "schema_version must use semver (X.Y.Z)",
        )

    supported = _parse_semver(OPERATION_ENVELOPE_SCHEMA_VERSION)
    if supported is None:
        return (
            False,
            "INVALID_SCHEMA_VERSION",
            "server schema negotiation is misconfigured",
        )

    if requested == supported:
        return True, None, None

    if requested > supported:
        return (
            False,
            "SCHEMA_VERSION_DOWNGRADE_REQUIRED",
            (
                f"schema_version {schema_version} is newer than supported "
                f"{OPERATION_ENVELOPE_SCHEMA_VERSION}; downgrade requested envelope version"
            ),
        )

    return (
        False,
        "SCHEMA_VERSION_UPGRADE_REQUIRED",
        (
            f"schema_version {schema_version} is older than minimum supported "
            f"{OPERATION_ENVELOPE_SCHEMA_VERSION}; upgrade requested envelope version"
        ),
    )


def _response_operation_name(operation_name: str) -> str:
    if operation_name.endswith(".request"):
        return f"{operation_name[:-8]}.result"
    return f"{operation_name}.result"


def _operation_runtime_metadata() -> dict[str, str]:
    return {
        "maturity_tier": settings.MERLIN_MATURITY_TIER,
        "maturity_policy_version": settings.MERLIN_MATURITY_POLICY_VERSION,
    }


def _apply_operation_deprecation_headers(
    response: JSONResponse, operation_name: str
) -> None:
    policy = DEPRECATED_OPERATION_POLICIES.get(operation_name)
    if policy is None:
        return

    response.headers["Deprecation"] = "true"
    sunset = policy.get("sunset")
    if sunset:
        response.headers["Sunset"] = sunset

    replacement_operation = policy.get("replacement_operation")
    if replacement_operation:
        response.headers["X-Merlin-Replacement-Operation"] = replacement_operation

    policy_link = policy.get("policy_link")
    if policy_link:
        response.headers["Link"] = f'<{policy_link}>; rel="deprecation-policy"'


def _operation_response(
    envelope: OperationEnvelopeRequest,
    payload: dict[str, Any],
    status_code: int = 200,
) -> JSONResponse:
    response_body = {
        "schema_name": OPERATION_ENVELOPE_SCHEMA_NAME,
        "schema_version": OPERATION_ENVELOPE_SCHEMA_VERSION,
        "message_id": str(uuid.uuid4()),
        "correlation_id": envelope.correlation_id or envelope.message_id,
        "causation_id": envelope.message_id,
        "trace_id": envelope.trace_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repo": "AaroneousAutomationSuite/Merlin",
            "component": "merlin_api_server",
        },
        "target": {
            "repo": envelope.source.repo,
            "component": envelope.source.component,
        },
        "operation": {
            "name": _response_operation_name(envelope.operation.name),
            "version": envelope.operation.version,
            "timeout_ms": envelope.operation.timeout_ms,
        },
        "payload": payload,
        "metadata": _operation_runtime_metadata(),
    }
    _remember_idempotency_response(
        envelope=envelope,
        response_body=response_body,
        status_code=status_code,
    )
    response = JSONResponse(status_code=status_code, content=response_body)
    _apply_operation_deprecation_headers(response, envelope.operation.name)
    return response


def _operation_error(
    envelope: OperationEnvelopeRequest,
    code: str,
    message: str,
    retryable: bool = False,
    status_code: int = 400,
) -> JSONResponse:
    error_category = _error_category_for_code(code)
    return _operation_response(
        envelope=envelope,
        payload={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "category": error_category,
            }
        },
        status_code=status_code,
    )


ERROR_CATEGORY_BY_CODE: dict[str, str] = {
    "INVALID_SCHEMA": "validation",
    "INVALID_SCHEMA_VERSION": "validation",
    "SCHEMA_VERSION_DOWNGRADE_REQUIRED": "validation",
    "SCHEMA_VERSION_UPGRADE_REQUIRED": "validation",
    "INVALID_OPERATION_VERSION": "validation",
    "INVALID_TIMEOUT": "validation",
    "MISSING_CORRELATION_ID": "validation",
    "MISSING_IDEMPOTENCY_KEY": "validation",
    "INVALID_PAYLOAD": "validation",
    "VALIDATION_ERROR": "validation",
    "PAYLOAD_TOO_LARGE": "validation",
    "RATE_LIMITED": "policy",
    "OPERATION_DISABLED": "policy",
    "OPERATION_NOT_ALLOWED_FOR_MATURITY_TIER": "policy",
    "OPERATION_REQUIRES_MENTOR_PASS": "policy",
    "AUTH_FAILED": "auth",
    "USER_AUTH_FAILED": "auth",
    "COMMAND_BLOCKED": "policy",
    "RESEARCH_MANAGER_READ_ONLY": "policy",
    "SEED_CONTROL_BLOCKED": "policy",
    "PLUGIN_PERMISSION_DENIED": "policy",
    "DEPENDENCY_CIRCUIT_OPEN": "dependency",
    "TOOL_EXECUTION_FAILED": "dependency",
    "TOOL_EXECUTION_ERROR": "dependency",
    "PLUGIN_EXECUTION_FAILED": "dependency",
    "PLUGIN_EXECUTION_ERROR": "dependency",
    "PLUGIN_PROCESS_SERIALIZATION_ERROR": "dependency",
    "PLUGIN_TIMEOUT": "dependency",
    "PLUGIN_CRASH_ISOLATED": "dependency",
    "AAS_TASK_CREATE_FAILED": "dependency",
    "VOICE_UNAVAILABLE": "dependency",
}


def _error_category_for_code(code: str) -> str:
    category = ERROR_CATEGORY_BY_CODE.get(code)
    if category is not None:
        return category

    if code.endswith("_NOT_FOUND"):
        return "validation"
    if code.startswith("INVALID_") or code.startswith("VALIDATION_"):
        return "validation"
    if code.endswith("_FAILED"):
        return "dependency"
    return "unknown"


def _payload_size_bytes(payload: Any) -> int:
    try:
        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        raw = str(payload)
    return len(raw.encode("utf-8"))


def _payload_size_limit_for_operation(operation_name: str) -> int:
    overrides = settings.MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION
    if operation_name in overrides:
        override_limit = overrides[operation_name]
        if isinstance(override_limit, int) and override_limit > 0:
            return override_limit
    return settings.MERLIN_OPERATION_PAYLOAD_MAX_BYTES


_OPERATION_RATE_LIMIT_LOCK = Lock()
_OPERATION_RATE_WINDOWS: dict[str, deque[float]] = {}
MUTATING_ENVELOPE_OPERATIONS: set[str] = {
    "assistant.tools.execute",
    "merlin.command.execute",
    "merlin.context.update",
    "merlin.discovery.run",
    "merlin.discovery.queue.drain",
    "merlin.discovery.queue.pause",
    "merlin.discovery.queue.resume",
    "merlin.discovery.queue.purge_deadletter",
    "merlin.seed.control",
    "merlin.seed.health.heartbeat",
    "merlin.seed.watchdog.tick",
    "merlin.seed.watchdog.control",
    "merlin.llm.ab.complete",
    "merlin.llm.ab.create",
    "merlin.llm.ab.result",
    "merlin.llm.adaptive.feedback",
    "merlin.llm.adaptive.reset",
    "merlin.llm.cost.budget.set",
    "merlin.llm.cost.pricing.set",
    "merlin.llm.cost.thresholds.set",
    "merlin.llm.parallel.strategy",
    "merlin.llm.predictive.feedback",
    "merlin.llm.predictive.select",
    "merlin.plugins.execute",
    "merlin.research.manager.session.create",
    "merlin.research.manager.session.signal.add",
    "merlin.tasks.create",
    "merlin.user_manager.create",
    "merlin.voice.synthesize",
    "merlin.genesis.manifest",
    "merlin.aas.create_task",
}
IDEMPOTENCY_KEY_REQUIRED_OPERATIONS: set[str] = {
    "merlin.context.update",
    "merlin.discovery.run",
    "merlin.discovery.queue.drain",
    "merlin.discovery.queue.pause",
    "merlin.discovery.queue.resume",
    "merlin.discovery.queue.purge_deadletter",
    "merlin.seed.control",
    "merlin.seed.health.heartbeat",
    "merlin.seed.watchdog.tick",
    "merlin.seed.watchdog.control",
    "merlin.llm.ab.create",
    "merlin.llm.cost.budget.set",
    "merlin.llm.cost.pricing.set",
    "merlin.llm.cost.thresholds.set",
    "merlin.research.manager.session.create",
    "merlin.research.manager.session.signal.add",
    "merlin.tasks.create",
    "merlin.user_manager.create",
    "merlin.genesis.manifest",
    "merlin.aas.create_task",
}
IDEMPOTENCY_REPLAY_OPERATIONS: set[str] = set(IDEMPOTENCY_KEY_REQUIRED_OPERATIONS)
IDEMPOTENCY_CACHE_TTL_SECONDS = 3600
_IDEMPOTENCY_LOCK = Lock()
_IDEMPOTENCY_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}


def _idempotency_key_for_envelope(envelope: OperationEnvelopeRequest) -> str | None:
    raw = envelope.operation.idempotency_key
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    if not normalized:
        return None
    return normalized


def _idempotency_cache_key(envelope: OperationEnvelopeRequest) -> str | None:
    if envelope.operation.name not in IDEMPOTENCY_REPLAY_OPERATIONS:
        return None
    key = _idempotency_key_for_envelope(envelope)
    if key is None:
        return None
    try:
        payload_text = json.dumps(
            envelope.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        payload_text = str(envelope.payload)
    payload_fingerprint = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()[:16]
    return f"{envelope.operation.name}::{key}::{payload_fingerprint}"


def _mask_idempotency_key(key: str) -> str:
    if len(key) <= 8:
        return key
    return f"{key[:4]}...{key[-4:]}"


def _purge_idempotency_cache(now: float) -> None:
    expired_keys = [
        cache_key
        for cache_key, value in _IDEMPOTENCY_RESPONSE_CACHE.items()
        if (now - float(value.get("stored_at", 0.0))) > IDEMPOTENCY_CACHE_TTL_SECONDS
    ]
    for cache_key in expired_keys:
        _IDEMPOTENCY_RESPONSE_CACHE.pop(cache_key, None)


def _idempotency_replay_response(
    envelope: OperationEnvelopeRequest,
) -> JSONResponse | None:
    cache_key = _idempotency_cache_key(envelope)
    if cache_key is None:
        return None

    now = time.time()
    with _IDEMPOTENCY_LOCK:
        _purge_idempotency_cache(now)
        cached = _IDEMPOTENCY_RESPONSE_CACHE.get(cache_key)
        if cached is None:
            return None
        status_code = int(cached.get("status_code", 200))
        payload = cached.get("body", {})

    response = JSONResponse(status_code=status_code, content=payload)
    response.headers["X-Merlin-Idempotent-Replay"] = "true"
    _apply_operation_deprecation_headers(response, envelope.operation.name)
    return response


def _remember_idempotency_response(
    envelope: OperationEnvelopeRequest,
    response_body: dict[str, Any],
    status_code: int,
) -> None:
    if status_code >= 400:
        return
    cache_key = _idempotency_cache_key(envelope)
    if cache_key is None:
        return

    now = time.time()
    with _IDEMPOTENCY_LOCK:
        _purge_idempotency_cache(now)
        _IDEMPOTENCY_RESPONSE_CACHE[cache_key] = {
            "stored_at": now,
            "status_code": status_code,
            "body": response_body,
        }


def _operation_replay_diagnostics_rows() -> list[dict[str, Any]]:
    now = time.time()
    rows: list[dict[str, Any]] = []
    with _IDEMPOTENCY_LOCK:
        _purge_idempotency_cache(now)
        for cache_key in sorted(_IDEMPOTENCY_RESPONSE_CACHE.keys()):
            cache_entry = _IDEMPOTENCY_RESPONSE_CACHE[cache_key]
            cache_parts = cache_key.split("::", 2)
            operation_name = cache_parts[0] if cache_parts else ""
            idempotency_key = cache_parts[1] if len(cache_parts) > 1 else ""
            stored_at = float(cache_entry.get("stored_at", 0.0))
            rows.append(
                {
                    "operation_name": operation_name,
                    "idempotency_key_preview": _mask_idempotency_key(idempotency_key),
                    "status_code": int(cache_entry.get("status_code", 200)),
                    "age_seconds": round(max(0.0, now - stored_at), 3),
                }
            )
    return rows


def _operation_rate_limit_for_operation(operation_name: str) -> int:
    overrides = settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION
    if operation_name in overrides:
        override_limit = overrides[operation_name]
        if isinstance(override_limit, int) and override_limit > 0:
            return override_limit
    return settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE


def _is_operation_enabled(operation_name: str) -> bool:
    feature_flags = settings.MERLIN_OPERATION_FEATURE_FLAGS
    if not isinstance(feature_flags, dict):
        return True
    value = feature_flags.get(operation_name)
    if isinstance(value, bool):
        return value
    return True


def _is_operation_allowed_for_maturity_tier(
    operation_name: str,
) -> tuple[bool, str]:
    maturity_tier = settings.MERLIN_MATURITY_TIER
    allowlists = settings.MERLIN_MATURITY_OPERATION_ALLOWLISTS
    if not isinstance(allowlists, dict):
        return True, maturity_tier

    raw_allowed_operations = allowlists.get(maturity_tier)
    if raw_allowed_operations is None:
        return True, maturity_tier

    allowed_operations: set[str] = set()
    if isinstance(raw_allowed_operations, (set, frozenset)):
        for item in raw_allowed_operations:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized:
                allowed_operations.add(normalized)
    elif isinstance(raw_allowed_operations, (list, tuple)):
        for item in raw_allowed_operations:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized:
                allowed_operations.add(normalized)
    else:
        return True, maturity_tier

    if "*" in allowed_operations:
        return True, maturity_tier
    return operation_name in allowed_operations, maturity_tier


def _is_operation_rate_limited(operation_name: str) -> bool:
    max_requests = _operation_rate_limit_for_operation(operation_name)
    if max_requests <= 0:
        return False

    import time

    now = time.time()
    window_seconds = 60.0

    with _OPERATION_RATE_LIMIT_LOCK:
        request_window = _OPERATION_RATE_WINDOWS.get(operation_name)
        if request_window is None:
            request_window = deque()
            _OPERATION_RATE_WINDOWS[operation_name] = request_window

        while request_window and (now - request_window[0]) > window_seconds:
            request_window.popleft()

        if len(request_window) >= max_requests:
            return True

        request_window.append(now)
    return False


def _validate_operation_envelope(
    envelope: OperationEnvelopeRequest,
) -> JSONResponse | None:
    if envelope.schema_name != OPERATION_ENVELOPE_SCHEMA_NAME:
        return _operation_error(
            envelope=envelope,
            code="INVALID_SCHEMA",
            message=f"schema_name must be {OPERATION_ENVELOPE_SCHEMA_NAME}",
            status_code=422,
        )
    is_compatible, version_error_code, version_error_message = (
        _negotiate_operation_envelope_schema_version(envelope.schema_version)
    )
    if not is_compatible and version_error_code and version_error_message:
        return _operation_error(
            envelope=envelope,
            code=version_error_code,
            message=version_error_message,
            status_code=422,
        )
    if envelope.operation.name in MUTATING_ENVELOPE_OPERATIONS:
        if not envelope.correlation_id or not envelope.correlation_id.strip():
            return _operation_error(
                envelope=envelope,
                code="MISSING_CORRELATION_ID",
                message=(
                    "correlation_id is required for mutating operation "
                    f"{envelope.operation.name}"
                ),
                status_code=422,
            )
    if envelope.operation.name in IDEMPOTENCY_KEY_REQUIRED_OPERATIONS:
        if _idempotency_key_for_envelope(envelope) is None:
            return _operation_error(
                envelope=envelope,
                code="MISSING_IDEMPOTENCY_KEY",
                message=(
                    "operation.idempotency_key is required for create/update-style "
                    f"operation {envelope.operation.name}"
                ),
                status_code=422,
            )
    if not _is_semver(envelope.operation.version):
        return _operation_error(
            envelope=envelope,
            code="INVALID_OPERATION_VERSION",
            message="operation.version must use semver (X.Y.Z)",
            status_code=422,
        )
    if envelope.operation.timeout_ms <= 0:
        return _operation_error(
            envelope=envelope,
            code="INVALID_TIMEOUT",
            message="operation.timeout_ms must be greater than zero",
            status_code=422,
        )
    if not _is_operation_enabled(envelope.operation.name):
        return _operation_error(
            envelope=envelope,
            code="OPERATION_DISABLED",
            message=(
                f"operation {envelope.operation.name} is disabled by "
                "MERLIN_OPERATION_FEATURE_FLAGS"
            ),
            status_code=403,
        )
    operation_allowed_for_maturity, maturity_tier = (
        _is_operation_allowed_for_maturity_tier(envelope.operation.name)
    )
    if not operation_allowed_for_maturity:
        return _operation_error(
            envelope=envelope,
            code="OPERATION_NOT_ALLOWED_FOR_MATURITY_TIER",
            message=(
                f"operation {envelope.operation.name} is not allowed for maturity tier "
                f"{maturity_tier} by MERLIN_MATURITY_OPERATION_ALLOWLISTS"
            ),
            status_code=403,
        )
    mentor_pass_decision = evaluate_operation_mentor_pass(
        envelope.operation.name,
        envelope.metadata,
        maturity_tier=maturity_tier,
    )
    if mentor_pass_decision.get("blocked"):
        operation_classes = mentor_pass_decision.get("operation_classes", [])
        class_names = ", ".join(operation_classes) if operation_classes else "high-risk"
        return _operation_error(
            envelope=envelope,
            code="OPERATION_REQUIRES_MENTOR_PASS",
            message=(
                f"operation {envelope.operation.name} requires mentor pass for class "
                f"{class_names} in maturity tier {maturity_tier}; provide "
                "metadata.mentor_pass approval"
            ),
            status_code=403,
        )

    payload_size = _payload_size_bytes(envelope.payload)
    payload_limit = _payload_size_limit_for_operation(envelope.operation.name)
    if payload_size > payload_limit:
        return _operation_error(
            envelope=envelope,
            code="PAYLOAD_TOO_LARGE",
            message=(
                "payload exceeds max bytes for operation "
                f"({payload_size} > {payload_limit})"
            ),
            status_code=413,
        )
    if _is_operation_rate_limited(envelope.operation.name):
        return _operation_error(
            envelope=envelope,
            code="RATE_LIMITED",
            message="operation rate limit exceeded for the current 60-second window",
            retryable=True,
            status_code=429,
        )
    return None


DEPENDENCY_CIRCUIT_KEY_BY_OPERATION: dict[str, str] = {
    "assistant.tools.execute": "assistant.tools.execute",
    "merlin.plugins.execute": "merlin.plugins.execute",
    "merlin.voice.status": "merlin.voice",
    "merlin.voice.synthesize": "merlin.voice",
    "merlin.voice.listen": "merlin.voice",
    "merlin.voice.transcribe": "merlin.voice",
    "merlin.aas.create_task": "merlin.aas.create_task",
}
_DEPENDENCY_CIRCUIT_BREAKER = EndpointCircuitBreaker(
    failure_threshold=settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    recovery_timeout_seconds=settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS,
)


def _dependency_circuit_enabled() -> bool:
    return bool(settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_ENABLED)


def _dependency_circuit_key_for_operation(operation_name: str) -> str | None:
    return DEPENDENCY_CIRCUIT_KEY_BY_OPERATION.get(operation_name)


def _dependency_circuit_allow(operation_name: str) -> tuple[bool, str | None]:
    dependency_key = _dependency_circuit_key_for_operation(operation_name)
    if dependency_key is None or not _dependency_circuit_enabled():
        return True, dependency_key
    return _DEPENDENCY_CIRCUIT_BREAKER.allow_request(dependency_key), dependency_key


def _dependency_circuit_record_success(operation_name: str) -> None:
    dependency_key = _dependency_circuit_key_for_operation(operation_name)
    if dependency_key is None or not _dependency_circuit_enabled():
        return
    _DEPENDENCY_CIRCUIT_BREAKER.record_success(dependency_key)


def _dependency_circuit_record_failure(operation_name: str, reason: str) -> None:
    dependency_key = _dependency_circuit_key_for_operation(operation_name)
    if dependency_key is None or not _dependency_circuit_enabled():
        return
    _DEPENDENCY_CIRCUIT_BREAKER.record_failure(dependency_key, reason=reason)


def _dependency_circuit_open_error(
    envelope: OperationEnvelopeRequest, dependency_key: str
) -> JSONResponse:
    return _operation_error(
        envelope=envelope,
        code="DEPENDENCY_CIRCUIT_OPEN",
        message=(
            "Dependency circuit is open for "
            f"{dependency_key}; retry after "
            f"{settings.MERLIN_DEPENDENCY_CIRCUIT_BREAKER_RESET_SECONDS} seconds"
        ),
        retryable=True,
        status_code=503,
    )


_OPERATION_METRICS_LOCK = Lock()
_OPERATION_METRICS: dict[str, dict[str, Any]] = {}


def _record_operation_metric(
    operation_name: str | None, status_code: int, latency_ms: float
) -> None:
    op_name = operation_name or "__unknown__"
    max_samples = max(1, settings.MERLIN_OPERATION_METRICS_MAX_SAMPLES)

    with _OPERATION_METRICS_LOCK:
        metric = _OPERATION_METRICS.get(op_name)
        if metric is None:
            metric = {
                "count": 0,
                "errors": 0,
                "latency_samples_ms": deque(maxlen=max_samples),
            }
            _OPERATION_METRICS[op_name] = metric

        samples = metric.get("latency_samples_ms")
        if not isinstance(samples, deque) or samples.maxlen != max_samples:
            previous_samples: list[float] = []
            if isinstance(samples, deque):
                previous_samples = list(samples)
            elif isinstance(samples, list):
                previous_samples = [float(item) for item in samples]
            samples = deque(previous_samples[-max_samples:], maxlen=max_samples)
            metric["latency_samples_ms"] = samples

        metric["count"] = int(metric.get("count", 0)) + 1
        if status_code >= 400:
            metric["errors"] = int(metric.get("errors", 0)) + 1
        samples.append(max(0.0, float(latency_ms)))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)

    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    interpolated = (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )
    return round(interpolated, 3)


SUPPORTED_ENVELOPE_OPERATIONS: list[str] = [
    "assistant.chat.request",
    "assistant.tools.execute",
    "merlin.alerts.list",
    "merlin.command.execute",
    "merlin.context.get",
    "merlin.context.update",
    "merlin.discovery.run",
    "merlin.discovery.queue.status",
    "merlin.discovery.queue.drain",
    "merlin.discovery.queue.pause",
    "merlin.discovery.queue.resume",
    "merlin.discovery.queue.purge_deadletter",
    "merlin.dynamic_components.list",
    "merlin.history.get",
    "merlin.llm.ab.complete",
    "merlin.llm.ab.create",
    "merlin.llm.ab.get",
    "merlin.llm.ab.list",
    "merlin.llm.ab.result",
    "merlin.llm.adaptive.feedback",
    "merlin.llm.adaptive.metrics",
    "merlin.llm.adaptive.reset",
    "merlin.llm.adaptive.status",
    "merlin.llm.cost.budget.get",
    "merlin.llm.cost.budget.set",
    "merlin.llm.cost.optimization.get",
    "merlin.llm.cost.pricing.set",
    "merlin.llm.cost.report",
    "merlin.llm.cost.thresholds.get",
    "merlin.llm.cost.thresholds.set",
    "merlin.llm.parallel.status",
    "merlin.llm.parallel.strategy",
    "merlin.llm.predictive.export",
    "merlin.llm.predictive.feedback",
    "merlin.llm.predictive.models",
    "merlin.llm.predictive.select",
    "merlin.llm.predictive.status",
    "merlin.plugins.list",
    "merlin.plugins.execute",
    "merlin.research.manager.session.create",
    "merlin.research.manager.sessions.list",
    "merlin.research.manager.session.get",
    "merlin.research.manager.session.signal.add",
    "merlin.research.manager.brief.get",
    "merlin.knowledge.search",
    "merlin.seed.status",
    "merlin.seed.health",
    "merlin.seed.health.heartbeat",
    "merlin.seed.watchdog.tick",
    "merlin.seed.watchdog.status",
    "merlin.seed.watchdog.control",
    "merlin.seed.control",
    "merlin.rag.query",
    "merlin.search.query",
    "merlin.voice.status",
    "merlin.voice.synthesize",
    "merlin.voice.listen",
    "merlin.voice.transcribe",
    "merlin.tasks.create",
    "merlin.tasks.list",
    "merlin.user_manager.create",
    "merlin.user_manager.authenticate",
    "merlin.system_info.get",
    "merlin.genesis.logs",
    "merlin.genesis.manifest",
    "merlin.aas.create_task",
]


def _setting_source(*env_names: str) -> str:
    for env_name in env_names:
        if os.getenv(env_name) is not None:
            return "env"
    return "default"


def _capability_flag(
    name: str, value: Any, source: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    record: dict[str, Any] = {"name": name, "value": value, "source": source}
    if details:
        record["details"] = details
    return record


def _operation_capability_flags() -> list[dict[str, Any]]:
    rate_limit_enabled = settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE > 0 or bool(
        settings.MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION
    )
    prometheus_metrics_enabled = not _coerce_bool(
        os.environ.get("MERLIN_DISABLE_PROMETHEUS_METRICS")
    )
    research_manager_writable = bool(getattr(research_manager, "allow_writes", True))

    return [
        _capability_flag(
            "llm_backend",
            settings.LLM_BACKEND,
            _setting_source("LLM_BACKEND"),
        ),
        _capability_flag(
            "parallel_strategy",
            settings.PARALLEL_STRATEGY,
            _setting_source("PARALLEL_STRATEGY"),
        ),
        _capability_flag(
            "dms_enabled",
            bool(settings.DMS_ENABLED),
            _setting_source("DMS_ENABLED"),
        ),
        _capability_flag(
            "dms_ab_enabled",
            bool(settings.DMS_AB_ENABLED),
            _setting_source("DMS_AB_ENABLED"),
        ),
        _capability_flag(
            "dms_error_budget_enabled",
            bool(settings.DMS_ERROR_BUDGET_ENABLED),
            _setting_source("DMS_ERROR_BUDGET_ENABLED"),
        ),
        _capability_flag(
            "research_manager_auto_archive_enabled",
            bool(settings.MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED),
            _setting_source("MERLIN_RESEARCH_AUTO_ARCHIVE_ENABLED"),
        ),
        _capability_flag(
            "operation_rate_limit_enabled",
            rate_limit_enabled,
            _setting_source(
                "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE",
                "MERLIN_OPERATION_RATE_LIMIT_PER_MINUTE_BY_OPERATION",
            ),
        ),
        _capability_flag(
            "operation_payload_override_enabled",
            bool(settings.MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION),
            _setting_source("MERLIN_OPERATION_PAYLOAD_MAX_BYTES_BY_OPERATION"),
        ),
        _capability_flag(
            "operation_feature_flags",
            settings.MERLIN_OPERATION_FEATURE_FLAGS,
            _setting_source("MERLIN_OPERATION_FEATURE_FLAGS"),
        ),
        _capability_flag(
            "prometheus_metrics_enabled",
            prometheus_metrics_enabled,
            _setting_source("MERLIN_DISABLE_PROMETHEUS_METRICS"),
        ),
        _capability_flag(
            "research_manager_writable",
            research_manager_writable,
            "runtime",
            details={"read_only_mode": not research_manager_writable},
        ),
    ]


def _operation_spec_snapshot_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for operation_name in SUPPORTED_ENVELOPE_OPERATIONS:
        deprecation_policy = DEPRECATED_OPERATION_POLICIES.get(operation_name, {})
        row: dict[str, Any] = {
            "name": operation_name,
            "version": "1.0.0",
            "stability": "stable",
            "deprecated": bool(deprecation_policy),
        }
        replacement_operation = deprecation_policy.get("replacement_operation")
        if replacement_operation:
            row["replacement_operation"] = replacement_operation
        sunset = deprecation_policy.get("sunset")
        if sunset:
            row["sunset"] = sunset
        rows.append(row)
    return rows


@app.get("/merlin/operations/capabilities")
async def operation_capabilities(api_key: str = Depends(get_api_key)):
    capabilities = [
        {
            "name": operation_name,
            "version": "1.0.0",
            "stability": "stable",
        }
        for operation_name in SUPPORTED_ENVELOPE_OPERATIONS
    ]
    return JSONResponse(
        content={
            "schema_name": "AAS.RepoCapabilityManifest",
            "schema_version": "1.0.0",
            "repo": "AaroneousAutomationSuite/Merlin",
            "service": "merlin_api_server",
            "endpoint": "/merlin/operations",
            "capabilities": capabilities,
        }
    )


@app.get("/merlin/operations/spec")
async def operation_spec_snapshot(api_key: str = Depends(get_api_key)):
    return JSONResponse(
        content={
            "schema_name": "AAS.OperationSpecSnapshot",
            "schema_version": "1.0.0",
            "repo": "AaroneousAutomationSuite/Merlin",
            "service": "merlin_api_server",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "endpoint": "/merlin/operations",
            "request_schema": {
                "schema_name": OPERATION_ENVELOPE_SCHEMA_NAME,
                "schema_version": OPERATION_ENVELOPE_SCHEMA_VERSION,
                "contract_path": "contracts/aas.operation-envelope.v1.schema.json",
            },
            "docs": {
                "protocol_readme": "docs/protocols/README.md",
                "capabilities": "docs/protocols/repo-capabilities-merlin-v1.md",
                "compatibility": "docs/protocols/compatibility-policy.md",
                "envelope": "docs/protocols/operation-envelope-v1.md",
            },
            "operations": _operation_spec_snapshot_rows(),
        }
    )


@app.get("/merlin/operations/capability-flags")
async def operation_capability_flags(api_key: str = Depends(get_api_key)):
    return JSONResponse(
        content={
            "schema_name": "AAS.RepoCapabilityFlags",
            "schema_version": "1.0.0",
            "repo": "AaroneousAutomationSuite/Merlin",
            "service": "merlin_api_server",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "flags": _operation_capability_flags(),
        }
    )


@app.get("/merlin/operations/replay-diagnostics")
async def operation_replay_diagnostics(api_key: str = Depends(get_api_key)):
    if not settings.MERLIN_OPERATION_REPLAY_DIAGNOSTICS_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    rows = _operation_replay_diagnostics_rows()
    return JSONResponse(
        content={
            "schema_name": "AAS.OperationReplayDiagnostics",
            "schema_version": "1.0.0",
            "repo": "AaroneousAutomationSuite/Merlin",
            "service": "merlin_api_server",
            "enabled": True,
            "ttl_seconds": IDEMPOTENCY_CACHE_TTL_SECONDS,
            "entry_count": len(rows),
            "entries": rows,
        }
    )


@app.get("/merlin/operations/metrics")
async def operation_metrics(api_key: str = Depends(get_api_key)):
    with _OPERATION_METRICS_LOCK:
        operations = []
        for operation_name in sorted(_OPERATION_METRICS.keys()):
            metric = _OPERATION_METRICS[operation_name]
            count = int(metric.get("count", 0))
            errors = int(metric.get("errors", 0))
            samples_raw = metric.get("latency_samples_ms")
            if isinstance(samples_raw, deque):
                samples = [float(value) for value in samples_raw]
            elif isinstance(samples_raw, list):
                samples = [float(value) for value in samples_raw]
            else:
                samples = []

            operations.append(
                {
                    "name": operation_name,
                    "count": count,
                    "error_count": errors,
                    "error_rate": round(errors / count, 4) if count else 0.0,
                    "latency_ms": {
                        "p50": _percentile(samples, 0.50),
                        "p95": _percentile(samples, 0.95),
                        "p99": _percentile(samples, 0.99),
                        "sample_count": len(samples),
                    },
                }
            )

    return JSONResponse(
        content={
            "schema_name": "AAS.OperationMetrics",
            "schema_version": "1.0.0",
            "service": "merlin_api_server",
            "max_samples_per_operation": settings.MERLIN_OPERATION_METRICS_MAX_SAMPLES,
            "operations": operations,
        }
    )


@app.post("/merlin/operations")
async def execute_operation(
    envelope: OperationEnvelopeRequest, api_key: str = Depends(get_api_key)
):
    validation_error = _validate_operation_envelope(envelope)
    if validation_error is not None:
        return validation_error
    replay_response = _idempotency_replay_response(envelope)
    if replay_response is not None:
        return replay_response
    dependency_allowed, dependency_key = _dependency_circuit_allow(
        envelope.operation.name
    )
    if not dependency_allowed and dependency_key is not None:
        return _dependency_circuit_open_error(envelope, dependency_key)

    def _build_discovery_operation_engine(
        payload: dict[str, Any],
    ) -> tuple[Any | None, JSONResponse | None]:
        raw_workspace_root = payload.get("workspace_root", None)
        raw_merlin_mode = payload.get("merlin_mode", "local")
        if raw_workspace_root is not None and not isinstance(raw_workspace_root, str):
            return None, _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.workspace_root must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_merlin_mode, str):
            return None, _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merlin_mode must be a string when provided",
                status_code=422,
            )
        merlin_mode = raw_merlin_mode.strip().lower() or "local"
        if merlin_mode not in {"local", "null"}:
            return None, _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merlin_mode must be one of: local, null",
                status_code=422,
            )

        workspace_root = (
            Path(raw_workspace_root).resolve()
            if isinstance(raw_workspace_root, str) and raw_workspace_root.strip()
            else Path.cwd().resolve()
        )
        try:
            engine = build_discovery_engine(
                workspace_root=workspace_root,
                merlin_mode=merlin_mode,
            )
        except Exception as exc:
            merlin_logger.error(f"Discovery engine init failed: {exc}")
            return None, _operation_error(
                envelope=envelope,
                code="DISCOVERY_ENGINE_INIT_FAILED",
                message="Discovery engine initialization failed",
                retryable=True,
                status_code=500,
            )
        return engine, None

    def _build_seed_access_controller(
        payload: dict[str, Any],
    ) -> tuple[Any | None, JSONResponse | None]:
        raw_workspace_root = payload.get("workspace_root", None)
        if raw_workspace_root is not None and not isinstance(raw_workspace_root, str):
            return None, _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.workspace_root must be a string when provided",
                status_code=422,
            )
        workspace_root = (
            raw_workspace_root.strip()
            if isinstance(raw_workspace_root, str) and raw_workspace_root.strip()
            else None
        )
        try:
            controller = build_seed_access(workspace_root=workspace_root)
        except Exception as exc:
            merlin_logger.error(f"Seed access init failed: {exc}")
            return None, _operation_error(
                envelope=envelope,
                code="SEED_ACCESS_INIT_FAILED",
                message="Seed access initialization failed",
                retryable=True,
                status_code=500,
            )
        return controller, None

    if envelope.operation.name == "assistant.chat.request":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="assistant.chat.request payload must be an object",
                status_code=422,
            )

        raw_user_input = envelope.payload.get("user_input", "")
        raw_user_id = envelope.payload.get("user_id", "default")
        raw_research_session_id = envelope.payload.get("research_session_id", None)

        user_input = raw_user_input if isinstance(raw_user_input, str) else ""
        user_id = raw_user_id if isinstance(raw_user_id, str) else "default"
        if raw_research_session_id is not None and not isinstance(
            raw_research_session_id, str
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.research_session_id must be a string when provided",
                status_code=422,
            )
        research_session_id = (
            raw_research_session_id if isinstance(raw_research_session_id, str) else ""
        )

        if not user_input.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.user_input is required",
                status_code=422,
            )

        include_metadata = _coerce_bool(envelope.payload.get("include_metadata", False))
        if include_metadata:
            reply, metadata = merlin_emotion_chat_with_metadata(user_input, user_id)
            response_payload: dict[str, Any] = {
                "reply": reply,
                "user_id": user_id,
                "metadata": metadata,
            }
            if research_session_id.strip() and isinstance(metadata, dict):
                response_payload["research_signal_ingest"] = (
                    ingest_planner_fallback_telemetry(
                        session_id=research_session_id,
                        metadata=metadata,
                        source="assistant.chat.request",
                    )
                )
            return _operation_response(
                envelope=envelope,
                payload=response_payload,
            )

        reply = merlin_emotion_chat(user_input, user_id)
        return _operation_response(
            envelope=envelope,
            payload={"reply": reply, "user_id": user_id},
        )

    if envelope.operation.name == "assistant.tools.execute":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="assistant.tools.execute payload must be an object",
                status_code=422,
            )

        raw_name = envelope.payload.get("name", "")
        raw_args = envelope.payload.get("args", [])
        raw_kwargs = envelope.payload.get("kwargs", {})

        tool_name = raw_name if isinstance(raw_name, str) else ""
        if not tool_name.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.name is required",
                status_code=422,
            )
        if not isinstance(raw_args, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.args must be an array when provided",
                status_code=422,
            )
        if not isinstance(raw_kwargs, dict):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.kwargs must be an object when provided",
                status_code=422,
            )

        try:
            result = plugin_manager.execute_plugin(tool_name, *raw_args, **raw_kwargs)
        except Exception as exc:
            merlin_logger.error(f"Tool execution failed: {tool_name}: {exc}")
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="TOOL_EXECUTION_ERROR",
            )
            return _operation_error(
                envelope=envelope,
                code="TOOL_EXECUTION_ERROR",
                message=f"Tool execution failed: {tool_name}",
                status_code=500,
            )

        if isinstance(result, dict) and "error" in result:
            result_code = str(result.get("code", "")).strip().upper()
            if result_code == "PLUGIN_PERMISSION_DENIED":
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_PERMISSION_DENIED",
                    message=str(result.get("error", "Plugin permission denied")),
                    status_code=403,
                )
            if result_code == "PLUGIN_TIMEOUT":
                _dependency_circuit_record_failure(
                    envelope.operation.name,
                    reason="PLUGIN_TIMEOUT",
                )
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_TIMEOUT",
                    message=str(result.get("error", "Plugin timed out")),
                    retryable=True,
                    status_code=504,
                )
            if result_code == "PLUGIN_PROCESS_SERIALIZATION_ERROR":
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_PROCESS_SERIALIZATION_ERROR",
                    message=str(
                        result.get("error", "Plugin process serialization failed")
                    ),
                    status_code=502,
                )
            if result_code == "PLUGIN_CRASH_ISOLATED":
                _dependency_circuit_record_failure(
                    envelope.operation.name,
                    reason="PLUGIN_CRASH_ISOLATED",
                )
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_CRASH_ISOLATED",
                    message=str(
                        result.get(
                            "error",
                            "Plugin isolated after repeated crashes",
                        )
                    ),
                    retryable=True,
                    status_code=503,
                )
            _dependency_circuit_record_success(envelope.operation.name)
            return _operation_error(
                envelope=envelope,
                code="TOOL_NOT_FOUND",
                message=str(result.get("error", f"Tool {tool_name} not found")),
                status_code=404,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"name": tool_name, "result": result},
        )

    if envelope.operation.name == "merlin.voice.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.voice.status payload must be an object",
                status_code=422,
            )

        voice_instance = get_voice()
        if not voice_instance:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_UNAVAILABLE",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        status_payload = voice_instance.status()
        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"status": status_payload},
        )

    if envelope.operation.name == "merlin.voice.synthesize":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.voice.synthesize payload must be an object",
                status_code=422,
            )

        raw_text = envelope.payload.get("text", "")
        raw_engine = envelope.payload.get("engine", None)

        text = raw_text if isinstance(raw_text, str) else ""
        engine = raw_engine if isinstance(raw_engine, str) else None
        if not text.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.text is required",
                status_code=422,
            )

        voice_instance = get_voice()
        if not voice_instance:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_UNAVAILABLE",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        output_path = voice_instance.synthesize_to_file(text, engine=engine)
        if not output_path:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_SYNTHESIS_FAILED",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_SYNTHESIS_FAILED",
                message="Voice synthesis failed",
                status_code=500,
            )
        output_path = Path(output_path)
        if not output_path.exists():
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_OUTPUT_MISSING",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_OUTPUT_MISSING",
                message="Voice output file missing after synthesis",
                status_code=500,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"path": output_path.as_posix(), "filename": output_path.name},
        )

    if envelope.operation.name == "merlin.voice.listen":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.voice.listen payload must be an object",
                status_code=422,
            )

        raw_engine = envelope.payload.get("engine", None)
        engine = raw_engine if isinstance(raw_engine, str) else None

        voice_instance = get_voice()
        if not voice_instance:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_UNAVAILABLE",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        text = voice_instance.listen(engine=engine)
        if not text:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_LISTEN_FAILED",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_LISTEN_FAILED",
                message="Voice listen failed",
                status_code=500,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"text": text},
        )

    if envelope.operation.name == "merlin.voice.transcribe":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.voice.transcribe payload must be an object",
                status_code=422,
            )

        raw_file_path = envelope.payload.get("file_path", "")
        raw_engine = envelope.payload.get("engine", None)

        file_path = raw_file_path if isinstance(raw_file_path, str) else ""
        engine = raw_engine if isinstance(raw_engine, str) else None
        if not file_path.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.file_path is required",
                status_code=422,
            )

        voice_instance = get_voice()
        if not voice_instance:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_UNAVAILABLE",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        text = voice_instance.transcribe_file(file_path, engine=engine)
        if not text:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="VOICE_TRANSCRIBE_FAILED",
            )
            return _operation_error(
                envelope=envelope,
                code="VOICE_TRANSCRIBE_FAILED",
                message="Voice transcription failed",
                status_code=500,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"text": text, "file_path": file_path},
        )

    if envelope.operation.name == "merlin.user_manager.create":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.user_manager.create payload must be an object",
                status_code=422,
            )

        raw_username = envelope.payload.get("username", "")
        raw_password = envelope.payload.get("password", "")
        raw_role = envelope.payload.get("role", "user")

        username = raw_username if isinstance(raw_username, str) else ""
        password = raw_password if isinstance(raw_password, str) else ""
        role = raw_role if isinstance(raw_role, str) and raw_role.strip() else "user"

        if not username.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.username is required",
                status_code=422,
            )
        if not password:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.password is required",
                status_code=422,
            )

        try:
            user = user_manager.create_user(username, password, role=role)
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="USER_EXISTS",
                message=str(exc),
                status_code=409,
            )
        except Exception as exc:
            merlin_logger.error(f"User creation failed for {username}: {exc}")
            return _operation_error(
                envelope=envelope,
                code="USER_CREATE_FAILED",
                message="User creation failed",
                status_code=500,
            )

        return _operation_response(
            envelope=envelope,
            payload={"user": user},
        )

    if envelope.operation.name == "merlin.user_manager.authenticate":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.user_manager.authenticate payload must be an object",
                status_code=422,
            )

        raw_username = envelope.payload.get("username", "")
        raw_password = envelope.payload.get("password", "")

        username = raw_username if isinstance(raw_username, str) else ""
        password = raw_password if isinstance(raw_password, str) else ""

        if not username.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.username is required",
                status_code=422,
            )
        if not password:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.password is required",
                status_code=422,
            )

        auth_user = user_manager.authenticate_user(username, password)
        if not auth_user:
            return _operation_error(
                envelope=envelope,
                code="AUTH_FAILED",
                message="Invalid username or password",
                status_code=401,
            )

        role = str(auth_user.get("role", "user"))
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": username, "role": role},
            expires_delta=access_token_expires,
        )

        return _operation_response(
            envelope=envelope,
            payload={
                "access_token": access_token,
                "token_type": "bearer",
                "username": username,
                "role": role,
                "expires_in_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
            },
        )

    if envelope.operation.name == "merlin.system_info.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.system_info.get payload must be an object",
                status_code=422,
            )
        return _operation_response(
            envelope=envelope,
            payload={"system_info": get_system_info()},
        )

    if envelope.operation.name == "merlin.genesis.logs":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.genesis.logs payload must be an object",
                status_code=422,
            )
        return _operation_response(
            envelope=envelope,
            payload={"logs": get_recent_logs()},
        )

    if envelope.operation.name == "merlin.aas.create_task":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.aas.create_task payload must be an object",
                status_code=422,
            )

        raw_title = envelope.payload.get("title", "")
        raw_description = envelope.payload.get("description", "")
        raw_priority = envelope.payload.get("priority", "Medium")

        title = raw_title if isinstance(raw_title, str) else ""
        description = raw_description if isinstance(raw_description, str) else ""
        priority = (
            raw_priority
            if isinstance(raw_priority, str) and raw_priority.strip()
            else "Medium"
        )

        if not title.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.title is required",
                status_code=422,
            )

        task_id = hub_client.create_aas_task(title, description, priority)
        if not task_id:
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="AAS_TASK_CREATE_FAILED",
            )
            return _operation_error(
                envelope=envelope,
                code="AAS_TASK_CREATE_FAILED",
                message="Failed to create AAS task",
                retryable=True,
                status_code=502,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"task_id": task_id},
        )

    if envelope.operation.name == "merlin.plugins.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.plugins.list payload must be an object",
                status_code=422,
            )

        raw_format = envelope.payload.get("format", "list")
        raw_capability = envelope.payload.get("capability", None)
        raw_health_state = envelope.payload.get("health_state", None)
        output_format = raw_format if isinstance(raw_format, str) else "list"
        if output_format not in {"list", "map"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.format must be one of: list, map",
                status_code=422,
            )
        if raw_capability is not None and not isinstance(raw_capability, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.capability must be a string when provided",
                status_code=422,
            )
        if raw_health_state is not None and not isinstance(raw_health_state, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.health_state must be a string when provided",
                status_code=422,
            )
        capability_filter = (
            raw_capability.strip() if isinstance(raw_capability, str) else ""
        )
        health_state_filter = (
            raw_health_state.strip().lower()
            if isinstance(raw_health_state, str)
            else ""
        )
        if health_state_filter and health_state_filter not in {
            "healthy",
            "degraded",
            "isolated",
        }:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.health_state must be one of: healthy, degraded, isolated",
                status_code=422,
            )

        plugin_info = plugin_manager.list_plugin_info()
        if capability_filter:
            plugin_info = {
                name: info
                for name, info in plugin_info.items()
                if capability_filter
                in (
                    info.get("capabilities", [])
                    if isinstance(info.get("capabilities"), list)
                    else []
                )
            }
        if health_state_filter:
            plugin_info = {
                name: info
                for name, info in plugin_info.items()
                if str(info.get("health_state", "")).strip().lower()
                == health_state_filter
            }
        plugins = plugin_info if output_format == "map" else list(plugin_info.values())
        return _operation_response(
            envelope=envelope,
            payload={
                "plugins": plugins,
                "format": output_format,
                "filters": {
                    "capability": capability_filter or None,
                    "health_state": health_state_filter or None,
                },
            },
        )

    if envelope.operation.name == "merlin.plugins.execute":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.plugins.execute payload must be an object",
                status_code=422,
            )

        raw_name = envelope.payload.get("name", "")
        raw_args = envelope.payload.get("args", [])
        raw_kwargs = envelope.payload.get("kwargs", {})

        plugin_name = raw_name if isinstance(raw_name, str) else ""
        if not plugin_name.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.name is required",
                status_code=422,
            )
        if not isinstance(raw_args, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.args must be an array when provided",
                status_code=422,
            )
        if not isinstance(raw_kwargs, dict):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.kwargs must be an object when provided",
                status_code=422,
            )

        try:
            result = plugin_manager.execute_plugin(plugin_name, *raw_args, **raw_kwargs)
        except Exception as exc:
            merlin_logger.error(f"Plugin execution failed: {plugin_name}: {exc}")
            _dependency_circuit_record_failure(
                envelope.operation.name,
                reason="PLUGIN_EXECUTION_ERROR",
            )
            return _operation_error(
                envelope=envelope,
                code="PLUGIN_EXECUTION_ERROR",
                message=f"Plugin execution failed: {plugin_name}",
                status_code=500,
            )

        if isinstance(result, dict) and "error" in result:
            error_message = str(result.get("error", f"Plugin {plugin_name} failed"))
            result_code = str(result.get("code", "")).strip().upper()
            if result_code == "PLUGIN_PERMISSION_DENIED":
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_PERMISSION_DENIED",
                    message=error_message,
                    status_code=403,
                )
            if result_code == "PLUGIN_TIMEOUT":
                _dependency_circuit_record_failure(
                    envelope.operation.name,
                    reason="PLUGIN_TIMEOUT",
                )
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_TIMEOUT",
                    message=error_message,
                    retryable=True,
                    status_code=504,
                )
            if result_code == "PLUGIN_PROCESS_SERIALIZATION_ERROR":
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_PROCESS_SERIALIZATION_ERROR",
                    message=error_message,
                    status_code=502,
                )
            if result_code == "PLUGIN_CRASH_ISOLATED":
                _dependency_circuit_record_failure(
                    envelope.operation.name,
                    reason="PLUGIN_CRASH_ISOLATED",
                )
                return _operation_error(
                    envelope=envelope,
                    code="PLUGIN_CRASH_ISOLATED",
                    message=error_message,
                    retryable=True,
                    status_code=503,
                )
            not_found = "not found" in error_message.lower()
            if not_found:
                _dependency_circuit_record_success(envelope.operation.name)
            else:
                _dependency_circuit_record_failure(
                    envelope.operation.name,
                    reason="PLUGIN_EXECUTION_FAILED",
                )
            return _operation_error(
                envelope=envelope,
                code="PLUGIN_NOT_FOUND" if not_found else "PLUGIN_EXECUTION_FAILED",
                message=error_message,
                status_code=404 if not_found else 400,
            )

        _dependency_circuit_record_success(envelope.operation.name)
        return _operation_response(
            envelope=envelope,
            payload={"name": plugin_name, "result": result},
        )

    if envelope.operation.name == "merlin.research.manager.session.create":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.research.manager.session.create payload must be an object",
                status_code=422,
            )

        raw_objective = envelope.payload.get("objective", "")
        raw_constraints = envelope.payload.get("constraints", None)
        raw_horizon_days = envelope.payload.get("horizon_days", 14)
        raw_tags = envelope.payload.get("tags", None)
        raw_impact = envelope.payload.get("impact", None)
        raw_uncertainty = envelope.payload.get("uncertainty", None)
        raw_time_horizon = envelope.payload.get("time_horizon", None)
        raw_linked_task_ids = envelope.payload.get("linked_task_ids", None)
        raw_planner_artifacts = envelope.payload.get("planner_artifacts", None)

        objective = raw_objective if isinstance(raw_objective, str) else ""
        if not objective.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.objective is required",
                status_code=422,
            )
        if raw_constraints is not None and not isinstance(raw_constraints, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.constraints must be an array when provided",
                status_code=422,
            )
        if raw_tags is not None and not isinstance(raw_tags, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.tags must be an array when provided",
                status_code=422,
            )
        if raw_linked_task_ids is not None and not isinstance(
            raw_linked_task_ids, list
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.linked_task_ids must be an array when provided",
                status_code=422,
            )
        if raw_planner_artifacts is not None and not isinstance(
            raw_planner_artifacts, list
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.planner_artifacts must be an array when provided",
                status_code=422,
            )
        if isinstance(raw_linked_task_ids, list):
            for item in raw_linked_task_ids:
                if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
                    return _operation_error(
                        envelope=envelope,
                        code="VALIDATION_ERROR",
                        message="payload.linked_task_ids values must be positive integers",
                        status_code=422,
                    )
        if isinstance(raw_planner_artifacts, list):
            for item in raw_planner_artifacts:
                if not isinstance(item, str) or not item.strip():
                    return _operation_error(
                        envelope=envelope,
                        code="VALIDATION_ERROR",
                        message="payload.planner_artifacts values must be non-empty strings",
                        status_code=422,
                    )
        if raw_impact is not None and not isinstance(raw_impact, (int, float)):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.impact must be a number when provided",
                status_code=422,
            )
        if raw_uncertainty is not None and not isinstance(
            raw_uncertainty, (int, float)
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.uncertainty must be a number when provided",
                status_code=422,
            )
        if raw_time_horizon is not None and not isinstance(raw_time_horizon, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.time_horizon must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_horizon_days, int) or raw_horizon_days <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.horizon_days must be an integer greater than zero",
                status_code=422,
            )

        try:
            session = research_manager.create_session(
                objective=objective,
                constraints=raw_constraints,
                horizon_days=raw_horizon_days,
                tags=raw_tags,
                impact=float(raw_impact) if raw_impact is not None else None,
                uncertainty=(
                    float(raw_uncertainty) if raw_uncertainty is not None else None
                ),
                time_horizon=raw_time_horizon,
                linked_task_ids=raw_linked_task_ids,
                planner_artifacts=raw_planner_artifacts,
                created_by=_operation_source_actor(envelope.source),
                source_operation=envelope.operation.name,
                policy_version=RESEARCH_SESSION_PROVENANCE_POLICY_VERSION,
            )
        except PermissionError as exc:
            return _operation_error(
                envelope=envelope,
                code="RESEARCH_MANAGER_READ_ONLY",
                message=str(exc),
                status_code=403,
            )
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={
                "session": session,
                "next_actions": research_manager.next_actions(session["session_id"]),
            },
        )

    if envelope.operation.name == "merlin.research.manager.sessions.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.research.manager.sessions.list payload must be an object",
                status_code=422,
            )

        raw_limit = envelope.payload.get("limit", 20)
        raw_tag = envelope.payload.get("tag", None)
        raw_topic = envelope.payload.get("topic", None)
        raw_cursor = envelope.payload.get("cursor", None)
        if not isinstance(raw_limit, int) or raw_limit <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.limit must be an integer greater than zero",
                status_code=422,
            )
        if raw_tag is not None and not isinstance(raw_tag, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.tag must be a string when provided",
                status_code=422,
            )
        if raw_topic is not None and not isinstance(raw_topic, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.topic must be a string when provided",
                status_code=422,
            )
        if raw_cursor is not None and not isinstance(raw_cursor, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.cursor must be a string when provided",
                status_code=422,
            )

        normalized_limit = min(raw_limit, 200)
        try:
            page = research_manager.list_sessions_page(
                limit=normalized_limit,
                cursor=raw_cursor,
                tag=raw_tag,
                topic_query=raw_topic,
            )
            sessions = page.get("sessions", [])
            next_cursor = page.get("next_cursor")
        except AttributeError:
            sessions = research_manager.list_sessions(
                limit=normalized_limit,
                tag=raw_tag,
                topic_query=raw_topic,
            )
            next_cursor = None
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        return _operation_response(
            envelope=envelope,
            payload={"sessions": sessions, "next_cursor": next_cursor},
        )

    if envelope.operation.name == "merlin.research.manager.session.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.research.manager.session.get payload must be an object",
                status_code=422,
            )

        raw_session_id = envelope.payload.get("session_id", "")
        session_id = raw_session_id if isinstance(raw_session_id, str) else ""
        if not session_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.session_id is required",
                status_code=422,
            )

        try:
            session = research_manager.get_session(session_id)
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except FileNotFoundError:
            return _operation_error(
                envelope=envelope,
                code="SESSION_NOT_FOUND",
                message="Research session not found",
                status_code=404,
            )

        return _operation_response(
            envelope=envelope,
            payload={"session": session},
        )

    if envelope.operation.name == "merlin.research.manager.session.signal.add":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.research.manager.session.signal.add payload must be an object",
                status_code=422,
            )

        raw_session_id = envelope.payload.get("session_id", "")
        raw_source = envelope.payload.get("source", "")
        raw_claim = envelope.payload.get("claim", "")
        raw_confidence = envelope.payload.get("confidence", 0.6)
        raw_novelty = envelope.payload.get("novelty", 0.5)
        raw_risk = envelope.payload.get("risk", 0.2)
        raw_supports = envelope.payload.get("supports", None)
        raw_contradicts = envelope.payload.get("contradicts", None)

        session_id = raw_session_id if isinstance(raw_session_id, str) else ""
        source = raw_source if isinstance(raw_source, str) else ""
        claim = raw_claim if isinstance(raw_claim, str) else ""

        if not session_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.session_id is required",
                status_code=422,
            )
        if not source.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.source is required",
                status_code=422,
            )
        if not claim.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.claim is required",
                status_code=422,
            )
        if not isinstance(raw_confidence, (int, float)):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.confidence must be a number when provided",
                status_code=422,
            )
        if not isinstance(raw_novelty, (int, float)):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.novelty must be a number when provided",
                status_code=422,
            )
        if not isinstance(raw_risk, (int, float)):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.risk must be a number when provided",
                status_code=422,
            )
        if raw_supports is not None and not isinstance(raw_supports, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.supports must be an array when provided",
                status_code=422,
            )
        if raw_contradicts is not None and not isinstance(raw_contradicts, list):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.contradicts must be an array when provided",
                status_code=422,
            )

        try:
            signal_result = research_manager.add_signal(
                session_id=session_id,
                source=source,
                claim=claim,
                confidence=float(raw_confidence),
                novelty=float(raw_novelty),
                risk=float(raw_risk),
                supports=raw_supports,
                contradicts=raw_contradicts,
            )
        except PermissionError as exc:
            return _operation_error(
                envelope=envelope,
                code="RESEARCH_MANAGER_READ_ONLY",
                message=str(exc),
                status_code=403,
            )
        except FileNotFoundError:
            return _operation_error(
                envelope=envelope,
                code="SESSION_NOT_FOUND",
                message="Research session not found",
                status_code=404,
            )
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload=signal_result,
        )

    if envelope.operation.name == "merlin.research.manager.brief.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.research.manager.brief.get payload must be an object",
                status_code=422,
            )

        raw_session_id = envelope.payload.get("session_id", "")
        session_id = raw_session_id if isinstance(raw_session_id, str) else ""
        if not session_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.session_id is required",
                status_code=422,
            )

        try:
            brief = research_manager.get_brief(session_id)
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except FileNotFoundError:
            return _operation_error(
                envelope=envelope,
                code="SESSION_NOT_FOUND",
                message="Research session not found",
                status_code=404,
            )

        return _operation_response(
            envelope=envelope,
            payload={"brief": brief},
        )

    if envelope.operation.name == "merlin.discovery.run":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.run payload must be an object",
                status_code=422,
            )

        raw_profile = envelope.payload.get("profile", "public")
        raw_out = envelope.payload.get("out", None)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_seeds_file = envelope.payload.get("seeds_file", None)
        raw_fixture_feed = envelope.payload.get("fixture_feed", None)
        raw_top_k = envelope.payload.get("top_k", 3)
        raw_min_score = envelope.payload.get("min_score", 0.35)
        raw_max_bundle_size = envelope.payload.get("max_bundle_size", 4)
        raw_max_items_per_seed = envelope.payload.get("max_items_per_seed", 10)
        raw_dry_run = envelope.payload.get("dry_run", False)
        raw_no_write = envelope.payload.get("no_write", False)
        raw_overwrite = envelope.payload.get("overwrite", False)
        raw_publisher_mode = envelope.payload.get("publisher_mode", "stage_only")
        raw_lease_ttl_seconds = envelope.payload.get("lease_ttl_seconds", 300)
        raw_max_retries = envelope.payload.get("max_retries", 2)
        raw_worker_id = envelope.payload.get("worker_id", "discovery-engine-v1")

        if not isinstance(raw_profile, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.profile must be a string when provided",
                status_code=422,
            )
        profile = raw_profile.strip().lower() or "public"
        if profile not in {"public", "experimental"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.profile must be one of: public, experimental",
                status_code=422,
            )
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if raw_seeds_file is not None and not isinstance(raw_seeds_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.seeds_file must be a string when provided",
                status_code=422,
            )
        if raw_fixture_feed is not None and not isinstance(raw_fixture_feed, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.fixture_feed must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_top_k, int) or raw_top_k <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.top_k must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_min_score, (int, float)):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.min_score must be a number when provided",
                status_code=422,
            )
        min_score = float(raw_min_score)
        if min_score < 0.0 or min_score > 1.0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.min_score must be between 0 and 1",
                status_code=422,
            )
        if not isinstance(raw_max_bundle_size, int) or raw_max_bundle_size <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.max_bundle_size must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_max_items_per_seed, int) or raw_max_items_per_seed <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.max_items_per_seed must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_dry_run, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.dry_run must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_no_write, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.no_write must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_overwrite, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.overwrite must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_publisher_mode, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.publisher_mode must be a string when provided",
                status_code=422,
            )
        publisher_mode = raw_publisher_mode.strip().lower() or "stage_only"
        if publisher_mode not in {"stage_only", "pr", "git", "push", "none"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.publisher_mode must be one of: stage_only, pr, git, push, none",
                status_code=422,
            )
        if not isinstance(raw_lease_ttl_seconds, int) or raw_lease_ttl_seconds <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.lease_ttl_seconds must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_max_retries, int) or raw_max_retries < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.max_retries must be an integer greater than or equal to zero",
                status_code=422,
            )
        if not isinstance(raw_worker_id, str) or not raw_worker_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.worker_id must be a non-empty string",
                status_code=422,
            )

        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error

        try:
            report = engine.run(
                profile=profile,
                out=raw_out,
                allow_live_automation=raw_allow_live_automation,
                seeds_file=raw_seeds_file,
                fixture_feed=raw_fixture_feed,
                top_k=raw_top_k,
                min_score=min_score,
                max_bundle_size=raw_max_bundle_size,
                max_items_per_seed=raw_max_items_per_seed,
                dry_run=raw_dry_run,
                no_write=raw_no_write,
                overwrite=raw_overwrite,
                publisher_mode=publisher_mode,
                lease_ttl_seconds=raw_lease_ttl_seconds,
                max_retries=raw_max_retries,
                worker_id=raw_worker_id.strip(),
            )
        except (ValueError, FileNotFoundError) as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except Exception as exc:
            merlin_logger.error(f"Discovery run failed: {exc}")
            return _operation_error(
                envelope=envelope,
                code="DISCOVERY_RUN_FAILED",
                message="Discovery run failed",
                retryable=True,
                status_code=500,
            )

        return _operation_response(
            envelope=envelope,
            payload={"report": report},
        )

    if envelope.operation.name == "merlin.discovery.queue.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.queue.status payload must be an object",
                status_code=422,
            )
        raw_out = envelope.payload.get("out", None)
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        status_payload = engine.queue_status(out=raw_out)
        return _operation_response(
            envelope=envelope,
            payload={"status": status_payload},
        )

    if envelope.operation.name == "merlin.discovery.queue.drain":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.queue.drain payload must be an object",
                status_code=422,
            )
        raw_out = envelope.payload.get("out", None)
        raw_run_id = envelope.payload.get("run_id", None)
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        if raw_run_id is not None and not isinstance(raw_run_id, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.run_id must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        drain_payload = engine.queue_drain(out=raw_out, run_id=raw_run_id)
        return _operation_response(
            envelope=envelope,
            payload={"drain": drain_payload},
        )

    if envelope.operation.name == "merlin.discovery.queue.pause":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.queue.pause payload must be an object",
                status_code=422,
            )
        raw_out = envelope.payload.get("out", None)
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        pause_payload = engine.queue_pause(out=raw_out)
        return _operation_response(
            envelope=envelope,
            payload={"pause": pause_payload},
        )

    if envelope.operation.name == "merlin.discovery.queue.resume":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.queue.resume payload must be an object",
                status_code=422,
            )
        raw_out = envelope.payload.get("out", None)
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        resume_payload = engine.queue_resume(out=raw_out)
        return _operation_response(
            envelope=envelope,
            payload={"resume": resume_payload},
        )

    if envelope.operation.name == "merlin.discovery.queue.purge_deadletter":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.discovery.queue.purge_deadletter payload must be an object",
                status_code=422,
            )
        raw_out = envelope.payload.get("out", None)
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        purge_payload = engine.queue_purge_deadletter(out=raw_out)
        return _operation_response(
            envelope=envelope,
            payload={"purge_deadletter": purge_payload},
        )

    if envelope.operation.name == "merlin.knowledge.search":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.knowledge.search payload must be an object",
                status_code=422,
            )
        raw_query = envelope.payload.get("query", "")
        raw_tag = envelope.payload.get("tag", None)
        raw_limit = envelope.payload.get("limit", 20)
        raw_out = envelope.payload.get("out", None)
        if not isinstance(raw_query, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.query must be a string when provided",
                status_code=422,
            )
        if raw_tag is not None and not isinstance(raw_tag, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.tag must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_limit, int) or raw_limit <= 0 or raw_limit > 200:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.limit must be between 1 and 200",
                status_code=422,
            )
        if raw_out is not None and not isinstance(raw_out, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.out must be a string when provided",
                status_code=422,
            )
        engine, build_error = _build_discovery_operation_engine(envelope.payload)
        if build_error is not None:
            return build_error
        search_payload = engine.knowledge_search(
            query=raw_query,
            out=raw_out,
            limit=raw_limit,
            tag=raw_tag,
        )
        return _operation_response(
            envelope=envelope,
            payload={"search": search_payload},
        )

    if envelope.operation.name == "merlin.seed.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.status payload must be an object",
                status_code=422,
            )

        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_include_log_tail = envelope.payload.get("include_log_tail", True)
        raw_tail_lines = envelope.payload.get("tail_lines", 40)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)

        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_include_log_tail, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.include_log_tail must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_tail_lines, int) or raw_tail_lines <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.tail_lines must be an integer greater than zero",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error
        status_payload = controller.status(
            status_file=raw_status_file,
            merged_jsonl=raw_merged_jsonl,
            merged_parquet=raw_merged_parquet,
            log_file=raw_log_file,
            include_log_tail=raw_include_log_tail,
            tail_lines=raw_tail_lines,
            allow_live_automation=raw_allow_live_automation,
        )
        return _operation_response(
            envelope=envelope,
            payload={"seed": status_payload},
        )

    if envelope.operation.name == "merlin.seed.health":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.health payload must be an object",
                status_code=422,
            )

        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_stale_after_seconds = envelope.payload.get("stale_after_seconds", 3600.0)

        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_stale_after_seconds, (int, float))
            or float(raw_stale_after_seconds) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.stale_after_seconds must be a number greater than zero",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error
        health_payload = controller.health(
            status_file=raw_status_file,
            merged_jsonl=raw_merged_jsonl,
            merged_parquet=raw_merged_parquet,
            log_file=raw_log_file,
            allow_live_automation=raw_allow_live_automation,
            stale_after_seconds=float(raw_stale_after_seconds),
        )
        return _operation_response(
            envelope=envelope,
            payload={"health": health_payload},
        )

    if envelope.operation.name == "merlin.seed.health.heartbeat":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.health.heartbeat payload must be an object",
                status_code=422,
            )

        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_stale_after_seconds = envelope.payload.get("stale_after_seconds", 3600.0)
        raw_heartbeat_file = envelope.payload.get("heartbeat_file", None)
        raw_write_event = envelope.payload.get("write_event", True)

        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_stale_after_seconds, (int, float))
            or float(raw_stale_after_seconds) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.stale_after_seconds must be a number greater than zero",
                status_code=422,
            )
        if raw_heartbeat_file is not None and not isinstance(raw_heartbeat_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.heartbeat_file must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_write_event, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.write_event must be a boolean when provided",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error
        heartbeat_payload = controller.heartbeat(
            status_file=raw_status_file,
            merged_jsonl=raw_merged_jsonl,
            merged_parquet=raw_merged_parquet,
            log_file=raw_log_file,
            allow_live_automation=raw_allow_live_automation,
            stale_after_seconds=float(raw_stale_after_seconds),
            heartbeat_file=raw_heartbeat_file,
            write_event=raw_write_event,
        )
        return _operation_response(
            envelope=envelope,
            payload={"heartbeat": heartbeat_payload},
        )

    if envelope.operation.name == "merlin.seed.watchdog.tick":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.watchdog.tick payload must be an object",
                status_code=422,
            )

        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_stale_after_seconds = envelope.payload.get("stale_after_seconds", 3600.0)
        raw_apply = envelope.payload.get("apply", False)
        raw_force = envelope.payload.get("force", False)
        raw_dry_run_control = envelope.payload.get("dry_run_control", False)

        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_stale_after_seconds, (int, float))
            or float(raw_stale_after_seconds) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.stale_after_seconds must be a number greater than zero",
                status_code=422,
            )
        if not isinstance(raw_apply, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.apply must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_force, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.force must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_dry_run_control, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.dry_run_control must be a boolean when provided",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error
        watchdog_payload = controller.watchdog(
            status_file=raw_status_file,
            merged_jsonl=raw_merged_jsonl,
            merged_parquet=raw_merged_parquet,
            log_file=raw_log_file,
            allow_live_automation=raw_allow_live_automation,
            stale_after_seconds=float(raw_stale_after_seconds),
            apply=raw_apply,
            force=raw_force,
            dry_run_control=raw_dry_run_control,
        )
        return _operation_response(
            envelope=envelope,
            payload={"watchdog": watchdog_payload},
        )

    if envelope.operation.name == "merlin.seed.watchdog.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.watchdog.status payload must be an object",
                status_code=422,
            )

        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_watchdog_log_file = envelope.payload.get("watchdog_log_file", None)
        raw_append_jsonl = envelope.payload.get("append_jsonl", None)
        raw_output_json = envelope.payload.get("output_json", None)
        raw_heartbeat_file = envelope.payload.get("heartbeat_file", None)
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_stale_after_seconds = envelope.payload.get("stale_after_seconds", 3600.0)

        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if raw_watchdog_log_file is not None and not isinstance(
            raw_watchdog_log_file, str
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.watchdog_log_file must be a string when provided",
                status_code=422,
            )
        if raw_append_jsonl is not None and not isinstance(raw_append_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.append_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_output_json is not None and not isinstance(raw_output_json, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.output_json must be a string when provided",
                status_code=422,
            )
        if raw_heartbeat_file is not None and not isinstance(raw_heartbeat_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.heartbeat_file must be a string when provided",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_stale_after_seconds, (int, float))
            or float(raw_stale_after_seconds) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.stale_after_seconds must be a number greater than zero",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error
        status_payload = controller.watchdog_runtime_status(
            status_file=raw_status_file,
            merged_jsonl=raw_merged_jsonl,
            merged_parquet=raw_merged_parquet,
            log_file=raw_log_file,
            watchdog_log_file=raw_watchdog_log_file,
            append_jsonl=raw_append_jsonl,
            output_json=raw_output_json,
            heartbeat_file=raw_heartbeat_file,
            allow_live_automation=raw_allow_live_automation,
            stale_after_seconds=float(raw_stale_after_seconds),
        )
        return _operation_response(
            envelope=envelope,
            payload={"watchdog_status": status_payload},
        )

    if envelope.operation.name == "merlin.seed.watchdog.control":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.watchdog.control payload must be an object",
                status_code=422,
            )

        raw_action = envelope.payload.get("action", "")
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_dry_run = envelope.payload.get("dry_run", False)
        raw_force = envelope.payload.get("force", False)
        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_watchdog_log_file = envelope.payload.get("watchdog_log_file", None)
        raw_append_jsonl = envelope.payload.get("append_jsonl", None)
        raw_output_json = envelope.payload.get("output_json", None)
        raw_heartbeat_file = envelope.payload.get("heartbeat_file", None)
        raw_stale_after_seconds = envelope.payload.get("stale_after_seconds", 3600.0)
        raw_apply = envelope.payload.get("apply", False)
        raw_dry_run_control = envelope.payload.get("dry_run_control", False)
        raw_interval_seconds = envelope.payload.get("interval_seconds", 60.0)
        raw_max_iterations = envelope.payload.get("max_iterations", 0)
        raw_emit_heartbeat = envelope.payload.get("emit_heartbeat", True)

        if not isinstance(raw_action, str) or not raw_action.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.action is required",
                status_code=422,
            )
        action = raw_action.strip().lower()
        if action not in {"start", "stop", "restart"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.action must be one of: start, stop, restart",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_dry_run, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.dry_run must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_force, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.force must be a boolean when provided",
                status_code=422,
            )
        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if raw_watchdog_log_file is not None and not isinstance(
            raw_watchdog_log_file, str
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.watchdog_log_file must be a string when provided",
                status_code=422,
            )
        if raw_append_jsonl is not None and not isinstance(raw_append_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.append_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_output_json is not None and not isinstance(raw_output_json, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.output_json must be a string when provided",
                status_code=422,
            )
        if raw_heartbeat_file is not None and not isinstance(raw_heartbeat_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.heartbeat_file must be a string when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_stale_after_seconds, (int, float))
            or float(raw_stale_after_seconds) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.stale_after_seconds must be a number greater than zero",
                status_code=422,
            )
        if not isinstance(raw_apply, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.apply must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_dry_run_control, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.dry_run_control must be a boolean when provided",
                status_code=422,
            )
        if (
            not isinstance(raw_interval_seconds, (int, float))
            or float(raw_interval_seconds) < 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.interval_seconds must be a number greater than or equal to zero",
                status_code=422,
            )
        if not isinstance(raw_max_iterations, int) or raw_max_iterations < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.max_iterations must be an integer greater than or equal to zero",
                status_code=422,
            )
        if not isinstance(raw_emit_heartbeat, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.emit_heartbeat must be a boolean when provided",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error

        try:
            control_payload = controller.watchdog_runtime_control(
                action=action,
                allow_live_automation=raw_allow_live_automation,
                dry_run=raw_dry_run,
                force=raw_force,
                status_file=raw_status_file,
                merged_jsonl=raw_merged_jsonl,
                merged_parquet=raw_merged_parquet,
                log_file=raw_log_file,
                watchdog_log_file=raw_watchdog_log_file,
                append_jsonl=raw_append_jsonl,
                output_json=raw_output_json,
                heartbeat_file=raw_heartbeat_file,
                stale_after_seconds=float(raw_stale_after_seconds),
                apply=raw_apply,
                dry_run_control=raw_dry_run_control,
                interval_seconds=float(raw_interval_seconds),
                max_iterations=raw_max_iterations,
                emit_heartbeat=raw_emit_heartbeat,
            )
        except (ValueError, FileNotFoundError) as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except Exception as exc:
            merlin_logger.error(f"Seed watchdog control failed: {exc}")
            return _operation_error(
                envelope=envelope,
                code="SEED_WATCHDOG_CONTROL_FAILED",
                message="Seed watchdog control failed",
                retryable=True,
                status_code=500,
            )

        decision = str(control_payload.get("decision", "")).strip().lower()
        if decision != "allowed":
            return _operation_error(
                envelope=envelope,
                code="SEED_WATCHDOG_CONTROL_BLOCKED",
                message=str(
                    control_payload.get(
                        "message", "Seed watchdog control blocked by policy decision"
                    )
                ),
                status_code=403,
            )

        return _operation_response(
            envelope=envelope,
            payload={"watchdog_control": control_payload},
        )

    if envelope.operation.name == "merlin.seed.control":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.seed.control payload must be an object",
                status_code=422,
            )

        raw_action = envelope.payload.get("action", "")
        raw_allow_live_automation = envelope.payload.get("allow_live_automation", None)
        raw_dry_run = envelope.payload.get("dry_run", False)
        raw_force = envelope.payload.get("force", False)
        raw_status_file = envelope.payload.get("status_file", None)
        raw_merged_jsonl = envelope.payload.get("merged_jsonl", None)
        raw_merged_parquet = envelope.payload.get("merged_parquet", None)
        raw_log_file = envelope.payload.get("log_file", None)
        raw_endpoint = envelope.payload.get("endpoint", "http://127.0.0.1:1234")
        raw_prompt_set = envelope.payload.get(
            "prompt_set", "scripts/eval/prompts_guild.json"
        )
        raw_target = envelope.payload.get("target", 50000)
        raw_increment = envelope.payload.get("increment", 500)
        raw_repeat = envelope.payload.get("repeat", 13)
        raw_eta_window = envelope.payload.get("eta_window", 5)
        raw_sleep_seconds = envelope.payload.get("sleep_seconds", 0.1)
        raw_delay_seconds = envelope.payload.get("delay_seconds", 1.0)
        raw_resource_aware = envelope.payload.get("resource_aware", True)
        raw_cpu_max = envelope.payload.get("cpu_max", 85.0)
        raw_mem_max = envelope.payload.get("mem_max", 85.0)
        raw_resource_wait = envelope.payload.get("resource_wait", 5.0)
        raw_notify_on_complete = envelope.payload.get("notify_on_complete", False)
        raw_teachers = envelope.payload.get("teachers", None)
        raw_config = envelope.payload.get("config", None)

        if not isinstance(raw_action, str) or not raw_action.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.action is required",
                status_code=422,
            )
        action = raw_action.strip().lower()
        if action not in {"start", "stop", "restart"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.action must be one of: start, stop, restart",
                status_code=422,
            )
        if raw_allow_live_automation is not None and not isinstance(
            raw_allow_live_automation, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.allow_live_automation must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_dry_run, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.dry_run must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_force, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.force must be a boolean when provided",
                status_code=422,
            )
        if raw_status_file is not None and not isinstance(raw_status_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.status_file must be a string when provided",
                status_code=422,
            )
        if raw_merged_jsonl is not None and not isinstance(raw_merged_jsonl, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_jsonl must be a string when provided",
                status_code=422,
            )
        if raw_merged_parquet is not None and not isinstance(raw_merged_parquet, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.merged_parquet must be a string when provided",
                status_code=422,
            )
        if raw_log_file is not None and not isinstance(raw_log_file, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.log_file must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_endpoint, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.endpoint must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_prompt_set, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.prompt_set must be a string when provided",
                status_code=422,
            )
        if not isinstance(raw_target, int) or raw_target <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.target must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_increment, int) or raw_increment <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.increment must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_repeat, int) or raw_repeat <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.repeat must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_eta_window, int) or raw_eta_window <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.eta_window must be an integer greater than zero",
                status_code=422,
            )
        if not isinstance(raw_sleep_seconds, (int, float)) or raw_sleep_seconds < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.sleep_seconds must be a number greater than or equal to zero",
                status_code=422,
            )
        if not isinstance(raw_delay_seconds, (int, float)) or raw_delay_seconds < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.delay_seconds must be a number greater than or equal to zero",
                status_code=422,
            )
        if not isinstance(raw_resource_aware, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.resource_aware must be a boolean when provided",
                status_code=422,
            )
        if not isinstance(raw_cpu_max, (int, float)) or raw_cpu_max <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.cpu_max must be a number greater than zero",
                status_code=422,
            )
        if not isinstance(raw_mem_max, (int, float)) or raw_mem_max <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.mem_max must be a number greater than zero",
                status_code=422,
            )
        if not isinstance(raw_resource_wait, (int, float)) or raw_resource_wait <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.resource_wait must be a number greater than zero",
                status_code=422,
            )
        if not isinstance(raw_notify_on_complete, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.notify_on_complete must be a boolean when provided",
                status_code=422,
            )
        if raw_teachers is not None and not isinstance(raw_teachers, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.teachers must be a string when provided",
                status_code=422,
            )
        if raw_config is not None and not isinstance(raw_config, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.config must be a string when provided",
                status_code=422,
            )

        controller, build_error = _build_seed_access_controller(envelope.payload)
        if build_error is not None:
            return build_error

        try:
            control_payload = controller.control(
                action=action,
                allow_live_automation=raw_allow_live_automation,
                dry_run=raw_dry_run,
                force=raw_force,
                status_file=raw_status_file,
                merged_jsonl=raw_merged_jsonl,
                merged_parquet=raw_merged_parquet,
                log_file=raw_log_file,
                endpoint=raw_endpoint,
                prompt_set=raw_prompt_set,
                target=raw_target,
                increment=raw_increment,
                repeat=raw_repeat,
                eta_window=raw_eta_window,
                sleep_seconds=float(raw_sleep_seconds),
                delay_seconds=float(raw_delay_seconds),
                resource_aware=raw_resource_aware,
                cpu_max=float(raw_cpu_max),
                mem_max=float(raw_mem_max),
                resource_wait=float(raw_resource_wait),
                notify_on_complete=raw_notify_on_complete,
                teachers=raw_teachers,
                config=raw_config,
            )
        except (ValueError, FileNotFoundError) as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except Exception as exc:
            merlin_logger.error(f"Seed control failed: {exc}")
            return _operation_error(
                envelope=envelope,
                code="SEED_CONTROL_FAILED",
                message="Seed control failed",
                retryable=True,
                status_code=500,
            )

        decision = str(control_payload.get("decision", "")).strip().lower()
        if decision != "allowed":
            return _operation_error(
                envelope=envelope,
                code="SEED_CONTROL_BLOCKED",
                message=str(
                    control_payload.get(
                        "message", "Seed control blocked by policy decision"
                    )
                ),
                status_code=403,
            )

        return _operation_response(
            envelope=envelope,
            payload={"control": control_payload},
        )

    if envelope.operation.name == "merlin.genesis.manifest":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.genesis.manifest payload must be an object",
                status_code=422,
            )

        raw_filename = envelope.payload.get("filename", "")
        raw_code = envelope.payload.get("code", "")

        filename = raw_filename if isinstance(raw_filename, str) else ""
        code = raw_code if isinstance(raw_code, str) else ""
        if not filename.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.filename is required",
                status_code=422,
            )

        append_manifest_entry(
            {
                "filename": filename,
                "code": code,
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return _operation_response(
            envelope=envelope,
            payload={"status": "queued", "filename": filename},
        )

    if envelope.operation.name == "merlin.command.execute":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.command.execute payload must be an object",
                status_code=422,
            )

        raw_command = envelope.payload.get("command", "")
        command = raw_command if isinstance(raw_command, str) else ""
        if not command.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.command is required",
                status_code=422,
            )

        if not policy_manager.is_command_allowed(command):
            return _operation_error(
                envelope=envelope,
                code="COMMAND_BLOCKED",
                message="Command blocked by policy",
                status_code=403,
            )

        try:
            result = execute_command(command)
        except Exception as exc:
            merlin_logger.error(f"Command execution failed: {exc}")
            return _operation_error(
                envelope=envelope,
                code="COMMAND_EXECUTION_ERROR",
                message="Command execution failed",
                retryable=True,
                status_code=500,
            )

        if "error" in result:
            return _operation_error(
                envelope=envelope,
                code="COMMAND_EXECUTION_FAILED",
                message=str(result["error"]),
                status_code=400,
            )

        output = result.get("stdout", "")
        if result.get("stderr"):
            output = f"{output}\n{result['stderr']}".strip()
        return _operation_response(
            envelope=envelope,
            payload={"output": output, "returncode": result.get("returncode")},
        )

    if envelope.operation.name == "merlin.search.query":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.search.query payload must be an object",
                status_code=422,
            )

        raw_query = envelope.payload.get("query", "")
        raw_limit = envelope.payload.get("limit", 5)

        query = raw_query if isinstance(raw_query, str) else ""
        if not query.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.query is required",
                status_code=422,
            )

        limit = raw_limit if isinstance(raw_limit, int) else 5
        if limit <= 0 or limit > 20:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.limit must be between 1 and 20",
                status_code=422,
            )

        matches = merlin_rag.search(query, limit=limit)
        citations = normalize_rag_citations(
            [item for item in matches if isinstance(item, dict)]
        )
        results = []
        for match in matches:
            if not isinstance(match, dict):
                results.append(str(match))
                continue
            text = str(match.get("text", ""))
            metadata = match.get("metadata", {})
            path = metadata.get("path") if isinstance(metadata, dict) else None
            if path:
                text = f"{path}: {text}"
            results.append(text)
        return _operation_response(
            envelope=envelope,
            payload={
                "results": results,
                "count": len(results),
                "citations": citations,
            },
        )

    if envelope.operation.name == "merlin.rag.query":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.rag.query payload must be an object",
                status_code=422,
            )

        raw_query = envelope.payload.get("query", "")
        raw_limit = envelope.payload.get("limit", 5)

        query = raw_query if isinstance(raw_query, str) else ""
        if not query.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.query is required",
                status_code=422,
            )

        limit = raw_limit if isinstance(raw_limit, int) else 5
        if limit <= 0 or limit > 20:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.limit must be between 1 and 20",
                status_code=422,
            )

        matches = merlin_rag.search(query, limit=limit)
        citations = normalize_rag_citations(
            [item for item in matches if isinstance(item, dict)]
        )
        results = []
        for match in matches:
            if not isinstance(match, dict):
                results.append(str(match))
                continue
            text = str(match.get("text", ""))
            metadata = match.get("metadata", {})
            path = metadata.get("path") if isinstance(metadata, dict) else None
            if path:
                text = f"{path}: {text}"
            results.append(text)

        return _operation_response(
            envelope=envelope,
            payload={
                "results": results,
                "count": len(results),
                "citations": citations,
            },
        )

    if envelope.operation.name == "merlin.tasks.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.tasks.list payload must be an object",
                status_code=422,
            )
        return _operation_response(
            envelope=envelope,
            payload={"tasks": task_manager.list_tasks()},
        )

    if envelope.operation.name == "merlin.tasks.create":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.tasks.create payload must be an object",
                status_code=422,
            )

        raw_title = envelope.payload.get("title", "")
        raw_description = envelope.payload.get("description", "")
        raw_priority = envelope.payload.get("priority", "Medium")

        title = raw_title if isinstance(raw_title, str) else ""
        description = raw_description if isinstance(raw_description, str) else ""
        priority = (
            raw_priority
            if isinstance(raw_priority, str) and raw_priority.strip()
            else "Medium"
        )

        if not title.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.title is required",
                status_code=422,
            )

        task = task_manager.add_task(title, description, priority)
        return _operation_response(
            envelope=envelope,
            payload={"task": task},
        )

    if envelope.operation.name == "merlin.history.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.history.get payload must be an object",
                status_code=422,
            )

        raw_user_id = envelope.payload.get("user_id", "")
        user_id = raw_user_id if isinstance(raw_user_id, str) else ""
        if not user_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.user_id is required",
                status_code=422,
            )

        history = load_chat(user_id)
        return _operation_response(
            envelope=envelope,
            payload={"user_id": user_id, "history": history},
        )

    if envelope.operation.name == "merlin.context.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.context.get payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"context": global_context.state},
        )

    if envelope.operation.name == "merlin.context.update":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.context.update payload must be an object",
                status_code=422,
            )

        raw_data = envelope.payload.get("data", {})
        if not isinstance(raw_data, dict):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.data must be an object",
                status_code=422,
            )

        global_context.update(raw_data)
        return _operation_response(
            envelope=envelope,
            payload={
                "status": "Context Synchronized",
                "context": global_context.state,
            },
        )

    if envelope.operation.name == "merlin.llm.parallel.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.parallel.status payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"status": parallel_llm_backend.get_status()},
        )

    if envelope.operation.name == "merlin.llm.parallel.strategy":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.parallel.strategy payload must be an object",
                status_code=422,
            )

        raw_strategy = envelope.payload.get("strategy", "")
        strategy = raw_strategy if isinstance(raw_strategy, str) else ""
        if strategy not in {"voting", "routing", "cascade", "consensus"}:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=(
                    "payload.strategy must be one of: voting, routing, cascade, consensus"
                ),
                status_code=422,
            )

        os.environ["PARALLEL_STRATEGY"] = strategy
        return _operation_response(
            envelope=envelope,
            payload={"status": "updated", "strategy": strategy},
        )

    if envelope.operation.name == "merlin.llm.adaptive.feedback":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.adaptive.feedback payload must be an object",
                status_code=422,
            )

        raw_model_name = envelope.payload.get("model_name", "")
        raw_rating = envelope.payload.get("rating", None)
        raw_task_type = envelope.payload.get("task_type", None)

        model_name = raw_model_name if isinstance(raw_model_name, str) else ""
        if not model_name.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.model_name is required",
                status_code=422,
            )

        if not isinstance(raw_rating, int) or isinstance(raw_rating, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.rating must be an integer between 1 and 5",
                status_code=422,
            )
        rating = raw_rating
        if rating < 1 or rating > 5:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.rating must be an integer between 1 and 5",
                status_code=422,
            )

        if raw_task_type is not None and not isinstance(raw_task_type, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.task_type must be a string when provided",
                status_code=422,
            )
        task_type = raw_task_type if isinstance(raw_task_type, str) else None

        adaptive_llm_backend.provide_feedback(model_name, rating, task_type)
        return _operation_response(
            envelope=envelope,
            payload={
                "status": "feedback recorded",
                "model": model_name,
                "rating": rating,
            },
        )

    if envelope.operation.name == "merlin.llm.adaptive.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.adaptive.status payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"status": adaptive_llm_backend.get_status()},
        )

    if envelope.operation.name == "merlin.llm.adaptive.metrics":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.adaptive.metrics payload must be an object",
                status_code=422,
            )

        status = adaptive_llm_backend.get_status()
        metrics = status.get("metrics", {}) if isinstance(status, dict) else {}
        return _operation_response(
            envelope=envelope,
            payload={"metrics": metrics},
        )

    if envelope.operation.name == "merlin.llm.adaptive.reset":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.adaptive.reset payload must be an object",
                status_code=422,
            )

        raw_model_name = envelope.payload.get("model_name", None)
        if raw_model_name is not None and not isinstance(raw_model_name, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.model_name must be a string when provided",
                status_code=422,
            )

        reset_model_name = (
            raw_model_name
            if isinstance(raw_model_name, str) and raw_model_name.strip()
            else None
        )
        adaptive_llm_backend.reset_metrics(reset_model_name)
        return _operation_response(
            envelope=envelope,
            payload={"status": "metrics reset", "model": reset_model_name or "all"},
        )

    if envelope.operation.name == "merlin.llm.ab.create":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.ab.create payload must be an object",
                status_code=422,
            )

        raw_name = envelope.payload.get("name", "")
        raw_variants = envelope.payload.get("variants", [])
        raw_weights = envelope.payload.get("weights", None)
        raw_duration_hours = envelope.payload.get("duration_hours", 24)

        name = raw_name if isinstance(raw_name, str) else ""
        if not name.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.name is required",
                status_code=422,
            )

        if not isinstance(raw_variants, list) or not raw_variants:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.variants must be a non-empty array",
                status_code=422,
            )
        variants: list[str] = []
        for variant in raw_variants:
            if not isinstance(variant, str) or not variant.strip():
                return _operation_error(
                    envelope=envelope,
                    code="VALIDATION_ERROR",
                    message="payload.variants must only contain non-empty strings",
                    status_code=422,
                )
            variants.append(variant)

        weights: list[float] | None = None
        if raw_weights is not None:
            if not isinstance(raw_weights, list):
                return _operation_error(
                    envelope=envelope,
                    code="VALIDATION_ERROR",
                    message="payload.weights must be an array when provided",
                    status_code=422,
                )
            parsed_weights: list[float] = []
            for weight in raw_weights:
                if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                    return _operation_error(
                        envelope=envelope,
                        code="VALIDATION_ERROR",
                        message="payload.weights must only contain numbers",
                        status_code=422,
                    )
                parsed_weights.append(float(weight))
            weights = parsed_weights

        if not isinstance(raw_duration_hours, int) or isinstance(
            raw_duration_hours, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.duration_hours must be an integer when provided",
                status_code=422,
            )
        if raw_duration_hours <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.duration_hours must be greater than zero",
                status_code=422,
            )

        try:
            test_id = ab_testing_manager.create_test(
                name=name,
                variants=variants,
                weights=weights,
                duration_hours=raw_duration_hours,
            )
        except ValueError as exc:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=422,
            )
        except Exception as exc:
            merlin_logger.error(f"A/B test creation failed: {exc}")
            return _operation_error(
                envelope=envelope,
                code="AB_TEST_CREATE_FAILED",
                message="A/B test creation failed",
                status_code=500,
            )

        return _operation_response(
            envelope=envelope,
            payload={"test_id": test_id, "status": "created", "name": name},
        )

    if envelope.operation.name == "merlin.llm.ab.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.ab.list payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"tests": ab_testing_manager.list_active_tests()},
        )

    if envelope.operation.name == "merlin.llm.ab.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.ab.get payload must be an object",
                status_code=422,
            )

        raw_test_id = envelope.payload.get("test_id", "")
        test_id = raw_test_id if isinstance(raw_test_id, str) else ""
        if not test_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.test_id is required",
                status_code=422,
            )

        status = ab_testing_manager.get_test_status(test_id)
        if not status:
            return _operation_error(
                envelope=envelope,
                code="AB_TEST_NOT_FOUND",
                message="Test not found",
                status_code=404,
            )

        return _operation_response(
            envelope=envelope,
            payload={"test": status},
        )

    if envelope.operation.name == "merlin.llm.ab.result":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.ab.result payload must be an object",
                status_code=422,
            )

        raw_test_id = envelope.payload.get("test_id", "")
        raw_variant = envelope.payload.get("variant", "")
        raw_user_rating = envelope.payload.get("user_rating", None)
        raw_latency = envelope.payload.get("latency", None)
        raw_success = envelope.payload.get("success", True)

        test_id = raw_test_id if isinstance(raw_test_id, str) else ""
        if not test_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.test_id is required",
                status_code=422,
            )

        variant = raw_variant if isinstance(raw_variant, str) else ""
        if not variant.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.variant is required",
                status_code=422,
            )

        if raw_user_rating is not None and (
            not isinstance(raw_user_rating, int)
            or isinstance(raw_user_rating, bool)
            or raw_user_rating < 1
            or raw_user_rating > 5
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.user_rating must be an integer between 1 and 5 when provided",
                status_code=422,
            )

        if raw_latency is not None and (
            not isinstance(raw_latency, (int, float))
            or isinstance(raw_latency, bool)
            or float(raw_latency) < 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.latency must be a non-negative number when provided",
                status_code=422,
            )

        if not isinstance(raw_success, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.success must be a boolean when provided",
                status_code=422,
            )

        if not ab_testing_manager.get_test_status(test_id):
            return _operation_error(
                envelope=envelope,
                code="AB_TEST_NOT_FOUND",
                message="Test not found",
                status_code=404,
            )

        user_rating = (
            raw_user_rating
            if isinstance(raw_user_rating, int) and raw_user_rating
            else None
        )
        latency = float(raw_latency) if isinstance(raw_latency, (int, float)) else 0.0
        ab_testing_manager.record_result(
            test_id=test_id,
            variant=variant,
            user_rating=user_rating,
            latency=latency,
            success=raw_success,
        )

        return _operation_response(
            envelope=envelope,
            payload={"status": "recorded", "test_id": test_id, "variant": variant},
        )

    if envelope.operation.name == "merlin.llm.ab.complete":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.ab.complete payload must be an object",
                status_code=422,
            )

        raw_test_id = envelope.payload.get("test_id", "")
        test_id = raw_test_id if isinstance(raw_test_id, str) else ""
        if not test_id.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.test_id is required",
                status_code=422,
            )

        winner = ab_testing_manager.complete_test(test_id)
        if winner is None:
            return _operation_error(
                envelope=envelope,
                code="AB_TEST_NOT_FOUND",
                message="Test not found",
                status_code=404,
            )

        return _operation_response(
            envelope=envelope,
            payload={"status": "completed", "winner": winner},
        )

    if envelope.operation.name == "merlin.llm.predictive.select":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.predictive.select payload must be an object",
                status_code=422,
            )

        raw_query = envelope.payload.get("query", "")
        query = raw_query if isinstance(raw_query, str) else ""
        if not query.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.query is required",
                status_code=422,
            )

        selected_model = predictive_model_selector.select_model(query)
        explanation = predictive_model_selector.get_model_explanation(
            selected_model, query
        )
        return _operation_response(
            envelope=envelope,
            payload={
                "selected_model": selected_model,
                "explanation": explanation,
                "query_preview": query[:100],
            },
        )

    if envelope.operation.name == "merlin.llm.predictive.feedback":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.predictive.feedback payload must be an object",
                status_code=422,
            )

        raw_model_name = envelope.payload.get("model_name", "")
        raw_was_successful = envelope.payload.get("was_successful", None)
        raw_latency = envelope.payload.get("latency", None)
        raw_task_type = envelope.payload.get("task_type", None)
        raw_rating = envelope.payload.get("rating", None)

        model_name = raw_model_name if isinstance(raw_model_name, str) else ""
        if not model_name.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.model_name is required",
                status_code=422,
            )

        if not isinstance(raw_was_successful, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.was_successful is required and must be a boolean",
                status_code=422,
            )

        if raw_latency is not None and (
            not isinstance(raw_latency, (int, float))
            or isinstance(raw_latency, bool)
            or float(raw_latency) < 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.latency must be a non-negative number when provided",
                status_code=422,
            )

        if raw_task_type is not None and not isinstance(raw_task_type, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.task_type must be a string when provided",
                status_code=422,
            )

        if raw_rating is not None and (
            not isinstance(raw_rating, int)
            or isinstance(raw_rating, bool)
            or raw_rating < 1
            or raw_rating > 5
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.rating must be an integer between 1 and 5 when provided",
                status_code=422,
            )

        latency = float(raw_latency) if isinstance(raw_latency, (int, float)) else 0.0
        task_type = raw_task_type if isinstance(raw_task_type, str) else "general"
        feedback_rating = raw_rating if isinstance(raw_rating, int) else None
        predictive_model_selector.record_feedback(
            model_name=model_name,
            was_successful=raw_was_successful,
            latency=latency,
            task_type=task_type,
            rating=feedback_rating,
        )

        return _operation_response(
            envelope=envelope,
            payload={
                "status": "recorded",
                "model_name": model_name,
                "updated_weights": predictive_model_selector.model_weights.get(
                    model_name, {}
                ),
            },
        )

    if envelope.operation.name == "merlin.llm.predictive.status":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.predictive.status payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"status": predictive_model_selector.get_status()},
        )

    if envelope.operation.name == "merlin.llm.predictive.models":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.predictive.models payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={
                "models": list(predictive_model_selector.model_weights.keys()),
                "weights": predictive_model_selector.model_weights,
                "feature_importance": predictive_model_selector.feature_importance,
            },
        )

    if envelope.operation.name == "merlin.llm.predictive.export":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.predictive.export payload must be an object",
                status_code=422,
            )

        return _operation_response(
            envelope=envelope,
            payload={"model_data": predictive_model_selector.export_model_data()},
        )

    if envelope.operation.name == "merlin.llm.cost.report":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.report payload must be an object",
                status_code=422,
            )

        raw_days = envelope.payload.get("days", 30)
        if not isinstance(raw_days, int) or isinstance(raw_days, bool):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.days must be an integer when provided",
                status_code=422,
            )
        if raw_days <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.days must be greater than zero",
                status_code=422,
            )

        manager = _cost_manager()
        report = manager.get_cost_report(raw_days)
        return _operation_response(
            envelope=envelope,
            payload={"report": report},
        )

    if envelope.operation.name == "merlin.llm.cost.budget.set":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.budget.set payload must be an object",
                status_code=422,
            )

        raw_budget_limit = envelope.payload.get("budget_limit", None)
        if not isinstance(raw_budget_limit, (int, float)) or isinstance(
            raw_budget_limit, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.budget_limit is required and must be a number",
                status_code=422,
            )

        budget_limit = float(raw_budget_limit)
        if budget_limit <= 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.budget_limit must be greater than zero",
                status_code=422,
            )

        manager = _cost_manager()
        manager.budget_limit = budget_limit
        return _operation_response(
            envelope=envelope,
            payload={"status": "updated", "new_budget_limit": manager.budget_limit},
        )

    if envelope.operation.name == "merlin.llm.cost.budget.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.budget.get payload must be an object",
                status_code=422,
            )

        manager = _cost_manager()
        month_pattern = datetime.now().strftime("%Y-%m-")
        current_month_spend = sum(
            sum(u.total_cost for u in usage_list if u.date.startswith(month_pattern))
            for usage_list in manager.daily_usage.values()
        )
        percentage_used = (
            (current_month_spend / manager.budget_limit) * 100
            if manager.budget_limit > 0
            else 0
        )
        return _operation_response(
            envelope=envelope,
            payload={
                "budget_limit": manager.budget_limit,
                "current_month_spend": current_month_spend,
                "percentage_used": percentage_used,
            },
        )

    if envelope.operation.name == "merlin.llm.cost.thresholds.set":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.thresholds.set payload must be an object",
                status_code=422,
            )

        raw_warning = envelope.payload.get("warning_threshold", None)
        raw_critical = envelope.payload.get("critical_threshold", None)

        if raw_warning is None and raw_critical is None:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.warning_threshold or payload.critical_threshold is required",
                status_code=422,
            )

        if raw_warning is not None and (
            not isinstance(raw_warning, (int, float))
            or isinstance(raw_warning, bool)
            or float(raw_warning) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.warning_threshold must be a number greater than zero when provided",
                status_code=422,
            )

        if raw_critical is not None and (
            not isinstance(raw_critical, (int, float))
            or isinstance(raw_critical, bool)
            or float(raw_critical) <= 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.critical_threshold must be a number greater than zero when provided",
                status_code=422,
            )

        manager = _cost_manager()
        if isinstance(raw_warning, (int, float)):
            manager.cost_thresholds["warning"] = float(raw_warning)
        if isinstance(raw_critical, (int, float)):
            manager.cost_thresholds["critical"] = float(raw_critical)

        return _operation_response(
            envelope=envelope,
            payload={
                "status": "updated",
                "warning_threshold": manager.cost_thresholds["warning"],
                "critical_threshold": manager.cost_thresholds["critical"],
            },
        )

    if envelope.operation.name == "merlin.llm.cost.thresholds.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.thresholds.get payload must be an object",
                status_code=422,
            )

        manager = _cost_manager()
        return _operation_response(
            envelope=envelope,
            payload={"thresholds": manager.cost_thresholds},
        )

    if envelope.operation.name == "merlin.llm.cost.optimization.get":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.optimization.get payload must be an object",
                status_code=422,
            )

        manager = _cost_manager()
        return _operation_response(
            envelope=envelope,
            payload={"recommendations": manager.get_cost_optimization_recommendation()},
        )

    if envelope.operation.name == "merlin.llm.cost.pricing.set":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.llm.cost.pricing.set payload must be an object",
                status_code=422,
            )

        raw_input_cost = envelope.payload.get("input_cost_per_1k", None)
        raw_output_cost = envelope.payload.get("output_cost_per_1k", None)
        raw_currency = envelope.payload.get("currency", "USD")
        raw_free_tier_limit = envelope.payload.get("free_tier_limit", None)
        raw_tier_name = envelope.payload.get("tier_name", None)

        if not isinstance(raw_input_cost, (int, float)) or isinstance(
            raw_input_cost, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.input_cost_per_1k is required and must be a number",
                status_code=422,
            )
        if float(raw_input_cost) < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.input_cost_per_1k must be non-negative",
                status_code=422,
            )

        if not isinstance(raw_output_cost, (int, float)) or isinstance(
            raw_output_cost, bool
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.output_cost_per_1k is required and must be a number",
                status_code=422,
            )
        if float(raw_output_cost) < 0:
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.output_cost_per_1k must be non-negative",
                status_code=422,
            )

        if not isinstance(raw_currency, str) or not raw_currency.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.currency must be a non-empty string when provided",
                status_code=422,
            )

        if raw_free_tier_limit is not None and (
            not isinstance(raw_free_tier_limit, int)
            or isinstance(raw_free_tier_limit, bool)
            or raw_free_tier_limit < 0
        ):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.free_tier_limit must be a non-negative integer when provided",
                status_code=422,
            )

        if raw_tier_name is not None and not isinstance(raw_tier_name, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.tier_name must be a string when provided",
                status_code=422,
            )

        pricing = {
            "input_cost_per_1k": float(raw_input_cost),
            "output_cost_per_1k": float(raw_output_cost),
            "currency": raw_currency,
            "free_tier_limit": raw_free_tier_limit,
            "tier_name": raw_tier_name,
        }

        return _operation_response(
            envelope=envelope,
            payload={"status": "pricing_updated", "pricing": pricing},
        )

    if envelope.operation.name == "merlin.dynamic_components.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.dynamic_components.list payload must be an object",
                status_code=422,
            )

        raw_user_id = envelope.payload.get("user_id", "default")
        if not isinstance(raw_user_id, str):
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.user_id must be a string when provided",
                status_code=422,
            )

        plugin_info = plugin_manager.list_plugin_info()
        components = []
        for name, info in plugin_info.items():
            components.append(
                {
                    "type": "plugin",
                    "title": info.get("name", name),
                    "description": info.get("description", ""),
                    "actionCommand": name,
                }
            )

        return _operation_response(
            envelope=envelope,
            payload={"user_id": raw_user_id, "components": components},
        )

    if envelope.operation.name == "merlin.alerts.list":
        if not isinstance(envelope.payload, dict):
            return _operation_error(
                envelope=envelope,
                code="INVALID_PAYLOAD",
                message="merlin.alerts.list payload must be an object",
                status_code=422,
            )

        alerts = [
            {
                "id": "1",
                "message": "System stress high",
                "severity": "warning",
                "timestamp": 0,
            }
        ]
        return _operation_response(
            envelope=envelope,
            payload={"alerts": alerts},
        )

    return _operation_error(
        envelope=envelope,
        code="UNSUPPORTED_OPERATION",
        message=f"Unsupported operation: {envelope.operation.name}",
    )


@app.post("/merlin/chat")
async def chat_endpoint(request: Request, api_key: str = Depends(get_api_key)):
    content_type = request.headers.get("content-type", "")
    user_input = ""
    user_id = "default"
    include_metadata = _coerce_bool(request.query_params.get("include_metadata", False))
    if "application/json" in content_type:
        payload = await request.json()
        user_input = payload.get("user_input", "")
        user_id = payload.get("user_id", "default")
        include_metadata = _coerce_bool(
            payload.get("include_metadata", include_metadata)
        )
    elif "multipart/form-data" in content_type:
        form = await request.form()
        raw_user_input = form.get("user_input", "")
        raw_user_id = form.get("user_id", "default")
        raw_include_metadata = form.get("include_metadata", include_metadata)
        user_input = raw_user_input if isinstance(raw_user_input, str) else ""
        user_id = raw_user_id if isinstance(raw_user_id, str) else "default"
        include_metadata = _coerce_bool(raw_include_metadata)
    else:
        raise HTTPException(status_code=415, detail="Unsupported content type")
    if not user_input:
        raise HTTPException(status_code=422, detail="user_input is required")
    if include_metadata:
        reply, metadata = merlin_emotion_chat_with_metadata(user_input, user_id)
        return JSONResponse(content={"reply": reply, "metadata": metadata})
    reply = merlin_emotion_chat(user_input, user_id)
    return JSONResponse(content={"reply": reply})


@app.get("/merlin/history/{user_id}")
async def get_history(user_id: str, api_key: str = Depends(get_api_key)):
    history = load_chat(user_id)
    return JSONResponse(content={"history": history})


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    api_key = websocket.headers.get(API_KEY_NAME) or websocket.query_params.get(
        "api_key"
    )
    try:
        while True:
            data = await websocket.receive_text()
            try:
                request_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text("[ERROR] Invalid payload")
                continue
            if request_data.get("api_key"):
                api_key = request_data.get("api_key")
            if ws_requires_api_key() and not is_valid_api_key(api_key):
                await websocket.send_text("[ERROR] Invalid API key")
                await websocket.close(code=1008)
                return
            user_input = request_data.get("user_input", "")
            user_id = request_data.get("user_id", "default")
            async for chunk in merlin_emotion_chat_stream(user_input, user_id):
                await websocket.send_text(chunk)
            await websocket.send_text("[DONE]")
    except WebSocketDisconnect:
        merlin_logger.info("WebSocket disconnected")


# --- OTHER ENDPOINTS (Plugins, Tasks, etc) ---


@app.get("/merlin/system_info")
async def system_info(api_key: str = Depends(get_api_key)):
    return JSONResponse(content=get_system_info())


@app.get("/merlin/plugins")
async def list_plugins(
    format: str = "list",
    capability: str | None = None,
    health_state: str | None = None,
    api_key: str = Depends(get_api_key),
):
    if format not in {"list", "map"}:
        raise HTTPException(status_code=422, detail="format must be one of: list, map")
    normalized_health_state = health_state.strip().lower() if health_state else ""
    if normalized_health_state and normalized_health_state not in {
        "healthy",
        "degraded",
        "isolated",
    }:
        raise HTTPException(
            status_code=422,
            detail="health_state must be one of: healthy, degraded, isolated",
        )

    plugin_info = plugin_manager.list_plugin_info()
    if capability:
        capability_filter = capability.strip()
        plugin_info = {
            name: info
            for name, info in plugin_info.items()
            if capability_filter
            in (
                info.get("capabilities", [])
                if isinstance(info.get("capabilities"), list)
                else []
            )
        }
    if normalized_health_state:
        plugin_info = {
            name: info
            for name, info in plugin_info.items()
            if str(info.get("health_state", "")).strip().lower()
            == normalized_health_state
        }
    if format == "map":
        return JSONResponse(content=plugin_info)
    return JSONResponse(content=list(plugin_info.values()))


@app.post("/merlin/plugin/{name}")
async def run_plugin(name: str, request: Request, api_key: str = Depends(get_api_key)):
    data = await request.json()
    return JSONResponse(content=plugin_manager.execute_plugin(name, **data))


@app.get("/merlin/tasks")
async def list_tasks(api_key: str = Depends(get_api_key)):
    return JSONResponse(content={"tasks": task_manager.list_tasks()})


@app.post("/merlin/tasks")
async def add_task(
    task_request: TaskCreateRequest, api_key: str = Depends(get_api_key)
):
    task = task_manager.add_task(
        task_request.title, task_request.description, task_request.priority
    )
    return JSONResponse(content={"task": task})


@app.post("/merlin/execute")
async def execute_shell_command(
    execute_request: ExecuteRequest, api_key: str = Depends(get_api_key)
):
    if not policy_manager.is_command_allowed(execute_request.command):
        raise HTTPException(status_code=403, detail="Command blocked by policy")
    result = execute_command(execute_request.command)
    if "error" in result:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    output = result.get("stdout", "")
    if result.get("stderr"):
        output = f"{output}\n{result['stderr']}".strip()
    return JSONResponse(
        content={"output": output, "returncode": result.get("returncode")}
    )


@app.post("/merlin/speak")
async def speak_text(request: SpeakRequest, api_key: str = Depends(get_api_key)):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(
            status_code=503, content={"error": "Voice subsystem unavailable"}
        )
    ok = voice_instance.speak(request.text, engine=request.engine)
    return JSONResponse(content={"ok": ok})


@app.post("/merlin/voice/synthesize")
async def synthesize_voice(
    request: VoiceSynthesizeRequest,
    mode: str = "file",
    api_key: str = Depends(get_api_key),
):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(
            status_code=503, content={"error": "Voice subsystem unavailable"}
        )
    output_path = voice_instance.synthesize_to_file(request.text, engine=request.engine)
    if not output_path:
        return JSONResponse(
            status_code=500, content={"error": "Voice synthesis failed"}
        )
    output_path = Path(output_path)
    if not output_path.exists():
        return JSONResponse(status_code=500, content={"error": "Voice output missing"})
    if mode == "json":
        return JSONResponse(
            content={"path": str(output_path), "filename": output_path.name}
        )
    if mode != "file":
        raise HTTPException(status_code=400, detail="Invalid mode; use file or json")
    return FileResponse(output_path, media_type="audio/wav", filename=output_path.name)


@app.get("/merlin/voice/status")
async def voice_status(api_key: str = Depends(get_api_key)):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(
            status_code=503, content={"error": "Voice subsystem unavailable"}
        )
    return JSONResponse(content=voice_instance.status())


@app.post("/merlin/voice/transcribe")
async def transcribe_voice(
    file: UploadFile = File(...),
    engine: str | None = None,
    api_key: str = Depends(get_api_key),
):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(
            status_code=503, content={"error": "Voice subsystem unavailable"}
        )
    suffix = Path(file.filename or "").suffix or ".wav"
    upload_dir = Path(settings.MERLIN_VOICE_CACHE_DIR or "artifacts/voice") / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"stt_upload_{uuid.uuid4().hex}{suffix}"
    try:
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        text = voice_instance.transcribe_file(temp_path, engine=engine)
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        if not settings.MERLIN_VOICE_KEEP_TEMP_AUDIO and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
    if not text:
        return JSONResponse(status_code=500, content={"error": "Transcription failed"})
    return JSONResponse(content={"text": text})


@app.post("/merlin/listen")
async def listen_for_speech(
    engine: str | None = None, api_key: str = Depends(get_api_key)
):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(
            status_code=503, content={"error": "Voice subsystem unavailable"}
        )
    text = voice_instance.listen(engine=engine)
    return JSONResponse(content={"text": text})


@app.post("/merlin/search")
async def search_knowledge(
    search_request: SearchRequest, api_key: str = Depends(get_api_key)
):
    matches = merlin_rag.search(search_request.query, limit=5)
    citations = normalize_rag_citations(
        [item for item in matches if isinstance(item, dict)]
    )
    results = []
    for match in matches:
        text = match.get("text", "")
        metadata = match.get("metadata", {})
        path = metadata.get("path") if isinstance(metadata, dict) else None
        if path:
            text = f"{path}: {text}"
        results.append(text)
    return JSONResponse(content={"results": results, "citations": citations})


@app.post("/merlin/genesis/manifest")
async def submit_manifest(
    manifest_request: ManifestRequest, api_key: str = Depends(get_api_key)
):
    entry = {
        "filename": manifest_request.filename,
        "code": manifest_request.code,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    append_manifest_entry(entry)
    return JSONResponse(content={"status": "queued"})


@app.get("/merlin/genesis/logs")
async def get_genesis_logs(api_key: str = Depends(get_api_key)):
    return JSONResponse(content={"logs": get_recent_logs()})


@app.get("/merlin/dynamic_components/{user_id}")
async def get_dynamic_components(user_id: str, api_key: str = Depends(get_api_key)):
    plugin_info = plugin_manager.list_plugin_info()
    components = []
    for name, info in plugin_info.items():
        components.append(
            {
                "type": "plugin",
                "title": info.get("name", name),
                "description": info.get("description", ""),
                "actionCommand": name,
            }
        )
    return JSONResponse(content=components)


@app.post("/merlin/aas/create_task")
async def create_aas_task(
    task_request: TaskCreateRequest, api_key: str = Depends(get_api_key)
):
    task_id = hub_client.create_aas_task(
        task_request.title, task_request.description, task_request.priority
    )
    if not task_id:
        raise HTTPException(status_code=502, detail="Failed to create AAS task")
    return JSONResponse(content={"task_id": task_id})


@app.get("/merlin/alerts")
async def get_alerts(api_key: str = Depends(get_api_key)):
    # Mock alerts for now, would poll AAS/System
    return {
        "alerts": [
            {
                "id": "1",
                "message": "System stress high",
                "severity": "warning",
                "timestamp": 0,
            }
        ]
    }


def _uvicorn_runtime_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": settings.MERLIN_API_HOST,
        "port": settings.MERLIN_API_PORT,
        "reload": _coerce_bool(os.getenv("MERLIN_API_RELOAD", "true")),
        "timeout_keep_alive": settings.MERLIN_HTTP_KEEP_ALIVE_TIMEOUT_S,
        "timeout_graceful_shutdown": settings.MERLIN_HTTP_GRACEFUL_SHUTDOWN_TIMEOUT_S,
    }
    if settings.MERLIN_HTTP_LIMIT_CONCURRENCY is not None:
        kwargs["limit_concurrency"] = settings.MERLIN_HTTP_LIMIT_CONCURRENCY
    return kwargs


if __name__ == "__main__":
    uvicorn.run("merlin_api_server:app", **_uvicorn_runtime_kwargs())

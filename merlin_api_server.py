# Merlin REST API server for Unity/Unreal integration
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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from typing import Any, Callable, List, cast
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import importlib
from merlin_system_info import get_system_info
from merlin_file_manager import list_files, delete_file, move_file, open_file
from merlin_command_executor import execute_command
from merlin_logger import merlin_logger, get_recent_logs
from merlin_policy import policy_manager
from merlin_tasks import task_manager
from merlin_audit import log_audit_event
from merlin_auth import (
    create_access_token,
    verify_password,
    ALGORITHM,
    SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from merlin_user_manager import user_manager
import merlin_settings as settings
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
import uuid
import re

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
        self._resolved = None

    def _get(self):
        if self._resolved is None:
            module = importlib.import_module(self._module_name)
            self._resolved = getattr(module, self._attr_name)
        return self._resolved

    def __call__(self, *args, **kwargs):
        return self._get()(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._get(), item)


class _LazySingleton:
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._instance = None

    def _get_instance(self):
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def __getattr__(self, item):
        return getattr(self._get_instance(), item)


def _build_plugin_manager():
    module = importlib.import_module("merlin_plugin_manager")
    manager = module.PluginManager()
    manager.load_plugins()
    return manager


def _build_hub_client():
    module = importlib.import_module("merlin_hub_client")
    return module.MerlinHubClient()


merlin_emotion_chat = _LazyAttr("merlin_emotion_chat", "merlin_emotion_chat")
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
handle_dashboard_websocket = _LazyAttr(
    "merlin_metrics_dashboard", "handle_dashboard_websocket"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not getattr(app.state, "bootstrap_ready", False):
        importlib.import_module("merlin_dashboard").setup_dashboard(app)
        Instrumentator().instrument(app).expose(app)
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
voice = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

API_KEY_NAME = "X-Merlin-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def is_valid_api_key(api_key: str | None) -> bool:
    expected_key = os.environ.get("MERLIN_API_KEY", "merlin-secret-key")
    return api_key == expected_key


def get_api_key(api_key: str = Depends(api_key_header)):
    if not is_valid_api_key(api_key):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key


MANIFEST_PATH = Path(
    os.environ.get("MERLIN_MANIFEST_PATH", "merlin_genesis_manifest.json")
)


def load_manifest_entries() -> list[dict]:
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            merlin_logger.error(f"Failed to read manifest queue: {exc}")
    return []


def append_manifest_entry(entry: dict) -> None:
    entries = load_manifest_entries()
    entries.append(entry)
    try:
        with MANIFEST_PATH.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except Exception as exc:
        merlin_logger.error(f"Failed to write manifest queue: {exc}")


def ws_requires_api_key() -> bool:
    return os.environ.get("MERLIN_WS_REQUIRE_API_KEY", "true").lower() == "true"


def get_voice():
    global voice
    if voice is None:
        try:
            voice_cls = importlib.import_module("merlin_voice").MerlinVoice
            voice = voice_cls()
        except Exception as exc:
            merlin_logger.error(f"Voice init failed: {exc}")
            return None
    return voice


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    import time
    import uuid

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
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


def _is_semver(value: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", value))


def _response_operation_name(operation_name: str) -> str:
    if operation_name.endswith(".request"):
        return f"{operation_name[:-8]}.result"
    return f"{operation_name}.result"


def _operation_response(
    envelope: OperationEnvelopeRequest,
    payload: dict[str, Any],
    status_code: int = 200,
) -> JSONResponse:
    response_body = {
        "schema_name": "AAS.OperationEnvelope",
        "schema_version": "1.0.0",
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
    }
    return JSONResponse(status_code=status_code, content=response_body)


def _operation_error(
    envelope: OperationEnvelopeRequest,
    code: str,
    message: str,
    retryable: bool = False,
    status_code: int = 400,
) -> JSONResponse:
    return _operation_response(
        envelope=envelope,
        payload={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            }
        },
        status_code=status_code,
    )


@app.post("/merlin/operations")
async def execute_operation(
    envelope: OperationEnvelopeRequest, api_key: str = Depends(get_api_key)
):
    if envelope.schema_name != "AAS.OperationEnvelope":
        return _operation_error(
            envelope=envelope,
            code="INVALID_SCHEMA",
            message="schema_name must be AAS.OperationEnvelope",
            status_code=422,
        )
    if envelope.schema_version != "1.0.0":
        return _operation_error(
            envelope=envelope,
            code="INVALID_SCHEMA_VERSION",
            message="schema_version must be 1.0.0",
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

        user_input = raw_user_input if isinstance(raw_user_input, str) else ""
        user_id = raw_user_id if isinstance(raw_user_id, str) else "default"

        if not user_input.strip():
            return _operation_error(
                envelope=envelope,
                code="VALIDATION_ERROR",
                message="payload.user_input is required",
                status_code=422,
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
            return _operation_error(
                envelope=envelope,
                code="TOOL_EXECUTION_ERROR",
                message=f"Tool execution failed: {tool_name}",
                status_code=500,
            )

        if isinstance(result, dict) and "error" in result:
            return _operation_error(
                envelope=envelope,
                code="TOOL_NOT_FOUND",
                message=str(result.get("error", f"Tool {tool_name} not found")),
                status_code=404,
            )

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
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        return _operation_response(
            envelope=envelope,
            payload={"status": voice_instance.status()},
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
            return _operation_error(
                envelope=envelope,
                code="VOICE_UNAVAILABLE",
                message="Voice subsystem unavailable",
                retryable=True,
                status_code=503,
            )

        output_path = voice_instance.synthesize_to_file(text, engine=engine)
        if not output_path:
            return _operation_error(
                envelope=envelope,
                code="VOICE_SYNTHESIS_FAILED",
                message="Voice synthesis failed",
                status_code=500,
            )
        output_path = Path(output_path)
        if not output_path.exists():
            return _operation_error(
                envelope=envelope,
                code="VOICE_OUTPUT_MISSING",
                message="Voice output file missing after synthesis",
                status_code=500,
            )

        return _operation_response(
            envelope=envelope,
            payload={"path": str(output_path), "filename": output_path.name},
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
            payload={"results": results, "count": len(results)},
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
    if "application/json" in content_type:
        payload = await request.json()
        user_input = payload.get("user_input", "")
        user_id = payload.get("user_id", "default")
    elif "multipart/form-data" in content_type:
        form = await request.form()
        raw_user_input = form.get("user_input", "")
        raw_user_id = form.get("user_id", "default")
        user_input = raw_user_input if isinstance(raw_user_input, str) else ""
        user_id = raw_user_id if isinstance(raw_user_id, str) else "default"
    else:
        raise HTTPException(status_code=415, detail="Unsupported content type")
    if not user_input:
        raise HTTPException(status_code=422, detail="user_input is required")
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
async def list_plugins(format: str = "list", api_key: str = Depends(get_api_key)):
    plugin_info = plugin_manager.list_plugin_info()
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
    results = []
    for match in matches:
        text = match.get("text", "")
        metadata = match.get("metadata", {})
        path = metadata.get("path") if isinstance(metadata, dict) else None
        if path:
            text = f"{path}: {text}"
        results.append(text)
    return JSONResponse(content={"results": results})


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


if __name__ == "__main__":
    uvicorn.run("merlin_api_server:app", host="0.0.0.0", port=8000, reload=True)

# Merlin REST API server for Unity/Unreal integration
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from merlin_emotion_chat import merlin_emotion_chat, load_chat, merlin_emotion_chat_stream
from merlin_system_info import get_system_info
from merlin_file_manager import list_files, delete_file, move_file, open_file
from merlin_command_executor import execute_command
from merlin_voice import MerlinVoice
from merlin_logger import merlin_logger, get_recent_logs
from merlin_plugin_manager import PluginManager
from merlin_hub_client import MerlinHubClient
from merlin_dashboard import setup_dashboard
from merlin_policy import policy_manager
from merlin_tasks import task_manager
from merlin_rag import merlin_rag
from merlin_audit import log_audit_event
from merlin_auth import create_access_token, verify_password, ALGORITHM, SECRET_KEY
from merlin_user_manager import user_manager
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta, datetime
import shutil
import tempfile
from fastapi.responses import FileResponse
import os
import platform
import ssl
import json
from pathlib import Path

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- UNIVERSAL CONTEXT (Cross-Platform Sync) ---
class UniversalContext:
    def __init__(self):
        self.state = {
            "last_active_platform": platform.system(),
            "current_task": "Resting",
            "perception_data": {},
            "divine_guidance": []
        }
    def update(self, data: dict):
        self.state.update(data)
        merlin_logger.info(f"Universal Context Sync: {self.state['last_active_platform']}")

global_context = UniversalContext()

# --- END CONTEXT ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    merlin_logger.error(f"Global Error: {exc} | Path: {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc) if os.getenv("DEBUG") else "An unexpected error occurred."}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    merlin_logger.warning(f"HTTP Error: {exc.detail} | Status: {exc.status_code} | Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

plugin_manager = PluginManager()
plugin_manager.load_plugins()
hub_client = MerlinHubClient()
voice = None
setup_dashboard(app)
Instrumentator().instrument(app).expose(app)

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

MANIFEST_PATH = Path(os.environ.get("MERLIN_MANIFEST_PATH", "merlin_genesis_manifest.json"))

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
            voice = MerlinVoice()
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
    return {"status": "ok", "platform": platform.system(), "execution_mode": policy_manager.mode.value}

# --- GENESIS & CONTEXT ENDPOINTS ---

@app.get("/merlin/genesis/dna")
async def get_merlin_dna(api_key: str = Depends(get_api_key)):
    dna = {}
    core_files = ["merlin_api_server.py", "merlin_policy.py", "merlin_agents.py", "merlin_emotion_chat.py", "merlin_watcher.py"]
    for f in core_files:
        if os.path.exists(f):
            with open(f, 'r') as file: dna[f] = file.read()
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

class SearchRequest(BaseModel):
    query: str

class ManifestRequest(BaseModel):
    filename: str
    code: str

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
        user_input = form.get("user_input", "")
        user_id = form.get("user_id", "default")
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
    api_key = websocket.headers.get(API_KEY_NAME) or websocket.query_params.get("api_key")
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
async def add_task(task_request: TaskCreateRequest, api_key: str = Depends(get_api_key)):
    task = task_manager.add_task(task_request.title, task_request.description, task_request.priority)
    return JSONResponse(content={"task": task})

@app.post("/merlin/execute")
async def execute_shell_command(execute_request: ExecuteRequest, api_key: str = Depends(get_api_key)):
    if not policy_manager.is_command_allowed(execute_request.command):
        raise HTTPException(status_code=403, detail="Command blocked by policy")
    result = execute_command(execute_request.command)
    if "error" in result:
        return JSONResponse(status_code=400, content={"error": result["error"]})
    output = result.get("stdout", "")
    if result.get("stderr"):
        output = f"{output}\n{result['stderr']}".strip()
    return JSONResponse(content={"output": output, "returncode": result.get("returncode")})

@app.post("/merlin/speak")
async def speak_text(request: SpeakRequest, api_key: str = Depends(get_api_key)):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(status_code=503, content={"error": "Voice subsystem unavailable"})
    ok = voice_instance.speak(request.text)
    return JSONResponse(content={"ok": ok})

@app.post("/merlin/listen")
async def listen_for_speech(api_key: str = Depends(get_api_key)):
    voice_instance = get_voice()
    if not voice_instance:
        return JSONResponse(status_code=503, content={"error": "Voice subsystem unavailable"})
    text = voice_instance.listen()
    return JSONResponse(content={"text": text})

@app.post("/merlin/search")
async def search_knowledge(search_request: SearchRequest, api_key: str = Depends(get_api_key)):
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
async def submit_manifest(manifest_request: ManifestRequest, api_key: str = Depends(get_api_key)):
    entry = {
        "filename": manifest_request.filename,
        "code": manifest_request.code,
        "received_at": datetime.utcnow().isoformat()
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
        components.append({
            "type": "plugin",
            "title": info.get("name", name),
            "description": info.get("description", ""),
            "actionCommand": name
        })
    return JSONResponse(content=components)

@app.post("/merlin/aas/create_task")
async def create_aas_task(task_request: TaskCreateRequest, api_key: str = Depends(get_api_key)):
    task_id = hub_client.create_aas_task(task_request.title, task_request.description, task_request.priority)
    if not task_id:
        raise HTTPException(status_code=502, detail="Failed to create AAS task")
    return JSONResponse(content={"task_id": task_id})

@app.get("/merlin/alerts")
async def get_alerts(api_key: str = Depends(get_api_key)):
    # Mock alerts for now, would poll AAS/System
    return {"alerts": [{"id": "1", "message": "System stress high", "severity": "warning", "timestamp": 0}]}

if __name__ == "__main__":
    uvicorn.run("merlin_api_server:app", host="0.0.0.0", port=8000, reload=True)

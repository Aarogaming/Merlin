"""
UAF API endpoints for Merlin API server.
These endpoints expose Unified Agent Framework functionality via REST API.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from merlin_uaf_integration import get_uaf_adapter, MerlinUAFAdapter

# Create router for UAF endpoints
uaf_router = APIRouter(prefix="/merlin/uaf", tags=["UAF"])


class UAFTaskRequest(BaseModel):
    """Request to execute a task via UAF."""

    task: str
    agent_type: str = "chat"
    thoroughness: str = "normal"
    preferred_agents: Optional[List[str]] = None
    constraints: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class UAFTaskResponse(BaseModel):
    """Response from UAF task execution."""

    ok: bool
    output: Any
    metadata: Dict[str, Any]
    elapsed_ms: float


class UAFChatRequest(BaseModel):
    """Request for chat completion via UAF."""

    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    prefer_local: bool = True


class UAFChatResponse(BaseModel):
    """Response from UAF chat completion."""

    response: str
    elapsed_ms: Optional[float] = None


@uaf_router.get("/status")
async def uaf_status():
    """
    Check if UAF is available and get its status.

    Returns:
        Dictionary with availability status and metrics
    """
    adapter = get_uaf_adapter()

    if not adapter.is_available():
        return {"available": False, "message": "UAF is not available or disabled"}

    metrics = adapter.get_metrics()

    return {"available": True, "metrics": metrics}


@uaf_router.post("/task", response_model=UAFTaskResponse)
async def execute_uaf_task(request: UAFTaskRequest):
    """
    Execute a task through the UAF orchestrator.

    This endpoint routes tasks to the appropriate agent (local models, cloud APIs, etc.)
    based on the agent_type, constraints, and preferences specified.

    Args:
        request: UAFTaskRequest with task details

    Returns:
        UAFTaskResponse with result from the orchestrator
    """
    adapter = get_uaf_adapter()

    if not adapter.is_available():
        raise HTTPException(
            status_code=503, detail="UAF is not available. Check server configuration."
        )

    result = adapter.delegate_task(
        task=request.task,
        agent_type=request.agent_type,
        thoroughness=request.thoroughness,
        preferred_agents=request.preferred_agents,
        constraints=request.constraints,
        context=request.context,
    )

    return UAFTaskResponse(
        ok=result.ok,
        output=result.output,
        metadata=result.metadata,
        elapsed_ms=result.elapsed_ms,
    )


@uaf_router.post("/chat", response_model=UAFChatResponse)
async def uaf_chat(request: UAFChatRequest):
    """
    Chat completion endpoint using UAF.

    This is compatible with existing chat interfaces but routes through UAF
    for intelligent model selection and cost optimization.

    Args:
        request: UAFChatRequest with messages and parameters

    Returns:
        UAFChatResponse with the assistant's reply
    """
    adapter = get_uaf_adapter()

    if not adapter.is_available():
        raise HTTPException(
            status_code=503, detail="UAF is not available. Check server configuration."
        )

    import time

    start = time.time()

    response = adapter.chat_completion(
        messages=request.messages,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        prefer_local=request.prefer_local,
    )

    elapsed_ms = (time.time() - start) * 1000

    return UAFChatResponse(response=response, elapsed_ms=elapsed_ms)


@uaf_router.get("/metrics")
async def uaf_metrics():
    """
    Get UAF orchestrator metrics.

    Returns:
        Dictionary with request counts, success rates, latency stats
    """
    adapter = get_uaf_adapter()

    if not adapter.is_available():
        raise HTTPException(
            status_code=503, detail="UAF is not available. Check server configuration."
        )

    return adapter.get_metrics()


# Task Decomposition Endpoint
class TaskDecompositionRequest(BaseModel):
    """Request to decompose a complex task into subtasks."""

    task: str
    max_subtasks: int = 10
    detail_level: str = "normal"


class SubTask(BaseModel):
    """A subtask from decomposition."""

    id: str
    description: str
    agent_type: str
    estimated_duration_s: Optional[float] = None
    dependencies: List[str] = []


class TaskDecompositionResponse(BaseModel):
    """Response from task decomposition."""

    ok: bool
    subtasks: List[SubTask]
    execution_plan: str


@uaf_router.post("/decompose", response_model=TaskDecompositionResponse)
async def decompose_task(request: TaskDecompositionRequest):
    """
    Decompose a complex task into manageable subtasks.

    This uses UAF to analyze the task and break it down into a sequence
    of subtasks with appropriate agent types and dependencies.

    Args:
        request: TaskDecompositionRequest with task details

    Returns:
        TaskDecompositionResponse with subtasks and execution plan
    """
    adapter = get_uaf_adapter()

    if not adapter.is_available():
        raise HTTPException(
            status_code=503, detail="UAF is not available. Check server configuration."
        )

    # Build a decomposition prompt
    decomposition_prompt = f"""
Break down this task into subtasks:

Task: {request.task}

Provide up to {request.max_subtasks} subtasks in this JSON format:
{{
  "subtasks": [
    {{
      "id": "task1",
      "description": "...",
      "agent_type": "code|chat|research|review|debug",
      "estimated_duration_s": 60,
      "dependencies": []
    }}
  ],
  "execution_plan": "..."
}}
"""

    result = adapter.delegate_task(
        task=decomposition_prompt,
        agent_type="architect",
        thoroughness=request.detail_level,
        preferred_agents=["local"],
        constraints={"response_format": "json"},
    )

    if not result.ok:
        return TaskDecompositionResponse(
            ok=False, subtasks=[], execution_plan="Failed to decompose task"
        )

    # Parse the response
    import json

    try:
        if isinstance(result.output, str):
            parsed = json.loads(result.output)
        else:
            parsed = result.output

        subtasks = [
            SubTask(
                id=st.get("id", f"task{i}"),
                description=st.get("description", ""),
                agent_type=st.get("agent_type", "chat"),
                estimated_duration_s=st.get("estimated_duration_s"),
                dependencies=st.get("dependencies", []),
            )
            for i, st in enumerate(parsed.get("subtasks", []))
        ]

        return TaskDecompositionResponse(
            ok=True,
            subtasks=subtasks,
            execution_plan=parsed.get("execution_plan", "Execute subtasks in order"),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: create a single subtask
        return TaskDecompositionResponse(
            ok=True,
            subtasks=[
                SubTask(
                    id="task1",
                    description=request.task,
                    agent_type="chat",
                    estimated_duration_s=None,
                    dependencies=[],
                )
            ],
            execution_plan="Execute as a single task",
        )


# Export router for integration into main app
__all__ = ["uaf_router"]

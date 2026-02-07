"""
Merlin UAF Integration Layer
Bridges Merlin's existing LLM backends with the Unified Agent Framework.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import time

# Add parent directory to path for UAF imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from uaf.orchestrator import UnifiedAgentOrchestrator, AgentRequest, AgentResult
    from uaf.merlin_core import MerlinUAFBridge

    UAF_AVAILABLE = True
except ImportError:
    UAF_AVAILABLE = False

    # Graceful degradation - define stubs
    @dataclass
    class AgentRequest:
        task_type: str
        description: str
        context: Optional[Dict[str, Any]] = None
        constraints: Optional[Dict[str, Any]] = None
        preferred_agents: Optional[List[str]] = None
        thoroughness: str = "normal"
        agent_hint: Optional[str] = None

    @dataclass
    class AgentResult:
        ok: bool
        output: str
        metadata: Dict[str, Any]
        elapsed_ms: float


class MerlinUAFAdapter:
    """
    Adapter that allows Merlin to route tasks through UAF.
    Provides backwards compatibility with existing Merlin LLM backends.
    """

    def __init__(self, enable_uaf: bool = True):
        """
        Initialize the UAF adapter.

        Args:
            enable_uaf: Whether to enable UAF routing (defaults to True if available)
        """
        self.uaf_enabled = enable_uaf and UAF_AVAILABLE

        if self.uaf_enabled:
            # Initialize UAF orchestrator with auto-discovery
            self.orchestrator = UnifiedAgentOrchestrator(
                enable_lmstudio=True, enable_opencode=True
            )
            self.bridge = MerlinUAFBridge(orchestrator=self.orchestrator)
        else:
            self.orchestrator = None
            self.bridge = None

    def is_available(self) -> bool:
        """Check if UAF is available and enabled."""
        return self.uaf_enabled

    def delegate_task(
        self,
        task: str,
        agent_type: str = "chat",
        thoroughness: str = "normal",
        preferred_agents: Optional[List[str]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """
        Delegate a task to the UAF orchestrator.

        Args:
            task: The task description
            agent_type: Type of agent needed (chat, code, research, etc.)
            thoroughness: How thorough to be (quick, normal, thorough)
            preferred_agents: List of preferred agent types (local, cloud, etc.)
            constraints: Constraints like max_cost, max_time
            context: Additional context for the task

        Returns:
            AgentResult with ok flag, output, metadata, and elapsed_ms
        """
        if not self.uaf_enabled:
            return AgentResult(
                ok=False,
                output="UAF not available",
                metadata={"error": "UAF not initialized or not available"},
                elapsed_ms=0.0,
            )

        return self.bridge.delegate(
            task=task,
            agent_type=agent_type,
            thoroughness=thoroughness,
            preferred_agents=preferred_agents,
            constraints=constraints,
            context=context,
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        prefer_local: bool = True,
    ) -> str:
        """
        Chat completion interface compatible with Merlin's existing LLM backends.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Specific model to use (optional)
            temperature: Temperature for generation
            max_tokens: Max tokens to generate
            prefer_local: Prefer local models over cloud APIs

        Returns:
            The assistant's response as a string
        """
        if not self.uaf_enabled:
            return "[UAF unavailable - please use standard LLM backend]"

        # Convert messages to a single prompt for UAF
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        task = "\n".join(prompt_parts)

        # Build constraints
        constraints = {}
        if max_tokens:
            constraints["max_tokens"] = max_tokens
        if temperature:
            constraints["temperature"] = temperature

        # Build preferred agents list
        preferred_agents = []
        if prefer_local:
            preferred_agents.append("local")
        if model:
            # If specific model requested, add to context
            constraints["preferred_model"] = model

        result = self.delegate_task(
            task=task,
            agent_type="chat",
            preferred_agents=preferred_agents if preferred_agents else None,
            constraints=constraints,
        )

        if result.ok:
            # Convert output to string if it's not already
            if isinstance(result.output, str):
                return result.output
            elif isinstance(result.output, dict):
                # Extract message if available
                return result.output.get("message", str(result.output))
            else:
                return str(result.output)
        else:
            return f"[Error: {result.metadata.get('error', 'Unknown error')}]"

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get UAF orchestrator metrics.

        Returns:
            Dictionary with metrics like request_count, success_rate, etc.
        """
        if not self.uaf_enabled or not self.orchestrator:
            return {"error": "UAF not available"}

        return self.orchestrator.get_metrics()

    def add_custom_delegate(self, name: str, delegate_func):
        """
        Add a custom delegate to the orchestrator.

        Args:
            name: Name of the delegate
            delegate_func: Function that takes AgentRequest and returns AgentResult
        """
        if self.uaf_enabled and self.orchestrator:
            self.orchestrator.add_delegate(name, delegate_func)


# Global instance for use across Merlin modules
merlin_uaf_adapter = MerlinUAFAdapter(enable_uaf=True)


def get_uaf_adapter() -> MerlinUAFAdapter:
    """Get the global UAF adapter instance."""
    return merlin_uaf_adapter


# Example usage for testing
if __name__ == "__main__":
    adapter = get_uaf_adapter()

    if adapter.is_available():
        print("✅ UAF is available and enabled")

        # Test chat completion
        result = adapter.chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": "Write a Python function to calculate fibonacci.",
                },
            ],
            prefer_local=True,
        )

        print(f"\n📝 Chat Response:\n{result}")

        # Get metrics
        metrics = adapter.get_metrics()
        print(f"\n📊 Metrics: {metrics}")
    else:
        print("❌ UAF is not available")

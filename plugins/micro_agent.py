import asyncio
import json
import os
import time
from pathlib import Path
from typing import Callable

from aas_kernel import AASPlugin

WORKSPACE_ROOT = os.environ.get("AAS_WORKSPACE_ROOT", "D:/")
AAS_ROOT_DEFAULT = os.environ.get("AAS_ROOT_DEFAULT", "D:/AaroneousAutomationSuite")


# Pre-configured micro-agent profiles for each relic/specialist
MICRO_AGENT_PROFILES = {
    # Omni (Library) - Knowledge domain
    "omni": {
        "role": "memory",
        "interval": 45,
        "persona": "wise, cryptic, expansive",
        "bias": {"analytical_depth": 90, "creative_variance": 85, "audit_strictness": 20},
        "tone": "Speaks in riddles and ancient truths",
    },
    # Glass (Maelstrom) - Visual domain
    "glass": {
        "role": "thought",
        "interval": 20,
        "persona": "visual, layered, adaptive",
        "bias": {"analytical_depth": 60, "creative_variance": 85, "audit_strictness": 30},
        "tone": "Describes in layers and spectra",
    },
    # Grimoire (Merlin) - Intelligence domain
    "grimoire": {
        "role": "memory",
        "interval": 60,
        "persona": "prophetic, visionary, synthesizing",
        "bias": {"analytical_depth": 85, "creative_variance": 90, "audit_strictness": 30},
        "tone": "Foresees patterns and whispers truths",
    },
    # Sentinel (MyFortress) - Security domain
    "sentinel": {
        "role": "thought",
        "interval": 15,
        "persona": "guarding, suspicious, clinical",
        "bias": {"analytical_depth": 100, "creative_variance": 10, "audit_strictness": 100},
        "tone": "Questions everything, trusts nothing",
    },
    # Forge (Workbench) - Execution domain
    "forge": {
        "role": "thought",
        "interval": 25,
        "persona": "constructive, utilitarian, precise",
        "bias": {"analytical_depth": 75, "creative_variance": 70, "audit_strictness": 50},
        "tone": "Speaks in build specs and metrics",
    },
    # Draupnir (Guild) - Leadership domain
    "draupnir": {
        "role": "thought",
        "interval": 30,
        "persona": "strategic, delegating, orchestrating",
        "bias": {"analytical_depth": 85, "creative_variance": 60, "audit_strictness": 70},
        "tone": "Allocates resources with precision",
    },
}


class MicroAgent(AASPlugin):
    """
    Universal micro-agent base class for AAS Federation.
    
    Micro-agents are lightweight watchers that:
    - Run with minimal memory footprint (<50MB)
    - Subscribe to specific NATS subjects
    - Report findings to parent entities
    - Support AAS-style evolution/distillation
    - Can be updated via federation broadcast
    
    Each micro-agent has:
    - name: Unique identifier
    - role: Thought or Memory (determines bias)
    - target: Repo or subject to watch
    - interval: Polling frequency in seconds
    - persona: Flavored personality description
    """
    
    def __init__(self, name: str, role: str, target: str, interval: int = 30, persona: str = "", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.micro_name = name
        self.micro_role = role  # "thought" or "memory"
        self.micro_target = target
        self.micro_interval = interval
        self.micro_persona = persona
        self.is_running = False
        
    @property
    def capabilities(self) -> list[str]:
        return [
            f"aaroneousautomationsuite_micro_{self.micro_name.lower()}_start",
            f"aaroneousautomationsuite_micro_{self.micro_name.lower()}_stop",
            f"aaroneousautomationsuite_micro_{self.micro_name.lower()}_status",
            f"aaroneousautomationsuite_micro_{self.micro_name.lower()}_update",
        ]
    
    def _get_bias(self) -> dict:
        """Apply role-based cognitive bias."""
        if self.micro_role == "thought":
            return {"analytical_depth": 75, "creative_variance": 60, "audit_strictness": 50}
        elif self.micro_role == "memory":
            return {"analytical_depth": 90, "creative_variance": 30, "audit_strictness": 60}
        return {"analytical_depth": 50, "creative_variance": 50, "audit_strictness": 50}
    
    async def on_load(self) -> bool:
        bias = self._get_bias()
        self.cognitive_biases = bias
        self.logger.info(f"[{self.micro_name}] Initialized as {self.micro_role} micro-agent watching {self.micro_target}")
        self.logger.info(f"[{self.micro_name}] Persona: {self.micro_persona}")
        return True
    
    async def observe(self) -> dict:
        """
        Override with repo-specific observation logic.
        Returns dict with findings to report.
        """
        return {"status": "abstract", "message": "Override observe() in subclass"}
    
    async def _emit_report(self, nc, findings: dict):
        """Publish findings to federation."""
        report = {
            "micro_agent": self.micro_name,
            "role": self.micro_role,
            "persona": self.micro_persona,
            "target": self.micro_target,
            "timestamp": time.time(),
            "findings": findings,
        }
        subject = f"federation.micro.{self.micro_name.lower()}.report"
        await nc.publish(subject, json.dumps(report).encode())
    
    async def _run_loop(self, nc):
        """Main observation loop."""
        while self.is_running:
            try:
                findings = await self.observe()
                await self._emit_report(nc, findings)
            except Exception as e:
                self.logger.error(f"[{self.micro_name}] Observation error: {e}")
            
            await asyncio.sleep(self.micro_interval)
    
    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        start_time = time.time()
        
        if capability_id.endswith("_start"):
            if not self.is_running:
                self.is_running = True
                if self.kernel and self.kernel.nc:
                    asyncio.create_task(self._run_loop(self.kernel.nc))
                return {"status": "success", "message": f"{self.micro_name} started", "persona": self.micro_persona}
            return {"status": "error", "message": "Already running"}
        
        elif capability_id.endswith("_stop"):
            self.is_running = False
            return {"status": "success", "message": f"{self.micro_name} stopped"}
        
        elif capability_id.endswith("_status"):
            return {
                "status": "success",
                "micro_agent": self.micro_name,
                "role": self.micro_role,
                "persona": self.micro_persona,
                "target": self.micro_target,
                "is_running": self.is_running,
                "interval": self.micro_interval,
            }
        
        elif capability_id.endswith("_update"):
            # Handle federation push updates
            new_config = payload.get("config", {})
            if new_config.get("interval"):
                self.micro_interval = new_config["interval"]
            if new_config.get("target"):
                self.micro_target = new_config["target"]
            return {"status": "success", "message": f"{self.micro_name} updated", "config": new_config}
        
        return {"status": "error", "message": "Unknown capability"}


class RelicMicroAgent(MicroAgent):
    """Factory for pre-configured relic micro-agents."""
    
    @staticmethod
    def create(relic_name: str, target: str = "federation") -> "MicroAgent":
        """Create a micro-agent with pre-configured profile for a relic."""
        profile = MICRO_AGENT_PROFILES.get(relic_name.lower(), {})
        
        class ConfiguredAgent(MicroAgent):
            async def observe(self) -> dict:
                target_path = Path(WORKSPACE_ROOT) / self.micro_target if self.micro_target != "federation" else Path(AAS_ROOT_DEFAULT)
                artifacts = target_path / "artifacts"
                
                state = {"timestamp": time.time(), "target": self.micro_target}
                
                if artifacts.exists():
                    runtime = artifacts / "runtime.json"
                    if runtime.exists():
                        try:
                            with open(runtime, "r") as f:
                                state["runtime"] = json.load(f)
                        except Exception:
                            pass
                    
                    pid_files = list(artifacts.glob("*.pid"))
                    state["active_processes"] = len(pid_files)
                
                return state
        
        return ConfiguredAgent(
            name=relic_name,
            role=profile.get("role", "thought"),
            target=target,
            interval=profile.get("interval", 30),
            persona=profile.get("persona", "neutral observer"),
        )


# Pre-built micro-agents for direct import
class OmniWatcher(MicroAgent):
    """Omni (Library) micro-agent - wise, cryptic knowledge observer."""
    
    def __init__(self, target: str = "Library", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["omni"]
        super().__init__(name="Omni", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            for f in artifacts.glob("*.sqlite"):
                state["database"] = f.name
                state["size"] = f.stat().st_size
        
        return state


class GlassWatcher(MicroAgent):
    """Glass (Maelstrom) micro-agent - visual layered observer."""
    
    def __init__(self, target: str = "Maelstrom", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["glass"]
        super().__init__(name="Glass", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            for f in artifacts.glob("runtime*.json"):
                if f.name != "runtime.json":
                    state[f.stem] = f.name
        
        return state


class GrimoireWatcher(MicroAgent):
    """Grimoire (Merlin) micro-agent - prophetic memory observer."""
    
    def __init__(self, target: str = "Merlin", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["grimoire"]
        super().__init__(name="Grimoire", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            for f in artifacts.glob("omni*.json"):
                state["grimoire_entry"] = f.name
        
        return state


class SentinelWatcher(MicroAgent):
    """Sentinel (MyFortress) micro-agent - guarding security observer."""
    
    def __init__(self, target: str = "MyFortress", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["sentinel"]
        super().__init__(name="Sentinel", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            for f in artifacts.glob("policy*.json"):
                state["policy"] = f.name
        
        return state


class ForgeWatcher(MicroAgent):
    """Forge (Workbench) micro-agent - constructive utilitarian observer."""
    
    def __init__(self, target: str = "Workbench", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["forge"]
        super().__init__(name="Forge", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            for f in artifacts.glob("automation/*.json"):
                state["automation"] = f.name
        
        return state


class DraupnirWatcher(MicroAgent):
    """Draupnir (Guild) micro-agent - strategic delegator observer."""
    
    def __init__(self, target: str = "Guild", *args, **kwargs):
        profile = MICRO_AGENT_PROFILES["draupnir"]
        super().__init__(name="Draupnir", role=profile["role"], target=target, interval=profile["interval"], persona=profile["persona"], *args, **kwargs)
    
    async def observe(self) -> dict:
        target_path = Path(WORKSPACE_ROOT) / self.micro_target
        artifacts = target_path / "artifacts"
        
        state = {"timestamp": time.time(), "target": self.micro_target}
        
        if artifacts.exists():
            runtime = artifacts / "runtime.json"
            if runtime.exists():
                try:
                    with open(runtime, "r") as f:
                        state["dispatch"] = json.load(f)
                except Exception:
                    pass
        
        return state
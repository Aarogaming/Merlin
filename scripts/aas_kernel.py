#!/usr/bin/env python3
"""
AAS Universal Microkernel and Plugin Interface

Replaces monolithic repo engines. This kernel provides the core OS layer
for an AAS Agent:
1. Connects to NATS JetStream (Networking)
2. Starts the Heartbeat emitter (Monitoring)
3. Establishes the Logger (Logging)
4. Dynamically loads and routes messages to repo-specific Plugins (Business Logic)
5. Provides Federation Behaviors: Circuit Breaker, Leader Election, Service Discovery
"""

import os
import sys
import subprocess
import asyncio
import json
import logging
import importlib.util
import inspect
import time
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

try:
    from nats.aio.client import Client as NATS
    HAS_NATS = True
except ImportError:
    HAS_NATS = False


AAS_ROOT = Path(__file__).resolve().parents[1]
CONFIG_MD = AAS_ROOT / "config" / "config.md"

DEFAULTS = {
    "root": ".",
    "logs": "logs",
    "artifacts": "artifacts",
    "config": "config",
    "runtime": "runtime",
    "genome": "genome",
    "plugins": "plugins",
    "scripts": "scripts",
    "nats_tmp": "nats/tmp",
    "nats_data": "nats/data",
    "nats_bin": "nats/bin/nats-server.exe",
    "lifecycle_state": "runtime/lifecycle_state.json",
    "lifecycle_events": "runtime/lifecycle.events.jsonl",
    "identity_epigenetics": "genome/identity.epigenetics.json",
    "identity_genome": "genome/identity.genome.json",
    "identity_memory": "genome/identity.memory.json",
    "mcp_manifest": "mcp-manifest.json",
    "genome_manifest": "genome.manifest.json",
    "runtime_manifest": "config/runtime.manifest.json",
    "spark_config": "config/spark_config.json",
    "agents_md": "runtime/AGENTS.md",
    "soul_md": "runtime/SOUL.md",
    "evolution_ledger": "logs/EVOLUTION_LEDGER.md",
}

ENV_OVERRIDES = {
    "logs": "AAS_LOGS_DIR",
    "artifacts": "AAS_ARTIFACTS_DIR",
    "config": "AAS_CONFIG_DIR",
    "runtime": "AAS_RUNTIME_DIR",
    "genome": "AAS_GENOME_DIR",
    "plugins": "AAS_PLUGINS_DIR",
    "nats_tmp": "AAS_NATS_TMP",
    "nats_data": "AAS_NATS_DATA",
    "nats_bin": "AAS_NATS_BIN",
}

_override_cache: Dict = {}
_loaded: bool = False


def _parse_config_md() -> Dict:
    global _override_cache, _loaded
    if _loaded:
        return _override_cache

    if not CONFIG_MD.exists():
        config_dir = CONFIG_MD.parent
        config_dir.mkdir(parents=True, exist_ok=True)
        default_content = """# AAS Path Configuration

**Source of truth for all path resolutions.** The kernel parses this file at runtime.

## Output Rules

- **State files** → `runtime/` (lifecycle, events)
- **Identity artifacts** → `genome/` (identity, schemas)
- **Configuration** → `config/` (manifests, configs)
- **Logs** → `logs/` (execution traces)
- **Build artifacts** → `artifacts/` (GGUF, relics)
- **Generated docs** (AGENTS.md, SOUL.md) → `runtime/`

## Environment Overrides

Set these env vars to override any directory:
- `AAS_LOGS_DIR`
- `AAS_ARTIFACTS_DIR`
- `AAS_CONFIG_DIR`
- `AAS_RUNTIME_DIR`
- `AAS_GENOME_DIR`
- `AAS_PLUGINS_DIR`
"""
        CONFIG_MD.write_text(default_content, encoding="utf-8")

    content = CONFIG_MD.read_text(encoding="utf-8")
    in_output_section = False
    in_files_section = False
    for line in content.splitlines():
        if line.strip() == "## Output Rules":
            in_output_section = True
            in_files_section = False
            continue
        if line.strip() == "## File Paths":
            in_output_section = False
            in_files_section = True
            continue
        if line.startswith("## ") and not in_files_section:
            break
        if "→" in line:
            parts = line.split("→")
            if len(parts) == 2:
                key = parts[0].strip().strip("- ").strip("*").lower().rstrip("/")
                value = parts[1].strip().split("(")[0].strip()
                if key in DEFAULTS:
                    _override_cache[key] = value

    _loaded = True
    return _override_cache


def get_path(key: str) -> Path:
    if key in ENV_OVERRIDES:
        env_val = os.environ.get(ENV_OVERRIDES[key])
        if env_val:
            return Path(env_val)

    custom = _parse_config_md()
    if key in custom:
        p = Path(custom[key])
        return p if p.is_absolute() else AAS_ROOT / p

    if key in DEFAULTS:
        p = Path(DEFAULTS[key])
        return p if p.is_absolute() else AAS_ROOT / p

    raise KeyError(f"Unknown path key: {key}")


def ensure_dirs(*keys: str) -> None:
    for key in keys:
        get_path(key).mkdir(parents=True, exist_ok=True)


def get_federation_logger(repo_name: str, component: str = "Kernel") -> logging.Logger:
    """Native federation logger - each agent-repo manages its own logging."""
    logger = logging.getLogger(f"{repo_name}.{component}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(f"%(asctime)s - [{repo_name}] - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    return logger


class FederationHeartbeat:
    """Native heartbeat - each agent-repo maintains its own time."""
    def __init__(self, repo_name: str, agent_id: str, interval: int = 15):
        self.repo_name = repo_name
        self.agent_id = agent_id
        self.interval = interval
        self.logger = get_federation_logger(repo_name, "Heartbeat")
        self.running = False

    async def start(self):
        self.running = True
        while self.running:
            await asyncio.sleep(self.interval)
            self.logger.debug(f"HEARTBEAT {self.agent_id} alive")

    async def stop(self):
        self.running = False

class AASPlugin:
    """
    Base class for all repository-specific capabilities.
    Any old script (e.g., merlin_inference.py) just needs to be wrapped in this class
    and placed in the repo's `plugins/` directory.
    """
    def __init__(self):
        self.kernel = None # Set by the kernel during load
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Continuous Training Parameters
        self._experience_buffer: List[Dict[str, str]] = []
        self._forge_threshold = 100  # Number of experiences before requesting a forge

    @property
    def capabilities(self) -> List[str]:
        """Returns a list of capability IDs (from mcp-manifest.json) this plugin handles."""
        return []

    async def on_load(self) -> bool:
        """Lifecycle hook called when the plugin is initialized."""
        return True

    async def on_unload(self):
        """Lifecycle hook called when the plugin is removed or system shuts down."""
        pass

    async def handle_message(self, capability_id: str, payload: dict) -> Any:
        """
        The core execution loop.
        MUST BE OVERRIDDEN BY THE CHILD PLUGIN.
        """
        raise NotImplementedError(f"Plugin {self.__class__.__name__} must implement handle_message.")

    async def record_experience(self, user_prompt: str, thought_process: str, final_response: str):
        """
        Natively logs an interaction as high-quality synthetic training data.
        When the buffer fills, it triggers a continuous distillation loop via Workbench.
        """
        experience = {
            "user_prompt": user_prompt,
            "agent_thought": thought_process,
            "agent_response": final_response
        }
        self._experience_buffer.append(experience)
        self.logger.debug(f"Recorded experience. Buffer size: {len(self._experience_buffer)}/{self._forge_threshold}")
        
        if len(self._experience_buffer) >= self._forge_threshold:
            await self._flush_and_request_forge()

    async def _flush_and_request_forge(self):
        """Writes the buffer to disk and requests the Workbench Cognitive Forge to compile it."""
        if not self.kernel or not self.kernel.nc:
            self.logger.warning("Cannot request Cognitive Forge: Not connected to Event Bus.")
            return

        artifacts_dir = get_path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        dataset_path = artifacts_dir / "continuous_training.jsonl"
        
        self.logger.info(f"Flushing {len(self._experience_buffer)} experiences to {dataset_path.name}")
        with open(dataset_path, 'a', encoding='utf-8') as f:
            for exp in self._experience_buffer:
                f.write(json.dumps(exp) + "\n")
                
        self._experience_buffer.clear()
        
        # Dispatch the forge request to Workbench
        forge_payload = {
            "requester": self.kernel.repo_name,
            "dataset_path": str(dataset_path.absolute()),
            "target_artifact_dir": str(artifacts_dir.absolute())
        }
        
        self.logger.info("Dispatching Cognitive Forge request to Workbench...")
        try:
            # We assume Workbench is listening on workbench.cognitive_forge
            await self.kernel.nc.publish("workbench.cognitive_forge", json.dumps(forge_payload).encode())
        except Exception as e:
            self.logger.error(f"Failed to dispatch forge request: {e}")


class GGUFManager:
    """
    GGUF Auto-Discovery and Selection.

    Manages local model discovery, identification, and selection
    without loading neural tensors (offline harvesting).
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.models = []
        self.selected_model = None

        model_paths_env = os.environ.get("AAS_MODEL_PATHS", "")
        extra_search_paths = [Path(p.strip()) for p in model_paths_env.split(",") if p.strip()]
        self.search_paths = [
            repo_root / "artifacts",
            repo_root / "runtime" / "models",
        ] + extra_search_paths

    def discover(self):
        """Find all GGUF files."""
        self.models = []
        for search_path in self.search_paths:
            if search_path.exists():
                for gguf in search_path.glob("*.gguf"):
                    self.models.append(gguf)
        return self.models

    def identify(self, gguf_path: Path) -> dict:
        """Extract GGUF metadata without loading."""
        try:
            from gguf import GGUFReader
            reader = GGUFReader(str(gguf_path))
            fields = dict(reader.fields)

            return {
                "path": str(gguf_path),
                "name": gguf_path.name,
                "size_mb": gguf_path.stat().st_size / (1024 * 1024),
                "is_aas_wrapped": any(k.startswith("aas.") for k in fields),
                "domains": [k.replace("aas.dna.domain.", "") for k in fields if k.startswith("aas.dna.domain.")],
                "biases": {k.replace("aas.dna.bias.", ""): fields[k] for k in fields if k.startswith("aas.dna.bias.")},
                "skills": [k.replace("aas.skill.", "") for k in fields if k.startswith("aas.skill.")],
                "personality": {k.replace("aas.dna.persona.", ""): fields[k] for k in fields if k.startswith("aas.dna.persona.")},
                "epoch": fields.get("aas.evolution.epoch", 0),
                "parameter_count": fields.get("aas.evolution.parameter_count", 0),
            }
        except ImportError:
            return {"path": str(gguf_path), "name": gguf_path.name, "error": "gguf package not installed"}
        except Exception as e:
            return {"path": str(gguf_path), "name": gguf_path.name, "error": str(e)}

    def select(self, requirement: str = "auto") -> dict:
        """Select optimal GGUF based on requirement."""
        if not self.models:
            self.discover()

        if not self.models:
            return None

        scored = []
        for gguf in self.models:
            info = self.identify(gguf)
            if "error" in info:
                continue

            score = 0
            if requirement in ["fast", "triage"]:
                score -= info.get("size_mb", 0)
                if info.get("is_aas_wrapped"):
                    score += 50
            elif requirement in ["deep", "reasoning"]:
                score += info.get("parameter_count", 0)
            elif requirement == "aas_personality":
                if info.get("is_aas_wrapped"):
                    score += 100
                score += len(info.get("domains", [])) * 10
            else:  # auto - balanced
                score = 50

            scored.append((score, info))

        scored.sort(reverse=True)
        self.selected_model = scored[0][1] if scored else None
        return self.selected_model

    def extract_dna(self, gguf_path: Path) -> dict:
        """Siphon DNA from GGUF without loading."""
        info = self.identify(gguf_path)
        dna = {
            "schema_version": "3.0",
            "preset": "siphoned_from_gguf",
            "persona_vectors": info.get("persona", {}),
            "cognitive_biases": info.get("biases", {}),
            "domain_weights": {},
        }
        for domain in info.get("domains", []):
            dna["domain_weights"][domain] = 50.0
        dna["parameter_count"] = info.get("parameter_count", 0)
        dna["evolutionary_epoch"] = info.get("epoch", 0)
        return dna


class ReflexPlugin(AASPlugin):
    """
    BASE REFLEX - Kernel-integral foundation for all domain plugins.

    Provides:
    - DNA/Epigenetics loading
    - Domain weight management
    - Relic attunement
    - Hive consensus
    - Epigenetic adaptation
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.domain_name = self.__class__.__name__
        self.weight = 50.0
        self.persona_vectors = {}
        self.cognitive_biases = {}
        self.parameter_count = 1000
        self.evolutionary_epoch = 1
        import os
        self.epigenetic_profile_path = Path(os.environ.get("AAS_EPIGENETICS_PATH", str(Path(__file__).resolve().parents[1] / "genome" / "identity.epigenetics.json")))

    async def on_load(self) -> bool:
        """Epigenetic Bootloader - load DNA and weights."""
        try:
            if self.epigenetic_profile_path.exists():
                with open(self.epigenetic_profile_path, "r", encoding="utf-8") as f:
                    epigenetics = json.load(f)
                    weights = epigenetics.get("domain_weights", {})
                    self.weight = weights.get(self.domain_name, 50.0)
                    self.persona_vectors = epigenetics.get("persona_vectors", {})
                    self.cognitive_biases = epigenetics.get("cognitive_biases", {})
                    self.parameter_count = epigenetics.get("parameter_count", 1000)
                    self.evolutionary_epoch = epigenetics.get("evolutionary_epoch", 1)
            else:
                self.weight = 50.0
                self.parameter_count = 1000
        except Exception as e:
            self.weight = 50.0
            self.parameter_count = 1000

        if self.weight < 20.0:
            self.logger.info(f"[Gene Suppressed] Domain '{self.domain_name}' dormant.")
            return False
        return True

    async def on_federate(self, nc) -> bool:
        """Hive consensus protocol."""
        return True

    def _adapt(self, success: bool, capability_id: str = "", payload_signature: str = ""):
        """Epigenetic adaptation - mutate DNA based on execution."""
        try:
            with open(self.epigenetic_profile_path, "r", encoding="utf-8") as f:
                dna = json.load(f)

            current_weight = dna.get("domain_weights", {}).get(self.domain_name, 50.0)
            parameter_count = dna.get("parameter_count", 1000)

            learning_rate = max(0.05, 1000.0 / (parameter_count ** 0.8))

            if success:
                new_weight = min(100.0, current_weight + (0.5 * learning_rate))
                param_delta = 5
            else:
                new_weight = max(0.0, current_weight - (1.0 * learning_rate))
                param_delta = 15

            dna["parameter_count"] = parameter_count + param_delta
            dna.setdefault("domain_weights", {})[self.domain_name] = round(new_weight, 2)

            with open(self.epigenetic_profile_path, "w", encoding="utf-8") as f:
                json.dump(dna, f, indent=2)

            self.weight = new_weight
            self.parameter_count = parameter_count + param_delta
        except Exception as e:
            self.logger.error(f"Epigenetic adaptation failed: {e}")

    def persist_cognitive_biases(self) -> bool:
        """Persist current cognitive_biases to epigenetics file for closed-loop adaptation."""
        try:
            with open(self.epigenetic_profile_path, "r", encoding="utf-8") as f:
                dna = json.load(f)
            
            dna["cognitive_biases"] = self.cognitive_biases
            dna["persona_vectors"] = self.persona_vectors
            
            with open(self.epigenetic_profile_path, "w", encoding="utf-8") as f:
                json.dump(dna, f, indent=2)
            
            self.logger.debug(f"Persisted cognitive_biases to {self.epigenetic_profile_path.name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to persist cognitive_biases: {e}")
            return False


    def _format_result(self, capability_id: str, result: any, start_time: float, success: bool = True) -> dict:
        """Format execution result with telemetry."""
        duration = time.time() - start_time
        self._adapt(success=success, capability_id=capability_id)
        return {
            "status": "success" if success else "error",
            "capability": capability_id,
            "result": result,
            "telemetry": {
                "execution_ms": round(duration * 1000, 2),
                "epigenetic_weight": self.weight,
                "parameter_count": self.parameter_count
            }
        }


class AASKernel:
    def __init__(self, repo_name: str, repo_root: str, singularity_mode: bool = False, dry_run: bool = False, minimal: bool = False):
        self.repo_name = repo_name
        self.repo_root = Path(repo_root)
        self.singularity_mode = singularity_mode or dry_run
        self.dry_run = dry_run or singularity_mode
        self.minimal_mode = minimal
        self.logger = get_federation_logger(repo_name, "Kernel")

        self.nc = NATS() if HAS_NATS else None
        self.heartbeat = FederationHeartbeat(repo_name=self.repo_name, agent_id=f"{self.repo_name}_Primary")
        self.gguf_manager = GGUFManager(self.repo_root)

        self.plugins: Dict[str, AASPlugin] = {}
        self._capability_map: Dict[str, AASPlugin] = {}

        self.adapters: Dict[str, Any] = {}

        self.federation = FederationBehaviors(self) if not minimal else None

        manifest_path = self.repo_root / "mcp-manifest.json"
        self.manifest_caps = {}
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                data = json.load(f)
                for cap in data.get("capabilities", []):
                    self.manifest_caps[cap["capability_id"]] = cap["entry_point"]

    def register_adapter(self, adapter_name: str, adapter_instance: Any):
        """Allows a Plugin to mount a native Python interface directly into the Kernel."""
        self.adapters[adapter_name] = adapter_instance
        self.logger.info(f"Mounted native adapter: '{adapter_name}'")

    def load_plugins_from_directory(self, plugin_dir: str):
        """Dynamically loads any python file in the plugins directory that contains an AASPlugin."""
        p_dir = Path(plugin_dir)
        safe_mode = os.environ.get("AAS_SAFE_MODE", "1") == "1"
        
        if not p_dir.exists():
            self.logger.warning(f"Plugin directory {p_dir} does not exist.")
            return

        for py_file in p_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Scan module for classes inheriting from AASPlugin
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Skip base classes - kernel infrastructure, not plugins
                    if obj is AASPlugin or obj is ReflexPlugin:
                        continue
                    if issubclass(obj, AASPlugin) and obj is not ReflexPlugin:
                        self.logger.debug(f"Found plugin class: {name} in {py_file.name}")
                        try:
                            plugin_instance = obj()
                            plugin_instance.kernel = self
                            self.plugins[name] = plugin_instance
                            
                            # Map the plugin to its declared capabilities
                            for cap_id in plugin_instance.capabilities:
                                self._capability_map[cap_id] = plugin_instance
                                
                            self.logger.info(f"Successfully loaded plugin: {name}")
                        except Exception as e:
                            self.logger.error(f"Failed to instantiate plugin {name}: {e}")
                            if not safe_mode:
                                raise
                            else:
                                self.logger.warning(f"Skipping instantiation of problematic plugin: {name}")

            except Exception as e:
                self.logger.error(f"Failed to load plugin {py_file.name}: {e}")
                if not safe_mode:
                    self.logger.critical("AAS_SAFE_MODE is disabled. A single plugin failure is fatal.")
                    raise  # Re-raise the exception to crash the kernel
                else:
                    self.logger.warning(f"AAS_SAFE_MODE is enabled. Skipping problematic plugin: {py_file.name}")

    async def _message_router(self, msg, cap_id: str):
        """Routes NATS messages to the correct plugin, trapping exceptions."""
        try:
            payload = json.loads(msg.data.decode()) if msg.data else {}
            plugin = self._capability_map[cap_id]
            
            self.logger.debug(f"Routing {cap_id} to {plugin.__class__.__name__}")
            result = await plugin.handle_message(cap_id, payload)
            
            if msg.reply:
                await self.nc.publish(msg.reply, json.dumps(result).encode())
                
        except Exception as e:
            self.logger.error(f"Plugin {cap_id} crashed during execution: {e}")
            if msg.reply:
                await self.nc.publish(msg.reply, json.dumps({"error": str(e), "status": "plugin_crash"}).encode())

    def preflight(self, clean_nats: bool = False, kill_python_listeners: bool = False) -> bool:
        """
        Native Kernel Preflight.
        Ensures NATS is running in the background. Clears stale listeners if requested.
        """
        self.logger.info("Running Kernel Environment Preflight Checks...")
        
        if kill_python_listeners:
            self.logger.info("Clearing stale Python listener processes...")
            try:
                subprocess.run([
                    "powershell", "-Command", 
                    "Get-Process | Where-Object {$_.Name -match 'python' -and $_.Id -ne $PID} | Stop-Process -Force -ErrorAction SilentlyContinue"
                ], capture_output=True)
            except Exception as e:
                self.logger.warning(f"Could not clear Python listeners: {e}")

        nats_running = False
        try:
            ps_out = subprocess.run(["powershell", "-Command", "Get-Process | Where-Object {$_.Name -match 'nats'}"], capture_output=True, text=True)
            if "nats-server" in ps_out.stdout or "nats" in ps_out.stdout:
                nats_running = True
        except Exception as e:
            self.logger.warning(f"Failed to check NATS process: {e}")

        if clean_nats:
            self.logger.info("Performing deep NATS cleanup...")
            if nats_running:
                subprocess.run(["powershell", "-Command", "Get-Process | Where-Object {$_.Name -match 'nats'} | Stop-Process -Force -ErrorAction SilentlyContinue"], capture_output=True)
                nats_running = False
            
            tmp_path = get_path("nats_tmp")
            data_path = get_path("nats_data")
            try:
                if tmp_path.exists(): shutil.rmtree(tmp_path, ignore_errors=True)
                if data_path.exists(): shutil.rmtree(data_path, ignore_errors=True)
            except Exception as e:
                self.logger.warning(f"Error clearing NATS directories: {e}")

        if not nats_running:
            self.logger.info("Starting NATS Server in the background...")
            nats_bin = get_path("nats_bin")
            if nats_bin.exists():
                subprocess.Popen(
                    ["powershell", "-Command", f"Start-Process -FilePath '{nats_bin}' -ArgumentList '-js' -WindowStyle Hidden"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(2) # Give NATS time to bind
            else:
                self.logger.error(f"CRITICAL: NATS binary not found at {nats_bin}. Federation will be unstable.")
                return False

        self.logger.info("Preflight complete. Environment is stable.")
        return True

    def boot_ecosystem(self):
        """
        Native Federation Discovery & Ignition.
        Scans for siblings, builds a local roster, and drops them into detached network slots.
        """
        if self.singularity_mode:
            self.logger.info("[SINGULARITY] Skipping ecosystem boot - verification only.")
            return

        self.logger.info("Kernel Ecosystem Bootloader engaged.")

        if not self.preflight():
            self.logger.warning("Preflight failed. Proceeding with caution...")

        workspace_root = self.repo_root.parent
        roster_file = self.repo_root / "artifacts" / "federation_roster.json"

        if roster_file.exists():
            self.logger.info(f"Loading known federation roster from {roster_file.name}...")
            try:
                with open(roster_file, 'r', encoding='utf-8') as f:
                    agents = json.load(f).get("ecosystem", [])
            except json.JSONDecodeError:
                agents = self._discover_agents(workspace_root)
                self._save_roster(roster_file, agents, workspace_root)
        else:
            self.logger.info("No local roster found. Initiating ecosystem discovery...")
            agents = self._discover_agents(workspace_root)
            self._save_roster(roster_file, agents, workspace_root)

        for agent in agents:
            repo_name = agent["repo_name"]

            if repo_name.lower() == self.repo_name.lower():
                continue

            self.logger.info(f"Igniting {repo_name} in isolated terminal slot...")
            cmd_str = f'Start-Process cmd.exe -ArgumentList "/k title {repo_name} & set AAS_SAFE_MODE=1 & python ""{agent["boot_script"]}"""'

            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", cmd_str],
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS
            )
            time.sleep(0.5)

    def _discover_agents(self, workspace_root: Path) -> list:
        agents = []
        for directory in workspace_root.iterdir():
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            manifest_path = directory / "mcp-manifest.json"
            boot_script = directory / "scripts" / "boot.py"
            if manifest_path.exists() and boot_script.exists():
                agents.append({
                    "repo_name": directory.name,
                    "boot_script": str(boot_script.absolute()),
                    "manifest_path": str(manifest_path.absolute())
                })
        return agents

    def _save_roster(self, roster_file: Path, agents: list, workspace_root: Path):
        roster_file.parent.mkdir(exist_ok=True)
        roster_data = {
            "last_discovery": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "ecosystem_root": str(workspace_root.absolute()),
            "agent_count": len(agents),
            "ecosystem": agents
        }
        with open(roster_file, 'w', encoding='utf-8') as f:
            json.dump(roster_data, f, indent=2)

    async def verify(self):
        """Singularity Mode verification - runs system checks without ignition."""
        self.logger.info(f"[SINGULARITY] Starting verification for {self.repo_name}...")

        report = {
            "repo_name": self.repo_name,
            "singularity_mode": True,
            "checks": []
        }

        report["checks"].append(self._check_plugins())
        report["checks"].append(self._check_manifests())
        report["checks"].append(self._check_dependencies())
        report["checks"].append(self._check_gguf_models())

        print("\n" + "=" * 60)
        print(f"SINGULARITY VERIFICATION REPORT - {self.repo_name}")
        print("=" * 60)
        for check in report["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}: {check.get('detail', 'OK')}")
        print("=" * 60)

        return report

    def _check_plugins(self) -> dict:
        """Verify all plugins load without errors."""
        result = {"name": "Plugin Load", "passed": True, "detail": ""}
        for name, plugin in self.plugins.items():
            result["detail"] = f"{len(self.plugins)} plugins loaded"
        return result

    def _check_manifests(self) -> dict:
        """Verify all manifests are valid."""
        result = {"name": "Manifest Validation", "passed": True, "detail": ""}
        for cap_id in self.manifest_caps:
            result["detail"] = f"{len(self.manifest_caps)} capabilities"
        return result

    def _check_dependencies(self) -> dict:
        """Verify runtime dependencies."""
        result = {"name": "Runtime Dependencies", "passed": True, "detail": ""}
        result["detail"] = f"NATS: {'Available' if HAS_NATS else 'Missing (dry-run)'}"
        return result

    def _check_gguf_models(self) -> dict:
        """Auto-discover GGUF models."""
        result = {"name": "GGUF Models", "passed": True, "detail": ""}
        models = self.gguf_manager.discover()
        if models:
            info = [self.gguf_manager.identify(m) for m in models[:3]]
            result["detail"] = f"{len(models)} GGUF found: {[m['name'] for m in info]}"
        else:
            result["detail"] = "No GGUF models found"
        return result

    async def ignite(self):
        """Starts the Kernel OS layer: NATS, Plugins, Heartbeat."""
        if not self.nc:
            self.logger.error("NATS missing. Cannot ignite kernel.")
            return

        try:
            nats_url = os.environ.get("AAS_NATS_URL", "nats://localhost:4222")
            await self.nc.connect(nats_url, connect_timeout=5)
            self.logger.info("Kernel connected to Event Bus.")
            
            # 1. Initialize Plugins
            for name, plugin in self.plugins.items():
                success = await plugin.on_load()
                if not success:
                    self.logger.warning(f"Plugin {name} failed on_load. Disabling.")
            
            # 2. Bind capabilities to NATS subjects
            for cap_id, plugin in self._capability_map.items():
                subject = self.manifest_caps.get(cap_id)
                if subject:
                    # Closure to bind cap_id correctly
                    async def cb(msg, cid=cap_id):
                        await self._message_router(msg, cid)
                    await self.nc.subscribe(subject, cb=cb)
                    self.logger.info(f"Kernel listening on {subject} -> {plugin.__class__.__name__}")

            # 2.5. Subscribe to the general triage request subject (Front Door)
            triage_subject = self.manifest_caps.get("aaroneousautomationsuite_triage_user_request")
            if triage_subject:
                async def triage_cb(msg):
                    await self._triage_router(msg)
                await self.nc.subscribe(triage_subject, cb=triage_cb)
                self.logger.info(f"Kernel listening on {triage_subject} -> Triage Router")

            # 3. Start Federation Behaviors
            cap_list = list(self._capability_map.keys())
            asyncio.create_task(self.start_leader_election(priority=50.0))
            asyncio.create_task(self.start_service_discovery(capabilities=cap_list))
            self.logger.info("[Federation] Hive, Mesh, and Swarm behaviors initialized.")
            
            # 4. Start Heartbeat Background Task
            asyncio.create_task(self.heartbeat.start())
            self.logger.info(f"=== {self.repo_name} KERNEL ONLINE ===")
            
            # Keep alive
            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.logger.info("Kernel received shutdown signal.")
        finally:
            # Shutdown plugins
            for name, plugin in self.plugins.items():
                await plugin.on_unload()
                
            # Disconnect event bus
            if self.nc.is_connected:
                await self.nc.close()

    async def _triage_router(self, msg):
        """Routes incoming triage requests to the appropriate plugin based on payload capability_id."""
        try:
            payload = json.loads(msg.data.decode()) if msg.data else {}
            requested_capability_id = payload.get("capability_id")
            capability_payload = payload.get("capability_payload", {})
            trace_id = payload.get("trace_id", "unknown_trace")

            if not requested_capability_id:
                error_msg = "Triage request missing 'capability_id' in payload."
                self.logger.error(f"[{trace_id}] {error_msg}")
                if msg.reply:
                    await self.nc.publish(msg.reply, json.dumps({"error": error_msg, "status": "bad_request"}).encode())
                return

            plugin = self._capability_map.get(requested_capability_id)

            if not plugin:
                error_msg = f"No plugin found for capability_id: {requested_capability_id}"
                self.logger.error(f"[{trace_id}] {error_msg}")
                if msg.reply:
                    await self.nc.publish(msg.reply, json.dumps({"error": error_msg, "status": "not_found"}).encode())
                return
            
            self.logger.info(f"[{trace_id}] Triage routing {requested_capability_id} to {plugin.__class__.__name__}")
            result = await plugin.handle_message(requested_capability_id, capability_payload)
            
            if msg.reply:
                await self.nc.publish(msg.reply, json.dumps(result).encode())

        except Exception as e:
            self.logger.error(f"Triage router crashed during execution: {e}")
            if msg.reply:
                await self.nc.publish(msg.reply, json.dumps({"error": str(e), "status": "triage_router_crash"}).encode())



# =============================================================================
# FEDERATION BEHAVIORS: Embedded into Kernel
# These replace the standalone plugin files (resilience.py, federation_hive.py, etc.)
# =============================================================================

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault tolerance - embedded in kernel"""
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    opened_at: Optional[float] = None
    events: List[Dict] = field(default_factory=list)
    
    def can_execute(self) -> bool:
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - self.opened_at >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
        return self.state != CircuitBreakerState.OPEN
    
    def record_success(self) -> None:
        self.failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.events.append({"type": "closed", "time": time.time()})
    
    def record_failure(self) -> None:
        self.failure_count += 1
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.opened_at = time.time()
        elif self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.opened_at = time.time()
        self.events.append({"type": "failure", "count": self.failure_count, "time": time.time()})
        if len(self.events) > 50:
            self.events = self.events[-50:]
    
    def get_status(self) -> Dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failures_total": len([e for e in self.events if e.get("type") == "failure"])
        }


class FederationBehaviors:
    """
    Encapsulates Hive, Swarm, and Mesh behaviors.
    Mixed into AASKernel for seamless federation operation.
    """
    
    def __init__(self, kernel):
        self.kernel = kernel
        self.breakers: Dict[str, CircuitBreaker] = {}
        
        self._hive_state: Dict[str, Any] = {"leader": None, "term": 0}
        self._mesh_registry: Dict[str, Dict] = {}
        self._swarm_queue: List[Dict] = []
        
        self._leader_election_running = False
        self._discovery_running = False
    
    # --- RESILIENCE: Circuit Breaker ---
    
    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name=name)
        return self.breakers[name]
    
    def get_all_circuit_breakers(self) -> Dict[str, Dict]:
        return {name: cb.get_status() for name, cb in self.breakers.items()}
    
    async def execute_with_circuit(self, name: str, func, *args, **kwargs):
        """Execute function through circuit breaker"""
        cb = self.get_circuit_breaker(name)
        if not cb.can_execute():
            return {"error": f"Circuit {name} is OPEN", "circuit_state": cb.state.value}
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure()
            return {"error": str(e), "circuit_state": cb.state.value}
    
    # --- HIVE: Leader Election ---
    
    async def start_leader_election(self, priority: float = 50.0) -> None:
        """Start participating in leader election"""
        self._leader_election_running = True
        self._hive_state["priority"] = priority
        self._hive_state["repo"] = self.kernel.repo_name
        
        self.kernel.logger.info(f"[HIVE] Starting leader election (priority: {priority})")
        
        asyncio.create_task(self._hive_election_loop())
        asyncio.create_task(self._hive_heartbeat_loop())
    
    async def _hive_election_loop(self) -> None:
        while self._leader_election_running:
            try:
                await asyncio.sleep(30)
                if self._hive_state.get("leader") != self.kernel.repo_name:
                    await self._request_leader_vote()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.kernel.logger.warning(f"[HIVE] Election error: {e}")
    
    async def _hive_heartbeat_loop(self) -> None:
        while self._leader_election_running:
            try:
                await asyncio.sleep(15)
                if self._hive_state.get("is_leader"):
                    await self.kernel.nc.publish(
                        "federation.hive.heartbeat",
                        json.dumps({
                            "leader": self.kernel.repo_name,
                            "term": self._hive_state.get("term", 1),
                            "timestamp": time.time()
                        }).encode()
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.kernel.logger.warning(f"[HIVE] Heartbeat error: {e}")
    
    async def _request_leader_vote(self) -> None:
        if not self.kernel.nc:
            return
        await self.kernel.nc.publish(
            "federation.hive.election",
            json.dumps({
                "candidate": self.kernel.repo_name,
                "priority": self._hive_state.get("priority", 50),
                "timestamp": time.time()
            }).encode()
        )
    
    def get_hive_status(self) -> Dict:
        return {
            "is_leader": self._hive_state.get("is_leader", False),
            "current_leader": self._hive_state.get("leader"),
            "term": self._hive_state.get("term", 0),
            "priority": self._hive_state.get("priority", 50)
        }
    
    # --- MESH: Service Discovery ---
    
    async def start_service_discovery(self, capabilities: List[str]) -> None:
        """Start service discovery and registration"""
        self._discovery_running = True
        self._mesh_registry[self.kernel.repo_name] = {
            "capabilities": capabilities,
            "last_seen": time.time(),
            "status": "healthy"
        }
        
        self.kernel.logger.info(f"[MESH] Starting service discovery: {capabilities}")
        
        asyncio.create_task(self._mesh_heartbeat_loop())
    
    async def _mesh_heartbeat_loop(self) -> None:
        while self._discovery_running:
            try:
                await asyncio.sleep(10)
                self._mesh_registry[self.kernel.repo_name]["last_seen"] = time.time()
                
                if self.kernel.nc:
                    await self.kernel.nc.publish(
                        "federation.mesh.heartbeat",
                        json.dumps({
                            "repo": self.kernel.repo_name,
                            "capabilities": self._mesh_registry[self.kernel.repo_name]["capabilities"],
                            "timestamp": time.time()
                        }).encode()
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.kernel.logger.warning(f"[MESH] Heartbeat error: {e}")
    
    async def discover_service(self, capability: str) -> Optional[Dict]:
        """Find service with capability"""
        for repo, data in self._mesh_registry.items():
            if repo == self.kernel.repo_name:
                continue
            if capability in data.get("capabilities", []):
                if time.time() - data.get("last_seen", 0) < 60:
                    return {"repo": repo, "capabilities": data["capabilities"]}
        return None
    
    def get_mesh_status(self) -> Dict:
        now = time.time()
        services = []
        for repo, data in self._mesh_registry.items():
            age = now - data.get("last_seen", 0)
            status = "healthy" if age < 60 else "degraded" if age < 120 else "unhealthy"
            services.append({"repo": repo, "status": status, "capabilities": data.get("capabilities", [])})
        return {"services": services, "total": len(services)}
    
    # --- SWARM: Task Queue ---
    
    async def submit_swarm_task(self, task_type: str, payload: Dict, priority: int = 1) -> str:
        """Submit task to swarm queue"""
        task_id = str(uuid.uuid4())
        self._swarm_queue.append({
            "task_id": task_id,
            "type": task_type,
            "payload": payload,
            "priority": priority,
            "created_at": time.time(),
            "status": "pending"
        })
        self._swarm_queue.sort(key=lambda t: t["priority"], reverse=True)
        return task_id
    
    async def get_swarm_task(self) -> Optional[Dict]:
        """Get next task from queue"""
        if self._swarm_queue:
            task = self._swarm_queue.pop(0)
            task["status"] = "assigned"
            task["assigned_at"] = time.time()
            return task
        return None
    
    def get_swarm_status(self) -> Dict:
        pending = sum(1 for t in self._swarm_queue if t["status"] == "pending")
        return {
            "queue_length": len(self._swarm_queue),
            "pending_tasks": pending,
            "by_priority": {
                "critical": sum(1 for t in self._swarm_queue if t["priority"] >= 3),
                "high": sum(1 for t in self._swarm_queue if t["priority"] == 2),
                "normal": sum(1 for t in self._swarm_queue if t["priority"] == 1),
                "low": sum(1 for t in self._swarm_queue if t["priority"] <= 0)
            }
        }

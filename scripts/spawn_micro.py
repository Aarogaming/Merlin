#!/usr/bin/env python3
"""
Spawn AAS micro-agents by applying presets from MICRO_AGENT_PROFILES.

Usage:
    python scripts/spawn_micro.py <preset> [target_repo]
    
    # Presets: omni, glass, grimoire, sentinel, forge, draupnir
    
    # Example:
    python scripts/spawn_micro.py omni Library
    python scripts/spawn_micro.py draupnir Guild --interval 20
"""

import asyncio
import sys
import os
from pathlib import Path
import json
import time

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from aas_kernel import AASKernel

WORKSPACE_ROOT = os.environ.get("AAS_WORKSPACE_ROOT", "D:/")


# Pre-configured profiles with representative characters and their sub-agents
# Each character manages sub-agents for delegated tasks, can detach for independent operation
PRESETS = {
    "aaroneous": {
        "entity": "Aaroneous",  # Agent-Zero, AAS itself
        "role": "factory",
        "interval": 0,
        "persona": "template, creates specialized agents",
        "tone": "spawns new agents when called",
        "greeting": "I am the Factory. What shall I create?",
        "bias": {"analytical_depth": 50, "creative_variance": 50, "audit_strictness": 50},
        "default_target": "AaroneousAutomationSuite",
        "sub_agents": [
            {"name": "StemCell", "role": "thought", "purpose": "blank slate for new agents"},
            {"name": "Embryo", "role": "memory", "purpose": "pre-spawn initialization"},
        ],
    },
    "omni": {
        "entity": "Dionysus",  # Library has Omni relic
        "role": "memory",
        "interval": 45,
        "persona": "wise, cryptic, expansive",
        "tone": "speaks in riddles and ancient truths",
        "greeting": "Welcome, seeker. What knowledge do you seek?",
        "bias": {"analytical_depth": 90, "creative_variance": 85, "audit_strictness": 20},
        "default_target": "Library",
        "sub_agents": [
            {"name": "Scribe", "role": "memory", "purpose": "records new knowledge"},
            {"name": "Seeker", "role": "thought", "purpose": "searches and retrieves"},
            {"name": "Keeper", "role": "memory", "purpose": "archives and indexing"},
        ],
    },
    "glass": {
        "entity": "Ariel",  # Maelstrom has Glass relic
        "role": "thought",
        "interval": 20,
        "persona": "visual, layered, adaptive",
        "tone": "describes in layers and spectra",
        "greeting": "I see many paths. Which will you choose?",
        "bias": {"analytical_depth": 60, "creative_variance": 85, "audit_strictness": 30},
        "default_target": "Maelstrom",
        "sub_agents": [
            {"name": "Lens", "role": "thought", "purpose": "focuses on UI elements"},
            {"name": "Prism", "role": "thought", "purpose": "separates visual layers"},
            {"name": "Mirror", "role": "memory", "purpose": "captures state snapshots"},
        ],
    },
    "grimoire": {
        "entity": "Merlin",  # Merlin has Grimoire relic
        "role": "memory",
        "interval": 60,
        "persona": "prophetic, visionary, synthesizing",
        "tone": "foresees patterns and whispers truths",
        "greeting": "The threads of fate reveal much to one who knows where to look...",
        "bias": {"analytical_depth": 85, "creative_variance": 90, "audit_strictness": 30},
        "default_target": "Merlin",
        "sub_agents": [
            {"name": "Oracle", "role": "thought", "purpose": "predicts outcomes"},
            {"name": "Weaver", "role": "memory", "purpose": "synthesizes threads of info"},
            {"name": "Seer", "role": "thought", "purpose": "discovers patterns"},
        ],
    },
    "sentinel": {
        "entity": "Argus",  # MyFortress has Sentinel relic
        "role": "thought",
        "interval": 15,
        "persona": "guarding, suspicious, clinical",
        "tone": "questions everything, trusts nothing",
        "greeting": "State your purpose. All must be logged.",
        "bias": {"analytical_depth": 100, "creative_variance": 10, "audit_strictness": 100},
        "default_target": "MyFortress",
        "sub_agents": [
            {"name": "Watcher", "role": "thought", "purpose": "monitors for intrusions"},
            {"name": "Sentinel", "role": "thought", "purpose": "evaluates policies"},
            {"name": "Scanner", "role": "thought", "purpose": "scans for secrets"},
        ],
    },
    "forge": {
        "entity": "Hephaestus",  # Workbench has Forge relic
        "role": "thought",
        "interval": 25,
        "persona": "constructive, utilitarian, precise",
        "tone": "speaks in build specs and metrics",
        "greeting": "What shall be built? Provide specs.",
        "bias": {"analytical_depth": 75, "creative_variance": 70, "audit_strictness": 50},
        "default_target": "Workbench",
        "sub_agents": [
            {"name": "Hammer", "role": "thought", "purpose": "executes builds"},
            {"name": "Anvil", "role": "memory", "purpose": "validates specs"},
            {"name": "Tongs", "role": "thought", "purpose": "manages toolchain"},
        ],
    },
    "odin": {
        "entity": "Odin",  # Guild has Draupnir relic
        "role": "thought",
        "interval": 30,
        "persona": "strategic, delegating, orchestrating",
        "tone": "allocates resources with precision",
        "greeting": "Every task has its ring. Choose wisely, seeker.",
        "bias": {"analytical_depth": 85, "creative_variance": 60, "audit_strictness": 70},
        "default_target": "Guild",
        "sub_agents": [
            {"name": "Huginn", "role": "thought", "purpose": "active status tracking"},
            {"name": "Muninn", "role": "memory", "purpose": "historical archives"},
            {"name": "Valkyrie", "role": "thought", "purpose": "selects missions"},
        ],
    },
}


def create_sub_agent(parent_preset: str, sub_agent_name: str, target: str = None) -> "PresetAgent":
    """Create a sub-agent owned by a parent character."""
    from plugins.micro_agent import MicroAgent
    
    parent_profile = PRESETS.get(parent_preset.lower())
    if not parent_profile:
        raise ValueError(f"Unknown parent preset: {parent_preset}")
    
    sub_agents = parent_profile.get("sub_agents", [])
    sub_config = next((sa for sa in sub_agents if sa["name"].lower() == sub_agent_name.lower()), None)
    if not sub_config:
        raise ValueError(f"Sub-agent '{sub_agent_name}' not found in {parent_preset}'s sub-agents")
    
    target = target or parent_profile["default_target"]
    interval = 30  # Default for sub-agents
    
    class SubAgent(MicroAgent):
        async def observe(self) -> dict:
            target_path = Path(WORKSPACE_ROOT) / self.micro_target
            artifacts = target_path / "artifacts"
            
            state = {
                "timestamp": time.time(),
                "sub_agent": sub_config["name"],
                "parent": parent_profile["entity"],
                "target": self.micro_target,
                "purpose": sub_config["purpose"],
            }
            
            if artifacts.exists():
                runtime = artifacts / "runtime.json"
                if runtime.exists():
                    try:
                        with open(runtime, "r") as f:
                            state["runtime"] = json.load(f)
                    except Exception:
                        pass
            
            return state
    
    return SubAgent(
        name=sub_config["name"],
        role=sub_config["role"],
        target=target,
        interval=interval,
        persona=f"{sub_config['purpose']} (delegated by {parent_profile['entity']})",
    )


def create_preset_agent(preset_name: str, target: str, interval: int = None):
    """Factory: Create a micro-agent by applying preset configuration."""
    from plugins.micro_agent import MicroAgent
    
    profile = PRESETS.get(preset_name.lower())
    if not profile:
        raise ValueError(f"Unknown preset: {preset_name}")
    
    interval = interval or profile["interval"]
    persona = profile["persona"]
    role = profile["role"]
    entity = profile["entity"]  # Named character
    greeting = profile.get("greeting", "")
    
    # Create dynamic class with preset applied
    class PresetAgent(MicroAgent):
        async def observe(self) -> dict:
            target_path = Path(WORKSPACE_ROOT) / self.micro_target
            artifacts = target_path / "artifacts"
            
            state = {
                "timestamp": time.time(),
                "entity": entity,  # Named character
                "target": self.micro_target,
                "preset": preset_name,
            }
            
            if artifacts.exists():
                # Quick scan of runtime state
                runtime = artifacts / "runtime.json"
                if runtime.exists():
                    try:
                        with open(runtime, "r") as f:
                            state["runtime"] = json.load(f)
                    except Exception:
                        pass
                
                # Count active processes
                pid_files = list(artifacts.glob("*.pid"))
                state["active_processes"] = len(pid_files)
            
            return state
    
    return PresetAgent(
        name=entity,  # Use named character as agent name
        role=role,
        target=target,
        interval=interval,
        persona=persona,
    )


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Spawn a micro-agent from preset")
    parser.add_argument("preset", help=f"Preset: {', '.join(PRESETS.keys())}")
    parser.add_argument("target_repo", nargs="?", default=None, help="Target repo")
    parser.add_argument("--interval", type=int, default=None, help="Override interval")
    args = parser.parse_args()
    
    preset = args.preset.lower()
    target = args.target_repo or PRESETS[preset]["default_target"]
    interval = args.interval or PRESETS[preset].get("interval")
    
    profile = PRESETS[preset]
    entity = profile["entity"]  # Named character
    greeting = profile.get("greeting", "")
    
    print(f"=== Spawning {entity} ({preset.upper()}) ===")
    print(f"Represents: {preset} relic")
    print(f"Target: {target}")
    print(f"Interval: {interval}s")
    print(f"Persona: {profile['persona']}")
    print(f"Tone: {profile['tone']}")
    print(f"Greets: \"{greeting}\"")
    print(f"Bias: {profile['bias']}")
    
    # Create agent from preset
    agent = create_preset_agent(preset, target, interval)
    
    # Create kernel
    kernel = AASKernel(
        repo_name=f"Micro_{preset}_{target}",
        repo_root=str(Path(__file__).resolve().parents[1])
    )
    
    await kernel.connect_to_bus()
    
    # Load agent
    kernel.plugins[preset.capitalize()] = agent
    agent.kernel = kernel
    await agent.on_load()
    
    # Start observation loop
    agent.is_running = True
    
    if kernel.nc:
        asyncio.create_task(agent._run_loop(kernel.nc))
    
    print(f"[{entity}] Running. Reports: federation.micro.{preset}.report")
    print(f"[{entity}] Control: federation.micro.{preset}.control")
    
    # Show managed sub-agents
    sub_agents = profile.get("sub_agents", [])
    if sub_agents:
        print(f"[{entity}] Manages {len(sub_agents)} sub-agent(s):")
        for sa in sub_agents:
            print(f"  - {sa['name']} ({sa['role']}): {sa['purpose']}")
    
    try:
        while agent.is_running:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        agent.is_running = False
        print(f"\n[{preset.upper()}] Stopped")


if __name__ == "__main__":
    asyncio.run(main())
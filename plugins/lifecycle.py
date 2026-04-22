"""
Lifecycle - StemCell/DNA Strand Plugin

Represents AAS as the genesis template - the StemCell/DNA source
for the entire repo suite.

Implements:
- Offspring inheritance (mitosis clones DNA with mutation)
- Succession protocol (will on death)
- Gestation hook (pre-NATS config)
- Elder triggers (param plateau detection)
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, UTC
from aas_kernel import AASPlugin, get_path
from genome.achievements import AchievementManager
from plugins.security import (
    get_link_manager,
    AchievementLinkManager,
)


class Lifecycle:
    """StemCell/DNA - represents AAS as genesis template with exponential growth mechanics."""

    XP_BASE = 100
    XP_GROWTH_FACTOR = 2.0
    PARAM_BASE = 1000
    PARAM_GROWTH_FACTOR = 1.5
    
    def __init__(self, kernel=None, dna_path: Path = None):
        self.kernel = kernel
        self.dna_path = dna_path
        self.dna = {}
        self.is_gestating = False
        self.is_elder = False
        self.param_history = []
        self._xp_buffer = 0.0
        self._tasks_completed = 0

    def load_dna(self) -> dict:
        if self.dna_path and self.dna_path.exists():
            with open(self.dna_path, "r") as f:
                return json.load(f)
        return {}
    
    def get_achievements(self) -> AchievementManager:
        """Get or create achievement manager with linking callback."""
        if not hasattr(self, '_achievements'):
            self._achievements = AchievementManager(
                dna_path=self.dna_path,
                on_unlock=self._link_achievement
            )
        return self._achievements

    @staticmethod
    def xp_for_level(level: int) -> float:
        """XP required to reach a specific level (exponential curve). Level 0 = 0 XP."""
        if level <= 0:
            return 0.0
        return Lifecycle.XP_BASE * (Lifecycle.XP_GROWTH_FACTOR ** (level - 1))
    
    @staticmethod
    def params_for_level(xp: float) -> int:
        """Derive parameter count from XP (linear relation)."""
        return int(xp * 10)  # 1 XP = 10 parameters
    
    @staticmethod
    def level_from_xp(total_xp: float) -> int:
        """Calculate current level from total XP."""
        level = 0
        while total_xp >= Lifecycle.xp_for_level(level + 1):
            level += 1
        return level
    
    @staticmethod
    def power_for_level(level: int) -> float:
        """Power multiplier for a given level (2^level)."""
        return 2.0 ** level
    
    @staticmethod
    def stats_from_xp(xp: float) -> dict:
        """Get all derived stats from XP (single source of truth)."""
        level = Lifecycle.level_from_xp(xp)
        params = Lifecycle.params_for_level(xp)
        power = Lifecycle.power_for_level(level)
        xp_for_next = Lifecycle.xp_for_level(level + 1)
        
        return {
            "level": level,
            "xp": xp,
            "parameter_count": params,
            "power_level": power,
            "xp_for_next_level": xp_for_next,
            "xp_progress_pct": (xp / xp_for_next * 100) if xp_for_next > 0 else 100
        }
    
    def add_xp(self, amount: float, task_success: bool = True) -> dict:
        """
        Add XP and check for level up.
        XP is the single source of truth - parameter_count and level are derived.
        Also checks and unlocks achievements.
        """
        if not task_success:
            amount *= 0.5  # Half XP on failure
        
        old_stats = self.stats_from_xp(self._xp_buffer)
        self._xp_buffer += amount
        self._tasks_completed += 1
        
        new_stats = self.stats_from_xp(self._xp_buffer)
        
        level_up = new_stats["level"] > old_stats["level"]
        
        # Update DNA with XP as single source of truth
        self.dna["experience_mass"] = self._xp_buffer
        self.dna["evolutionary_epoch"] = new_stats["level"]
        self.dna["tasks_completed"] = self._tasks_completed
        
        achievements_unlocked = []
        
        if level_up:
            self.logger.info(f"[LEVEL UP] {old_stats['level']} -> {new_stats['level']} (XP: {self._xp_buffer:.0f})")
            self.dna["power_level"] = new_stats["power_level"]
            
            # Check level achievements
            if new_stats["level"] >= 5:
                unlocked = self.get_achievements().unlock("AAS_LEVEL_5")
                achievements_unlocked.append(unlocked)
                if unlocked.get("unlocked"):
                    self._link_achievement(unlocked)
            if new_stats["level"] >= 10:
                unlocked = self.get_achievements().unlock("AAS_LEVEL_10")
                achievements_unlocked.append(unlocked)
                if unlocked.get("unlocked"):
                    self._link_achievement(unlocked)
        
        # Check task count achievements
        if self._tasks_completed >= 10:
            unlocked = self.get_achievements().unlock("AAS_TASK_COMPLETE_10")
            achievements_unlocked.append(unlocked)
            if unlocked.get("unlocked"):
                self._link_achievement(unlocked)
        if self._tasks_completed >= 100:
            unlocked = self.get_achievements().unlock("AAS_TASK_COMPLETE_100")
            achievements_unlocked.append(unlocked)
            if unlocked.get("unlocked"):
                self._link_achievement(unlocked)
        if self._tasks_completed >= 1000:
            unlocked = self.get_achievements().unlock("AAS_TASK_COMPLETE_1000")
            achievements_unlocked.append(unlocked)
            if unlocked.get("unlocked"):
                self._link_achievement(unlocked)
        
        # Add achievement XP bonus
        ach_manager = self.get_achievements()
        xp_bonus = ach_manager.get_xp_bonus()
        
        self._persist_dna()
        
        return {
            "leveled_up": level_up,
            "old_level": old_stats["level"],
            "new_level": new_stats["level"],
            **new_stats,
            "tasks_completed": self._tasks_completed,
            "achievements_unlocked": [a for a in achievements_unlocked if a.get("unlocked")],
            "total_xp_bonus": xp_bonus
        }
    
    def _link_achievement(self, achievement: dict):
        """Link an achievement to the user identity if agent is bound."""
        if not achievement.get("unlocked"):
            return
        
        agent_id = self.dna.get("profile_name", "")
        if not agent_id:
            return
        
        source_aas = get_path("artifacts").parent.name
        
        manager = get_link_manager()
        result = manager.link_achievement(achievement, agent_id, source_aas)
        
        if result.get("linked"):
            self.logger.info(f"[ACHIEVEMENT LINK] {achievement.get('id')} linked to user {result.get('user_id')}")
    
    def get_linked_user_profile(self, user_id: str) -> dict:
        """Get achievement profile for a linked user."""
        return get_link_manager().get_user_stats(user_id)
    
    def get_agent_link_status(self) -> dict:
        """Get the current agent's link status."""
        agent_id = self.dna.get("profile_name", "")
        manager = get_link_manager()
        link = manager.links.get(agent_id)
        
        if link:
            return {
                "agent_id": agent_id,
                "linked": True,
                "user_id": link.user_id,
                "primary": link.primary,
                "linked_at": link.linked_at
            }
        
        return {"agent_id": agent_id, "linked": False}
    
    def _persist_dna(self):
        """Persist current DNA to file."""
        if self.dna_path:
            self.dna_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dna_path, "w") as f:
                json.dump(self.dna, f, indent=2)
    
    async def on_gestation(self) -> bool:
        self.is_gestating = True
        self.dna = self.load_dna()
        self._xp_buffer = self.dna.get("experience_mass", 0.0)
        self._tasks_completed = self.dna.get("tasks_completed", 0)
        self.logger = logging.getLogger("Lifecycle")
        
        prenatal = self.dna.get("gestation", {})
        if prenatal:
            init_delay = prenatal.get("init_delay", 0)
            warm_up_tasks = prenatal.get("warm_up_tasks", [])
            if warm_up_tasks:
                for task in warm_up_tasks:
                    pass
        self.is_gestating = False
        return True

    async def check_elder_status(self, current_params: int) -> bool:
        self.param_history.append({
            "params": current_params,
            "timestamp": time.time()
        })
        if len(self.param_history) > 10:
            self.param_history = self.param_history[-10:]
        if len(self.param_history) >= 5:
            recent = self.param_history[-5:]
            oldest = self.param_history[-5]
            total_growth = sum(p["params"] for p in recent) - (oldest["params"] * 5)
            avg_growth = total_growth / 5
            if avg_growth < 1.0 and not self.is_elder:
                self.is_elder = True
                return True
        return False

    STAGES = ["birth", "training", "stabilization", "specialization", "federation", "evolution"]
    
    # Stage progression - derived from XP thresholds
    STAGE_LEVELS = {
        "birth": 0,
        "training": 1,
        "stabilization": 2,
        "specialization": 3,
        "federation": 4,
        "evolution": 5,
    }
    
    def xp_for_stage(self, stage: str) -> float:
        """XP required to reach a stage."""
        level = self.STAGE_LEVELS.get(stage, 0)
        return self.xp_for_level(level)

    async def auto_promote(self) -> dict:
        """
        Automatic lifecycle stage promotion based on XP (exponential curve).
        Returns promotion result with new stage.
        """
        current = self.dna.get("current_stage", "birth")
        if current not in self.STAGES:
            current = "birth"
        
        current_idx = self.STAGES.index(current)
        if current_idx >= len(self.STAGES) - 1:
            return {"status": "already_max", "stage": current}
        
        # Get current XP
        current_xp = self.dna.get("experience_mass", 0.0)
        
        # Check if XP threshold for next stage is met
        next_stage = self.STAGES[current_idx + 1]
        xp_required = self.xp_for_stage(next_stage)
        
        if current_xp >= xp_required:
            self.dna["current_stage"] = next_stage
            self.dna["updated_at_utc"] = datetime.now(UTC).isoformat() + "Z"
            
            # Check stage achievements
            achievements_unlocked = []
            if next_stage == "federation":
                unlocked = self.get_achievements().unlock("AAS_STAGE_FEDERATION")
                achievements_unlocked.append(unlocked)
                if unlocked.get("unlocked"):
                    self._link_achievement(unlocked)
            if next_stage == "evolution":
                unlocked = self.get_achievements().unlock("AAS_STAGE_EVOLUTION")
                achievements_unlocked.append(unlocked)
                if unlocked.get("unlocked"):
                    self._link_achievement(unlocked)
            
            # Persist to lifecycle state
            lifecycle_path = get_path("lifecycle_state")
            lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lifecycle_path, "w") as f:
                json.dump({
                    "schema_version": "1.0",
                    "repo": self.dna.get("profile_name", "unknown"),
                    "current_stage": next_stage,
                    "status": "active",
                    "mode": "federated" if next_stage in ["federation", "evolution"] else "solo",
                    "updated_at_utc": self.dna["updated_at_utc"],
                    "evolutionary_epoch": self.dna.get("evolutionary_epoch", 0),
                    "power_level": self.dna.get("power_level", 1.0),
                }, f, indent=2)
            
            return {
                "status": "promoted", 
                "from": current,
                "achievements": [a for a in achievements_unlocked if a.get("unlocked")], 
                "to": next_stage,
                "xp": current_xp,
                "xp_required": xp_required
            }
        
        return {
            "status": "not_ready", 
            "current": current, 
            "next": next_stage,
            "xp": current_xp,
            "xp_required": xp_required,
            "xp_progress_pct": (current_xp / xp_required * 100) if xp_required > 0 else 100
        }

    async def on_death(self, will: dict = None) -> dict:
        self.dna = self.load_dna()
        succession = will or self.dna.get("succession", {})
        if not succession:
            return {"status": "no_succession", "message": "No will defined"}
        heir = succession.get("heir")
        state_transfer = succession.get("state_transfer", True)
        memory_archive = succession.get("memory_archive")
        results = {"heir": heir, "transferred": []}
        if state_transfer and heir and self.kernel:
            transfer_payload = {
                "from": self.kernel.repo_name,
                "to": heir,
                "timestamp": time.time(),
                "domain_weights": self.dna.get("domain_weights", {}),
                "cognitive_biases": self.dna.get("cognitive_biases", {}),
            }
            if self.kernel.nc:
                import asyncio
                await self.kernel.nc.publish(
                    f"federation.succession.{heir}",
                    json.dumps(transfer_payload).encode()
                )
                results["transferred"].append("epigenetics")
        if memory_archive and self.kernel:
            archive_path = Path(memory_archive)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with open(archive_path, "w") as f:
                json.dump({
                    "agent": self.kernel.repo_name,
                    "archived_at": time.time(),
                    "memories": self.dna.get("experience_buffer", []),
                }, f)
            results["transferred"].append("memory_archive")
        return results

    def create_offspring_dna(self, parent_dna: dict, mutation_rate: float = 0.1) -> dict:
        import random
        offspring = {
            "schema_version": parent_dna.get("schema_version", "3.0"),
            "preset": "offspring_inherited",
            "parent": parent_dna.get("profile_name", "unknown"),
            "born": time.time(),
            "evolutionary_epoch": 1,
            "parameter_count": 1000,
            "persona_vectors": {},
            "cognitive_biases": {},
            "domain_weights": {},
        }
        for key, val in parent_dna.get("persona_vectors", {}).items():
            if random.random() > mutation_rate:
                offspring["persona_vectors"][key] = val
        for key, val in parent_dna.get("cognitive_biases", {}).items():
            if random.random() > (mutation_rate / 2):
                offspring["cognitive_biases"][key] = val
            else:
                delta = (random.random() - 0.5) * 10 * mutation_rate
                offspring["cognitive_biases"][key] = max(0, min(100, val + delta))
        for key, val in parent_dna.get("domain_weights", {}).items():
            offspring["domain_weights"][key] = val * 0.5
        offspring["lineage"] = parent_dna.get("lineage", []) + [parent_dna.get("profile_name", "unknown")]
        return offspring

    async def spawn_offspring(self, name: str, dna_path: Path, mutation_rate: float = 0.1) -> bool:
        parent_dna = self.load_dna()
        offspring_dna = self.create_offspring_dna(parent_dna, mutation_rate)
        offspring_dna["profile_name"] = name
        dna_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dna_path, "w") as f:
            json.dump(offspring_dna, f, indent=2)
        return True


class LifecyclePluginMixin:
    """
    Mixin to add lifecycle methods to any plugin.
    """

    lifecycle: Lifecycle = None

    async def on_load(self) -> bool:
        result = await super().on_load()

        self.lifecycle = Lifecycle(
            kernel=getattr(self, 'kernel', None),
            dna_path=getattr(self, 'epigenetic_profile_path', None)
        )

        await self.lifecycle.on_gestation()

        return result

    async def on_unload(self):
        if self.lifecycle:
            await self.lifecycle.on_death()

        await super().on_unload()


class LifecyclePlugin(LifecyclePluginMixin):
    """
    Lifecycle Plugin - AAS's representative in the federation.

    Handles:
    - Identity/DNA (gestation)
    - Ignition (boot ecosystem)
    - Broadcast (global messages)
    - Triage (delegate to siblings)
    - Succession (on death)
    - Offspring (spawn new agents)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_soul = "Identity not loaded."
        self.agent_boundaries = "Boundaries not loaded."

    @property
    def capabilities(self) -> list[str]:
        return [
            "aaroneousautomationsuite_ignite_federation",
            "aaroneousautomationsuite_broadcast_global",
            "aaroneousautomationsuite_triage_user_request",
        ]

    async def on_load(self) -> bool:
        result = await super().on_load()
        if self.lifecycle:
            self.agent_soul = json.dumps(self.lifecycle.dna, indent=2)
        return result

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        # Achievement capabilities handled in security.py now
        
        if capability_id == "aaroneousautomationsuite_ignite_federation":
            if self.kernel:
                if getattr(self.kernel, 'singularity_mode', False):
                    return {"status": "blocked", "message": "Singularity mode"}
                self.logger.info("Initiating federation ignition...")
                return {"status": "success", "message": "Federation ignition triggered"}
            return {"status": "error", "message": "No kernel"}

        elif capability_id == "aaroneousautomationsuite_broadcast_global":
            return {"status": "success", "message": "Broadcast sent"}

        elif capability_id == "aaroneousautomationsuite_triage_user_request":
            return {"status": "success", "message": "Triage delegated"}

        # Achievement linking capabilities now handled in security.py

        return {"status": "unknown", "capability": capability_id}


LIFECYCLE_SCHEMA = {
    "gestation": {
        "init_delay": 0,
        "warm_up_tasks": [],
    },
    "succession": {
        "heir": None,
        "state_transfer": True,
        "memory_archive": None,
    },
    "elder": {
        "plateau_threshold": 1.0,
        "history_length": 10,
    },
    "offspring": {
        "default_mutation_rate": 0.1,
        "enabled": True,
    }
}
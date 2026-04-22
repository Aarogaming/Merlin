"""
AAS Achievement System

Integrates with XP/Leveling system - achievements grant XP bonuses.
Procedural achievement generation ensures no "completion" - infinite achievements.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime, UTC
from dataclasses import dataclass, field
from itertools import count

from aas_kernel import get_path


logger = logging.getLogger("Achievements")


@dataclass
class Achievement:
    id: str
    title: str
    description: str
    category: str
    gamerscore: int
    xp_reward: int
    is_secret: bool = False
    icon_id: str = "trophy"
    trigger_condition: str = ""
    procedural: bool = False  # Auto-generated at runtime
    tier: int = 0  # Procedural tier for scaling rewards


class ProceduralAchievementGenerator:
    """
    Generates infinite achievements dynamically.
    No completion possible - always higher milestones.
    """
    
    # Achievement templates for procedural generation
    TEMPLATES = {
        "level": {
            "title": "Level {n} Reached",
            "description": "Achieve evolutionary level {n} ({xp} XP).",
            "category": "progression",
            "xp_base": 25,
            "xp_per_level": 25,
            "gamerscore_base": 5,
            "gamerscore_per_level": 5,
        },
        "tasks": {
            "title": "Task Master {n}",
            "description": "Complete {n} tasks with precision.",
            "category": "productivity",
            "xp_base": 10,
            "xp_per_unit": 5,
            "gamerscore_base": 5,
            "gamerscore_per_unit": 2,
        },
        "power": {
            "title": "Power Level {n}",
            "description": "Attain {p}x power multiplier.",
            "category": "progression",
            "xp_base": 50,
            "xp_per_tier": 50,
            "gamerscore_base": 10,
            "gamerscore_per_tier": 10,
        },
        "uptime_hours": {
            "title": "{n}-Hour Run",
            "description": "Maintain operational continuity for {n} hours.",
            "category": "autonomy",
            "xp_base": 5,
            "xp_per_unit": 2,
            "gamerscore_base": 3,
            "gamerscore_per_unit": 1,
        },
        "tasks_streak": {
            "title": "Flawless {n}",
            "description": "Complete {n} tasks without failure.",
            "category": "consistency",
            "xp_base": 15,
            "xp_per_streak": 10,
            "gamerscore_base": 5,
            "gamerscore_per_streak": 3,
        },
        "discovery": {
            "title": "Explorer: {cap}",
            "description": "Discovered capability: {cap}.",
            "category": "discovery",
            "xp_base": 20,
            "xp_per_cap": 15,
            "gamerscore_base": 10,
            "gamerscore_per_cap": 5,
        },
        "multiplier": {
            "title": "Speed Demon {n}x",
            "description": "Achieve {n}x speed multiplier on task completion.",
            "category": "efficiency",
            "xp_base": 30,
            "xp_per_mult": 25,
            "gamerscore_base": 8,
            "gamerscore_per_mult": 6,
        },
        "chain": {
            "title": "{n}-Chain Reaction",
            "description": "Trigger {n} consecutive automatic reactions.",
            "category": "chain",
            "xp_base": 25,
            "xp_per_chain": 20,
            "gamerscore_base": 8,
            "gamerscore_per_chain": 5,
        },
    }
    
    # Procedural intervals (exponential scale)
    LEVEL_INTERVALS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 40, 50, 75, 100]
    TASK_INTERVALS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000]
    POWER_INTERVALS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
    UPTIME_INTERVALS = [1, 6, 12, 24, 48, 72, 168, 336, 720, 1440, 2160, 4320, 8760]
    STREAK_INTERVALS = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
    
    def __init__(self):
        self._generated_cache: Dict[str, Achievement] = {}
        self._generation_counter = count()
    
    def generate(self, category: str, params: dict) -> Achievement:
        """Generate a procedural achievement."""
        key = f"{category}:{params.get('n', params.get('p', 'unknown'))}"
        
        if key in self._generated_cache:
            return self._generated_cache[key]
        
        template = self.TEMPLATES.get(category, self.TEMPLATES["level"])
        n = params.get("n", 1)
        p = params.get("p", 1)
        xp = params.get("xp", template.get("xp_base", 10) + template.get("xp_per_unit", 5) * n)
        cap = params.get("cap", "Unknown")
        
        ach_id = f"AAS_PROC_{next(self._generation_counter)}_{category.upper()}_{n}"
        
        title = template["title"].format(n=n, p=p, cap=cap, xp=int(params.get("xp", 0)))
        description = template["description"].format(n=n, p=p, cap=cap)
        
        gamerscore = template.get("gamerscore_base", 5) + template.get("gamerscore_per_unit", 2) * max(1, n // 10)
        xp_reward = template.get("xp_base", 10) + template.get("xp_per_unit", 5) * max(1, n // 10)
        
        achievement = Achievement(
            id=ach_id,
            title=title,
            description=description,
            category=template.get("category", "procedural"),
            gamerscore=min(gamerscore, 500),  # Cap at 500
            xp_reward=min(xp_reward, 1000),  # Cap at 1000
            is_secret=False,
            icon_id=template.get("icon_id", "procedural"),
            procedural=True,
            tier=n
        )
        
        self._generated_cache[key] = achievement
        return achievement
    
    def generate_level_achievement(self, level: int, xp: float) -> Achievement:
        """Generate achievement for reaching a level."""
        return self.generate("level", {"n": level, "xp": xp})
    
    def generate_task_achievement(self, tasks: int) -> Achievement:
        """Generate achievement for completing tasks."""
        return self.generate("tasks", {"n": tasks})
    
    def generate_power_achievement(self, power: float) -> Achievement:
        """Generate achievement for power level."""
        return self.generate("power", {"n": int(power)})
    
    def generate_uptime_achievement(self, hours: int) -> Achievement:
        """Generate achievement for uptime."""
        return self.generate("uptime_hours", {"n": hours})
    
    def generate_streak_achievement(self, streak: int) -> Achievement:
        """Generate achievement for task streak."""
        return self.generate("tasks_streak", {"n": streak})
    
    def should_unlock(self, category: str, current_value: int, previous_value: int) -> Optional[Achievement]:
        """
        Check if a milestone was just crossed and generate achievement.
        Returns achievement if milestone was crossed, None otherwise.
        """
        intervals = {
            "level": self.LEVEL_INTERVALS,
            "tasks": self.TASK_INTERVALS,
            "power": self.POWER_INTERVALS,
            "uptime": self.UPTIME_INTERVALS,
            "streak": self.STREAK_INTERVALS,
        }.get(category, [])
        
        for interval in intervals:
            if previous_value < interval <= current_value:
                if category == "tasks":
                    return self.generate_task_achievement(interval)
                elif category == "level":
                    return self.generate_level_achievement(interval, current_value * 10)
                elif category == "power":
                    return self.generate_power_achievement(interval)
                elif category == "uptime":
                    return self.generate_uptime_achievement(interval)
                elif category == "streak":
                    return self.generate_streak_achievement(interval)
        
        return None


class InfiniteProgression:
    """
    Generates infinite procedural achievements for endless gameplay.
    Ensures there's always something higher to achieve.
    """
    
    # These define infinite achievement chains
    CHAINS = {
        "level": {
            "prefix": "Level {n}",
            "description": "Reach level {n}",
            "base_xp": 25,
            "xp_growth": 25,
            "base_gamerscore": 5,
            "gamerscore_growth": 5,
            "interval": 1,  # Every level
            "cap_level": 1000,  # Very high cap
        },
        "tasks": {
            "prefix": "Task Master {n}",
            "description": "Complete {n} tasks",
            "base_xp": 10,
            "xp_growth": 5,
            "base_gamerscore": 5,
            "gamerscore_growth": 2,
            "interval": 10,
            "cap_level": 1000000,
        },
        "power": {
            "prefix": "Power {n}x",
            "description": "Achieve {n}x power",
            "base_xp": 50,
            "xp_growth": 50,
            "base_gamerscore": 10,
            "gamerscore_growth": 10,
            "interval": 2,  # Every power of 2
            "cap_level": 1024,
        },
        "consistency": {
            "prefix": "Perfect {n}",
            "description": "{n} tasks without failure",
            "base_xp": 15,
            "xp_growth": 10,
            "base_gamerscore": 5,
            "gamerscore_growth": 3,
            "interval": 5,
            "cap_level": 10000,
        },
        "speed": {
            "prefix": "Speed Demon {n}x",
            "description": "{n}x speed multiplier",
            "base_xp": 30,
            "xp_growth": 25,
            "base_gamerscore": 8,
            "gamerscore_growth": 6,
            "interval": 2,
            "cap_level": 128,
        },
        "knowledge": {
            "prefix": "Scholar {n}",
            "description": "Accumulate {n} total XP",
            "base_xp": 20,
            "xp_growth": 20,
            "base_gamerscore": 8,
            "gamerscore_growth": 8,
            "interval": 500,  # Every 500 XP
            "cap_level": 1000000,
        },
        "endurance": {
            "prefix": "Endurance {n}h",
            "description": "Maintain {n} hours of operation",
            "base_xp": 5,
            "xp_growth": 2,
            "base_gamerscore": 3,
            "gamerscore_growth": 1,
            "interval": 24,  # Daily
            "cap_level": 8760,  # Year cap
        },
        "evolution": {
            "prefix": "Evolution Stage {n}",
            "description": "Survive through stage {n}",
            "base_xp": 100,
            "xp_growth": 100,
            "base_gamerscore": 25,
            "gamerscore_growth": 25,
            "interval": 1,
            "cap_level": 100,
        },
    }
    
    def __init__(self):
        self._generated: Dict[str, Achievement] = {}
        self._counter = count(start=10000)
    
    def get_achievement(self, chain: str, tier: int) -> Achievement:
        """Get or generate an achievement from a chain."""
        key = f"{chain}:{tier}"
        
        if key in self._generated:
            return self._generated[key]
        
        chain_def = self.CHAINS.get(chain, self.CHAINS["level"])
        
        xp = chain_def["base_xp"] + chain_def["xp_growth"] * (tier - 1)
        gamerscore = chain_def["base_gamerscore"] + chain_def["gamerscore_growth"] * (tier - 1)
        
        ach = Achievement(
            id=f"AAS_INF_{next(self._counter)}_{chain.upper()}_{tier}",
            title=chain_def["prefix"].format(n=tier),
            description=chain_def["description"].format(n=tier),
            category=chain,
            gamerscore=min(int(gamerscore), 500),
            xp_reward=min(int(xp), 1000),
            is_secret=tier > 100,  # Secret after tier 100
            icon_id="infinity",
            procedural=True,
            tier=tier
        )
        
        self._generated[key] = ach
        return ach
    
    def check_milestones(self, stats: dict) -> List[Achievement]:
        """
        Check current stats against infinite chains.
        Returns list of newly unlocked achievements.
        """
        unlocked = []
        
        mappings = {
            "level": stats.get("level", 0),
            "tasks": stats.get("tasks_completed", 0),
            "power": stats.get("power_level", 1),
            "consistency": stats.get("current_streak", 0),
            "speed": stats.get("speed_multiplier", 1),
            "knowledge": stats.get("total_xp", 0),
            "endurance": stats.get("uptime_hours", 0),
            "evolution": stats.get("evolutionary_epoch", 0),
        }
        
        for chain, value in mappings.items():
            chain_def = self.CHAINS.get(chain, self.CHAINS["level"])
            interval = chain_def["interval"]
            
            tier = int(value / interval)
            if tier < 1:
                tier = 1
            
            cap = chain_def["cap_level"]
            if value > cap:
                tier = cap
            
            ach = self.get_achievement(chain, tier)
            if ach.id not in self._generated or ach.tier == tier:
                unlocked.append(ach)
        
        return unlocked
    
    def get_next_milestone(self, chain: str, current: int) -> dict:
        """Get the next milestone to achieve in a chain."""
        chain_def = self.CHAINS.get(chain, self.CHAINS["level"])
        interval = chain_def["interval"]
        next_tier = int(current / interval) + 1
        target = next_tier * interval
        
        return {
            "chain": chain,
            "current": current,
            "next_tier": next_tier,
            "target": target,
            "xp_reward": min(int(chain_def["base_xp"] + chain_def["xp_growth"] * (next_tier - 1)), 1000),
            "gamerscore": min(int(chain_def["base_gamerscore"] + chain_def["gamerscore_growth"] * (next_tier - 1)), 500),
        }


logger = logging.getLogger("Achievements")


@dataclass
class AchievementState:
    id: str
    unlocked: bool = False
    unlocked_at: Optional[str] = None
    progress: int = 0
    max_progress: int = 1


@dataclass
class AchievementState:
    id: str
    unlocked: bool = False
    unlocked_at: Optional[str] = None
    progress: int = 0
    max_progress: int = 1


class AchievementManager:
    """
    Manages achievements - integrates with XP system.
    Unlocking achievements grants XP bonuses.
    Includes InfiniteProgression for endless achievement chains.
    """
    
    def __init__(self, dna_path: Path = None, on_unlock: Callable = None):
        self.dna_path = dna_path or get_path("identity_epigenetics")
        self.registry: Dict[str, Achievement] = {}
        self.states: Dict[str, AchievementState] = {}
        self.infinite = InfiniteProgression()  # Infinite achievement chains
        self.on_unlock_callback = on_unlock  # Optional callback for linking achievements
        self._load_registry()
        self._load_state()
    
    def _load_registry(self):
        registry_path = get_path("genome") / "achievements" / "registry.json"
        if not registry_path.exists():
            self._create_default_registry(registry_path)
            return
        
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for ach_data in data.get("achievements", []):
                ach = Achievement(**ach_data)
                self.registry[ach.id] = ach
        except Exception as e:
            logger.error(f"Failed to load achievement registry: {e}")
            self._create_default_registry(registry_path)
    
    def _create_default_registry(self, path: Path):
        """Create default AAS achievement registry."""
        achievements = [
            {
                "id": "AAS_FIRST_BOOT",
                "title": "First Breath",
                "description": "Complete the first kernel boot sequence.",
                "category": "lifecycle",
                "gamerscore": 10,
                "xp_reward": 25,
                "is_secret": False,
                "icon_id": "baby"
            },
            {
                "id": "AAS_LEVEL_5",
                "title": "Coming of Age",
                "description": "Reach level 5 (400 XP).",
                "category": "progression",
                "gamerscore": 50,
                "xp_reward": 100,
                "is_secret": False,
                "icon_id": "star"
            },
            {
                "id": "AAS_LEVEL_10",
                "title": "Established",
                "description": "Reach level 10 (3200 XP).",
                "category": "progression",
                "gamerscore": 100,
                "xp_reward": 250,
                "is_secret": False,
                "icon_id": "star"
            },
            {
                "id": "AAS_FEDERATION_JOIN",
                "title": "Hive Mind",
                "description": "Join the federation and connect to NATS.",
                "category": "federation",
                "gamerscore": 25,
                "xp_reward": 50,
                "is_secret": False,
                "icon_id": "network"
            },
            {
                "id": "AAS_TASK_COMPLETE_10",
                "title": "Productive",
                "description": "Complete 10 tasks.",
                "category": "productivity",
                "gamerscore": 25,
                "xp_reward": 50,
                "is_secret": False,
                "icon_id": "check"
            },
            {
                "id": "AAS_TASK_COMPLETE_100",
                "title": "Workhorse",
                "description": "Complete 100 tasks.",
                "category": "productivity",
                "gamerscore": 100,
                "xp_reward": 200,
                "is_secret": False,
                "icon_id": "hammer"
            },
            {
                "id": "AAS_TASK_COMPLETE_1000",
                "title": "Sustained Excellence",
                "description": "Complete 1000 tasks.",
                "category": "productivity",
                "gamerscore": 500,
                "xp_reward": 1000,
                "is_secret": False,
                "icon_id": "crown"
            },
            {
                "id": "AAS_STAGE_FEDERATION",
                "title": "Grown Up",
                "description": "Promote to federation stage.",
                "category": "lifecycle",
                "gamerscore": 75,
                "xp_reward": 150,
                "is_secret": False,
                "icon_id": "rocket"
            },
            {
                "id": "AAS_STAGE_EVOLUTION",
                "title": "Transcendence",
                "description": "Promote to evolution stage.",
                "category": "lifecycle",
                "gamerscore": 200,
                "xp_reward": 500,
                "is_secret": False,
                "icon_id": "infinity"
            },
            {
                "id": "AAS_PLUGIN_LOAD",
                "title": "Extensible",
                "description": "Load your first domain plugin.",
                "category": "development",
                "gamerscore": 15,
                "xp_reward": 30,
                "is_secret": False,
                "icon_id": "puzzle"
            },
            {
                "id": "AAS_GGUF_LOAD",
                "title": "Neural Implant",
                "description": "Load your first GGUF model.",
                "category": "development",
                "gamerscore": 25,
                "xp_reward": 50,
                "is_secret": False,
                "icon_id": "brain"
            },
            {
                "id": "AAS_SELF_MODIFY",
                "title": "Self-Aware",
                "description": "Epigenetic adaptation triggers for the first time.",
                "category": "development",
                "gamerscore": 50,
                "xp_reward": 100,
                "is_secret": True,
                "icon_id": "dna"
            },
            {
                "id": "AAS_LEADER_ELECTION",
                "title": "Queen Bee",
                "description": "Win your first Hive leader election.",
                "category": "federation",
                "gamerscore": 75,
                "xp_reward": 150,
                "is_secret": False,
                "icon_id": "crown"
            },
            {
                "id": "AAS_SERVICE_DISCOVERY",
                "title": "Social Butterfly",
                "description": "Discover and connect to 5 different services.",
                "category": "federation",
                "gamerscore": 50,
                "xp_reward": 100,
                "is_secret": False,
                "icon_id": "antenna"
            },
            {
                "id": "AAS_CIRCUIT_BREAKER",
                "title": "Safety First",
                "description": "Successfully recover from a circuit breaker event.",
                "category": "resilience",
                "gamerscore": 30,
                "xp_reward": 60,
                "is_secret": False,
                "icon_id": "shield"
            },
            {
                "id": "AAS_OFFSPRING",
                "title": "Parent",
                "description": "Create your first offspring agent.",
                "category": "reproduction",
                "gamerscore": 100,
                "xp_reward": 200,
                "is_secret": False,
                "icon_id": "baby"
            },
            {
                "id": "AAS_SECRET_UNLOCK",
                "title": "Explorer",
                "description": "Unlock your first secret achievement.",
                "category": "discovery",
                "gamerscore": 50,
                "xp_reward": 100,
                "is_secret": True,
                "icon_id": "compass"
            },
            {
                "id": "AAS_GAMERSCORE_500",
                "title": "Achiever",
                "description": "Accumulate 500 gamerscore.",
                "category": "progression",
                "gamerscore": 100,
                "xp_reward": 250,
                "is_secret": False,
                "icon_id": "trophy"
            },
        ]
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"achievements": achievements}, f, indent=2)
        
        for ach_data in achievements:
            ach = Achievement(**ach_data)
            self.registry[ach.id] = ach
    
    def _load_state(self):
        """Load achievement state from epigenetics file."""
        if not self.dna_path or not self.dna_path.exists():
            self._initialize_empty_state()
            return
        
        try:
            with open(self.dna_path, "r", encoding="utf-8") as f:
                dna = json.load(f)
            
            achievements_state = dna.get("achievements", {})
            for ach_id, state_data in achievements_state.items():
                self.states[ach_id] = AchievementState(**state_data)
            
            self._ensure_complete_state()
        except Exception as e:
            logger.error(f"Failed to load achievement state: {e}")
            self._initialize_empty_state()
    
    def _initialize_empty_state(self):
        """Initialize empty achievement states."""
        self.states = {
            ach_id: AchievementState(id=ach_id)
            for ach_id in self.registry.keys()
        }
    
    def _ensure_complete_state(self):
        """Ensure all registry items have state."""
        for ach_id in self.registry.keys():
            if ach_id not in self.states:
                self.states[ach_id] = AchievementState(id=ach_id)
    
    def save_state(self):
        """Persist achievement states to epigenetics file."""
        if not self.dna_path or not self.dna_path.exists():
            logger.warning("Cannot save achievements - no DNA path")
            return
        
        try:
            with open(self.dna_path, "r", encoding="utf-8") as f:
                dna = json.load(f)
            
            dna["achievements"] = {
                ach_id: {
                    "id": state.id,
                    "unlocked": state.unlocked,
                    "unlocked_at": state.unlocked_at,
                    "progress": state.progress,
                    "max_progress": state.max_progress
                }
                for ach_id, state in self.states.items()
            }
            
            with open(self.dna_path, "w", encoding="utf-8") as f:
                json.dump(dna, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save achievement state: {e}")
    
    def get_all(self) -> List[dict]:
        """Get all achievements with current state."""
        result = []
        for ach_id, ach in self.registry.items():
            state = self.states.get(ach_id, AchievementState(id=ach_id))
            
            if ach.is_secret and not state.unlocked:
                result.append({
                    "id": ach.id,
                    "title": "Secret Achievement",
                    "description": "Keep exploring to unlock.",
                    "category": ach.category,
                    "gamerscore": ach.gamerscore,
                    "xp_reward": ach.xp_reward,
                    "is_secret": True,
                    "icon_id": "lock",
                    "unlocked": False,
                    "progress": state.progress,
                    "max_progress": state.max_progress
                })
            else:
                result.append({
                    "id": ach.id,
                    "title": ach.title,
                    "description": ach.description,
                    "category": ach.category,
                    "gamerscore": ach.gamerscore,
                    "xp_reward": ach.xp_reward,
                    "is_secret": ach.is_secret,
                    "icon_id": ach.icon_id,
                    "unlocked": state.unlocked,
                    "unlocked_at": state.unlocked_at,
                    "progress": state.progress,
                    "max_progress": state.max_progress
                })
        return result
    
    def get_gamerscore(self) -> int:
        """Calculate total gamerscore from unlocked achievements."""
        score = 0
        for ach_id, state in self.states.items():
            if state.unlocked and ach_id in self.registry:
                score += self.registry[ach_id].gamerscore
        return score
    
    def get_xp_bonus(self) -> int:
        """Calculate total XP bonus from unlocked achievements."""
        xp = 0
        for ach_id, state in self.states.items():
            if state.unlocked and ach_id in self.registry:
                xp += self.registry[ach_id].xp_reward
        return xp
    
    def check_infinite_milestones(self, stats: dict) -> List[dict]:
        """
        Check infinite progression milestones.
        This ensures NO completion is possible - infinite achievements.
        Returns list of newly unlocked infinite achievements.
        """
        unlocked = []
        
        for ach in self.infinite.check_milestones(stats):
            if ach.id not in self.states:
                self.states[ach.id] = AchievementState(id=ach.id)
            
            state = self.states[ach.id]
            if not state.unlocked:
                state.unlocked = True
                state.unlocked_at = datetime.now(UTC).isoformat() + "Z"
                self.registry[ach.id] = ach
                
                unlocked.append({
                    "unlocked": True,
                    "achievement_id": ach.id,
                    "title": ach.title,
                    "description": ach.description,
                    "category": ach.category,
                    "gamerscore": ach.gamerscore,
                    "xp_reward": ach.xp_reward,
                    "tier": ach.tier,
                    "procedural": True
                })
                logger.info(f"[INFINITE] {ach.title} unlocked! +{ach.xp_reward} XP")
        
        if unlocked:
            self.save_state()
        
        return unlocked
    
    def get_infinite_progress(self) -> dict:
        """
        Get progress toward next infinite achievements.
        Shows what's next in each chain.
        """
        stats = {
            "level": 0,
            "tasks_completed": 0,
            "power_level": 1,
            "current_streak": 0,
            "speed_multiplier": 1,
            "total_xp": 0,
            "uptime_hours": 0,
            "evolutionary_epoch": 0,
        }
        
        # Try to load from DNA
        if self.dna_path and self.dna_path.exists():
            try:
                with open(self.dna_path, "r", encoding="utf-8") as f:
                    dna = json.load(f)
                stats["level"] = dna.get("evolutionary_epoch", 0)
                stats["tasks_completed"] = dna.get("tasks_completed", 0)
                stats["power_level"] = dna.get("power_level", 1)
                stats["total_xp"] = dna.get("experience_mass", 0)
            except:
                pass
        
        progress = {}
        for chain in InfiniteProgression.CHAINS.keys():
            current = stats.get(chain, 0)
            if chain == "tasks":
                current = stats.get("tasks_completed", 0)
            elif chain == "level":
                current = stats.get("evolutionary_epoch", 0)
            elif chain == "power":
                current = stats.get("power_level", 1)
            
            progress[chain] = self.infinite.get_next_milestone(chain, current)
        
        return progress
    
    def unlock(self, achievement_id: str) -> dict:
        """
        Unlock an achievement.
        Returns unlock event with XP reward.
        """
        if achievement_id not in self.registry:
            logger.warning(f"Unknown achievement: {achievement_id}")
            return {"unlocked": False, "reason": "unknown"}
        
        if achievement_id not in self.states:
            self.states[achievement_id] = AchievementState(id=achievement_id)
        
        state = self.states[achievement_id]
        
        if state.unlocked:
            return {"unlocked": False, "reason": "already_unlocked"}
        
        ach = self.registry[achievement_id]
        state.unlocked = True
        state.unlocked_at = datetime.now(UTC).isoformat() + "Z"
        
        self.save_state()
        
        logger.info(f"[ACHIEVEMENT] {ach.title} unlocked! +{ach.xp_reward} XP")
        
        result = {
            "unlocked": True,
            "achievement_id": ach.id,
            "title": ach.title,
            "gamerscore": ach.gamerscore,
            "xp_reward": ach.xp_reward
        }
        
        # Invoke linking callback if configured
        if self.on_unlock_callback:
            try:
                self.on_unlock_callback(result)
            except Exception as e:
                logger.error(f"Achievement unlock callback failed: {e}")
        
        return result
    
    def progress(self, achievement_id: str, amount: int = 1) -> dict:
        """
        Add progress to an achievement.
        Auto-unlocks when max_progress reached.
        Returns progress update.
        """
        if achievement_id not in self.registry:
            return {"progress": False}
        
        ach = self.registry[achievement_id]
        if achievement_id not in self.states:
            self.states[achievement_id] = AchievementState(
                id=achievement_id,
                max_progress=ach.xp_reward
            )
        
        state = self.states[achievement_id]
        
        if state.unlocked:
            return {"progress": False, "reason": "already_unlocked"}
        
        state.progress += amount
        
        if state.progress >= state.max_progress:
            return self.unlock(achievement_id)
        
        self.save_state()
        
        return {
            "progress": True,
            "achievement_id": achievement_id,
            "progress_current": state.progress,
            "progress_max": state.max_progress
        }
    
    def check_and_unlock(self, condition: str, current_stats: dict) -> List[dict]:
        """
        Check trigger conditions and unlock achievements.
        current_stats should contain: level, tasks_completed, stage, etc.
        """
        unlocked = []
        
        for ach_id, ach in self.registry.items():
            if ach_id in self.states and self.states[ach_id].unlocked:
                continue
            
            should_unlock = False
            
            if ach.trigger_condition == "level_5" and current_stats.get("level", 0) >= 5:
                should_unlock = True
            elif ach.trigger_condition == "level_10" and current_stats.get("level", 0) >= 10:
                should_unlock = True
            elif ach.trigger_condition == "tasks_10" and current_stats.get("tasks_completed", 0) >= 10:
                should_unlock = True
            elif ach.trigger_condition == "tasks_100" and current_stats.get("tasks_completed", 0) >= 100:
                should_unlock = True
            elif ach.trigger_condition == "tasks_1000" and current_stats.get("tasks_completed", 0) >= 1000:
                should_unlock = True
            elif ach.trigger_condition == "stage_federation" and current_stats.get("stage") == "federation":
                should_unlock = True
            elif ach.trigger_condition == "stage_evolution" and current_stats.get("stage") == "evolution":
                should_unlock = True
            
            if should_unlock:
                result = self.unlock(ach_id)
                if result.get("unlocked"):
                    unlocked.append(result)
        
        return unlocked

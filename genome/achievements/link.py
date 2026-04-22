"""
Achievement Linking System

Links achievements to user identities (OAuth/GitAuth).
Users bind their AAS identity to external auth providers once.
All achievements become permanently linked to their user account.
"""

import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, UTC
from dataclasses import dataclass, field
from enum import Enum

from aas_kernel import get_path


logger = logging.getLogger("AchievementLink")


class AuthProvider(Enum):
    GITHUB = "github"
    GOOGLE = "google"
    GITLAB = "gitlab"
    EMAIL = "email"
    AAS_NATIVE = "aas_native"


@dataclass
class UserIdentity:
    """A user identity bound to one or more auth providers."""
    user_id: str
    display_name: str
    providers: Dict[str, str]  # provider -> provider_user_id
    created_at: str
    last_linked: str
    achievement_count: int = 0
    total_xp: int = 0
    total_gamerscore: int = 0


@dataclass
class LinkedAchievement:
    """An achievement linked to a user identity."""
    achievement_id: str
    user_id: str
    linked_at: str
    xp_earned: int
    gamerscore: int
    source_aas: str  # Which AAS instance earned it


@dataclass
class AchievementLink:
    """Links an AAS agent to a user identity."""
    agent_id: str  # AAS agent identifier
    user_id: str
    link_code: str  # One-time code to verify ownership
    linked_at: str
    primary: bool = False


class AchievementLinkManager:
    """
    Manages achievement-user linking.
    
    Flow:
    1. User authenticates via OAuth (GitHub, etc.)
    2. AAS agent generates a link code
    3. User provides link code to bind their identity
    4. All achievements become permanently linked to user
    
    Local storage for now, cloud sync planned.
    """
    
    def __init__(self, data_path: Path = None):
        self.data_path = data_path or get_path("artifacts") / "achievement_links"
        self.data_path.mkdir(parents=True, exist_ok=True)
        
        self.identities_file = self.data_path / "identities.json"
        self.links_file = self.data_path / "links.json"
        self.achievements_file = self.data_path / "linked_achievements.json"
        
        self.identities: Dict[str, UserIdentity] = {}
        self.links: Dict[str, AchievementLink] = {}
        self.linked_achievements: Dict[str, List[LinkedAchievement]] = {}  # user_id -> achievements
        
        self._load()
    
    def _load(self):
        """Load data from disk."""
        # Load identities
        if self.identities_file.exists():
            try:
                with open(self.identities_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for uid, idata in data.items():
                        self.identities[uid] = UserIdentity(**idata)
            except Exception as e:
                logger.error(f"Failed to load identities: {e}")
        
        # Load links
        if self.links_file.exists():
            try:
                with open(self.links_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for agent_id, ldata in data.items():
                        self.links[agent_id] = AchievementLink(**ldata)
            except Exception as e:
                logger.error(f"Failed to load links: {e}")
        
        # Load linked achievements
        if self.achievements_file.exists():
            try:
                with open(self.achievements_file, "r", encoding="utf-8") as f:
                    self.linked_achievements = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load linked achievements: {e}")
    
    def _save(self):
        """Persist data to disk."""
        # Save identities
        with open(self.identities_file, "w", encoding="utf-8") as f:
            json.dump({uid: i.__dict__ for uid, i in self.identities.items()}, f, indent=2)
        
        # Save links
        with open(self.links_file, "w", encoding="utf-8") as f:
            json.dump({aid: l.__dict__ for aid, l in self.links.items()}, f, indent=2)
        
        # Save linked achievements
        with open(self.achievements_file, "w", encoding="utf-8") as f:
            json.dump(self.linked_achievements, f, indent=2)
    
    def create_identity(self, display_name: str) -> UserIdentity:
        """Create a new user identity."""
        user_id = hashlib.sha256(f"{display_name}{time.time()}".encode()).hexdigest()[:16]
        
        identity = UserIdentity(
            user_id=user_id,
            display_name=display_name,
            providers={},
            created_at=datetime.now(UTC).isoformat() + "Z",
            last_linked=datetime.now(UTC).isoformat() + "Z"
        )
        
        self.identities[user_id] = identity
        self._save()
        
        return identity
    
    def link_provider(self, user_id: str, provider: AuthProvider, provider_user_id: str) -> bool:
        """Link an auth provider to an existing identity."""
        if user_id not in self.identities:
            logger.error(f"Identity not found: {user_id}")
            return False
        
        identity = self.identities[user_id]
        identity.providers[provider.value] = provider_user_id
        identity.last_linked = datetime.now(UTC).isoformat() + "Z"
        
        self._save()
        
        logger.info(f"[LINK] {provider.value}:{provider_user_id} linked to user {user_id}")
        return True
    
    def generate_link_code(self, agent_id: str, user_id: str) -> str:
        """Generate a one-time link code for an AAS agent."""
        link_code = hashlib.sha256(f"{agent_id}{user_id}{time.time()}".encode()).hexdigest()[:12]
        
        link = AchievementLink(
            agent_id=agent_id,
            user_id=user_id,
            link_code=link_code,
            linked_at=datetime.now(UTC).isoformat() + "Z"
        )
        
        self.links[agent_id] = link
        self._save()
        
        return link_code
    
    def verify_link_code(self, agent_id: str, code: str) -> Optional[str]:
        """Verify link code and return user_id if valid."""
        link = self.links.get(agent_id)
        if not link:
            return None
        
        if link.link_code != code:
            return None
        
        # Mark as primary link
        link.primary = True
        self._save()
        
        return link.user_id
    
    def link_achievement(self, achievement: dict, agent_id: str, source_aas: str = "local") -> bool:
        """
        Link an earned achievement to the user bound to this agent.
        Returns True if linked, False if no user bound.
        """
        link = self.links.get(agent_id)
        if not link or not link.primary:
            # Agent not linked to a user - achievement stays with agent
            return False
        
        user_id = link.user_id
        
        if user_id not in self.linked_achievements:
            self.linked_achievements[user_id] = []
        
        # Check if already linked (don't duplicate)
        for la in self.linked_achievements[user_id]:
            if la["achievement_id"] == achievement.get("id"):
                return False  # Already linked
        
        linked = LinkedAchievement(
            achievement_id=achievement.get("id", "unknown"),
            user_id=user_id,
            linked_at=datetime.now(UTC).isoformat() + "Z",
            xp_earned=achievement.get("xp_reward", 0),
            gamerscore=achievement.get("gamerscore", 0),
            source_aas=source_aas
        )
        
        self.linked_achievements[user_id].append(linked.__dict__)
        
        # Update identity stats
        if user_id in self.identities:
            self.identities[user_id].achievement_count += 1
            self.identities[user_id].total_xp += achievement.get("xp_reward", 0)
            self.identities[user_id].total_gamerscore += achievement.get("gamerscore", 0)
        
        self._save()
        
        logger.info(f"[LINK] Achievement {achievement.get('id')} linked to user {user_id}")
        return True
    
    def get_user_achievements(self, user_id: str) -> List[dict]:
        """Get all achievements linked to a user."""
        return self.linked_achievements.get(user_id, [])
    
    def get_user_stats(self, user_id: str) -> dict:
        """Get user's total stats."""
        identity = self.identities.get(user_id)
        achievements = self.get_user_achievements(user_id)
        
        return {
            "user_id": user_id,
            "display_name": identity.display_name if identity else "Unknown",
            "providers": identity.providers if identity else {},
            "achievement_count": len(achievements),
            "total_xp": sum(a["xp_earned"] for a in achievements),
            "total_gamerscore": sum(a["gamerscore"] for a in achievements),
            "achievements": achievements
        }
    
    def find_user_by_provider(self, provider: AuthProvider, provider_user_id: str) -> Optional[UserIdentity]:
        """Find a user identity by their auth provider."""
        for identity in self.identities.values():
            if identity.providers.get(provider.value) == provider_user_id:
                return identity
        return None
    
    def export_user_data(self, user_id: str) -> dict:
        """
        Export all user data for sync to cloud.
        This is what gets uploaded when cloud sync is enabled.
        """
        return self.get_user_stats(user_id)


class CrossAASAchievementSync:
    """
    Syncs achievements between multiple AAS instances.
    When an agent moves to a new AAS, it can sync achievements.
    """
    
    def __init__(self, link_manager: AchievementLinkManager):
        self.link_manager = link_manager
        self.sync_manifest = get_path("artifacts") / "achievement_sync.json"
        self.pending_sync: List[dict] = []
        self._load_sync_queue()
    
    def _load_sync_queue(self):
        if self.sync_manifest.exists():
            try:
                with open(self.sync_manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.pending_sync = data.get("pending", [])
            except:
                self.pending_sync = []
    
    def _save_sync_queue(self):
        with open(self.sync_manifest, "w", encoding="utf-8") as f:
            json.dump({"pending": self.pending_sync}, f, indent=2)
    
    def queue_sync(self, achievement: dict, source_aas: str, target_user_id: str):
        """Queue an achievement for sync to another AAS instance."""
        self.pending_sync.append({
            "achievement": achievement,
            "source_aas": source_aas,
            "target_user": target_user_id,
            "queued_at": datetime.now(UTC).isoformat() + "Z"
        })
        self._save_sync_queue()
    
    def process_sync_queue(self) -> List[dict]:
        """Process pending syncs."""
        processed = []
        
        for sync in self.pending_sync:
            user_id = sync["target_user"]
            achievement = sync["achievement"]
            
            linked = self.link_manager.link_achievement(achievement, "", sync["source_aas"])
            if linked:
                processed.append(sync)
        
        # Remove processed from queue
        for p in processed:
            self.pending_sync.remove(p)
        
        self._save_sync_queue()
        
        return processed

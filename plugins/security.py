import json
import re
import os
import secrets
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
from dataclasses import dataclass, field
from enum import Enum
import httpx
import logging
from aas_kernel import ReflexPlugin, AASPlugin, get_path

SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", "API Key"),
    (r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?", "Password"),
    (r"(?i)(bearer|token|auth[_-]?token)\s+[a-zA-Z0-9_\-\.]+", "Auth Token"),
    (r"(?i)(private[_-]?key|privatekey)\s*[:=]\s*['\"]?-----BEGIN[^\n]+-----", "Private Key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth"),
    (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab Token"),
    (r"sk-[a-zA-Z0-9]{48,}", "OpenAI API Key"),
    (r"sk-proj-[a-zA-Z0-9_\-]{48,}", "OpenAI Project Key"),
    (r"(?i)aws[_-]?(access[_-]?key[_-?id|secret]|secret[_-]?access)", "AWS Credentials"),
    (r"xox[baprs]-[a-zA-Z0-9]{10,}", "Slack Token"),
    (r"(?i)(mysql|postgres|mongodb)://[^\s]+", "Database URL"),
]


# === OAuth Configuration ===
OAUTH_CONFIG = {
    "github": {
        "client_id": os.getenv("AAS_GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GITHUB_CLIENT_SECRET", ""),
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_url": "https://api.github.com/user",
        "scopes": ["read:user", "user:email"],
    },
    "google": {
        "client_id": os.getenv("AAS_GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GOOGLE_CLIENT_SECRET", ""),
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "gitlab": {
        "client_id": os.getenv("AAS_GITLAB_CLIENT_ID", ""),
        "client_secret": os.getenv("AAS_GITLAB_CLIENT_SECRET", ""),
        "authorize_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "user_url": "https://gitlab.com/api/v4/user",
        "scopes": ["read_user"],
    },
}


# === Auth & Link Classes ===
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
    providers: Dict[str, str]
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
    source_aas: str


@dataclass
class AchievementLinkRecord:
    """Links an AAS agent to a user identity."""
    agent_id: str
    user_id: str
    link_code: str
    linked_at: str
    primary: bool = False


@dataclass
class AuthSession:
    """OAuth session state."""
    session_id: str
    user_id: str
    provider: str
    code_verifier: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat() + "Z")
    completed: bool = False


class VulnerabilityHistoryManager:
    """
    Manages the history of vulnerability scan results.
    """
    def __init__(self, data_path: Path = None):
        self.data_path = data_path or get_path("artifacts") / "security_scans"
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_path / "vulnerability_history.jsonl"

    def add_scan_result(self, repo_owner: str, repo_name: str, vulnerabilities: List[Dict]) -> None:
        scan_record = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "vulnerabilities": vulnerabilities,
            "count": len(vulnerabilities),
        }
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(scan_record) + "\n")
        logger.info(f"[VULN HISTORY] Recorded {len(vulnerabilities)} vulnerabilities for {repo_owner}/{repo_name}")

    def get_history(self) -> List[Dict]:
        if not self.history_file.exists():
            return []
        history = []
        with open(self.history_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse history line: {e} - {line.strip()}")
        return history


class AchievementLinkManager:
    """
    Manages achievement-user linking.
    Handles identity creation, OAuth linking, and achievement sync.
    """
    
    def __init__(self, data_path: Path = None):
        self.data_path = data_path or get_path("artifacts") / "achievement_links"
        self.data_path.mkdir(parents=True, exist_ok=True)
        
        self.identities_file = self.data_path / "identities.json"
        self.links_file = self.data_path / "links.json"
        self.achievements_file = self.data_path / "linked_achievements.json"
        
        self.identities: Dict[str, UserIdentity] = {}
        self.links: Dict[str, AchievementLinkRecord] = {}
        self.linked_achievements: Dict[str, List[dict]] = {}
        self._load()
    
    def _load(self):
        if self.identities_file.exists():
            try:
                with open(self.identities_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for uid, idata in data.items():
                        self.identities[uid] = UserIdentity(**idata)
            except Exception as e:
                logger.error(f"Failed to load identities: {e}")
        
        if self.links_file.exists():
            try:
                with open(self.links_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for aid, ldata in data.items():
                        self.links[aid] = AchievementLinkRecord(**ldata)
            except Exception as e:
                logger.error(f"Failed to load links: {e}")
        
        if self.achievements_file.exists():
            try:
                with open(self.achievements_file, "r", encoding="utf-8") as f:
                    self.linked_achievements = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load linked achievements: {e}")
    
    def _save(self):
        with open(self.identities_file, "w", encoding="utf-8") as f:
            json.dump({uid: i.__dict__ for uid, i in self.identities.items()}, f, indent=2)
        with open(self.links_file, "w", encoding="utf-8") as f:
            json.dump({aid: l.__dict__ for aid, l in self.links.items()}, f, indent=2)
        with open(self.achievements_file, "w", encoding="utf-8") as f:
            json.dump(self.linked_achievements, f, indent=2)
    
    def create_identity(self, display_name: str) -> UserIdentity:
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
        link_code = hashlib.sha256(f"{agent_id}{user_id}{time.time()}".encode()).hexdigest()[:12]
        link = AchievementLinkRecord(
            agent_id=agent_id,
            user_id=user_id,
            link_code=link_code,
            linked_at=datetime.now(UTC).isoformat() + "Z"
        )
        self.links[agent_id] = link
        self._save()
        return link_code
    
    def verify_link_code(self, agent_id: str, code: str) -> Optional[str]:
        link = self.links.get(agent_id)
        if not link or link.link_code != code:
            return None
        link.primary = True
        self._save()
        return link.user_id
    
    def link_achievement(self, achievement: dict, agent_id: str, source_aas: str = "local") -> bool:
        link = self.links.get(agent_id)
        if not link or not link.primary:
            return False
        
        user_id = link.user_id
        if user_id not in self.linked_achievements:
            self.linked_achievements[user_id] = []
        
        for la in self.linked_achievements[user_id]:
            if la["achievement_id"] == achievement.get("id"):
                return False
        
        linked = {
            "achievement_id": achievement.get("id", "unknown"),
            "user_id": user_id,
            "linked_at": datetime.now(UTC).isoformat() + "Z",
            "xp_earned": achievement.get("xp_reward", 0),
            "gamerscore": achievement.get("gamerscore", 0),
            "source_aas": source_aas
        }
        self.linked_achievements[user_id].append(linked)
        
        if user_id in self.identities:
            self.identities[user_id].achievement_count += 1
            self.identities[user_id].total_xp += achievement.get("xp_reward", 0)
            self.identities[user_id].total_gamerscore += achievement.get("gamerscore", 0)
        
        self._save()
        logger.info(f"[LINK] Achievement {achievement.get('id')} linked to user {user_id}")
        return True
    
    def get_user_stats(self, user_id: str) -> dict:
        identity = self.identities.get(user_id)
        achievements = self.linked_achievements.get(user_id, [])
        return {
            "user_id": user_id,
            "display_name": identity.display_name if identity else "Unknown",
            "providers": identity.providers if identity else {},
            "achievement_count": len(achievements),
            "total_xp": sum(a["xp_earned"] for a in achievements),
            "total_gamerscore": sum(a["gamerscore"] for a in achievements),
            "achievements": achievements
        }
    
    def export_user_data(self, user_id: str) -> dict:
        return self.get_user_stats(user_id)


# Global link manager
LINK_MANAGER = None
VULN_HISTORY_MANAGER = None

def get_link_manager() -> AchievementLinkManager:
    global LINK_MANAGER
    if LINK_MANAGER is None:
        LINK_MANAGER = AchievementLinkManager()
    return LINK_MANAGER

def get_vulnerability_history_manager() -> VulnerabilityHistoryManager:
    global VULN_HISTORY_MANAGER
    if VULN_HISTORY_MANAGER is None:
        VULN_HISTORY_MANAGER = VulnerabilityHistoryManager()
    return VULN_HISTORY_MANAGER



class Security(ReflexPlugin):
    """
    Domain: MyFortress (Security)
    Handles Policy Gates, Secrets Scanning, and Architectural compliance.
    """
    @property
    def capabilities(self) -> list[str]:
        return [
            "aaroneousautomationsuite_fortress_policy_evaluate",
            "aaroneousautomationsuite_fortress_scan_for_secrets",
            "aaroneousautomationsuite_link_identity",
            "aaroneousautomationsuite_link_oauth",
            "aaroneousautomationsuite_generate_link_code",
            "aaroneousautomationsuite_verify_link",
            "aaroneousautomationsuite_get_profile",
            "aaroneousautomationsuite_export_cloud",
            "aaroneousautomationsuite_fortress_scan_vulnerabilities",
            "aaroneousautomationsuite_fortress_get_vulnerabilities_history",
        ]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()

        if capability_id == "aaroneousautomationsuite_fortress_policy_evaluate":
            op = payload.get("operation")
            
            # --- Dynamic Spectrum Implementation ---
            # Instead of a hardcoded fail/pass, we use the agent's fluid cognitive bias.
            risk_tolerance = self.cognitive_biases.get("risk_tolerance", 50.0)
            strictness = self.cognitive_biases.get("audit_strictness", 50.0)
            
            # If the agent is paranoid (high strictness > 80, low risk tolerance < 20)
            if strictness > 80.0 and risk_tolerance < 20.0:
                # Require explicit override flags in the payload to pass
                if not payload.get("force_override"):
                    return self._format_result(
                        capability_id, 
                        {"message": f"Blocked: Operation '{op}' failed Sentinel strictness gate. Risk tolerance exceeded."}, 
                        start_time, 
                        success=False
                    )
            
            result = {"approved": True, "details": f"Operation '{op}' passed gates (Risk Tolerance: {risk_tolerance})."}
            return self._format_result(capability_id, result, start_time, success=True)

        elif capability_id == "aaroneousautomationsuite_fortress_scan_for_secrets":
            file_path = payload.get("file_path")
            if not file_path:
                return self._format_result(capability_id, {"message": "file_path required"}, start_time, success=False)

            path = Path(file_path)
            if not path.exists():
                return self._format_result(capability_id, {"message": f"File not found: {file_path}"}, start_time, success=False)

            if not path.is_file():
                return self._format_result(capability_id, {"message": f"Not a file: {file_path}"}, start_time, success=False)

            findings = []
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                for pattern, secret_type in SECRET_PATTERNS:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        line_num = content[:match.start()].count('\n') + 1
                        findings.append({
                            "type": secret_type,
                            "line": line_num,
                            "context": content[max(0, match.start()-20):match.end()+20]
                        })
            except Exception as e:
                return self._format_result(capability_id, {"message": f"Error scanning file: {e}"}, start_time, success=False)

            if findings:
                result = {
                    "status": "SECRETS_DETECTED",
                    "file": str(file_path),
                    "findings": findings,
                    "count": len(findings)
                }
            else:
                result = {
                    "status": "CLEAR",
                    "file": str(file_path),
                    "findings": [],
                    "count": 0
                }

            return self._format_result(capability_id, result, start_time, success=True)

        # Achievement linking capabilities
        elif capability_id == "aaroneousautomationsuite_link_identity":
            display_name = payload.get("display_name", "")
            if not display_name:
                return self._format_result(capability_id, {"message": "display_name required"}, start_time, success=False)
            identity = get_link_manager().create_identity(display_name)
            return self._format_result(capability_id, {
                "user_id": identity.user_id,
                "display_name": identity.display_name,
                "created_at": identity.created_at
            }, start_time, success=True)

        elif capability_id == "aaroneousautomationsuite_link_oauth":
            user_id = payload.get("user_id", "")
            provider = payload.get("provider", "")
            provider_user_id = payload.get("provider_user_id", "")
            if not all([user_id, provider, provider_user_id]):
                return self._format_result(capability_id, {"message": "user_id, provider, provider_user_id required"}, start_time, success=False)
            try:
                auth_provider = AuthProvider(provider)
                success = get_link_manager().link_provider(user_id, auth_provider, provider_user_id)
                return self._format_result(capability_id, {"success": success}, start_time, success=True)
            except ValueError as e:
                return self._format_result(capability_id, {"message": str(e)}, start_time, success=False)

        elif capability_id == "aaroneousautomationsuite_generate_link_code":
            agent_id = payload.get("agent_id", "")
            user_id = payload.get("user_id", "")
            if not all([agent_id, user_id]):
                return self._format_result(capability_id, {"message": "agent_id and user_id required"}, start_time, success=False)
            code = get_link_manager().generate_link_code(agent_id, user_id)
            return self._format_result(capability_id, {"link_code": code}, start_time, success=True)

        elif capability_id == "aaroneousautomationsuite_verify_link":
            agent_id = payload.get("agent_id", "")
            code = payload.get("code", "")
            if not all([agent_id, code]):
                return self._format_result(capability_id, {"message": "agent_id and code required"}, start_time, success=False)
            user_id = get_link_manager().verify_link_code(agent_id, code)
            if user_id:
                return self._format_result(capability_id, {"user_id": user_id}, start_time, success=True)
            return self._format_result(capability_id, {"message": "Invalid or expired link code"}, start_time, success=False)

        elif capability_id == "aaroneousautomationsuite_get_profile":
            user_id = payload.get("user_id", "")
            if not user_id:
                return self._format_error(capability_id, "user_id required")
            profile = get_link_manager().get_user_stats(user_id)
            return self._format_success(capability_id, profile, start_time)

        elif capability_id == "aaroneousautomationsuite_export_cloud":
            user_id = payload.get("user_id", "")
            if not user_id:
                return self._format_error(capability_id, "user_id required")
            data = get_link_manager().export_user_data(user_id)
            return self._format_success(capability_id, data, start_time)

        elif capability_id == "aaroneousautomationsuite_fortress_scan_vulnerabilities":
            repo_owner = payload.get("repo_owner")
            repo_name = payload.get("repo_name")
            github_token = os.getenv("GITHUB_TOKEN") # Assuming GITHUB_TOKEN is set as an environment variable

            if not all([repo_owner, repo_name, github_token]):
                return self._format_error(capability_id, "repo_owner, repo_name, and GITHUB_TOKEN environment variable required")

            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            # GitHub API for Dependabot alerts (requires 'security_events' scope or fine-grained token permissions)
            # This API path might be deprecated or require specific permissions.
            # A more robust solution might involve using the GraphQL API or checking for the correct REST API endpoint.
            # For simplicity, we'll try the common Dependabot alerts endpoint.
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/dependabot/alerts"

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, headers=headers, timeout=30.0)
                    response.raise_for_status() # Raise an exception for HTTP errors

                alerts = response.json()
                vulnerabilities = []
                for alert in alerts:
                    vulnerabilities.append({
                        "id": alert.get("number"),
                        "severity": alert.get("security_advisory", {}).get("severity"),
                        "state": alert.get("state"),
                        "created_at": alert.get("created_at"),
                        "updated_at": alert.get("updated_at"),
                        "summary": alert.get("security_advisory", {}).get("summary"),
                        "package_name": alert.get("security_vulnerability", {}).get("package", {}).get("name"),
                        "vulnerable_version_range": alert.get("security_vulnerability", {}).get("vulnerable_version_range"),
                        "fixed_in": alert.get("security_vulnerability", {}).get("first_patch_version", {}).get("identifier"),
                        "url": alert.get("html_url"),
                    })

                result = {
                    "status": "VULNERABILITIES_SCANNED",
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "vulnerability_count": len(vulnerabilities),
                    "vulnerabilities": vulnerabilities,
                }
                get_vulnerability_history_manager().add_scan_result(repo_owner, repo_name, vulnerabilities)
            return self._format_result(capability_id, result, start_time, success=True)

            except httpx.HTTPStatusError as e:
                self.logger.error(f"GitHub API HTTP error: {e.response.status_code} - {e.response.text}")
                return self._format_error(capability_id, f"GitHub API HTTP error: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                self.logger.error(f"GitHub API request error: {e}")
                return self._format_error(capability_id, f"GitHub API request error: {e}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode GitHub API response: {e}")
                return self._format_error(capability_id, f"Failed to decode GitHub API response: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error during vulnerability scan: {e}")
                return self._format_error(capability_id, f"Unexpected error: {e}")

        elif capability_id == "aaroneousautomationsuite_fortress_get_vulnerabilities_history":
            history = get_vulnerability_history_manager().get_history()
            return self._format_success(capability_id, {"history": history, "count": len(history)}, start_time)

        return self._format_error(capability_id, "Unknown security capability.")

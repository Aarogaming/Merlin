# Merlin Plugin: User Manager
from typing import Any, Dict, Optional

from merlin_user_manager import user_manager


def _sanitize_user(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    return {"username": user.get("username"), "role": user.get("role")}


class MerlinUserManagerPlugin:
    def __init__(self):
        self.name = "user_manager"
        self.description = "Manage Merlin users (create/get/auth)."
        self.version = "1.0.0"
        self.author = "AAS"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, action: str, **kwargs: Any):
        if not action:
            return {"error": "action_required", "actions": ["create", "get", "auth"]}
        action = str(action).strip().lower()
        if action == "create":
            username = kwargs.get("username")
            password = kwargs.get("password")
            role = kwargs.get("role") or "user"
            if not username or not password:
                return {"error": "username_and_password_required"}
            try:
                user = user_manager.create_user(str(username), str(password), role=str(role))
            except Exception as exc:
                return {"error": "create_failed", "detail": str(exc)}
            return {"user": _sanitize_user(user)}
        if action == "get":
            username = kwargs.get("username")
            if not username:
                return {"error": "username_required"}
            user = user_manager.get_user_by_username(str(username))
            return {"user": _sanitize_user(user)}
        if action == "auth":
            username = kwargs.get("username")
            password = kwargs.get("password")
            if not username or not password:
                return {"error": "username_and_password_required"}
            user = user_manager.authenticate_user(str(username), str(password))
            return {"ok": bool(user), "user": _sanitize_user(user)}
        return {"error": "unsupported_action", "action": action}


def get_plugin():
    return MerlinUserManagerPlugin()

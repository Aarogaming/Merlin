from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from merlin_auth import get_password_hash, verify_password
except Exception:  # pragma: no cover - optional dependency fallback.
    def get_password_hash(password: str) -> str:
        return f"insecure::{password}"

    def verify_password(password: str, hashed_password: str) -> bool:
        if hashed_password == password:
            return True
        return hashed_password == get_password_hash(password)

from merlin_logger import merlin_logger

USER_SCHEMA_VERSION = 1


class MerlinUserManager:
    def __init__(self, users_file: str = "merlin_users.json"):
        self.users_file = users_file
        self.users = self._load_users()
        if not self.users:
            self.create_user("admin", "admin123", role="admin")

    @staticmethod
    def _migrate_user_record(user: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        migrated = dict(user)
        changed = False

        # Legacy key migration support.
        if "hashed_password" not in migrated and isinstance(
            migrated.get("password_hash"), str
        ):
            migrated["hashed_password"] = migrated["password_hash"]
            changed = True

        schema_version = migrated.get("schema_version")
        if schema_version != USER_SCHEMA_VERSION:
            migrated["schema_version"] = USER_SCHEMA_VERSION
            changed = True

        if "role" not in migrated:
            migrated["role"] = "user"
            changed = True

        return migrated, changed

    def migrate_users_schema(self) -> Dict[str, int]:
        migrated_users: List[Dict[str, Any]] = []
        migrated_count = 0
        for user in self.users:
            migrated, changed = self._migrate_user_record(user)
            migrated_users.append(migrated)
            if changed:
                migrated_count += 1
        if migrated_count > 0:
            self.users = migrated_users
            self._save_users()
        return {"migrated_count": migrated_count, "schema_version": USER_SCHEMA_VERSION}

    def _load_users(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError("users file must be a JSON array")

                users: List[Dict[str, Any]] = []
                changed = False
                for item in loaded:
                    if not isinstance(item, dict):
                        continue
                    migrated, user_changed = self._migrate_user_record(item)
                    users.append(migrated)
                    if user_changed:
                        changed = True

                if changed:
                    self.users = users
                    self._save_users()
                return users
            except Exception as e:
                merlin_logger.error(f"Failed to load users: {e}")
        return []

    def _save_users(self):
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save users: {e}")

    def create_user(
        self, username: str, password: str, role: str = "user"
    ) -> Dict[str, Any]:
        if self.get_user_by_username(username):
            raise ValueError("User already exists")

        user = {
            "schema_version": USER_SCHEMA_VERSION,
            "username": username,
            "hashed_password": get_password_hash(password),
            "role": role,
        }
        self.users.append(user)
        self._save_users()
        merlin_logger.info(f"Created user: {username} (Role: {role})")
        return {
            "schema_version": USER_SCHEMA_VERSION,
            "username": username,
            "role": role,
        }

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        for user in self.users:
            if user.get("username") == username:
                return user
        return None

    def authenticate_user(
        self, username: str, password: str
    ) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_username(username)
        if user and verify_password(password, user["hashed_password"]):
            return user
        return None


user_manager = MerlinUserManager()

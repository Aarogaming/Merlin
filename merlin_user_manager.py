import json
import os
from typing import List, Dict, Any, Optional
from merlin_auth import get_password_hash, verify_password
from merlin_logger import merlin_logger

class MerlinUserManager:
    def __init__(self, users_file="merlin_users.json"):
        self.users_file = users_file
        self.users = self._load_users()
        if not self.users:
            # Create default admin user
            self.create_user("admin", "admin123", role="admin")

    def _load_users(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                merlin_logger.error(f"Failed to load users: {e}")
        return []

    def _save_users(self):
        try:
            with open(self.users_file, "w") as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save users: {e}")

    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        if self.get_user_by_username(username):
            raise ValueError("User already exists")
            
        user = {
            "username": username,
            "hashed_password": get_password_hash(password),
            "role": role
        }
        self.users.append(user)
        self._save_users()
        merlin_logger.info(f"Created user: {username} (Role: {role})")
        return {"username": username, "role": role}

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        for user in self.users:
            if user["username"] == username:
                return user
        return None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_username(username)
        if user and verify_password(password, user["hashed_password"]):
            return user
        return None

user_manager = MerlinUserManager()

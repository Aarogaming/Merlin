from __future__ import annotations

import json
from pathlib import Path

from merlin_user_manager import MerlinUserManager, USER_SCHEMA_VERSION


def test_load_users_migrates_legacy_schema_and_persists(tmp_path: Path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps(
            [
                {
                    "username": "legacy_user",
                    "hashed_password": "legacy-hash",
                    "role": "user",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = MerlinUserManager(users_file=str(users_file))
    user = manager.get_user_by_username("legacy_user")
    assert user is not None
    assert user["schema_version"] == USER_SCHEMA_VERSION

    persisted = json.loads(users_file.read_text(encoding="utf-8"))
    assert persisted[0]["schema_version"] == USER_SCHEMA_VERSION


def test_load_users_migrates_legacy_password_hash_key(tmp_path: Path):
    users_file = tmp_path / "users.json"
    users_file.write_text(
        json.dumps(
            [
                {
                    "username": "legacy_hash_user",
                    "password_hash": "legacy-hash",
                    "role": "admin",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = MerlinUserManager(users_file=str(users_file))
    user = manager.get_user_by_username("legacy_hash_user")
    assert user is not None
    assert user["hashed_password"] == "legacy-hash"
    assert user["schema_version"] == USER_SCHEMA_VERSION


def test_create_user_includes_schema_version(tmp_path: Path):
    users_file = tmp_path / "users.json"
    manager = MerlinUserManager(users_file=str(users_file))
    result = manager.create_user("new_user", "test-password", role="user")

    assert result["schema_version"] == USER_SCHEMA_VERSION
    persisted = json.loads(users_file.read_text(encoding="utf-8"))
    matched = [user for user in persisted if user["username"] == "new_user"]
    assert matched
    assert matched[0]["schema_version"] == USER_SCHEMA_VERSION

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from merlin_logger import merlin_logger

try:
    from merlin_settings import (
        MERLIN_SQLITE_BUSY_TIMEOUT_MS,
        MERLIN_SQLITE_CACHE_SIZE_KB,
        MERLIN_SQLITE_JOURNAL_MODE,
        MERLIN_SQLITE_SYNCHRONOUS,
        MERLIN_SQLITE_TEMP_STORE,
        MERLIN_SQLITE_WAL_AUTOCHECKPOINT,
    )
except Exception:
    MERLIN_SQLITE_JOURNAL_MODE = "WAL"
    MERLIN_SQLITE_SYNCHRONOUS = "NORMAL"
    MERLIN_SQLITE_BUSY_TIMEOUT_MS = 5000
    MERLIN_SQLITE_WAL_AUTOCHECKPOINT = 1000
    MERLIN_SQLITE_CACHE_SIZE_KB = 8192
    MERLIN_SQLITE_TEMP_STORE = "MEMORY"

DB_PATH = "merlin.db"

_VALID_SQLITE_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
_VALID_SQLITE_SYNCHRONOUS = {"OFF", "NORMAL", "FULL", "EXTRA"}
_TEMP_STORE_TO_PRAGMA = {"DEFAULT": 0, "FILE": 1, "MEMORY": 2}


@dataclass(frozen=True)
class MigrationDefinition:
    id: str
    description: str
    up_sql: tuple[str, ...]
    down_sql: tuple[str, ...]


MIGRATIONS: tuple[MigrationDefinition, ...] = (
    MigrationDefinition(
        id="001_audit_logs_timestamp_index",
        description="Add timestamp index for audit log queries.",
        up_sql=(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)",
        ),
        down_sql=("DROP INDEX IF EXISTS idx_audit_logs_timestamp",),
    ),
    MigrationDefinition(
        id="002_migration_notes_table",
        description="Add migration notes table for migration metadata.",
        up_sql=(
            """
            CREATE TABLE IF NOT EXISTS migration_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ),
        down_sql=("DROP TABLE IF EXISTS migration_notes",),
    ),
)


def _normalized_journal_mode() -> str:
    journal_mode = str(MERLIN_SQLITE_JOURNAL_MODE).strip().upper()
    if journal_mode in _VALID_SQLITE_JOURNAL_MODES:
        return journal_mode
    return "WAL"


def _normalized_synchronous() -> str:
    synchronous = str(MERLIN_SQLITE_SYNCHRONOUS).strip().upper()
    if synchronous in _VALID_SQLITE_SYNCHRONOUS:
        return synchronous
    return "NORMAL"


def _normalized_temp_store() -> int:
    temp_store = str(MERLIN_SQLITE_TEMP_STORE).strip().upper()
    return _TEMP_STORE_TO_PRAGMA.get(temp_store, _TEMP_STORE_TO_PRAGMA["MEMORY"])


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA journal_mode={_normalized_journal_mode()}")
    conn.execute(f"PRAGMA synchronous={_normalized_synchronous()}")
    conn.execute(f"PRAGMA busy_timeout={max(1, int(MERLIN_SQLITE_BUSY_TIMEOUT_MS))}")
    conn.execute(
        f"PRAGMA wal_autocheckpoint={max(1, int(MERLIN_SQLITE_WAL_AUTOCHECKPOINT))}"
    )
    conn.execute(f"PRAGMA temp_store={_normalized_temp_store()}")
    conn.execute(f"PRAGMA cache_size={-max(1, int(MERLIN_SQLITE_CACHE_SIZE_KB))}")


def _connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    timeout_seconds = max(1.0, float(MERLIN_SQLITE_BUSY_TIMEOUT_MS) / 1000.0)
    conn = sqlite3.connect(db_path, timeout=timeout_seconds)
    _configure_connection(conn)
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_migration(item: MigrationDefinition | dict[str, Any]) -> MigrationDefinition:
    if isinstance(item, MigrationDefinition):
        return item

    migration_id = str(item.get("id", "")).strip()
    if not migration_id:
        raise ValueError("Migration must define a non-empty id")

    description = str(item.get("description", "")).strip()
    up_sql = item.get("up_sql", [])
    down_sql = item.get("down_sql", [])
    if not isinstance(up_sql, list) or not isinstance(down_sql, list):
        raise ValueError(f"Migration {migration_id} must define list up/down SQL")

    up_sql_statements = tuple(str(statement).strip() for statement in up_sql if str(statement).strip())
    down_sql_statements = tuple(
        str(statement).strip() for statement in down_sql if str(statement).strip()
    )
    if not up_sql_statements:
        raise ValueError(f"Migration {migration_id} must include at least one up_sql statement")

    return MigrationDefinition(
        id=migration_id,
        description=description,
        up_sql=up_sql_statements,
        down_sql=down_sql_statements,
    )


def _normalize_migrations(
    migrations: Sequence[MigrationDefinition | dict[str, Any]] | None = None,
) -> list[MigrationDefinition]:
    source = list(migrations) if migrations is not None else list(MIGRATIONS)
    normalized: list[MigrationDefinition] = []
    seen_ids: set[str] = set()

    for item in source:
        migration = _coerce_migration(item)
        if migration.id in seen_ids:
            raise ValueError(f"Duplicate migration id: {migration.id}")
        seen_ids.add(migration.id)
        normalized.append(migration)

    return normalized


def _ensure_base_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            due_date TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )


def _ensure_migration_tracking(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL,
            rollback_sql TEXT NOT NULL
        )
        """
    )


def init_db(db_path: str = DB_PATH) -> None:
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        _ensure_base_schema(cursor)
        _ensure_migration_tracking(cursor)
        conn.commit()
    finally:
        conn.close()


def get_schema_version(db_path: str = DB_PATH) -> int:
    return len(list_applied_migrations(db_path))


def list_applied_migrations(db_path: str = DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            """
            SELECT migration_id, description, applied_at
            FROM schema_migrations
            ORDER BY applied_at ASC, migration_id ASC
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "migration_id": str(row[0]),
            "description": str(row[1]),
            "applied_at": str(row[2]),
        }
        for row in rows
    ]


def run_migrations(
    db_path: str = DB_PATH,
    *,
    backup_before_migrate: bool = False,
    backup_dir: str = "backups",
    migrations: Sequence[MigrationDefinition | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    normalized_migrations = _normalize_migrations(migrations)
    backup_path = None
    if backup_before_migrate:
        try:
            from merlin_backup import backup_database_snapshot

            backup_path = backup_database_snapshot(db_path=db_path, backup_dir=backup_dir)
        except Exception as exc:
            merlin_logger.error(f"Database backup before migration failed: {exc}")

    conn = _connect(db_path)
    applied_now: list[str] = []
    skipped: list[str] = []
    try:
        cursor = conn.cursor()
        existing_rows = cursor.execute(
            "SELECT migration_id FROM schema_migrations"
        ).fetchall()
        applied_ids = {str(row[0]) for row in existing_rows}

        for migration in normalized_migrations:
            if migration.id in applied_ids:
                skipped.append(migration.id)
                continue

            conn.execute("BEGIN")
            try:
                for statement in migration.up_sql:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    INSERT INTO schema_migrations (
                        migration_id,
                        description,
                        applied_at,
                        rollback_sql
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        migration.id,
                        migration.description,
                        _utc_now_iso(),
                        json.dumps(list(migration.down_sql)),
                    ),
                )
                conn.commit()
                applied_ids.add(migration.id)
                applied_now.append(migration.id)
            except Exception as exc:
                conn.rollback()
                raise RuntimeError(
                    f"Migration failed for {migration.id}: {exc}"
                ) from exc
    finally:
        conn.close()

    return {
        "db_path": db_path,
        "backup_path": backup_path,
        "applied": applied_now,
        "skipped": skipped,
        "schema_version": len(applied_now) + len(skipped),
    }


def rollback_last_migration(db_path: str = DB_PATH) -> dict[str, Any]:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT migration_id, rollback_sql
            FROM schema_migrations
            ORDER BY applied_at DESC, migration_id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return {"db_path": db_path, "rolled_back": None}

        migration_id = str(row[0])
        rollback_sql = json.loads(str(row[1]))
        if not isinstance(rollback_sql, list):
            raise ValueError(f"Migration {migration_id} rollback_sql must be a list")

        conn.execute("BEGIN")
        try:
            for statement in rollback_sql:
                cursor.execute(str(statement))
            cursor.execute(
                "DELETE FROM schema_migrations WHERE migration_id = ?",
                (migration_id,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()

    return {"db_path": db_path, "rolled_back": migration_id}


def rollback_migrations(
    db_path: str = DB_PATH,
    *,
    steps: int = 1,
    backup_before_rollback: bool = False,
    backup_dir: str = "backups",
) -> dict[str, Any]:
    if steps <= 0:
        raise ValueError("steps must be greater than zero")

    backup_path = None
    if backup_before_rollback:
        try:
            from merlin_backup import backup_database_snapshot

            backup_path = backup_database_snapshot(db_path=db_path, backup_dir=backup_dir)
        except Exception as exc:
            merlin_logger.error(f"Database backup before rollback failed: {exc}")

    rolled_back: list[str] = []
    for _ in range(steps):
        result = rollback_last_migration(db_path=db_path)
        migration_id = result.get("rolled_back")
        if migration_id is None:
            break
        rolled_back.append(str(migration_id))

    return {"db_path": db_path, "backup_path": backup_path, "rolled_back": rolled_back}


def log_audit(user_id: int | None, action: str, details: str, db_path: str = DB_PATH) -> None:
    init_db(db_path)
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    summary = run_migrations(backup_before_migrate=True)
    print(json.dumps(summary, indent=2))
    print(
        f"Applied migrations: {migration_result['applied']}, "
        f"skipped: {migration_result['skipped']}"
    )

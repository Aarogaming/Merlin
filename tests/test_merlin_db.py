from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

import merlin_db


def _table_exists(db_path: Path, table_name: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def _index_exists(db_path: Path, index_name: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def test_run_migrations_applies_expected_changes_and_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "merlin.db"
    backup_dir = tmp_path / "backups"

    first = merlin_db.run_migrations(
        db_path=str(db_path),
        backup_before_migrate=True,
        backup_dir=str(backup_dir),
    )

    assert first["applied"] == [
        "001_audit_logs_timestamp_index",
        "002_migration_notes_table",
    ]
    assert first["skipped"] == []
    assert first["backup_path"] is not None
    assert Path(str(first["backup_path"])).exists()
    assert _table_exists(db_path, "migration_notes")
    assert _index_exists(db_path, "idx_audit_logs_timestamp")

    second = merlin_db.run_migrations(db_path=str(db_path))
    assert second["applied"] == []
    assert second["skipped"] == [
        "001_audit_logs_timestamp_index",
        "002_migration_notes_table",
    ]
    assert merlin_db.get_schema_version(str(db_path)) == 2


def test_rollback_last_migration_reverts_latest_change(tmp_path: Path):
    db_path = tmp_path / "merlin.db"
    merlin_db.run_migrations(db_path=str(db_path))

    result = merlin_db.rollback_last_migration(db_path=str(db_path))

    assert result["rolled_back"] == "002_migration_notes_table"
    assert not _table_exists(db_path, "migration_notes")
    assert _index_exists(db_path, "idx_audit_logs_timestamp")
    assert merlin_db.get_schema_version(str(db_path)) == 1


def test_rollback_multiple_migrations_stops_at_empty_history(tmp_path: Path):
    db_path = tmp_path / "merlin.db"
    merlin_db.run_migrations(db_path=str(db_path))

    result = merlin_db.rollback_migrations(
        db_path=str(db_path),
        steps=5,
        backup_before_rollback=True,
        backup_dir=str(tmp_path / "rollback_backups"),
    )

    assert result["rolled_back"] == [
        "002_migration_notes_table",
        "001_audit_logs_timestamp_index",
    ]
    assert result["backup_path"] is not None
    assert Path(str(result["backup_path"])).exists()
    assert merlin_db.get_schema_version(str(db_path)) == 0
    assert not _table_exists(db_path, "migration_notes")
    assert not _index_exists(db_path, "idx_audit_logs_timestamp")


def test_failed_migration_statement_rolls_back_transaction(tmp_path: Path):
    db_path = tmp_path / "merlin.db"
    migrations = [
        {
            "id": "001_bad_migration",
            "description": "intentional failure for rollback test",
            "up_sql": [
                "CREATE TABLE IF NOT EXISTS migration_should_rollback (id INTEGER)",
                "THIS IS INVALID SQL",
            ],
            "down_sql": ["DROP TABLE IF EXISTS migration_should_rollback"],
        }
    ]

    with pytest.raises(RuntimeError):
        merlin_db.run_migrations(db_path=str(db_path), migrations=migrations)

    assert not _table_exists(db_path, "migration_should_rollback")
    assert merlin_db.list_applied_migrations(str(db_path)) == []


def test_sqlite_pragmas_are_applied_from_settings(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MERLIN_CHAT_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("MERLIN_SQLITE_JOURNAL_MODE", "WAL")
    monkeypatch.setenv("MERLIN_SQLITE_SYNCHRONOUS", "NORMAL")
    monkeypatch.setenv("MERLIN_SQLITE_BUSY_TIMEOUT_MS", "4200")
    monkeypatch.setenv("MERLIN_SQLITE_WAL_AUTOCHECKPOINT", "222")
    monkeypatch.setenv("MERLIN_SQLITE_CACHE_SIZE_KB", "2048")
    monkeypatch.setenv("MERLIN_SQLITE_TEMP_STORE", "MEMORY")

    settings = importlib.import_module("merlin_settings")
    importlib.reload(settings)
    reloaded_merlin_db = importlib.reload(merlin_db)

    db_path = tmp_path / "pragma_test.db"
    conn = reloaded_merlin_db._connect(str(db_path))
    try:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        wal_autocheckpoint = conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        cache_size = conn.execute("PRAGMA cache_size").fetchone()[0]
        temp_store = conn.execute("PRAGMA temp_store").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    assert busy_timeout == 4200
    assert wal_autocheckpoint == 222
    assert cache_size == -2048
    assert temp_store == 2
    assert str(journal_mode).lower() == "wal"

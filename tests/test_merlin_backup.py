from __future__ import annotations

import json
from pathlib import Path

from merlin_backup import (
    backup_database_snapshot,
    cleanup_old_backups,
    compute_file_sha256,
    create_backup,
    restore_backup_archive,
    restore_database_snapshot,
    run_restore_smoke_test,
    verify_backup_integrity,
)


def _create_sample_workspace(tmp_path: Path) -> None:
    (tmp_path / "merlin_chat_history").mkdir(parents=True, exist_ok=True)
    (tmp_path / "merlin_chat_history" / "session_1.json").write_text(
        json.dumps({"message": "hello"}, indent=2),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "app.log").write_text("log-entry\n", encoding="utf-8")
    (tmp_path / "merlin_tasks.json").write_text(
        json.dumps([{"id": 1, "title": "demo task"}]),
        encoding="utf-8",
    )


def test_create_backup_writes_integrity_manifest_and_verifies(monkeypatch, tmp_path: Path):
    _create_sample_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    backup_path = create_backup(backup_dir="backups")
    assert backup_path is not None
    archive_path = Path(str(backup_path))
    assert archive_path.exists()

    manifest_path = archive_path.with_suffix(archive_path.suffix + ".integrity.json")
    assert manifest_path.exists()

    verify_result = verify_backup_integrity(archive_path)
    assert verify_result["ok"] is True
    assert verify_result["expected_sha256"] == compute_file_sha256(archive_path)


def test_verify_backup_integrity_detects_checksum_mismatch(monkeypatch, tmp_path: Path):
    _create_sample_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    backup_path = create_backup(backup_dir="backups")
    assert backup_path is not None
    archive_path = Path(str(backup_path))

    # Tamper with archive bytes after integrity manifest is written.
    with archive_path.open("ab") as handle:
        handle.write(b"tamper")

    verify_result = verify_backup_integrity(archive_path)
    assert verify_result["ok"] is False
    assert verify_result["reason"] == "checksum_mismatch"


def test_database_snapshot_backup_and_restore(tmp_path: Path):
    db_path = tmp_path / "merlin.db"
    db_path.write_text("original-db", encoding="utf-8")

    backup_path = backup_database_snapshot(
        db_path=str(db_path),
        backup_dir=str(tmp_path / "db_backups"),
    )
    assert backup_path is not None
    snapshot_path = Path(str(backup_path))
    assert snapshot_path.exists()

    db_path.write_text("mutated-db", encoding="utf-8")
    restore_result = restore_database_snapshot(snapshot_path, db_path=str(db_path))
    assert restore_result["ok"] is True
    assert db_path.read_text(encoding="utf-8") == "original-db"


def test_restore_smoke_test_and_explicit_restore(monkeypatch, tmp_path: Path):
    _create_sample_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    backup_path = create_backup(backup_dir="backups")
    assert backup_path is not None
    archive_path = Path(str(backup_path))

    smoke_result = run_restore_smoke_test(archive_path)
    assert smoke_result["ok"] is True
    assert smoke_result["restored_file_count"] > 0

    restore_dir = tmp_path / "restored"
    restore_result = restore_backup_archive(archive_path, restore_dir=restore_dir)
    assert restore_result["ok"] is True
    assert (restore_dir / "merlin_chat_history" / "session_1.json").exists()


def test_cleanup_old_backups_removes_old_archives_and_manifests(monkeypatch, tmp_path: Path):
    _create_sample_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    backup_dir = tmp_path / "backups"

    paths: list[Path] = []
    for _ in range(3):
        backup_path = create_backup(backup_dir=str(backup_dir))
        assert backup_path is not None
        paths.append(Path(str(backup_path)))

    cleanup_old_backups(backup_dir=str(backup_dir), keep=1)

    remaining_archives = sorted(backup_dir.glob("merlin_backup_*.zip"))
    assert len(remaining_archives) == 1
    for original in paths[:-1]:
        assert not original.exists()
        assert not original.with_suffix(original.suffix + ".integrity.json").exists()

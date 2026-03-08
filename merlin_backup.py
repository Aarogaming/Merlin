from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from merlin_logger import merlin_logger


def _ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def compute_file_sha256(file_path: str | Path, chunk_size: int = 65536) -> str:
    path = Path(file_path)
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def write_backup_integrity_manifest(
    backup_path: str | Path,
    *,
    checksum: str | None = None,
) -> str:
    path = Path(backup_path)
    resolved_checksum = checksum or compute_file_sha256(path)
    payload = {
        "schema_name": "AAS.BackupIntegrityManifest",
        "schema_version": "1.0.0",
        "backup_path": str(path),
        "backup_name": path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": path.stat().st_size,
        "algorithm": "sha256",
        "sha256": resolved_checksum,
    }
    manifest_path = path.with_suffix(path.suffix + ".integrity.json")
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return str(manifest_path)


def verify_backup_integrity(
    backup_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    path = Path(backup_path)
    if not path.exists():
        return {
            "ok": False,
            "backup_path": str(path),
            "reason": "backup_not_found",
        }

    resolved_expected = expected_sha256
    resolved_manifest = Path(manifest_path) if manifest_path else path.with_suffix(
        path.suffix + ".integrity.json"
    )
    if resolved_expected is None and resolved_manifest.exists():
        try:
            with resolved_manifest.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            candidate = payload.get("sha256")
            if isinstance(candidate, str) and candidate.strip():
                resolved_expected = candidate.strip().lower()
        except Exception as exc:
            return {
                "ok": False,
                "backup_path": str(path),
                "manifest_path": str(resolved_manifest),
                "reason": f"manifest_read_error:{exc}",
            }

    computed = compute_file_sha256(path)
    ok = resolved_expected is None or computed == resolved_expected.lower()
    result: dict[str, Any] = {
        "ok": ok,
        "backup_path": str(path),
        "manifest_path": str(resolved_manifest),
        "computed_sha256": computed,
        "expected_sha256": resolved_expected,
    }
    if not ok:
        result["reason"] = "checksum_mismatch"
    return result


def backup_database_snapshot(
    db_path: str = "merlin.db",
    backup_dir: str = "backups",
    *,
    with_integrity_manifest: bool = True,
) -> str | None:
    db_file = Path(db_path)
    if not db_file.exists():
        merlin_logger.warning(f"Database backup skipped; file not found: {db_path}")
        return None

    backup_directory = _ensure_directory(backup_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_directory / f"merlin_db_backup_{timestamp}.sqlite"

    try:
        shutil.copy2(db_file, backup_path)
        if with_integrity_manifest:
            write_backup_integrity_manifest(backup_path)
        merlin_logger.info(f"Database backup created successfully: {backup_path}")
        return str(backup_path)
    except Exception as exc:
        merlin_logger.error(f"Database backup failed: {exc}")
        return None


def restore_database_snapshot(
    backup_path: str | Path,
    *,
    db_path: str = "merlin.db",
) -> dict[str, Any]:
    snapshot = Path(backup_path)
    target_db = Path(db_path)
    if not snapshot.exists():
        return {
            "ok": False,
            "backup_path": str(snapshot),
            "db_path": str(target_db),
            "reason": "snapshot_not_found",
        }

    _ensure_directory(target_db.parent if str(target_db.parent) else ".")
    try:
        shutil.copy2(snapshot, target_db)
    except Exception as exc:
        return {
            "ok": False,
            "backup_path": str(snapshot),
            "db_path": str(target_db),
            "reason": f"restore_failed:{exc}",
        }
    return {
        "ok": True,
        "backup_path": str(snapshot),
        "db_path": str(target_db),
    }


def create_backup(
    backup_dir: str = "backups",
    *,
    with_integrity_manifest: bool = True,
) -> str | None:
    backup_directory = _ensure_directory(backup_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_directory / f"merlin_backup_{timestamp}.zip"

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            chat_dir = Path("merlin_chat_history")
            if chat_dir.exists():
                for root, _dirs, files in os.walk(chat_dir):
                    for file in files:
                        file_path = Path(root) / file
                        zipf.write(file_path, file_path.relative_to(chat_dir.parent))

            log_dir = Path("logs")
            if log_dir.exists():
                for root, _dirs, files in os.walk(log_dir):
                    for file in files:
                        file_path = Path(root) / file
                        zipf.write(file_path, file_path.relative_to(log_dir.parent))

            tasks_file = Path("merlin_tasks.json")
            if tasks_file.exists():
                zipf.write(tasks_file)

        if with_integrity_manifest:
            write_backup_integrity_manifest(backup_path)
        merlin_logger.info(f"Backup created successfully: {backup_path}")
        return str(backup_path)
    except Exception as exc:
        merlin_logger.error(f"Backup failed: {exc}")
        return None


def restore_backup_archive(
    backup_path: str | Path,
    *,
    restore_dir: str | Path,
) -> dict[str, Any]:
    archive_path = Path(backup_path)
    destination = Path(restore_dir)
    if not archive_path.exists():
        return {
            "ok": False,
            "backup_path": str(archive_path),
            "restore_dir": str(destination),
            "reason": "backup_not_found",
        }

    _ensure_directory(destination)
    try:
        with zipfile.ZipFile(archive_path, "r") as zipf:
            zipf.extractall(destination)
            restored_files = zipf.namelist()
    except Exception as exc:
        return {
            "ok": False,
            "backup_path": str(archive_path),
            "restore_dir": str(destination),
            "reason": f"restore_failed:{exc}",
        }

    return {
        "ok": True,
        "backup_path": str(archive_path),
        "restore_dir": str(destination),
        "restored_file_count": len(restored_files),
        "restored_files": restored_files[:20],
    }


def run_restore_smoke_test(backup_path: str | Path) -> dict[str, Any]:
    archive_path = Path(backup_path)
    with tempfile.TemporaryDirectory(prefix="merlin_restore_smoke_") as temp_dir:
        restore_result = restore_backup_archive(archive_path, restore_dir=temp_dir)
        if not restore_result.get("ok"):
            return {
                "ok": False,
                "backup_path": str(archive_path),
                "restore_result": restore_result,
                "reason": "restore_failed",
            }
        restored_count = int(restore_result.get("restored_file_count", 0))
        return {
            "ok": restored_count > 0,
            "backup_path": str(archive_path),
            "restored_file_count": restored_count,
            "restore_result": restore_result,
            "reason": None if restored_count > 0 else "no_files_restored",
        }


def cleanup_old_backups(backup_dir: str = "backups", keep: int = 7) -> None:
    try:
        backup_directory = Path(backup_dir)
        if not backup_directory.exists():
            return
        backups = sorted(
            path
            for path in backup_directory.iterdir()
            if path.name.startswith("merlin_backup_") and path.suffix == ".zip"
        )
        if len(backups) > keep:
            for old_backup in backups[:-keep]:
                old_backup.unlink()
                manifest = old_backup.with_suffix(old_backup.suffix + ".integrity.json")
                if manifest.exists():
                    manifest.unlink()
                merlin_logger.info(f"Removed old backup: {old_backup}")
    except Exception as exc:
        merlin_logger.error(f"Backup cleanup failed: {exc}")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Merlin backup utility")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create backup archive")
    create_parser.add_argument("--backup-dir", default="backups")

    verify_parser = subparsers.add_parser("verify", help="Verify backup integrity")
    verify_parser.add_argument("backup_path")
    verify_parser.add_argument("--manifest-path", default=None)
    verify_parser.add_argument("--sha256", default=None)

    smoke_parser = subparsers.add_parser(
        "smoke-test", help="Restore backup in temp dir and validate extraction"
    )
    smoke_parser.add_argument("backup_path")

    cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup old backups")
    cleanup_parser.add_argument("--backup-dir", default="backups")
    cleanup_parser.add_argument("--keep", type=int, default=7)

    args = parser.parse_args()
    command = args.command or "create"

    if command == "create":
        path = create_backup(backup_dir=args.backup_dir)
        if path:
            cleanup_old_backups(backup_dir=args.backup_dir)
            print(path)
            return 0
        return 1
    if command == "verify":
        result = verify_backup_integrity(
            args.backup_path,
            manifest_path=args.manifest_path,
            expected_sha256=args.sha256,
        )
        print(json.dumps(result, indent=2))
        return 0 if bool(result.get("ok")) else 1
    if command == "smoke-test":
        result = run_restore_smoke_test(args.backup_path)
        print(json.dumps(result, indent=2))
        return 0 if bool(result.get("ok")) else 1
    if command == "cleanup":
        cleanup_old_backups(backup_dir=args.backup_dir, keep=max(1, args.keep))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())

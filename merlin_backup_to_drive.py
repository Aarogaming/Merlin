"""Backup Merlin chat history to Google Drive."""

from __future__ import annotations

import datetime
import os
import pickle
import shutil
import tempfile
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from merlin_backup import (
    compute_file_sha256,
    verify_backup_integrity,
    write_backup_integrity_manifest,
)
from merlin_settings import MERLIN_CHAT_HISTORY_DIR

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = os.environ.get("MERLIN_GDRIVE_CREDENTIALS", "credentials.json")
TOKEN_PICKLE = os.environ.get("MERLIN_GDRIVE_TOKEN", "token.pickle")
BACKUP_FOLDER_ID = os.environ.get("MERLIN_GDRIVE_FOLDER_ID", "")


def _get_drive_service():
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(creds, token)
    return build("drive", "v3", credentials=creds)


def _zip_chat_history(chat_dir: Path) -> Path:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_base = Path(tmpdir) / f"merlin_chat_history_{timestamp}"
        zip_path = shutil.make_archive(str(zip_base), "zip", str(chat_dir))
        staged = Path.cwd() / Path(zip_path).name
        shutil.move(zip_path, staged)
        return staged


def backup_chat_history():
    chat_dir = Path(MERLIN_CHAT_HISTORY_DIR)
    if not chat_dir.exists():
        print(f"Chat history directory not found: {chat_dir}")
        return 1

    zip_path = _zip_chat_history(chat_dir)
    checksum = compute_file_sha256(zip_path)
    manifest_path = Path(write_backup_integrity_manifest(zip_path, checksum=checksum))
    verify_result = verify_backup_integrity(zip_path, expected_sha256=checksum)
    if not verify_result.get("ok"):
        print(f"Backup integrity verification failed: {verify_result}")
        if zip_path.exists():
            zip_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()
        return 1

    try:
        service = _get_drive_service()
        metadata = {
            "name": zip_path.name,
            "description": f"sha256={checksum}",
        }
        if BACKUP_FOLDER_ID:
            metadata["parents"] = [BACKUP_FOLDER_ID]
        media = MediaFileUpload(str(zip_path), mimetype="application/zip")
        file = (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
        print(
            f"Uploaded backup: {zip_path.name} "
            f"(file ID: {file.get('id')}, sha256: {checksum})"
        )
        return 0
    finally:
        if zip_path.exists():
            zip_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()


if __name__ == "__main__":
    raise SystemExit(backup_chat_history())

import os
import shutil
import zipfile
from datetime import datetime
from merlin_logger import merlin_logger


def create_backup(backup_dir: str = "backups"):
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"merlin_backup_{timestamp}.zip"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Backup chat history
            chat_dir = "merlin_chat_history"
            if os.path.exists(chat_dir):
                for root, dirs, files in os.walk(chat_dir):
                    for file in files:
                        zipf.write(
                            os.path.join(root, file),
                            os.path.relpath(
                                os.path.join(root, file), os.path.join(chat_dir, "..")
                            ),
                        )

            # Backup logs
            log_dir = "logs"
            if os.path.exists(log_dir):
                for root, dirs, files in os.walk(log_dir):
                    for file in files:
                        zipf.write(
                            os.path.join(root, file),
                            os.path.relpath(
                                os.path.join(root, file), os.path.join(log_dir, "..")
                            ),
                        )

            # Backup tasks
            if os.path.exists("merlin_tasks.json"):
                zipf.write("merlin_tasks.json")

        merlin_logger.info(f"Backup created successfully: {backup_path}")
        return backup_path
    except Exception as e:
        merlin_logger.error(f"Backup failed: {e}")
        return None


def cleanup_old_backups(backup_dir: str = "backups", keep: int = 7):
    try:
        backups = sorted(
            [
                os.path.join(backup_dir, f)
                for f in os.listdir(backup_dir)
                if f.startswith("merlin_backup_")
            ]
        )
        if len(backups) > keep:
            for b in backups[:-keep]:
                os.remove(b)
                merlin_logger.info(f"Removed old backup: {b}")
    except Exception as e:
        merlin_logger.error(f"Backup cleanup failed: {e}")


if __name__ == "__main__":
    path = create_backup()
    if path:
        cleanup_old_backups()

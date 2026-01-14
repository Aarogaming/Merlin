# Merlin Scheduled Backup Script
# This script runs as a background process and backs up chat history every night at 2am.

import time
import subprocess
import datetime

BACKUP_CMD = ['python', 'merlin_backup_to_drive.py']  # Or your backup script
BACKUP_HOUR = 2  # 2am

print('Merlin scheduled backup running. Will back up every day at 2am.')

while True:
    now = datetime.datetime.now()
    if now.hour == BACKUP_HOUR and now.minute == 0:
        print(f'[{now}] Running backup...')
        subprocess.run(BACKUP_CMD)
        time.sleep(60)  # Avoid running multiple times in the same minute
    time.sleep(30)

# Merlin Config Sync Script
# Syncs Merlin config files across devices using a shared cloud folder (e.g., Dropbox, Google Drive, OneDrive)

import shutil
import os

# Path to your Merlin config and the shared sync folder
CONFIG_FILES = ['merlin_resource_config.json', 'merlin_resource_index.json']
SYNC_FOLDER = os.path.expanduser('~/Dropbox/MerlinConfigSync')  # Change to your cloud folder

os.makedirs(SYNC_FOLDER, exist_ok=True)

for fname in CONFIG_FILES:
    if os.path.exists(fname):
        print(f'Syncing {fname} to {SYNC_FOLDER}')
        shutil.copy2(fname, os.path.join(SYNC_FOLDER, fname))
    else:
        print(f'Config file {fname} not found.')

# Merlin Automation Launcher
# This script starts the Merlin backend and a selected client (e.g., Electron desktop) automatically.
# Optionally, it can also trigger a backup after startup.

import subprocess
import sys
import time
import os

# Paths to your backend and client launch commands
BACKEND_CMD = [sys.executable, "merlin_api_server.py"]
CLIENT_CMD = ["npm", "start"]  # Example: Electron app (adjust as needed)
BACKUP_CMD = [sys.executable, "merlin_backup_to_drive.py"]  # Optional

# Start backend
print("Starting Merlin backend...")
backend_proc = subprocess.Popen(BACKEND_CMD)
time.sleep(3)  # Give backend time to start

# Start client
print("Starting Merlin client...")
client_proc = subprocess.Popen(CLIENT_CMD)

# Optional: Run backup after startup
# print('Running backup...')
# subprocess.run(BACKUP_CMD)

try:
    # Wait for either process to exit
    while True:
        if backend_proc.poll() is not None:
            print("Backend exited. Shutting down client.")
            client_proc.terminate()
            break
        if client_proc.poll() is not None:
            print("Client exited. Shutting down backend.")
            backend_proc.terminate()
            break
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")
    backend_proc.terminate()
    client_proc.terminate()

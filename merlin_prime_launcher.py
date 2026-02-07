import subprocess
import sys
import os
import time
import signal
import platform


def launch_component(name, command, cwd=None):
    print(f"🚀 Launching {name}...")
    try:
        # On Windows, use CREATE_NEW_CONSOLE to open in a new window
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = subprocess.CREATE_NEW_CONSOLE

        process = subprocess.Popen(
            command,
            cwd=cwd,
            creationflags=creationflags,
            shell=True if platform.system() == "Windows" else False,
        )
        return process
    except Exception as e:
        print(f"❌ Failed to launch {name}: {e}")
        return None


def main():
    print("=" * 50)
    print("🧙‍♂️ MERLIN PRIME - UNIFIED ASCENSION LAUNCHER")
    print("=" * 50)

    # Determine python path (check for venv)
    python_cmd = sys.executable
    if os.path.exists(".venv/Scripts/python.exe"):
        python_cmd = os.path.abspath(".venv/Scripts/python.exe")
    elif os.path.exists(".venv/bin/python"):
        python_cmd = os.path.abspath(".venv/bin/python")

    processes = []

    # 1. API Server
    processes.append(
        launch_component("API Server", [python_cmd, "merlin_api_server.py"])
    )

    # 2. Librarian Watcher
    processes.append(
        launch_component("Librarian Watcher", [python_cmd, "merlin_watcher.py"])
    )

    # 3. Windows Overlay (The Orb)
    overlay_path = os.path.abspath("../Maelstrom/Client")
    if os.path.exists(overlay_path):
        processes.append(
            launch_component(
                "Windows Overlay", [python_cmd, "merlin_overlay.py"], cwd=overlay_path
            )
        )
    else:
        print("⚠️ Windows Overlay path not found, skipping...")

    print("\n✅ All components requested. Check the new windows for status.")
    print("Press Ctrl+C in this window to stop (Note: child windows may stay open).")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down launcher...")
        # In a more advanced version, we'd kill the subprocesses here
        # but Popen with CREATE_NEW_CONSOLE makes them independent.


if __name__ == "__main__":
    main()

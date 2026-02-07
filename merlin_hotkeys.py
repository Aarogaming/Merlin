import keyboard
import requests
import os
from merlin_logger import merlin_logger

API_URL = "http://localhost:8000/merlin/listen"
API_KEY = os.environ.get("MERLIN_API_KEY", "merlin-secret-key")


def on_hotkey():
    merlin_logger.info("Hotkey pressed! Triggering Merlin listen...")
    try:
        response = requests.post(API_URL, headers={"X-Merlin-Key": API_KEY}, timeout=10)
        if response.status_code == 200:
            text = response.json().get("text")
            if text:
                print(f"Merlin heard: {text}")
            else:
                print("Merlin didn't hear anything.")
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        merlin_logger.error(f"Hotkey trigger failed: {e}")


def start_hotkey_listener():
    # Task 91: Implement Global Hotkeys
    # Default hotkey: Ctrl+Shift+M
    keyboard.add_hotkey("ctrl+shift+m", on_hotkey)
    merlin_logger.info("Hotkey listener started (Ctrl+Shift+M).")
    keyboard.wait()


if __name__ == "__main__":
    start_hotkey_listener()

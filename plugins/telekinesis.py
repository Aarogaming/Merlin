# Merlin Plugin: Telekinesis (Digital Interface Manipulation)
import pyautogui
import pygetwindow as gw
import time
from merlin_logger import merlin_logger

class TelekinesisPlugin:
    def __init__(self):
        self.name = "telekinesis"
        self.description = "Allows Merlin to move windows, control the cursor, and type across the OS."
        self.category = "Automation"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category
        }

    def execute(self, spell_type: str, target: str = "", extra: dict = None):
        merlin_logger.info(f"Merlin exercising telekinetic power: {spell_type} on {target}")

        try:
            if spell_type == "accio":
                # Bring a window to the front
                windows = gw.getWindowsWithTitle(target)
                if windows:
                    windows[0].activate()
                    return {"output": f"Accio {target}! The window has been summoned to the front."}
                return {"error": f"I cannot find a window titled '{target}'."}

            elif spell_type == "wingardium_leviosa":
                # Move or resize a window
                windows = gw.getWindowsWithTitle(target)
                if windows and extra:
                    win = windows[0]
                    x = extra.get("x", win.left)
                    y = extra.get("y", win.top)
                    win.moveTo(x, y)
                    return {"output": f"Wingardium Leviosa! I have shifted {target} to coordinates ({x}, {y})."}
                return {"error": "Window not found or missing coordinates."}

            elif spell_type == "imperio":
                # Force typing or clicking
                if extra and "text" in extra:
                    pyautogui.write(extra["text"], interval=0.1)
                    return {"output": f"Imperio! I have manifested your words into the active field."}
                elif extra and "click" in extra:
                    pyautogui.click()
                    return {"output": "Imperio! I have executed a physical click at the current focus."}
                return {"error": "No text or action specified for Imperio."}

            elif spell_type == "confundo":
                # Shake the cursor (useful for a 'wake up' or alert)
                for _ in range(5):
                    pyautogui.moveRel(10, 0, duration=0.1)
                    pyautogui.moveRel(-10, 0, duration=0.1)
                return {"output": "Confundo! I have rattled the digital focus."}

            else:
                return {"error": f"Unknown telekinetic spell: {spell_type}"}

        except Exception as e:
            merlin_logger.error(f"Telekinesis Error: {e}")
            return {"error": f"My mental grip slipped: {str(e)}"}

def get_plugin():
    return TelekinesisPlugin()

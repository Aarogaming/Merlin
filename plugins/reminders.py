import json
import os
from datetime import datetime
from merlin_plugin_manager import MerlinPlugin

class RemindersPlugin(MerlinPlugin):
    def __init__(self):
        super().__init__(
            name="Reminders",
            description="Manage personal reminders and todos",
            version="1.0.0",
            author="Merlin Core"
        )
        self.reminders_file = "merlin_reminders.json"

    def _load_reminders(self):
        if os.path.exists(self.reminders_file):
            with open(self.reminders_file, "r") as f:
                return json.load(f)
        return []

    def _save_reminders(self, reminders):
        with open(self.reminders_file, "w") as f:
            json.dump(reminders, f, indent=2)

    def execute(self, action: str = "list", text: str | None = None, due: str | None = None):
        reminders = self._load_reminders()
        
        if action == "add":
            reminder = {
                "id": len(reminders) + 1,
                "text": text,
                "due": due,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            reminders.append(reminder)
            self._save_reminders(reminders)
            return {"status": "added", "reminder": reminder}
            
        elif action == "list":
            return reminders
            
        elif action == "complete":
            # text here would be the ID
            for r in reminders:
                if str(r["id"]) == str(text):
                    r["status"] = "completed"
                    self._save_reminders(reminders)
                    return {"status": "completed", "reminder": r}
            return {"error": "Reminder not found"}
            
        return {"error": "Invalid action"}

def get_plugin():
    return RemindersPlugin()

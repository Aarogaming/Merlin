import json
import os
from datetime import datetime
from typing import List, Dict, Any
from merlin_logger import merlin_logger

class MerlinTaskManager:
    def __init__(self, tasks_file="merlin_tasks.json"):
        self.tasks_file = tasks_file
        self.tasks = self._load_tasks()

    def _load_tasks(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                merlin_logger.error(f"Failed to load tasks: {e}")
        return []

    def _save_tasks(self):
        try:
            with open(self.tasks_file, "w") as f:
                json.dump(self.tasks, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save tasks: {e}")

    def add_task(self, title: str, description: str, priority: str = "Medium") -> Dict[str, Any]:
        task = {
            "id": len(self.tasks) + 1,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "Pending",
            "created_at": datetime.now().isoformat()
        }
        self.tasks.append(task)
        self._save_tasks()
        merlin_logger.info(f"Added local task: {title}")
        return task

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.tasks

    def update_task_status(self, task_id: int, status: str):
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                self._save_tasks()
                merlin_logger.info(f"Updated task {task_id} status to {status}")
                return True
        return False

task_manager = MerlinTaskManager()

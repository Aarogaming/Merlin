# Merlin Plugin: Tasks
from typing import Any

from merlin_tasks import task_manager


class MerlinTasksPlugin:
    def __init__(self):
        self.name = "tasks"
        self.description = "Manage Merlin local tasks."
        self.version = "1.0.0"
        self.author = "AAS"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, action: str, **kwargs: Any):
        if not action:
            return {"error": "action_required", "actions": ["list", "add", "update"]}
        action = str(action).strip().lower()
        if action == "list":
            return {"tasks": task_manager.list_tasks()}
        if action == "add":
            title = kwargs.get("title")
            description = kwargs.get("description") or ""
            priority = kwargs.get("priority") or "Medium"
            if not title:
                return {"error": "title_required"}
            task = task_manager.add_task(title, description, priority=priority)
            return {"task": task}
        if action == "update":
            task_id = kwargs.get("task_id")
            status = kwargs.get("status")
            if task_id is None or status is None:
                return {"error": "task_id_and_status_required"}
            ok = task_manager.update_task_status(int(task_id), str(status))
            return {"ok": bool(ok)}
        return {"error": "unsupported_action", "action": action}


def get_plugin():
    return MerlinTasksPlugin()

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Callable
from merlin_logger import merlin_logger
from manager_health_protocol import (
    HealthCheckResult,
    HealthStatus,
    LifecycleState,
    LifecycleStateMixin,
    StatusPayloadBuilder,
)


class MerlinTaskManager(LifecycleStateMixin):
    def __init__(self, tasks_file="merlin_tasks.json"):
        LifecycleStateMixin.__init__(self)
        self._transition_state(LifecycleState.STARTING)
        self.tasks_file = tasks_file
        self.tasks = self._load_tasks()
        self._cancel_hooks: dict[int, Callable[[], None]] = {}
        self._transition_state(LifecycleState.RUNNING)

    def get_status(self) -> Dict:
        """Return standardised status payload."""
        return (
            StatusPayloadBuilder("MerlinTaskManager")
            .with_lifecycle_state(self._lifecycle_state)
            .with_health_status(
                HealthStatus.HEALTHY if self.is_running() else HealthStatus.DEGRADED
            )
            .with_metrics({
                "task_count": len(self.tasks),
                "tasks_file": self.tasks_file,
            })
            .build()
        )

    def health_check(self) -> HealthCheckResult:
        """Return a named-check health report."""
        is_running = self.is_running()
        tasks_list_ok = isinstance(self.tasks, list)
        all_ok = is_running and tasks_list_ok
        return HealthCheckResult(
            status=HealthStatus.HEALTHY if all_ok else HealthStatus.DEGRADED,
            is_healthy=all_ok,
            message="MerlinTaskManager is operational" if all_ok else "One or more checks failed",
            checks={
                "lifecycle_running": is_running,
                "tasks_list_ok": tasks_list_ok,
            },
        )

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

    def add_task(
        self, title: str, description: str, priority: str = "Medium"
    ) -> Dict[str, Any]:
        task = {
            "id": len(self.tasks) + 1,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "Pending",
            "created_at": datetime.now().isoformat(),
        }
        self.tasks.append(task)
        self._save_tasks()
        merlin_logger.info(f"Added local task: {title}")
        return task

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.tasks

    def get_task(self, task_id: int) -> Dict[str, Any] | None:
        for task in self.tasks:
            if task.get("id") == task_id:
                return task
        return None

    def list_tasks_by_ids(self, task_ids: List[int]) -> List[Dict[str, Any]]:
        ordered: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for raw_task_id in task_ids:
            if not isinstance(raw_task_id, int) or raw_task_id <= 0:
                continue
            if raw_task_id in seen:
                continue
            seen.add(raw_task_id)
            task = self.get_task(raw_task_id)
            if task is not None:
                ordered.append(task)
        return ordered

    def update_task_status(self, task_id: int, status: str):
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                self._save_tasks()
                merlin_logger.info(f"Updated task {task_id} status to {status}")
                return True
        return False

    def register_cancellation_hook(
        self, task_id: int, cancel_hook: Callable[[], None]
    ) -> bool:
        if not isinstance(task_id, int) or task_id <= 0:
            return False
        if not callable(cancel_hook):
            return False
        self._cancel_hooks[task_id] = cancel_hook
        return True

    def clear_cancellation_hook(self, task_id: int) -> None:
        self._cancel_hooks.pop(task_id, None)

    def cancel_task(self, task_id: int) -> bool:
        hook = self._cancel_hooks.pop(task_id, None)
        hook_invoked = False
        if hook is not None:
            try:
                hook()
                hook_invoked = True
            except Exception as exc:
                merlin_logger.error(f"Failed to cancel task {task_id}: {exc}")
        updated = self.update_task_status(task_id, "Cancelled")
        return hook_invoked or updated


task_manager = MerlinTaskManager()

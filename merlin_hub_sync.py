import time
import os
from merlin_hub_client import MerlinHubClient
from merlin_logger import merlin_logger
from merlin_tasks import task_manager


class MerlinHubSync:
    def __init__(self):
        self.client = MerlinHubClient()
        self.sync_interval = int(os.getenv("MERLIN_SYNC_INTERVAL", "60"))

    def send_heartbeat(self):
        merlin_logger.info("Sending heartbeat to AAS Hub...")
        has_bridge = any(
            getattr(self.client, attr_name, None) is not None
            for attr_name in ("bridge_client", "grpc_client")
        )
        if not has_bridge:
            merlin_logger.warning(
                "Heartbeat skipped: Hub client gRPC channel unavailable"
            )
            return False
        return True

    def sync_tasks(self):
        merlin_logger.info("Syncing tasks with AAS Hub...")
        # 1. Push local tasks to Hub
        local_tasks = task_manager.list_tasks()
        for task in local_tasks:
            if task.get("hub_id") is None:
                hub_id = self.client.create_aas_task(
                    title=task["title"],
                    description=task["description"],
                    priority=task["priority"],
                )
                if hub_id:
                    task["hub_id"] = hub_id
                    task_manager._save_tasks()
                    merlin_logger.info(f"Synced task {task['id']} to Hub as {hub_id}")

    def run_forever(self):
        merlin_logger.info(
            f"Starting Hub Sync Service (Interval: {self.sync_interval}s)"
        )
        while True:
            try:
                self.send_heartbeat()
                self.sync_tasks()
            except Exception as e:
                merlin_logger.error(f"Sync error: {e}")
            time.sleep(self.sync_interval)


if __name__ == "__main__":
    sync_service = MerlinHubSync()
    sync_service.run_forever()

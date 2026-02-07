import time
import requests
import subprocess
import sys
from merlin_logger import merlin_logger


class MerlinSelfHealing:
    def __init__(self, api_url="http://localhost:8000/health"):
        self.api_url = api_url
        self.check_interval = 30
        self.restart_count = 0

    def check_health(self) -> bool:
        try:
            response = requests.get(self.api_url, timeout=5)
            if response.status_code == 200:
                return True
            return False
        except Exception:
            return False

    def restart_service(self):
        merlin_logger.warning(
            "Self-Healing: API Server appears down. Attempting restart..."
        )
        try:
            # In a real scenario, we might use systemd or a process manager
            # Here we'll try to launch it via the unified launcher
            subprocess.Popen([sys.executable, "merlin_launcher.py"])
            self.restart_count += 1
            merlin_logger.info(
                f"Self-Healing: Restart attempt {self.restart_count} initiated."
            )
        except Exception as e:
            merlin_logger.error(f"Self-Healing: Restart failed: {e}")

    def run_forever(self):
        merlin_logger.info("Starting Merlin Self-Healing Service...")
        while True:
            if not self.check_health():
                self.restart_service()
            else:
                if self.restart_count > 0:
                    merlin_logger.info("Self-Healing: Service is back online.")
                    self.restart_count = 0
            time.sleep(self.check_interval)


if __name__ == "__main__":
    healer = MerlinSelfHealing()
    healer.run_forever()

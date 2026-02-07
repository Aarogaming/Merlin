import psutil
import platform
from merlin_plugin_manager import MerlinPlugin


class SystemMonitorPlugin(MerlinPlugin):
    def __init__(self):
        super().__init__("System Monitor")
        self.description = "Provides real-time system performance metrics"
        self.version = "1.0.0"
        self.author = "Merlin Core"

    def execute(self, *args, **kwargs):
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "percent": psutil.virtual_memory().percent,
            },
            "disk": {
                "total": psutil.disk_usage("/").total,
                "used": psutil.disk_usage("/").used,
                "free": psutil.disk_usage("/").free,
                "percent": psutil.disk_usage("/").percent,
            },
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        }


def get_plugin():
    return SystemMonitorPlugin()

import platform
import socket
import os

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency.
    psutil = None


def get_system_info():
    info = {}
    try:
        # OS Info
        info["os"] = platform.system()
        info["os_release"] = platform.release()
        info["os_version"] = platform.version()
        info["architecture"] = platform.machine()
        info["hostname"] = socket.gethostname()

        if psutil is not None:
            info["cpu_count"] = psutil.cpu_count(logical=True)
            info["cpu_usage_percent"] = psutil.cpu_percent(interval=1)

            mem = psutil.virtual_memory()
            info["memory_total_gb"] = round(mem.total / (1024**3), 2)
            info["memory_available_gb"] = round(mem.available / (1024**3), 2)
            info["memory_usage_percent"] = mem.percent

            disk = psutil.disk_usage("/")
            info["disk_total_gb"] = round(disk.total / (1024**3), 2)
            info["disk_free_gb"] = round(disk.free / (1024**3), 2)
            info["disk_usage_percent"] = disk.percent

            net = psutil.net_if_addrs()
            info["network_interfaces"] = list(net.keys())
        else:
            info["cpu_count"] = os.cpu_count() or 0
            info["cpu_usage_percent"] = None
            info["memory_total_gb"] = None
            info["memory_available_gb"] = None
            info["memory_usage_percent"] = None
            info["disk_total_gb"] = None
            info["disk_free_gb"] = None
            info["disk_usage_percent"] = None
            info["network_interfaces"] = []
            info["psutil_available"] = False

    except Exception as e:
        info["error"] = str(e)

    return info


if __name__ == "__main__":
    import json

    print(json.dumps(get_system_info(), indent=2))

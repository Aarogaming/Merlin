# Merlin Plugin: Scrying (System Visibility)
import os
import psutil
from merlin_logger import merlin_logger


class ScryingPlugin:
    def __init__(self):
        self.name = "scrying"
        self.description = "Allows Merlin to see what processes are running and 'spy' on system resources."
        self.category = "Intelligence"

    def execute(self, spell_type: str, target: str = ""):
        merlin_logger.info(f"Merlin invoking Scrying: {spell_type}")

        try:
            if spell_type == "scry_processes":
                # List top 5 CPU consuming processes
                procs = sorted(
                    psutil.process_iter(["name", "cpu_percent"]),
                    key=lambda x: x.info["cpu_percent"],
                    reverse=True,
                )[:5]
                p_list = [f"{p.info['name']} ({p.info['cpu_percent']}%)" for p in procs]
                return {
                    "output": f"Scrying complete! I see these entities draining your energy: {', '.join(p_list)}"
                }

            elif spell_type == "scry_network":
                # Check for active connections
                conns = len(psutil.net_connections())
                return {
                    "output": f"The digital winds are busy. I detect {conns} active threads weaving through your gateway."
                }

            else:
                return {"error": f"Unknown Scrying spell: {spell_type}"}

        except Exception as e:
            return {"error": f"The scrying pool is dark: {str(e)}"}


def get_plugin():
    return ScryingPlugin()

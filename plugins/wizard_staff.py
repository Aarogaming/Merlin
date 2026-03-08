# Merlin Plugin: The Wizard's Staff (Universal Orchestrator)
import os
import subprocess
from merlin_logger import merlin_logger


class WizardStaff:
    def __init__(self):
        self.name = "wizard_staff"
        self.description = "The core orchestrator tool. Can cast 'spells' (AAS scripts) and manage the Dev Library."
        self.version = "1.0.0"
        self.author = "Creator"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, spell_type: str, target: str = ""):
        """Executes various 'spells' (automation tasks)."""
        merlin_logger.info(
            f"Merlin raising his staff for spell: {spell_type} on {target}"
        )

        if spell_type == "revelio":
            # Reveal details about a project or file
            return self._revelio(target)
        elif spell_type == "scourgify":
            # Clean up temporary files/build artifacts
            return self._scourgify(target)
        elif spell_type == "alohomora":
            # Open/Unlock a specific tool or project
            return self._alohomora(target)
        elif spell_type == "finite_incantatem":
            # Stop all running background processes (Hub/Gateway)
            return self._finite_incantatem()
        else:
            return {"error": f"Unknown spell: {spell_type}"}

    def _revelio(self, target):
        # Use relative path or environment variable
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        path = os.path.join(base_dir, target)
        if os.path.exists(path):
            files = os.listdir(path)[:10]
            return {
                "output": f"Revelio! I see these files in {target}: {', '.join(files)}"
            }
        return {"error": "Path not found in Dev Library."}

    def _scourgify(self, target):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        base = os.path.abspath(
            os.path.join(
                base_dir, target or "artifacts"
            )
        )
        if not os.path.exists(base):
            return {"error": f"Path not found: {base}"}

        removed = []
        errors = []
        removable_names = {"__pycache__", ".pytest_cache", ".ruff_cache"}
        removable_suffixes = (".tmp", ".temp", ".log")

        for root, dirs, files in os.walk(base, topdown=False):
            for filename in files:
                file_path = os.path.join(root, filename)
                if not filename.lower().endswith(removable_suffixes):
                    continue
                try:
                    os.remove(file_path)
                    removed.append(file_path)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{file_path}: {exc}")

            for dirname in dirs:
                if dirname not in removable_names:
                    continue
                dir_path = os.path.join(root, dirname)
                try:
                    import shutil

                    shutil.rmtree(dir_path, ignore_errors=False)
                    removed.append(dir_path)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{dir_path}: {exc}")

        return {
            "output": f"Scourgify complete in {base}",
            "removed_count": len(removed),
            "errors": errors,
            "removed_sample": removed[:20],
        }

    def _alohomora(self, target):
        # Open a project folder in explorer or VS Code
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        path = os.path.abspath(
            os.path.join(base_dir, target)
        )
        if os.path.exists(path):
            os.startfile(path)
            return {"output": f"Alohomora! The doors to {target} are open."}
        return {"error": "Cannot find the lock for this path."}

    def _finite_incantatem(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        pid_files = [
            os.path.join(base_dir, "artifacts/opencode.pid"),
            os.path.join(base_dir, "artifacts/hub.pid"),
        ]
        commands = []
        for pid_file in pid_files:
            if not os.path.exists(pid_file):
                continue
            try:
                with open(pid_file, "r", encoding="utf-8") as handle:
                    pid_value = handle.read().strip()
                if pid_value.isdigit():
                    commands.append(["taskkill", "/F", "/PID", pid_value])
            except Exception as exc:  # noqa: BLE001
                commands.append(["cmd", "/c", f"rem failed to read {pid_file}: {exc}"])

        results = []
        if not commands:
            return {
                "output": "Finite Incantatem complete. No known PID files found.",
                "commands": [],
            }

        for cmd in commands:
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                results.append(
                    {
                        "command": " ".join(cmd),
                        "returncode": completed.returncode,
                        "stdout": (completed.stdout or "").strip()[-400:],
                        "stderr": (completed.stderr or "").strip()[-400:],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "command": " ".join(cmd),
                        "error": str(exc),
                    }
                )

        return {
            "output": "Finite Incantatem complete.",
            "commands": results,
        }


def get_plugin():
    return WizardStaff()

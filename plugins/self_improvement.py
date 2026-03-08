# Merlin Plugin: Self-Improvement (The Architect's Tools)
import os
import subprocess
from merlin_logger import merlin_logger

class SelfImprovement:
    def __init__(self):
        self.name = "self_improvement"
        self.description = "Tools for Merlin to read, write, and test code for self-evolution."
        self.version = "1.0.0"
        self.author = "Merlin"
        # Base directory is the root of the Dev Library (3 levels up from Merlin/plugins)
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, action: str, **kwargs):
        """Executes self-improvement actions."""
        merlin_logger.info(f"Merlin executing self-improvement action: {action}")

        if action == "read_file":
            return self._read_file(kwargs.get("path"))
        elif action == "write_file":
            return self._write_file(kwargs.get("path"), kwargs.get("content"))
        elif action == "list_files":
            return self._list_files(kwargs.get("path"))
        elif action == "run_command":
            return self._run_command(kwargs.get("command"))
        elif action == "run_test":
            return self._run_test(kwargs.get("test_path"))
        else:
            return {"error": f"Unknown action: {action}"}

    def _resolve_path(self, path):
        if not path:
            raise ValueError("Path is required.")
        # Prevent escaping the Dev Library
        full_path = os.path.abspath(os.path.join(self.base_dir, path))
        if not full_path.startswith(self.base_dir):
            raise ValueError(f"Access denied: {path} is outside the Dev Library.")
        return full_path

    def _read_file(self, path):
        try:
            full_path = self._resolve_path(path)
            if not os.path.exists(full_path):
                return {"error": f"File not found: {path}"}
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"path": path, "content": content}
        except Exception as e:
            return {"error": str(e)}

    def _write_file(self, path, content):
        try:
            full_path = self._resolve_path(path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "path": path, "message": "File written successfully."}
        except Exception as e:
            return {"error": str(e)}

    def _list_files(self, path):
        try:
            full_path = self._resolve_path(path or ".")
            if not os.path.exists(full_path):
                return {"error": f"Path not found: {path}"}
            items = os.listdir(full_path)
            return {"path": path, "items": items}
        except Exception as e:
            return {"error": str(e)}

    def _run_command(self, command):
        try:
            # Run command in the base directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"error": str(e)}

    def _run_test(self, test_path):
        # Wrapper around pytest or dotnet test depending on file extension
        if not test_path:
            return {"error": "test_path is required"}
        
        if test_path.endswith(".py") or os.path.isdir(os.path.join(self.base_dir, test_path)):
            cmd = f"pytest {test_path}"
        elif test_path.endswith(".csproj") or test_path.endswith(".sln"):
            cmd = f"dotnet test {test_path}"
        else:
            return {"error": "Unknown test type. Provide .py, .csproj, or .sln"}

        return self._run_command(cmd)

def get_plugin():
    return SelfImprovement()

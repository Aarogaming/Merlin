import subprocess
import os

SAFE_MODE = os.environ.get("MERLIN_SAFE_MODE", "false").lower() == "true"
COMMAND_ALLOWLIST = os.environ.get(
    "MERLIN_COMMAND_ALLOWLIST", "dir,ls,pwd,whoami,echo"
).split(",")


def execute_command(command):
    # Task 35: Conduct a security audit of the subprocess.run usage.
    # Switching to shell=False and using a list of arguments to prevent shell injection.
    import shlex

    args = shlex.split(command)
    if not args:
        return {"error": "Empty command."}

    base_cmd = args[0]
    if base_cmd not in COMMAND_ALLOWLIST:
        return {"error": f"Command '{base_cmd}' is not in the allowlist."}
    if SAFE_MODE:
        return {"error": "Command execution is disabled in Safe Mode."}
    try:
        # Run command and capture output
        result = subprocess.run(
            args, shell=False, capture_output=True, text=True, timeout=30
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(execute_command(cmd))
    else:
        print(execute_command("dir"))

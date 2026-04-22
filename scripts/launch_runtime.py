import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_runtime_env(repo_root: Path, env_path_arg: str | None) -> tuple[Path, dict]:
    env_path = Path(env_path_arg).resolve() if env_path_arg else (repo_root / "runtime" / "runtime_env.json").resolve()
    if not env_path.exists():
        raise FileNotFoundError(f"Runtime env not found: {env_path}")
    with open(env_path, "r", encoding="utf-8") as f:
        return env_path, json.load(f)


def _boot_script(repo_root: Path, script_arg: str | None) -> Path:
    if script_arg:
        return Path(script_arg).resolve()
    return (repo_root / "scripts" / "boot.py").resolve()


def _compose_env(runtime_env: dict, isolated: bool) -> dict:
    base_env = {} if isolated else dict(os.environ)
    py_path_entries = [str(p) for p in runtime_env.get("pythonpath_prepend", []) if str(p).strip()]
    existing = base_env.get("PYTHONPATH", "")
    joined = os.pathsep.join(py_path_entries + ([existing] if existing else []))

    base_env["PYTHONPATH"] = joined
    if runtime_env.get("nats_bin"):
        base_env["AAS_NATS_BIN"] = str(runtime_env.get("nats_bin"))
    return base_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch AAS with local runtime_env package isolation.")
    parser.add_argument("--repo-path", default=str(ROOT), help="Path to repository root")
    parser.add_argument("--env-path", help="Path to runtime/runtime_env.json")
    parser.add_argument("--script", help="Script path to launch (default scripts/boot.py)")
    parser.add_argument("--bootstrap-if-missing", action="store_true", help="Run bootstrap_runtime.py --mode install when runtime env is missing")
    parser.add_argument("--isolated", action="store_true", help="Use mostly clean process env (local runtime focused)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to launched script")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    try:
        env_path = Path(args.env_path).resolve() if args.env_path else (repo_root / "runtime" / "runtime_env.json").resolve()
        if not env_path.exists() and args.bootstrap_if_missing:
            bootstrap = (repo_root / "scripts" / "bootstrap_runtime.py").resolve()
            subprocess.run([str(sys.executable), str(bootstrap), "--repo-path", str(repo_root), "--mode", "install"], check=True)

        runtime_env_path, runtime_env = _load_runtime_env(repo_root, str(env_path))
        python_exe = Path(runtime_env.get("python_executable", sys.executable)).resolve()
        script = _boot_script(repo_root, args.script)
        if not script.exists():
            raise FileNotFoundError(f"Launch script not found: {script}")

        launch_env = _compose_env(runtime_env, isolated=args.isolated)
        forwarded = args.args or []
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]

        command = [str(python_exe), str(script)] + forwarded
        print(json.dumps({
            "runtime_env": str(runtime_env_path),
            "python_executable": str(python_exe),
            "script": str(script),
            "command": command,
        }, indent=2))
        result = subprocess.run(command, env=launch_env)
        return int(result.returncode)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

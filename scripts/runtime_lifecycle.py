import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent


def _script(name: str) -> Path:
    path = (SCRIPT_DIR / name).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Required script not found: {path}")
    return path


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def _manifest_path(repo_root: Path, manifest_arg: str | None) -> Path:
    if manifest_arg:
        return Path(manifest_arg).resolve()
    return (repo_root / "runtime.manifest.json").resolve()


def _status(repo_root: Path, manifest_arg: str | None) -> int:
    manifest_path = _manifest_path(repo_root, manifest_arg)
    runtime_env = (repo_root / "runtime" / "runtime_env.json").resolve()

    report = {
        "repo_root": str(repo_root),
        "manifest": {
            "path": str(manifest_path),
            "exists": manifest_path.exists(),
        },
        "runtime": {
            "runtime_env": {
                "path": str(runtime_env),
                "exists": runtime_env.exists(),
            }
        },
    }

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            report["manifest"]["error"] = str(exc)
            print(json.dumps(report, indent=2))
            return 1

        deps = manifest.get("dependencies", {})
        wheelhouse = (repo_root / str(deps.get("wheelhouse_dir", "runtime/wheelhouse"))).resolve()
        lock_file = (repo_root / str(deps.get("wheelhouse_lock_file", "runtime/wheelhouse.lock.json"))).resolve()
        install_target = (repo_root / str(deps.get("install_target_dir", "runtime/site-packages"))).resolve()

        report["runtime"].update(
            {
                "wheelhouse": {
                    "path": str(wheelhouse),
                    "exists": wheelhouse.exists(),
                },
                "wheelhouse_lock": {
                    "path": str(lock_file),
                    "exists": lock_file.exists(),
                },
                "site_packages": {
                    "path": str(install_target),
                    "exists": install_target.exists(),
                },
                "policy": {
                    "myfortress_ready": bool(manifest.get("security_ops_adapters", {}).get("myfortress_ready", False)),
                    "local_policy_fallback": str(manifest.get("security_ops_adapters", {}).get("local_policy_fallback", "deny")),
                    "security_hardening": manifest.get("spectrums", {}).get("security_hardening"),
                },
            }
        )

    print(json.dumps(report, indent=2))
    return 0


def _toggle_headless(repo_root: Path) -> int:
    env_path = repo_root / "runtime" / "runtime_env.json"
    if not env_path.exists():
        print("Runtime environment not found. Please install the runtime first.")
        return 1
    try:
        data = json.loads(env_path.read_text(encoding="utf-8"))
        current = bool(data.get("headless", False))
        data["headless"] = not current
        env_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Headless mode set to: {not current}")
        return 0
    except Exception as exc:
        print(f"Failed to toggle headless mode: {exc}")
        return 1


def _menu(repo_root: Path, manifest_arg: str | None, build_script: Path, bootstrap_script: Path, launch_script: Path) -> int:
    common = ["--repo-path", str(repo_root)]
    if manifest_arg:
        common.extend(["--manifest", str(Path(manifest_arg).resolve())])

    self_prefix = [str(sys.executable), str(__file__), "--repo-path", str(repo_root)]
    if manifest_arg:
        self_prefix.extend(["--manifest", str(Path(manifest_arg).resolve())])

    actions = {
        "1": ("Status", self_prefix + ["status"]),
        "2": ("Build Wheelhouse", [str(sys.executable), str(build_script)] + common),
        "3": ("Install Runtime", [str(sys.executable), str(bootstrap_script)] + common + ["--mode", "install"]),
        "4": ("Verify Runtime", [str(sys.executable), str(bootstrap_script)] + common + ["--mode", "verify"]),
        "5": ("Update (Build+Install)", self_prefix + ["update"]),
        "6": ("Launch", [str(sys.executable), str(launch_script), "--repo-path", str(repo_root), "--bootstrap-if-missing"]),
    }

    while True:
        print("\n=== AAS Runtime Lifecycle Menu ===")
        print("1) Status")
        print("2) Build Wheelhouse")
        print("3) Install Runtime")
        print("4) Verify Runtime")
        print("5) Update (Build + Install)")
        print("6) Launch")
        print("7) Dry-Run Update")
        print("8) Custom Command")
        print("T) Toggle Headless Mode")
        print("9) Exit")

        choice = input("Select an option [1-9, T]: ").strip()
        if choice == "9":
            return 0
        if choice.upper() == "T":
            _toggle_headless(repo_root)
            continue
        if choice == "7":
            cmd = self_prefix + ["update", "--dry-run"]
            rc = _run(cmd)
            print(f"[menu] command exit code: {rc}")
            continue
        if choice == "8":
            raw = input("Enter arguments after runtime_lifecycle.py (example: install --dry-run): ").strip()
            if not raw:
                continue
            extra = shlex.split(raw)
            cmd = list(self_prefix)
            cmd.extend(extra)
            rc = _run(cmd)
            print(f"[menu] command exit code: {rc}")
            continue

        action = actions.get(choice)
        if not action:
            print("Invalid choice.")
            continue

        label, cmd = action
        print(f"\n[menu] Running: {label}")
        rc = _run(cmd)
        print(f"[menu] command exit code: {rc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified local AAS runtime lifecycle orchestration.")
    parser.add_argument("--repo-path", default=str(ROOT), help="Path to repository root")
    parser.add_argument("--manifest", help="Path to runtime manifest (default runtime.manifest.json)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build wheelhouse (and lock by default)")
    p_build.add_argument("--dry-run", action="store_true", help="Show command only")
    p_build.add_argument("--no-deps", action="store_true", help="Top-level requirements only")
    p_build.add_argument("--skip-lock", action="store_true", help="Do not write lock file")

    p_install = sub.add_parser("install", help="Bootstrap local runtime dependency install")
    p_install.add_argument("--dry-run", action="store_true", help="Show plan only")
    p_install.add_argument("--skip-policy-gate", action="store_true", help="Bypass MyFortress policy gate")

    sub.add_parser("verify", help="Verify runtime imports using runtime policy")

    p_launch = sub.add_parser("launch", help="Launch AAS through runtime env")
    p_launch.add_argument("--env-path", help="Path to runtime/runtime_env.json")
    p_launch.add_argument("--script", help="Script to launch (default scripts/boot.py)")
    p_launch.add_argument("--bootstrap-if-missing", action="store_true", help="Bootstrap runtime first if env missing")
    p_launch.add_argument("--isolated", action="store_true", help="Use mostly clean env")
    p_launch.add_argument("args", nargs=argparse.REMAINDER, help="Arguments forwarded to launch script")

    p_update = sub.add_parser("update", help="Build wheelhouse then install runtime")
    p_update.add_argument("--dry-run", action="store_true", help="Show plan only")
    p_update.add_argument("--no-deps", action="store_true", help="Top-level requirements only when building wheels")
    p_update.add_argument("--skip-lock", action="store_true", help="Do not write lock file")
    p_update.add_argument("--skip-policy-gate", action="store_true", help="Bypass MyFortress policy gate for install")

    sub.add_parser("status", help="Show runtime bundle and policy status")
    sub.add_parser("menu", help="Interactive runtime lifecycle menu")

    p_start = sub.add_parser("start", help="Auto-start based on headless preference")
    p_start.add_argument("--headless", action="store_true", help="Force headless launch")
    p_start.add_argument("--menu", action="store_true", help="Force menu launch")

    args = parser.parse_args()
    repo_root = Path(args.repo_path).resolve()

    build_script = _script("build_runtime_wheelhouse.py")
    bootstrap_script = _script("bootstrap_runtime.py")
    launch_script = _script("launch_runtime.py")

    common = ["--repo-path", str(repo_root)]
    if args.manifest:
        common.extend(["--manifest", str(Path(args.manifest).resolve())])

    if args.command == "build":
        cmd = [str(sys.executable), str(build_script)] + common
        if args.dry_run:
            cmd.append("--dry-run")
        if args.no_deps:
            cmd.append("--no-deps")
        if args.skip_lock:
            cmd.append("--skip-lock")
        return _run(cmd)

    if args.command == "install":
        cmd = [str(sys.executable), str(bootstrap_script)] + common + ["--mode", "install"]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.skip_policy_gate:
            cmd.append("--skip-policy-gate")
        return _run(cmd)

    if args.command == "verify":
        cmd = [str(sys.executable), str(bootstrap_script)] + common + ["--mode", "verify"]
        return _run(cmd)

    if args.command == "launch":
        cmd = [str(sys.executable), str(launch_script), "--repo-path", str(repo_root)]
        if args.env_path:
            cmd.extend(["--env-path", str(Path(args.env_path).resolve())])
        if args.script:
            cmd.extend(["--script", str(Path(args.script).resolve())])
        if args.bootstrap_if_missing:
            cmd.append("--bootstrap-if-missing")
        if args.isolated:
            cmd.append("--isolated")
        if args.args:
            cmd.extend(args.args)
        return _run(cmd)

    if args.command == "update":
        build_cmd = [str(sys.executable), str(build_script)] + common
        if args.dry_run:
            build_cmd.append("--dry-run")
        if args.no_deps:
            build_cmd.append("--no-deps")
        if args.skip_lock:
            build_cmd.append("--skip-lock")
        rc = _run(build_cmd)
        if rc != 0:
            return rc

        install_cmd = [str(sys.executable), str(bootstrap_script)] + common + ["--mode", "install"]
        if args.dry_run:
            install_cmd.append("--dry-run")
        if args.skip_policy_gate:
            install_cmd.append("--skip-policy-gate")
        return _run(install_cmd)

    if args.command == "status":
        return _status(repo_root, args.manifest)

    if args.command == "menu":
        return _menu(repo_root, args.manifest, build_script, bootstrap_script, launch_script)

    if args.command == "start":
        is_headless = False
        if args.headless:
            is_headless = True
        elif args.menu:
            is_headless = False
        else:
            env_path = repo_root / "runtime" / "runtime_env.json"
            if env_path.exists():
                try:
                    data = json.loads(env_path.read_text(encoding="utf-8"))
                    is_headless = bool(data.get("headless", False))
                except Exception:
                    pass
        
        if is_headless:
            print("[AAS] Launching in Headless Mode...")
            cmd = [str(sys.executable), str(__file__), "--repo-path", str(repo_root), "launch", "--bootstrap-if-missing"]
            if args.manifest:
                cmd.extend(["--manifest", str(Path(args.manifest).resolve())])
            return _run(cmd)
        else:
            print("[AAS] Launching Interactive Menu...")
            return _menu(repo_root, args.manifest, build_script, bootstrap_script, launch_script)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

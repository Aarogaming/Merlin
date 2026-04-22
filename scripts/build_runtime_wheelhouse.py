import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_manifest(repo_root: Path, manifest_arg: str | None) -> tuple[Path, dict]:
    path = Path(manifest_arg).resolve() if manifest_arg else (repo_root / "runtime.manifest.json").resolve()
    if not path.exists():
        raise FileNotFoundError(f"Runtime manifest not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return path, json.load(f)


def _resolve_python(repo_root: Path, manifest: dict) -> Path:
    py_cfg = manifest.get("python", {})
    embedded = (repo_root / str(py_cfg.get("executable_relpath", "runtime/python/python.exe"))).resolve()
    if embedded.exists():
        return embedded
    return Path(sys.executable).resolve()


def _wheelhouse_command(repo_root: Path, manifest: dict, python_exe: Path, include_deps: bool) -> list[str]:
    deps = manifest.get("dependencies", {})
    requirements = (repo_root / str(deps.get("requirements_file", "requirements.txt"))).resolve()
    constraints_file = deps.get("constraints_file")
    constraints = (repo_root / str(constraints_file)).resolve() if constraints_file else None
    wheelhouse = (repo_root / str(deps.get("wheelhouse_dir", "runtime/wheelhouse"))).resolve()
    wheelhouse.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_exe),
        "-m",
        "pip",
        "wheel",
        "-r",
        str(requirements),
        "-w",
        str(wheelhouse),
    ]
    if constraints and constraints.exists():
        cmd.extend(["-c", str(constraints)])
    if not include_deps:
        cmd.append("--no-deps")
    return cmd


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_wheelhouse_lock(repo_root: Path, manifest: dict) -> Path:
    deps = manifest.get("dependencies", {})
    wheelhouse = (repo_root / str(deps.get("wheelhouse_dir", "runtime/wheelhouse"))).resolve()
    lock_path = (repo_root / str(deps.get("wheelhouse_lock_file", "runtime/wheelhouse.lock.json"))).resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    files = []
    for item in sorted(wheelhouse.iterdir()):
        if not item.is_file():
            continue
        if item.suffix not in {".whl", ".gz", ".zip"}:
            continue
        files.append({
            "name": item.name,
            "sha256": _hash_file(item),
            "size": item.stat().st_size,
        })

    payload = {
        "schema_version": "1.0",
        "wheelhouse": str(wheelhouse),
        "file_count": len(files),
        "files": files,
    }
    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return lock_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local wheelhouse for AAS runtime bundle.")
    parser.add_argument("--repo-path", default=str(ROOT), help="Path to repository root")
    parser.add_argument("--manifest", help="Path to runtime manifest (default runtime.manifest.json)")
    parser.add_argument("--dry-run", action="store_true", help="Print the wheel build command only")
    parser.add_argument("--no-deps", action="store_true", help="Build only top-level wheels from requirements")
    parser.add_argument("--skip-lock", action="store_true", help="Do not write wheelhouse lock file")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    try:
        manifest_path, manifest = _load_manifest(repo_root, args.manifest)
        python_exe = _resolve_python(repo_root, manifest)
        cmd = _wheelhouse_command(repo_root, manifest, python_exe, include_deps=not args.no_deps)
        report = {
            "repo_root": str(repo_root),
            "manifest": str(manifest_path),
            "python_executable": str(python_exe),
            "command": cmd,
            "lock_file": str((repo_root / str(manifest.get("dependencies", {}).get("wheelhouse_lock_file", "runtime/wheelhouse.lock.json"))).resolve()),
        }
        if args.dry_run:
            print(json.dumps(report, indent=2))
            return 0

        subprocess.run(cmd, check=True)
        if not args.skip_lock:
            lock_path = _write_wheelhouse_lock(repo_root, manifest)
            report["lock_file_written"] = str(lock_path)
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

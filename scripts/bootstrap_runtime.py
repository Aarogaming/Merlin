import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from nats.aio.client import Client as NATS
    HAS_NATS = True
except ImportError:
    HAS_NATS = False


ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_manifest(repo_root: Path, manifest_arg: str | None) -> Path:
    if manifest_arg:
        return Path(manifest_arg).resolve()
    env_path = os.environ.get("AAS_RUNTIME_MANIFEST")
    if env_path:
        return Path(env_path).resolve()
    return (repo_root / "runtime.manifest.json").resolve()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _to_unit(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number > 1.0:
        number = number / 100.0
    return _clamp(number, 0.0, 1.0)


def _resolve_python(repo_root: Path, manifest: dict) -> Path:
    py_cfg = manifest.get("python", {})
    strategy = str(py_cfg.get("strategy", "embedded_preferred"))
    embedded = (repo_root / str(py_cfg.get("executable_relpath", "runtime/python/python.exe"))).resolve()

    if strategy in {"embedded_preferred", "embedded_required"} and embedded.exists():
        return embedded
    if strategy == "embedded_required" and not embedded.exists():
        raise FileNotFoundError(f"Embedded python required but missing: {embedded}")

    allow_system = bool(py_cfg.get("allow_system_fallback", True))
    if not allow_system and strategy != "system_only":
        raise RuntimeError("System fallback is disabled by runtime policy.")

    return Path(sys.executable).resolve()


def _choose_install_mode(manifest: dict, wheelhouse: Path) -> str:
    deps = manifest.get("dependencies", {})
    install_mode = str(deps.get("install_mode", "offline_prefer"))
    clamps = manifest.get("policy_clamps", {})
    spectrums = manifest.get("spectrums", {})

    force_offline = bool(clamps.get("force_offline_when_wheelhouse_present", True))
    portability_bias = _to_unit(spectrums.get("portability_bias"), 0.8)
    dependency_trust = _to_unit(spectrums.get("dependency_trust"), 0.3)

    if wheelhouse.exists() and force_offline:
        return "offline_required"
    if install_mode == "offline_prefer" and wheelhouse.exists() and portability_bias >= 0.6:
        return "offline_required"
    if install_mode == "online_allowed" and dependency_trust < 0.25:
        return "offline_prefer"
    return install_mode


def _ensure_runtime_mutation_allowed(manifest: dict):
    clamps = manifest.get("policy_clamps", {})
    if not bool(clamps.get("allow_runtime_mutation", True)):
        raise RuntimeError("Runtime mutation disabled by policy clamp.")


def _requirements_have_hashes(requirements_path: Path) -> bool:
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            continue
        if "--hash=" not in line:
            return False
    return True


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _wheelhouse_lock_path(repo_root: Path, manifest: dict) -> Path:
    deps = manifest.get("dependencies", {})
    lock_rel = str(deps.get("wheelhouse_lock_file", "runtime/wheelhouse.lock.json"))
    return (repo_root / lock_rel).resolve()


def _verify_wheelhouse_lock(repo_root: Path, manifest: dict, wheelhouse: Path) -> tuple[bool, str]:
    lock_path = _wheelhouse_lock_path(repo_root, manifest)
    if not lock_path.exists():
        return False, f"wheelhouse lock file missing: {lock_path}"

    try:
        lock = _load_json(lock_path)
    except Exception as exc:
        return False, f"invalid wheelhouse lock file: {exc}"

    expected = lock.get("files", []) if isinstance(lock, dict) else []
    if not isinstance(expected, list) or not expected:
        return False, "wheelhouse lock file has no files"

    expected_map = {}
    for row in expected:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        sha = str(row.get("sha256", "")).strip().lower()
        if name and sha:
            expected_map[name] = sha

    actual_map = {}
    for item in sorted(wheelhouse.iterdir()):
        if not item.is_file():
            continue
        if item.suffix not in {".whl", ".gz", ".zip"}:
            continue
        actual_map[item.name] = _hash_file(item)

    if expected_map != actual_map:
        missing = sorted(set(expected_map) - set(actual_map))
        extra = sorted(set(actual_map) - set(expected_map))
        mismatched = sorted([name for name in expected_map if name in actual_map and expected_map[name] != actual_map[name]])
        details = {
            "missing": missing,
            "extra": extra,
            "mismatched": mismatched,
            "lock": str(lock_path),
        }
        return False, f"wheelhouse lock mismatch: {json.dumps(details)}"

    return True, f"wheelhouse lock verified: {lock_path}"


def _policy_fallback_result(manifest: dict, reason: str) -> tuple[bool, str]:
    adapters = manifest.get("security_ops_adapters", {})
    mode = str(adapters.get("local_policy_fallback", "deny"))
    security_hardening = _to_unit(manifest.get("spectrums", {}).get("security_hardening"), 0.75)
    threshold = _to_unit(adapters.get("fallback_security_hardening_max"), 0.6)

    if mode == "allow":
        return True, f"policy fallback allow: {reason}"
    if mode == "adaptive" and security_hardening <= threshold:
        return True, f"policy fallback adaptive allow ({security_hardening:.2f} <= {threshold:.2f}): {reason}"
    return False, reason


async def _request_policy_gate(manifest: dict, operation: str, details: dict) -> tuple[bool, str]:
    adapters = manifest.get("security_ops_adapters", {})
    if not bool(adapters.get("myfortress_ready", False)):
        return True, "policy gate not required"

    subject = str(adapters.get("policy_subject", "aaroneousautomationsuite.fortress_policy_evaluate"))
    security_hardening = _to_unit(manifest.get("spectrums", {}).get("security_hardening"), 0.75)
    fail_closed = security_hardening >= 0.7

    if not HAS_NATS:
        if fail_closed:
            return _policy_fallback_result(manifest, "policy gate failed closed: nats-py unavailable")
        return True, "policy gate bypassed: nats-py unavailable"

    nats_url = os.environ.get("AAS_NATS_URL", "nats://localhost:4222")
    nc = NATS()
    try:
        await nc.connect(nats_url, connect_timeout=4)
        payload = {
            "operation": operation,
            "component": "runtime_bundle",
            "details": details,
            "requester": "bootstrap_runtime",
        }
        reply = await nc.request(subject, json.dumps(payload).encode(), timeout=8.0)
        try:
            response = json.loads(reply.data.decode())
        except Exception:
            response = {}
        approved = bool(response.get("approved"))
        if not approved:
            message = str(response.get("details") or response.get("message") or "policy denied")
            return False, f"policy denied: {message}"
        return True, str(response.get("details") or "policy approved")
    except Exception as exc:
        if fail_closed:
            return _policy_fallback_result(manifest, f"policy gate failed closed: {exc}")
        return True, f"policy gate bypassed after error: {exc}"
    finally:
        if nc.is_connected:
            await nc.close()


def enforce_policy_gate(manifest: dict, operation: str, details: dict, skip_policy_gate: bool) -> dict:
    if skip_policy_gate:
        return {"enforced": False, "approved": True, "message": "policy gate skipped by flag"}
    approved, message = asyncio.run(_request_policy_gate(manifest, operation, details))
    return {"enforced": True, "approved": approved, "message": message}


def install_dependencies(repo_root: Path, manifest: dict, python_exe: Path, dry_run: bool) -> dict:
    deps = manifest.get("dependencies", {})
    requirements = (repo_root / str(deps.get("requirements_file", "requirements.txt"))).resolve()
    wheelhouse = (repo_root / str(deps.get("wheelhouse_dir", "runtime/wheelhouse"))).resolve()
    target = (repo_root / str(deps.get("install_target_dir", "runtime/site-packages"))).resolve()
    constraints = deps.get("constraints_file")
    constraints_path = (repo_root / str(constraints)).resolve() if constraints else None

    if not requirements.exists():
        raise FileNotFoundError(f"requirements file not found: {requirements}")

    install_mode = _choose_install_mode(manifest, wheelhouse)
    target.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_exe),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "-r",
        str(requirements),
        "--target",
        str(target),
    ]

    if constraints_path and constraints_path.exists():
        cmd.extend(["-c", str(constraints_path)])

    clamps = manifest.get("policy_clamps", {})
    require_hashes = bool(clamps.get("require_hashes_for_online_fallback", True))
    require_wheelhouse_lock = bool(clamps.get("require_wheelhouse_lock_for_offline", False))

    hash_warning = None
    lock_status = None

    if install_mode in {"offline_required", "offline_prefer"} and wheelhouse.exists():
        cmd.extend(["--no-index", "--find-links", str(wheelhouse)])
        if require_wheelhouse_lock:
            ok, message = _verify_wheelhouse_lock(repo_root, manifest, wheelhouse)
            lock_status = message
            if not ok and not dry_run:
                raise RuntimeError(message)
    elif install_mode == "offline_required" and not wheelhouse.exists():
        raise RuntimeError(f"Offline mode required but wheelhouse missing: {wheelhouse}")
    elif require_hashes and not _requirements_have_hashes(requirements):
        if dry_run:
            hash_warning = "Online fallback requires hashed requirements by policy clamp, but requirements.txt lacks --hash entries."
        else:
            raise RuntimeError(
                "Online fallback requires hashed requirements by policy clamp, but requirements.txt lacks --hash entries."
            )

    if dry_run:
        return {
            "mode": install_mode,
            "command": cmd,
            "target": str(target),
            "wheelhouse": str(wheelhouse),
            "warning": hash_warning,
            "wheelhouse_lock": lock_status,
        }

    subprocess.run(cmd, check=True)
    return {
        "mode": install_mode,
        "target": str(target),
        "wheelhouse": str(wheelhouse),
        "wheelhouse_lock": lock_status,
    }


def write_runtime_env(repo_root: Path, manifest: dict, python_exe: Path) -> Path:
    deps = manifest.get("dependencies", {})
    target = (repo_root / str(deps.get("install_target_dir", "runtime/site-packages"))).resolve()
    env_dir = repo_root / "runtime"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_path = (env_dir / "runtime_env.json").resolve()
    payload = {
        "python_executable": str(python_exe),
        "pythonpath_prepend": [str(target)],
        "nats_bin": str((repo_root / manifest.get("services", {}).get("nats_bin", "nats/bin/nats-server.exe")).resolve()),
        "nats_data_dir": str((repo_root / manifest.get("services", {}).get("nats_data_dir", "nats/data")).resolve()),
    }
    env_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return env_path


def verify_imports(manifest: dict, python_exe: Path) -> list[str]:
    required = manifest.get("health_checks", {}).get("required_imports", [])
    failures: list[str] = []
    for module in required:
        command = [
            str(python_exe),
            "-c",
            f"import {module}",
        ]
        proc = subprocess.run(command, capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{module}: {proc.stderr.strip() or 'import failed'}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap local AAS runtime bundle without Docker/Kubernetes.")
    parser.add_argument("--repo-path", default=str(ROOT), help="Path to repository root")
    parser.add_argument("--manifest", help="Path to runtime manifest (default runtime.manifest.json)")
    parser.add_argument("--mode", choices=["install", "verify", "all"], default="all", help="Install dependencies, verify imports, or run both")
    parser.add_argument("--dry-run", action="store_true", help="Show planned install command without applying changes")
    parser.add_argument("--skip-policy-gate", action="store_true", help="Bypass MyFortress policy gate checks")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    manifest_path = _resolve_manifest(repo_root, args.manifest)
    if not manifest_path.exists():
        print(f"Runtime manifest not found: {manifest_path}")
        return 1

    manifest = _load_json(manifest_path)
    _ensure_runtime_mutation_allowed(manifest)
    python_exe = _resolve_python(repo_root, manifest)

    report: dict = {
        "repo_root": str(repo_root),
        "manifest": str(manifest_path),
        "python_executable": str(python_exe),
    }

    try:
        if args.mode in {"install", "all"}:
            gate = enforce_policy_gate(
                manifest,
                operation="runtime_bundle_install",
                details={
                    "repo": str(repo_root.name),
                    "manifest": str(manifest_path),
                    "dry_run": bool(args.dry_run),
                },
                skip_policy_gate=args.skip_policy_gate,
            )
            report["policy_gate"] = gate
            if not gate.get("approved") and args.dry_run:
                report["policy_gate"]["dry_run_bypass"] = True
                report["policy_gate"]["message"] = f"{gate.get('message')} (bypassed for dry-run)"
            elif not gate.get("approved"):
                raise RuntimeError(str(gate.get("message") or "policy gate denied"))

            install_report = install_dependencies(repo_root, manifest, python_exe, dry_run=args.dry_run)
            report["install"] = install_report
            if not args.dry_run:
                env_path = write_runtime_env(repo_root, manifest, python_exe)
                report["runtime_env"] = str(env_path)

        if args.mode in {"verify", "all"}:
            failures = verify_imports(manifest, python_exe)
            report["verify"] = {
                "status": "ok" if not failures else "failed",
                "failures": failures,
            }
            print(json.dumps(report, indent=2))
            return 0 if not failures else 1

        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        report["error"] = str(exc)
        print(json.dumps(report, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

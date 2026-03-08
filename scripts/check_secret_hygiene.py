import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BLOCKED_BASENAMES = {
    ".env",
    "credentials.json",
    "keystore.properties",
    "merlin-key",
    "token.pickle",
}
BLOCKED_SUFFIXES = (".jks", ".keystore", ".p12")
BLOCKED_PREFIXES = ("logs/",)
ALLOWLIST_BASENAMES = {".env.example"}


def _run_git(args):
    return subprocess.check_output(["git", *args], text=False)


def _candidate_paths(include_all):
    if include_all:
        out = _run_git(["ls-files", "-z"])
    else:
        out = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
    if not out:
        return []
    return [
        part.decode("utf-8", errors="replace") for part in out.split(b"\x00") if part
    ]


def _is_blocked(path):
    normalized = path.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    lowered = normalized.lower()

    if basename in ALLOWLIST_BASENAMES:
        return False
    if basename in BLOCKED_BASENAMES:
        return True
    if lowered.endswith(BLOCKED_SUFFIXES):
        return True
    if any(normalized.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return True
    return False


def _plugin_dependency_violations(plugin_dir: str) -> list[str]:
    try:
        from merlin_plugin_manager import PluginManager
    except Exception as exc:
        return [f"plugin preflight unavailable: {exc}"]

    manager = PluginManager(plugin_dir=plugin_dir)
    issues = manager.check_packaged_plugin_dependency_compatibility()
    violations: list[str] = []
    for plugin_name in sorted(issues.keys()):
        for issue in issues[plugin_name]:
            violations.append(f"{plugin_name}: {issue}")
    return violations


def _build_report(
    *,
    include_all: bool,
    candidates: list[str],
    file_violations: list[str],
    dependency_violations: list[str],
) -> dict:
    violations = [
        {"type": "path", "severity": "high", "value": path}
        for path in sorted(file_violations)
    ]
    violations.extend(
        {"type": "plugin_dependency", "severity": "high", "value": issue}
        for issue in sorted(dependency_violations)
    )
    return {
        "schema_name": "AAS.SecretHygieneReport",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "all_tracked" if include_all else "staged_only",
        "candidate_count": len(candidates),
        "violation_count": len(violations),
        "violations": violations,
        "ok": len(violations) == 0,
    }


def _should_fail(violations: list[dict], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    if fail_on == "high":
        return any(item.get("severity") == "high" for item in violations)
    return len(violations) > 0


def main():
    parser = argparse.ArgumentParser(
        description="Fail when tracked files match sensitive/local-only filename patterns."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all tracked files instead of staged files only.",
    )
    parser.add_argument(
        "--plugin-dependency-check",
        action="store_true",
        help="Run plugin dependency compatibility preflight checks.",
    )
    parser.add_argument(
        "--plugin-dir",
        default="plugins",
        help="Plugin directory used for dependency preflight checks.",
    )
    parser.add_argument(
        "--report-json",
        default=None,
        help="Optional output path for machine-readable hygiene report.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("any", "high", "none"),
        default="any",
        help="Fail policy for discovered violations (default: any).",
    )
    args = parser.parse_args()

    candidates = []
    try:
        candidates = _candidate_paths(include_all=args.all)
    except Exception:
        # Don't block on environments where git metadata is unavailable,
        # unless explicit plugin dependency preflight was requested.
        if not args.plugin_dependency_check:
            return 0

    file_violations = sorted(path for path in candidates if _is_blocked(path))
    dependency_violations: list[str] = []
    if args.plugin_dependency_check:
        dependency_violations = _plugin_dependency_violations(args.plugin_dir)

    report = _build_report(
        include_all=args.all,
        candidates=candidates,
        file_violations=file_violations,
        dependency_violations=dependency_violations,
    )
    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if not file_violations and not dependency_violations:
        return 0

    if file_violations:
        scope = "tracked" if args.all else "staged"
        sys.stderr.write(f"Error: {scope} files include sensitive/local-only paths:\n")
        for violation in file_violations:
            sys.stderr.write(f"  - {violation}\n")

    if dependency_violations:
        sys.stderr.write("Error: plugin dependency compatibility preflight failed:\n")
        for violation in dependency_violations:
            sys.stderr.write(f"  - {violation}\n")

    return 2 if _should_fail(report["violations"], args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())

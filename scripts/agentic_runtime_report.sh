#!/usr/bin/env bash
set -euo pipefail

quiet=false
for arg in "$@"; do
  case "$arg" in
    -Quiet|--quiet)
      quiet=true
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "agentic_runtime_report: git is required" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "agentic_runtime_report: not in git repository" >&2
  exit 1
fi

mkdir -p "$repo_root/artifacts/diagnostics"
output_path="$repo_root/artifacts/diagnostics/agentic_runtime_report.json"

python - "$output_path" <<'PY'
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

output_path = Path(sys.argv[1])

def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ""

payload = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "hostname": socket.gethostname(),
    "platform": platform.platform(),
    "python_version": sys.version.split()[0],
    "cwd": str(Path.cwd()),
    "repo_root": _run(["git", "rev-parse", "--show-toplevel"]),
    "git_branch": _run(["git", "branch", "--show-current"]),
    "git_head": _run(["git", "rev-parse", "HEAD"]),
}

output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(str(output_path))
PY

if [[ "$quiet" == "true" ]]; then
  echo "agentic_runtime_report: ok -> $output_path"
else
  cat "$output_path"
fi

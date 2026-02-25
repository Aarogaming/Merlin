#!/usr/bin/env bash
set -euo pipefail

emit_json_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --emit-json)
      emit_json_path="${2:-}"
      shift 2
      ;;
    *)
      echo "check_governance_guardrails: unknown argument '$1'" >&2
      exit 2
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "check_governance_guardrails: git is required" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "check_governance_guardrails: not in git repository" >&2
  exit 1
fi

checks=(
  "docs/protocols/README.md"
  "docs/protocols/operation-envelope-v1.md"
  "docs/protocols/repo-capabilities-merlin-v1.md"
  "contracts/aas.operation-envelope.v1.schema.json"
)

missing=()
for rel in "${checks[@]}"; do
  if [[ ! -f "$repo_root/$rel" ]]; then
    missing+=("$rel")
  fi
done

status="ok"
if [[ ${#missing[@]} -gt 0 ]]; then
  status="failed"
fi

if [[ -n "$emit_json_path" ]]; then
  mkdir -p "$(dirname "$emit_json_path")"
  python - "$emit_json_path" "$status" "${missing[@]}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

out = Path(sys.argv[1])
status = sys.argv[2]
missing = sys.argv[3:]
payload = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "missing": missing,
}
out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
fi

if [[ "$status" == "failed" ]]; then
  echo "check_governance_guardrails: failed"
  printf ' - missing: %s\n' "${missing[@]}"
  exit 1
fi

echo "check_governance_guardrails: ok"

#!/usr/bin/env bash
set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  echo "check_guild_guardrails: git is required" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "check_guild_guardrails: not in git repository" >&2
  exit 1
fi

required_files=(
  ".gitleaks.toml"
  "contracts/aas.operation-envelope.v1.schema.json"
  "docs/protocols/operation-envelope-v1.md"
  "pytest.ini"
)

missing=()
for rel in "${required_files[@]}"; do
  if [[ ! -f "$repo_root/$rel" ]]; then
    missing+=("$rel")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "check_guild_guardrails: missing required files:"
  printf ' - %s\n' "${missing[@]}"
  exit 1
fi

echo "check_guild_guardrails: ok"

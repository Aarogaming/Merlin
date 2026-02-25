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

missing=()
for cmd in git python; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing+=("$cmd")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "agentic_health: missing required commands: ${missing[*]}" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "agentic_health: not in git repository" >&2
  exit 1
fi

if [[ "$quiet" == "true" ]]; then
  echo "agentic_health: ok"
else
  echo "agentic_health: ok"
  echo "repo_root=$repo_root"
  echo "python=$(python --version 2>&1)"
  echo "git=$(git --version)"
fi

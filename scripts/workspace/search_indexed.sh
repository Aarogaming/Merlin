#!/usr/bin/env bash
set -euo pipefail

query=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -Query|--query)
      query="${2:-}"
      shift 2
      ;;
    *)
      echo "search_indexed: unknown argument '$1'" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$query" ]]; then
  echo "search_indexed: -Query is required" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
index_file="$repo_root/artifacts/diagnostics/workspace_search_index.txt"

if [[ -f "$index_file" ]]; then
  if command -v rg >/dev/null 2>&1; then
    rg --line-number --no-heading "$query" "$index_file"
    exit 0
  fi
  grep -n -- "$query" "$index_file"
  exit 0
fi

exec "$script_dir/search_local.sh" -Query "$query" -Repo "$repo_root"

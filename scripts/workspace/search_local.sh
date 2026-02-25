#!/usr/bin/env bash
set -euo pipefail

query=""
repo_path="."

while [[ $# -gt 0 ]]; do
  case "$1" in
    -Query|--query)
      query="${2:-}"
      shift 2
      ;;
    -Repo|--repo)
      repo_path="${2:-.}"
      shift 2
      ;;
    *)
      echo "search_local: unknown argument '$1'" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$query" ]]; then
  echo "search_local: -Query is required" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "search_local: ripgrep (rg) is required" >&2
  exit 1
fi

rg --line-number --no-heading --hidden --glob '!.git/*' "$query" "$repo_path"

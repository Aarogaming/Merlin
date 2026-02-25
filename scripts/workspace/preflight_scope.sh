#!/usr/bin/env bash
set -euo pipefail

skip_apply_profile=false
for arg in "$@"; do
  case "$arg" in
    -SkipApplyProfile|--skip-apply-profile)
      skip_apply_profile=true
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "preflight_scope: git is required but not available" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "preflight_scope: current directory is not inside a git repository" >&2
  exit 1
fi

mkdir -p "$repo_root/artifacts/diagnostics"

if [[ "$skip_apply_profile" == "true" ]]; then
  profile_mode="skipped"
else
  profile_mode="not_implemented"
fi

echo "preflight_scope: ok"
echo "repo_root=$repo_root"
echo "profile_apply=$profile_mode"

#!/usr/bin/env bash
set -euo pipefail

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks is required for this hook. Install it from https://github.com/gitleaks/gitleaks/releases or run:"
  echo "  curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh -s -- -b \"$HOME/.local/bin\""
  exit 1
fi

config_args=()
if [ -f .gitleaks.toml ]; then
  config_args+=(--config .gitleaks.toml)
fi

stage="${PRE_COMMIT_STAGE:-pre-commit}"
if [ "$stage" = "pre-push" ]; then
  if upstream_ref=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null); then
    commit_range="${upstream_ref}..HEAD"
    commit_count=$(git rev-list --count "$commit_range" 2>/dev/null || echo 0)
    if [ "$commit_count" -gt 0 ]; then
      gitleaks git --no-banner --redact --exit-code 1 --log-opts "$commit_range" "${config_args[@]}"
      exit 0
    fi
  fi
fi

gitleaks git --staged --no-banner --redact --exit-code 1 "${config_args[@]}"

# Runbook

## Baseline checks

- Repository state:
  - `git status --short --branch`
- Protocol baseline present:
  - `test -f protocols/AGENT_INTEROP_V1.md && echo ok`

## Search hygiene

- Prefer repo-local scoped searches.
- Use `.rgignore` and `.ignore` to avoid scanning heavy paths.

## Incident templates

Subsystem-specific incident templates are maintained at:

- `docs/research/INCIDENT_RUNBOOK_TEMPLATES_2026-02-19.md`

Templates currently included:

- API incident
- Routing incident
- Plugin incident
- Research manager incident

## Release checklist

Run release readiness checks before handoff or publish:

- `python3 scripts/run_release_checklist.py --strict`
- `python3 scripts/run_release_checklist.py --run-commands --strict`

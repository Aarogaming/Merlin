# Knowledge Layout

Discovery artifacts are persisted under `knowledge/` so the repo itself becomes searchable memory.

## Directories

- `knowledge/feeds/<source>/<YYYY-MM-DD>.jsonl`
- `knowledge/research/<YYYY>/<MM>/<DD>/<slug>.md`
- `knowledge/templates/research_note.md`
- `knowledge/index.json`
- `knowledge/tags.json`

## Canonical Rules

- Every collected item must have a canonical URL.
- `canonical_key` is the stable SHA-256-derived key for dedupe and index merge.
- Artifacts are append-oriented; existing files are not overwritten unless explicitly requested.

## Artifact Template Contract

Artifacts must include frontmatter fields:

- `title`
- `date`
- `source`
- `canonical_url`
- `tags`
- `confidence`
- `run_id`

Artifacts must include required sections:

- `# Summary`
- `# Why This Matters To AAS`
- `# Technical Notes`
- `# Integration Ideas (AAS)`
- `# Risks / Policy Notes`
- `# Action Items`

## Profile Behavior

- Public profile (`green`): offline collectors only.
- Experimental profile (`red`): live collectors/publishing require `ALLOW_LIVE_AUTOMATION=true` (default).
- Set `ALLOW_LIVE_AUTOMATION` to `false` to explicitly disable live behavior.

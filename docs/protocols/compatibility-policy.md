# Compatibility Policy

This policy governs cross-repo operation contracts used by Merlin integrations.

## Versioning

- Contract docs and schemas use SemVer.
- Major version changes are for breaking changes.
- Minor version changes are additive and backward compatible.
- Patch versions are clarifications/fixes without shape changes.

## Reverse-Compatibility Rules

1. Additive fields are allowed in minor releases.
2. Removing or renaming fields requires a major version.
3. Required new fields require a major version unless they have a safe default.
4. Consumers must ignore unknown fields by default.
5. Producers should continue emitting deprecated fields during the deprecation window.

## Deprecation Window

- Minimum deprecation period: two release cycles or 30 days (whichever is longer) before removal.
- Deprecations must be documented in this folder and in repo release notes/changelog if present.

## Change Checklist

Before merging contract changes:

1. Update protocol docs under `docs/protocols/`.
2. Update JSON schema in `contracts/`.
3. Verify producer/consumer compatibility tests or fixtures.
4. Document migration notes when behavior changes.

## Safety Defaults

- Prefer additive evolution over replacement.
- Keep timeout and retry values explicit.
- Require idempotency keys for mutating operations.

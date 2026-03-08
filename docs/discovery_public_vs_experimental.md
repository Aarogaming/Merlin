# Discovery Profiles: Public vs Experimental

## Public (Green)

Default safe mode.

- `ALLOW_LIVE_AUTOMATION` default is `true`.
- Offline collectors only (`local_fixture`, `local_cache`).
- Live collectors (`rss`, `github_trending`, etc.) are blocked.
- Publisher defaults to `stage_only`.

## Experimental (Red)

Still policy governed.

- If `ALLOW_LIVE_AUTOMATION=true`: live capability gates can transition to allowed.
- If `ALLOW_LIVE_AUTOMATION` is set to `false`: live collectors/publishers are stubbed/blocked.
- DiscoveryEngine v1 keeps live collectors/publishers as explicit stubs behind these gates.

## Policy Rule

All executors/capabilities exist and negotiate status at runtime:

- `allowed`
- `blocked`
- `stubbed`

There is no hidden fallback from blocked live capability to implicit network behavior.

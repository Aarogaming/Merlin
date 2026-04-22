# DiscoveryEngine v1

DiscoveryEngine is a single plugin that composes:

- Library responsibilities: artifact layout, validation, index/tags update.
- Guild responsibilities: queue files, work leasing, retries/deadletter.
- Merlin responsibilities: score/classify/summarize through stable adapters.

## Policy Model

- Default profile: `public` (green)
- Default live flag: `ALLOW_LIVE_AUTOMATION=true`
- Public mode is offline-first (fixtures/local cache only).
- Experimental mode can enable live collectors/publishers only when explicitly allowed.

## CLI

Run via CLI:

```bash
python merlin_cli.py discovery run --profile public --out ./artifacts/discovery
```

Queue commands:

```bash
python merlin_cli.py discovery queue status --out ./artifacts/discovery
python merlin_cli.py discovery queue drain --out ./artifacts/discovery
python merlin_cli.py discovery queue purge-deadletter --out ./artifacts/discovery
python merlin_cli.py discovery queue pause --out ./artifacts/discovery
python merlin_cli.py discovery queue resume --out ./artifacts/discovery
```

Knowledge search:

```bash
python merlin_cli.py knowledge search "policy" --out ./artifacts/discovery
```

## Outputs

- `knowledge/feeds/<source>/<YYYY-MM-DD>.jsonl`
- `knowledge/research/<YYYY>/<MM>/<DD>/<slug>.md`
- `knowledge/index.json`
- `knowledge/tags.json`
- `runs/<run_id>/report.json`
- `runs/<run_id>/events.jsonl`

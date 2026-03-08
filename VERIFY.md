# VERIFY DiscoveryEngine v1

## 1) Run tests

```bash
pytest -q tests/test_discovery_contract_schemas.py tests/test_merlin_discovery_engine.py tests/test_merlin_cli_discovery.py
```

## 2) Offline Public run (fixtures only)

```bash
python merlin_cli.py discovery run \
  --profile public \
  --out ./artifacts/discovery_public \
  --seeds-file ./tests/fixtures/discovery/seeds.public.json \
  --fixture-feed ./knowledge/feeds/_fixtures/local_fixture.jsonl
```

## 3) Inspect outputs

- `artifacts/discovery_public/knowledge/research/...`
- `artifacts/discovery_public/knowledge/index.json`
- `artifacts/discovery_public/runs/<run_id>/report.json`
- `artifacts/discovery_public/runs/<run_id>/events.jsonl`

## 4) Policy-gated behavior check

Run with a network collector seed in `public` profile and verify report `counts.blocked_by_policy > 0`.

## 5) Queue pause/resume + knowledge search

```bash
python merlin_cli.py discovery queue pause --out ./artifacts/discovery_public
python merlin_cli.py discovery queue status --out ./artifacts/discovery_public
python merlin_cli.py discovery queue resume --out ./artifacts/discovery_public
python merlin_cli.py knowledge search "policy" --out ./artifacts/discovery_public
```

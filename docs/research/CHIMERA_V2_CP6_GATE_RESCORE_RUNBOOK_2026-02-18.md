# CHIMERA V2 CP6 Gate Rescore Runbook (2026-02-18)

Use this when new repo returns arrive and you need to update gate verdicts without manual matrix edits.

## Inputs

- Gate matrix:
  - `docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.json`
- One or more intake JSON files containing repo-level booleans.
- Example intake file:
  - `docs/research/CHIMERA_V2_CP6_GATE_RESCORE_INTAKE_EXAMPLE_2026-02-18.json`

## Intake JSON shape

Each record supports these fields:
- `repo`
- `six_block`
- `success_flow`
- `expected_failure_branch`
- `artifact_present`
- `live_probe`
- `live_chain_proof`
- optional: `retry_packet`
- optional: `notes`

Supported payload wrappers:
- object with `repos: []`
- raw list of records
- single record object

## Rescore command

```bash
python3 scripts/chimera_v2_cp6_gate_rescore.py \
  --matrix docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.json \
  --intake docs/research/CHIMERA_V2_CP6_GATE_RESCORE_INTAKE_EXAMPLE_2026-02-18.json
```

Optional output file instead of in-place overwrite:

```bash
python3 scripts/chimera_v2_cp6_gate_rescore.py \
  --matrix docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.json \
  --intake path/to/new_intake.json \
  --out docs/research/CHIMERA_V2_CP6_CROSS_REPO_GATE_MATRIX_2026-02-18.updated.json
```

## Verdict rules

- `PASS`: base criteria + live probe + live chain proof are all true.
- `CONDITIONAL_PASS`: base criteria true, but one or both live criteria false.
- `FAIL`: any base criterion is false.

Base criteria:
- `six_block`
- `success_flow`
- `expected_failure_branch`
- `artifact_present`

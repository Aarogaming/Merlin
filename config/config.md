# AAS Path Configuration

**Source of truth for all path resolutions.** The kernel parses this file at runtime.

## Output Rules

- logs → logs/ (execution traces)
- artifacts → artifacts/ (built artifacts, GGUF, relics)
- config → config/ (manifests, configs)
- runtime → runtime/ (lifecycle state, events)
- genome → genome/ (identity, DNA, schemas)
- nats_tmp → nats/tmp (NATS temp files)
- nats_data → nats/data (NATS jetstream data)
- nats_bin → nats/bin/nats-server.exe (NATS binary)

## Model Paths

- models → runtime/models (local GGUF models)
- Additional model paths can be set via AAS_MODEL_PATHS env var (comma-separated)

## Environment Overrides

Set these env vars to override any directory:
- `AAS_LOGS_DIR`
- `AAS_ARTIFACTS_DIR`
- `AAS_CONFIG_DIR`
- `AAS_RUNTIME_DIR`
- `AAS_GENOME_DIR`
- `AAS_PLUGINS_DIR`
- `AAS_NATS_TMP`
- `AAS_NATS_DATA`
- `AAS_NATS_BIN`
- `AAS_MODEL_PATHS`
- `AAS_NATS_URL` (default: nats://localhost:4222)
- `AAS_WORKSPACE_ROOT` (default: D:/)

## File Paths

- lifecycle_state → runtime/lifecycle_state.json
- lifecycle_events → runtime/lifecycle.events.jsonl
- identity_epigenetics → genome/identity.epigenetics.json
- identity_genome → genome/identity.genome.json
- identity_memory → genome/identity.memory.json
- mcp_manifest → mcp-manifest.json
- genome_manifest → genome.manifest.json
- runtime_manifest → config/runtime.manifest.json
- spark_config → config/spark_config.json
- agents_md → runtime/AGENTS.md
- soul_md → runtime/SOUL.md
- evolution_ledger → logs/EVOLUTION_LEDGER.md
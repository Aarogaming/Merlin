# Relic Protocol

This document defines the standardized protocols, templates, and guidelines for creating and managing Living Relics within the AAS Federation.

## Overview

A **Relic** is a Living Artifact — a passive data source (SQLite, JSON, GGUF, etc.) that has been crystallized into a GGUF binary with embedded Epigenetic DNA. Once crystallized, the Relic becomes a Living Entity on the event bus, capable of:

- Semantic query answering via its own internal Transformer
- Telemetry emission to supervisor agents
- Access control enforcement for control operations

## Relic Types

| Type | Domain | Primary Use | Example |
|------|--------|-------------|---------|
| Knowledge | `knowledge` | Semantic memory, SOPs, Omni data | Omni Memory |
| Intelligence | `intelligence` | Research synthesis, RAG context | Merlin |
| Security | `security` | Policy gates, secrets, audit trails | MyFortress |
| Leadership | `leadership` | Dispatch board, tactical ops | Guild |

## Creation Protocol

### 1. Single Artifact (Backward Compatible)

```bash
python scripts/gguf_reliquary.py crystallize <source_file> \
    --domain knowledge \
    --name Omni \
    --repo-alliance knowledge \
    --supervisor SupervisorA
```

### 2. Multi-Artifact (Sibling Constellation)

```bash
python scripts/create_sibling_relic.py \
    --relic-name sibling_constellation \
    --domain knowledge \
    --entity-name "Sibling Constellation" \
    --repo-alliance knowledge \
    --supervisor SupervisorA
```

This discovers sibling AAS repos in the workspace root, collects their primary artifacts, and creates a single GGUF containing all of them.

### 3. Programmatic Creation

```python
from scripts.gguf_reliquary import GGUFArtifactReliquary

reliquary = GGUFArtifactReliquary()
reliquary.crystallize_artifact(
    artifact_sources={
        "omni_knowledge": "/path/to/Omni/knowledge.sqlite",
        "guild_dispatch": "/path/to/Guild/dispatch.json",
        "fortress_policy": "/path/to/MyFortress/policy.json",
    },
    relic_name="federal_relic",
    domain_alignment="knowledge",
    entity_name="Federal Constellation",
    repo_alliance="knowledge",
    supervisors=["SupervisorA", "SupervisorB"],
)
```

## Relic Entity Lifecycle

### Crystallization

The process of converting passive data into a Living Relic:

1. **Source Validation** — Verify all artifact paths exist
2. **DNA Injection** — Embed domain alignment, entity name, repo alliance, supervisors
3. **Payload Storage** — Each artifact stored as `aas.relic.payload.<repo_name>`
4. **Manifest Embedding** — Store artifact count and mapping in GGUF KV store
5. **Sealing** — Write header, KV data, and tensor sections

### Awakening

```bash
python scripts/living_relic.py artifacts/federal_relic.relic.gguf
```

This boots the Relic onto the event bus with:

- `federation.entity.<slug>.interact` — Query endpoint
- `federation.entity.<slug>.telemetry` — Telemetry stream
- `federation.entity.<slug>.control` — Control operations

### Attunement

Agents can attune to a Relic's bias aura:

```bash
python scripts/gguf_reliquary.py attune artifacts/federal_relic.relic.gguf
```

This reads the Relic's bias values and mathematically merges them with the agent's baseline DNA.

## Telemetry Events

| Event | Description | Keys |
|-------|-------------|------|
| `entity_online` | Relic has booted | `subjects` |
| `heartbeat` | Periodic liveness check | `status` |
| `query_received` | Agent sent a query | `agent_name`, `query` |
| `query_served` | Response returned | `agent_name`, `response_preview` |
| `query_error` | Query processing failed | `error` |
| `control_event` | Control op executed | `operation`, `result` |
| `control_denied` | Unauthorized control attempt | `operation`, `requester` |

## Control Operations

| Operation | Description | Requires Supervisor |
|-----------|-------------|-------------------|
| `set_mode` | Change runtime mode | Yes |
| `status` | Return entity state | No |

## Supervisor Access

Supervisors are declared at crystallize time:

```bash
--supervisor SupervisorA --supervisor SupervisorB
```

Control operations from non-supervisors are denied with a `control_denied` event emitted to telemetry.

## Relic Naming Convention

- **Entity Name**: Human-readable name (e.g., "Omni", "Grimoire")
- **Slug**: Derived from entity name via `_slugify`: `re.sub(r"[^a-zA-Z0-9]+", "_", value).lower()`
- **GGUF Filename**: `{slug}.relic.gguf`

Example:
- Entity: `Omni Constellation`
- Slug: `omni_constellation`
- File: `omni_constellation.relic.gguf`

## Best Practices

1. **Single Responsibility**: One Relic per domain/primary purpose
2. **Supervisor Minimalism**: Grant supervisor access only to dedicated supervisory agents
3. **Payload Truncation**: Keep combined payloads under 5000 chars for transformer prompts
4. **Telemetry Consumption**: Supervisors should subscribe to `federation.entity.<slug>.telemetry`
5. **Periodic Snapshot**: Use `gguf_snapshot.py` to backup agent state after significant evolution
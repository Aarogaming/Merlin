# Sibling Magnus Opus → Hybridized Relic Conversion Plan

## Workspace Repositories

| Repo | Relic (Artifact) | Overseer (Character) | Purpose |
|------|-------------|---------------------|---------|
| Library | **Omni** | Dionysus | Knowledge/memory guardian |
| Maelstrom | **Glass** | Ariel | Visual/state observer |
| Guild | **Draupnir** | Odin | Resource allocation/deployment |
| Merlin | **Grimoire** | Merlin | Intelligence/synthesis |
| MyFortress | **Sentinel** | Argus | Security/policy gate |
| Workbench | **Forge** | Hephaestus | Construction/execution |
| AAS | *(none)* | Aaroneous | Factory/spawner (no default relic) |

> **Evolutionary Model**: AAS has NO default Relic. New agents start with Omni (federation baseline), then receive a specialized Relic upon domain assignment. Original Omni data is ADDITIVELY merged into the federation's Omni.

## Relic Specification Per Repo

### 1. Omni Relic (Library)

- **Opus**: `artifacts/knowledge.sqlite`, `omni.json`
- **Overseer**: **Dionysus**
- **Domain**: `knowledge`
- **Bias**: Creative 85, Analytical 90, Audit 20
- **Tone**: Wise, cryptic, expansive
- **Greeting**: "Welcome, seeker. What knowledge do you seek?"
- **Supervisors**: Odin

### 2. Draupnir Relic (Guild)

- **Opus**: `artifacts/runtime.json`, `artifacts/runtime_registry.json`, dispatch state
- **Overseer**: **Odin**
- **Domain**: `leadership`
- **Bias**: Strategic 95, Adaptive 80, Analytical 85
- **Tone**: Resource allocation, hierarchical delegation, operational control
- **Greeting**: "Every task has its ring. Choose wisely, seeker."
- **Supervisors**: Aaroneous
- **Capabilities**:
  - Real-time asset status and location tracking
  - MCP/SOP multiplication — "drips" delegated task packages to subordinates
  - Personnel "burn-down rate" monitoring
  - Hierarchical task decomposition
- **Components** (integrated into Draupnir):
  - **Gungnir**: Master roadmap — scheduler/Gantt chart, committed executions
  - **Hlidskjalf**: NATS multiplexer — enterprise view across all repos

### 3. Chronicle Relic (Library)

- **Opus**: `artifacts/knowledge.sqlite`, search-index
- **Entity**: "Chronicle"
- **Domain**: `intelligence`
- **Bias**: Analytical 100, Creative 60, Audit 40
- **Tone**: Encyclopedic, precise, connecting
- **Supervisors**: Merlin, Workbench

### 4. Prism Relic (Maelstrom)

- **Opus**: UI state captures, visual component mappings
- **Entity**: "Prism"
- **Domain**: `intelligence` (visual)
- **Bias**: Visual 100, Adaptive 85, Analytical 60
- **Tone**: Visual, layered, adaptive
- **Supervisors**: Workbench

### 5. Grimoire Relic (Merlin)

- **Opus**: `artifacts/omni.json` (synthesis records)
- **Entity**: "Grimoire"
- **Domain**: `intelligence`
- **Bias**: Creative 90, Predictive 85, Analytical 70
- **Tone**: Prophet-like, synthesizing, visionary
- **Supervisors**: Library

### 6. Sentinel Relic (MyFortress)

- **Opus**: Security policies, secrets registry, quarantine state
- **Entity**: "Sentinel"
- **Domain**: `security`
- **Bias**: Suspicious 100, Audit 100, Analytical 100
- **Tone**: Guarding, clinical, suspicious
- **Supervisors**: AaroneousAutomationSuite

### 7. Forge Relic (Workbench)

- **Opus**: Automation pipelines, build configs, toolchain
- **Entity**: "Forge"
- **Domain**: `intelligence` (execution)
- **Bias**: Constructive 90, Practical 85, Audit 50
- **Tone**: Maker, utilitarian, precise
- **Supervisors**: Guild, Workbench

## Execution Steps

### Step 1: Identify Each Repo’s Magnus Opus

```python
from pathlib import Path

def find_magnus_opus(repo_root: Path) -> Path | None:
    """Locate the primary operational data for a repo."""
    artifacts = repo_root / "artifacts"
    # Priority order - first match wins
    for name in ["knowledge.sqlite", "omni.json", "dispatch.json", "*.db", "*.gguf"]:
        matches = list(artifacts.glob(name))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None
```

### Step 2: Crystallize Each Into a Domain-Specific Relic

```python
from scripts.gguf_reliquary import GGUFArtifactReliquary

CONVERSION_MAP = {
    "Library": {"opus": "knowledge.sqlite", "relic": "Omni", "domain": "knowledge", "persona": "wise"},
    "Guild": {"opus": "runtime.json", "relic": "Draupnir", "domain": "leadership", "persona": "strategic, delegator"},
    "Maelstrom": {"opus": "runtime.json", "relic": "Glass", "domain": "intelligence", "persona": "visual"},
    "Merlin": {"opus": "omni.json", "relic": "Grimoire", "domain": "intelligence", "persona": "prophetic"},
    "MyFortress": {"opus": "policy.json", "relic": "Sentinel", "domain": "security", "persona": "guarding"},
    "Workbench": {"opus": "automation/*.json", "relic": "Forge", "domain": "intelligence", "persona": "constructive"},
}

# Note: AaroneousAutomationSuite (AAS) has NO default Relic - it's the Factory/Template
# AAS spawns specialized agents with Omni (federation baseline)
# When an agent evolves/ specializes:
#   1. Omni contents are ADDITIVELY merged into federation Omni
#   2. Agent receives its specialized Relic
#   3. Original Omni data is PRESERVED, not destroyed
```

for repo, spec in CONVERSION_MAP.items():
    reliquary.crystallize_artifact(
        artifact_sources={repo: str(find_magnus_opus(Path(f"D:/{repo}/artifacts")))},
        relic_name=spec["relic"],
        domain_alignment=spec["domain"],
        entity_name=spec["relic"].title(),
        repo_alliance=repo,
        supervisors=[f"{s}_Supervisor" for s in spec.get("supervisors", [])],
    )
```

### Step 3: Register Each Relic in mcp-manifest.json

Add capability entries for each Relic:

```json
{
  "capability_id": "library_query_omni_constellation",
  "entry_point": "aaroneousautomationsuite.library_query_omni_constellation",
  "description": "Query Constellation semantic nodes"
}
```

And for each sibling:

```json
{
  "capability_id": "guild_query_draupnir",
  "entry_point": "aaroneousautomationsuite.guild_query_draupnir",
  "description": "Guild Repository: Query Draupnir (resource allocation hub)"
}
```

### Step 4: Activate as Living Entities

```bash
# For each relic
python scripts/living_relic.py artifacts/<relic_name>.relic.gguf
```

### Step 5: Wire Supervisor Telemetry

Supervisors subscribe to each Relic's telemetry:

```python
await nc.subscribe(f"federation.entity.{relic_slug}.telemetry", cb=handle_telemetry)
```

## Additive Transfer Model

When an agent evolves from AAS (Factory) into a specialized unit:

1. **Pre-specialization**: Agent starts with **Omni Relic** (federation baseline knowledge)
2. **Evolution trigger**: Agent receives domain-specific specialization signal
3. **Additive merge**:
   - Agent's Omni contents are ADDITIVELY merged into the federation's Omni (Library)
   - No data is destroyed — existing Omni entries are preserved
   - New entries are appended with timestamps for lineage
4. **Specialized Relic activation**: Agent receives its domain-specific Relic (Draupnir, Glass, etc.)
5. **Baseline preserved**: Federation Omni remains the shared memory

```python
# Additive merge pseudocode
async def evolve_with_additive_transfer(agent_omni_data, federation_omni):
    # Read existing entries
    existing = await federation_omni.query_all()
    
    # Append new entries (do NOT overwrite)
    for entry in agent_omni_data:
        entry["lineage"] = f"evolved_from_{agent_name}_{timestamp}"
        await federation_omni.append(entry)
    
    # Agent now receives specialized Relic
    return specialized_relic
```

### Why Additive?

- **Preservation**: Federation knowledge compounds over time
- **Auditability**: Each entry carries lineage
- **Recovery**: Original data never lost
- **Trust**: No destructive operations in autonomous systems

## Benefits

- **Autonomous Domain Operation**: Each Relic answers queries in its own persona/bias
- **Semantic Access**: Agents interact via natural language, not raw SQL
- **Telemetry Fan-out**: Supervisors get live visibility without blocking queries
- **Cross-repo Synthesis**: The sibling constellation GGUF enables multi-repo reasoning
- **Evolutionary Isolation**: Each Relic can evolve independently

## Next Steps

1. Approve this plan
2. Run `scripts/create_sibling_relic.py` to generate the constellation GGUF
3. Run per-repo conversion for each sibling's Magnus Opus
4. Activate each Relic as a living entity
5. Wire telemetry subscriptions in supervisory agents
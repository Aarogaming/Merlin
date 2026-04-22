GGUF Discovery, Selection, and Distillation for AAS

=== DISCOVERY ===

```python
from pathlib import Path
from gguf import GGUFReader

ARTIFACTS = Path("artifacts")
GGUF_DIRS = [
    ARTIFACTS,
    Path("D:/Models"),  # External model store
    Path("runtime/models"),
]

def discover_gguf():
    """Find all available GGUF files."""
    gguf_list = []
    for dir in GGUF_DIRS:
        if dir.exists():
            gguf_list.extend(dir.glob("*.gguf"))
    return gguf_list

def identify_gguf(path):
    """Extract GGUF metadata and capabilities."""
    reader = GGUFReader(str(path))
    fields = dict(reader.fields)
    
    return {
        "path": str(path),
        "name": path.name,
        "size_mb": path.stat().st_size / (1024*1024),
        "is_aas_wrapped": any(k.startswith("aas.") for k in fields),
        "domains": [k.replace("aas.dna.domain.", "") for k in fields if k.startswith("aas.dna.domain.")],
        "biases": {k.replace("aas.dna.bias.", ""): fields[k] for k in fields if k.startswith("aas.dna.bias.")},
        "skills": [k.replace("aas.skill.", "") for k in fields if k.startswith("aas.skill.")],
        "personality": {k.replace("aas.dna.persona.", ""): fields[k] for k in fields if k.startswith("aas.dna.persona.")},
        "epoch": fields.get("aas.evolution.epoch", 0),
        "parameter_count": fields.get("aas.evolution.parameter_count", 0),
        "tokenizer": fields.get("tokenizer", "unknown"),
        "architecture": fields.get("general.architecture", "unknown"),
    }
```

=== SELECTION STRATEGY ===

| Model Type     | Quantization | Size/1B params | Latency | Use Case              |
|---------------|---------------|----------------|---------|----------------------|
| Q4_K_M        | 4-bit        | ~1GB           | ~50ms   | Fast reflex, triage   |
| Q5_K_M        | 5-bit        | ~1.3GB        | ~100ms  | Balanced operations  |
| Q8_0          | 8-bit        | ~2GB          | ~200ms  | Deep reasoning       |
| F16           | 16-bit       | ~4GB          | ~500ms  | Maximum quality      |

def select_gguf(task_requirement):
    """Select optimal GGUF based on task."""
    available = discover_gguf()
    
    if not available:
        return None  # Fall back to external API
    
    # Score each GGUF
    scored = []
    for gguf in available:
        info = identify_gguf(gguf)
        score = 0
        
        if task_requirement == "fast":
            # Prefer smaller, faster
            score -= info["size_mb"]
            if info["is_aas_wrapped"]:
                score += 100  # Bonus for AAS personality
        elif task_requirement == "deep":
            # Prefer larger, more capable
            score += info.get("parameter_count", 0)
        elif task_requirement == "reasoning":
            # Prefer domain-specific
            score += len(info["domains"]) * 10
        
        scored.append((score, info))
    
    scored.sort(reverse=True)
    return scored[0][1] if scored else None

=== DISTILLATION ===

A GGUF can be updated with AAS-specific DNA:

```python
from gguf import GGUFWriter

def distill_gguf(gguf_path, epigenetics_path):
    """Inject AAS DNA into GGUF."""
    reader = GGUFReader(str(gguf_path))
    writer = GGUFWriter(str(Path(gguf_path).with_suffix(".aas.gguf")), "aas_agent")
    
    # Copy original fields
    for key, field in reader.fields.items():
        if not key.startswith("aas."):
            copy_field(writer, key, field)
    
    # Inject AAS DNA
    import json
    with open(epigenetics_path) as f:
        dna = json.load(f)
    
    writer.add_string("aas.profile.name", dna.get("profile_name"))
    writer.add_uint32("aas.evolution.epoch", dna.get("evolutionary_epoch", 1))
    writer.add_uint32("aas.evolution.parameter_count", dna.get("parameter_count", 0))
    
    for domain, weight in dna.get("domain_weights", {}).items():
        writer.add_float32(f"aas.dna.domain.{domain}", weight)
    
    for bias, value in dna.get("cognitive_biases", {}).items():
        writer.add_float32(f"aas.dna.bias.{bias}", value)
    
    writer.write()
    return writer
```

=== INFERENCE TIER ===

| Tier | Model Source | Latency | Cost | Use Case |
|------|-------------|---------|------|---------|
| Tier 1 | Local GGUF (Q4) | ~50ms | Free | Fast triage, routing |
| Tier 2 | Local GGUF (Q8) | ~200ms | Free | Complex reasoning |
| Tier 3 | External API | ~2s | $ | Fallback |

=== ADVANTAGES OVER EXTERNAL APIs ===

| Aspect | Local GGUF | External API (OpenAI/Anthropic) |
|--------|-------------|------------------------------|
| Latency | 50-500ms | 2000-10000ms |
| Cost | Free (perpetual) | Per-token pricing |
| Privacy | 100% local | Data leaves machine |
| Customization | DNA injection | Fixed personality |
| Offline | Full operation | Network required |
| Ownership | Your model | Vendor controls |
| Evolution | Real-time mutation | Static model |

=== MCP BRIDGE - THREE TIER ACCESS ===

```
External Agents (VS Code, Claude Desktop)
         │
         ▼ MCP Standard (tools only)
┌────────────────────────────────┐
│      MCP Bridge / Gateway       │
└────────────────────────────────┘
         │
         ▼ NATS (rich federation ops)
┌────────────────────────────────┐
│    Internal AAS Protocol        │
└────────────────────────────────┘
```

**Usage:**

```bash
# View all tiers
python scripts/mcp_bridge.py --tiers

# List external MCP tools
python scripts/mcp_bridge.py --list-tools

# Generate MCP config for VS Code
python scripts/mcp_bridge.py --generate
```

**Tiers:**

| Tier | Access | What |
|------|--------|------|
| 1 | External MCP | Standard tools only |
| 2 | NATS Bridge | Full metadata + routing |
| 3 | Internal | DNA, epigenetics, evolution |

=== OFFLINE PARTITIONING ===

GGUF allows reading metadata without loading neural tensors (0 VRAM):

```python
from gguf import GGUFReader

# Instant scan - milliseconds, 0 VRAM
reader = GGUFReader("model.gguf")
fields = dict(reader.fields)

# Extract AAS DNA
for key in fields:
    if key.startswith("aas.dna."): ...
    
# Extract embedded skills  
for key in fields:
    if key.startswith("aas.skill."): ...
```

**Existing Tools:**
- `scripts/gguf_partitioner.py` - Inspect/extract without loading
- `scripts/dynamic_gguf.py` - Inject DNA into GGUF
- `scripts/aas_inference.py` - Full loader with partial layers

**Operations:**
1. **Inspect** - `gguf_partitioner.py --inspect model.gguf`
2. **Extract DNA** - `gguf_partitioner.py --extract-dna model.gguf`
3. **Extract Skill** - `gguf_partitioner.py --extract-skill skill_name`
4. **Distill DNA** - `dynamic_gguf.py model.gguf epigenetics.json`
5. **Partial Load** - `aas_inference.py` with n_gpu_layers parameter
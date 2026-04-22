import json
import argparse
from pathlib import Path

try:
    from gguf import GGUFWriter, GGUFReader
    HAS_GGUF = True
except ImportError:
    HAS_GGUF = False

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"

class GGUFArtifactReliquary:
    """
    Transforms passive databases (like Omni SQLite or Grimoire JSONs) into 
    Active GGUF Relics. 
    By compiling data into a GGUF, the artifact itself can hold Epigenetic DNA, 
    meaning a database can dictate HOW it should be queried (its own strictness, 
    variance, and behavior) when an agent attaches to it.
    """
    def __init__(self):
        if not HAS_GGUF:
            print("Simulating GGUF Reliquary since package is missing...")
            self.simulating = True
            return
        self.simulating = False

    def crystallize_artifact(
        self,
        artifact_sources: dict[str, str] | str,
        relic_name: str,
        domain_alignment: str,
        entity_name: str = "Unnamed Relic",
        repo_alliance: str = "knowledge",
        supervisors: list[str] | None = None,
    ):
        """
        Compile one or more artifacts into a Living GGUF Relic.
        
        Args:
            artifact_sources: Either a single path string (for backward compatibility) 
                            or a dictionary mapping repo_name to artifact path
            relic_name: Name for the relic (without extension)
            domain_alignment: Knowledge, intelligence, security, leadership, etc.
            entity_name: Name of the Living Entity (e.g., Omni, Grimoire)
            repo_alliance: Owning alliance/domain responsible for this entity
            supervisors: List of supervisor agents granted direct telemetry/control access
        """
        # Handle backward compatibility - single source
        if isinstance(artifact_sources, str):
            artifact_sources = {"primary": artifact_sources}
            
        # Validate all sources exist
        for repo_name, source_path in artifact_sources.items():
            src = Path(source_path)
            if not src.exists():
                print(f"Error: Source for {repo_name} not found at {src}")
                return
                
        out_path = ARTIFACTS_DIR / f"{relic_name}.relic.gguf"
        print(f"--- GGUF Reliquary ---")
        print(f"Crystallizing {len(artifact_sources)} artifact(s) -> {out_path.name}")
        
        alignment = domain_alignment.lower()
        owner_alliance = repo_alliance.lower()
        supervisor_list = supervisors or []
        
        if self.simulating:
            with open(out_path, "wb") as f:
                f.write(b"GGUF_SIMULATION_RELIC")
            # We also save a JSON sidecar in simulation mode to act as the metadata store
            with open(str(out_path) + ".meta.json", "w") as f:
                json.dump({
                    "alignment": alignment,
                    "entity_name": entity_name,
                    "repo_alliance": owner_alliance,
                    "supervisors": supervisor_list,
                    "artifact_sources": {k: str(v) for k, v in artifact_sources.items()}
                }, f)
            print(f"[Simulation Success] Artifact sealed into Living GGUF Relic.")
            print(f"Entity Awakened: {entity_name} of the {alignment} domain (owner: {owner_alliance}).")
            return
        
        writer = GGUFWriter(str(out_path), "aas_relic")
        writer.add_string("aas.relic.domain", alignment)
        
        # --- THE LIVING RELIC ENTITY DATA ---
        writer.add_string("aas.relic.entity.name", entity_name)
        writer.add_string("aas.relic.owner.repo_alliance", owner_alliance)
        writer.add_string("aas.relic.owner.supervisors_json", json.dumps(supervisor_list))
        writer.add_uint32("aas.relic.entity.transformer_active", 1) # Boolean flag indicating it needs a transformer host
        
        if alignment in ["knowledge", "intelligence"]:
            writer.add_float32("aas.relic.bias.creative_variance", 85.0)
            writer.add_float32("aas.relic.bias.analytical_depth", 90.0)
            writer.add_float32("aas.relic.bias.audit_strictness", 20.0)
            writer.add_string("aas.relic.entity.tone", "wise, cryptic, expansive")
        elif alignment in ["security", "leadership"]:
            writer.add_float32("aas.relic.bias.creative_variance", 10.0)
            writer.add_float32("aas.relic.bias.analytical_depth", 100.0)
            writer.add_float32("aas.relic.bias.audit_strictness", 100.0)
            writer.add_string("aas.relic.entity.tone", "suspicious, clinical, guarding")
        else:
            writer.add_float32("aas.relic.bias.creative_variance", 50.0)
            writer.add_float32("aas.relic.bias.analytical_depth", 50.0)
            writer.add_float32("aas.relic.bias.audit_strictness", 50.0)
            writer.add_string("aas.relic.entity.tone", "neutral, factual")
        
        # Store each artifact as a separate payload with repo name as key
        for repo_name, source_path in artifact_sources.items():
            src = Path(source_path)
            with open(src, "rb") as f:
                raw_bytes = f.read()
                
            writer.add_array(f"aas.relic.payload.{repo_name}", list(raw_bytes))
            writer.add_string(f"aas.relic.payload.{repo_name}.filename", src.name)
            writer.add_string(f"aas.relic.payload.{repo_name}.size", str(len(raw_bytes)))
        
        # Add manifest of all artifacts
        writer.add_string("aas.relic.artifact_count", str(len(artifact_sources)))
        writer.add_string("aas.relic.artifact_manifest", json.dumps({k: str(v) for k, v in artifact_sources.items()}))
        
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file()
        writer.close()
        
        print(f"[Success] Artifact sealed into Living GGUF Relic.")
        print(f"Entity Awakened: {entity_name} of the {alignment} domain (owner: {owner_alliance}).")
        print(f"Included artifacts from: {', '.join(artifact_sources.keys())}")

    def attune_to_relic(self, relic_path: str):
        if self.simulating:
            print(f"Simulating attunement to {Path(relic_path).name}")
            return
            
        relic = Path(relic_path)
        reader = GGUFReader(str(relic))
        
        print(f"Attuning agent to Relic: {relic.name}")
        
        relic_biases = {}
        for key, field in reader.fields.items():
            if key.startswith("aas.relic.bias."):
                val = field.parts[field.data[0]] if hasattr(field, 'parts') else field.parts[-1]
                if isinstance(val, (list, tuple)) and len(val) > 0: val = val[0]
                relic_biases[key.split('.')[-1]] = val
                
        print(f"Relic emits cognitive aura: {relic_biases}")
        print("Agent physics temporarily altered by Artifact aura.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile passive data into an Active GGUF Relic.")
    parser.add_argument("action", choices=["crystallize", "attune"])
    parser.add_argument("target", help="Path to the source file (crystallize) or .relic.gguf (attune)")
    parser.add_argument("--domain", default="knowledge", help="Domain alignment for the relic")
    parser.add_argument("--name", default="Unnamed Relic", help="The name of the Living Entity (e.g., Omni, Grimoire)")
    parser.add_argument("--repo-alliance", default="knowledge", help="Owning alliance/domain responsible for this entity")
    parser.add_argument("--supervisor", action="append", default=[], help="Supervisor agent granted direct telemetry/control access (repeatable)")
    
    args = parser.parse_args()
    reliquary = GGUFArtifactReliquary()
    
    if args.action == "crystallize":
        # For CLI usage, treat target as primary artifact
        reliquary.crystallize_artifact(
            {"primary": args.target},
            Path(args.target).stem,
            args.domain,
            args.name,
            args.repo_alliance,
            args.supervisor,
        )
    elif args.action == "attune":
        reliquary.attune_to_relic(args.target)

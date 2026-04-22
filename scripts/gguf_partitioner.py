import os
import json
import argparse
from pathlib import Path

try:
    from gguf import GGUFReader
    HAS_GGUF = True
except ImportError:
    HAS_GGUF = False

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = BASE_DIR / "artifacts"
SKILLS_DIR = BASE_DIR / "plugins" / "skills"
EPIGENETICS_PATH = BASE_DIR / "genome" / "identity.epigenetics.json"

class GGUFPartitioner:
    """
    Dynamic Partitioning Engine.
    Because GGUF separates Key-Value metadata from heavy Neural Tensors, 
    we can instantly 'Siphon' specific components (DNA, Skills, Configs) 
    out of a massive 70B model file without ever loading the AI into VRAM.
    """
    def __init__(self):
        if not HAS_GGUF:
            print("Error: The 'gguf' python package is required. Run: pip install gguf")
            return

    def inspect(self, gguf_path: str):
        """Instantly lists all partitionable components inside the GGUF."""
        if not HAS_GGUF: return
        
        path = Path(gguf_path)
        if not path.exists():
            print(f"File not found: {path}")
            return
            
        print(f"--- GGUF Partition Inspector ---")
        print(f"Scanning: {path.name}")
        
        # Reads ONLY the header and KV store. Takes milliseconds, 0 VRAM.
        reader = GGUFReader(str(path))
        
        dna_keys = 0
        skills = []
        
        for key in reader.fields.keys():
            if key.startswith("aas.dna."):
                dna_keys += 1
            elif key.startswith("aas.skill.") and key != "aas.skill.total_count":
                skills.append(key.replace("aas.skill.", ""))
                
        print(f"\n[Partitions Available for Extraction]")
        print(f"- Epigenetic DNA (Found {dna_keys} genetic markers)")
        print(f"- Embedded Python Skills ({len(skills)} found):")
        for s in skills:
            print(f"  * {s}")
        print("\nUse --extract to pull a specific partition.")

    def extract_dna(self, gguf_path: str):
        """Siphons the Epigenetic profile and overwrites local DNA."""
        if not HAS_GGUF: return
        reader = GGUFReader(str(gguf_path))
        
        # Reconstruct the JSON from binary floats/strings
        dna = {
            "schema_version": "3.0",
            "preset": "siphoned_from_gguf",
            "persona_vectors": {},
            "cognitive_biases": {},
            "domain_weights": {}
        }
        
        for key, field in reader.fields.items():
            val = self._extract_val(field)
            if key == "aas.profile.name": dna["profile_name"] = val
            elif key == "aas.evolution.epoch": dna["evolutionary_epoch"] = val
            elif key == "aas.evolution.parameter_count": dna["parameter_count"] = val
            elif key.startswith("aas.dna.domain."): dna["domain_weights"][key.split('.')[-1].capitalize()] = val
            elif key.startswith("aas.dna.bias."): dna["cognitive_biases"][key.split('.')[-1]] = val
            elif key.startswith("aas.dna.persona."): dna["persona_vectors"][key.split('.')[-1]] = val
            
        with open(EPIGENETICS_PATH, "w", encoding="utf-8") as f:
            json.dump(dna, f, indent=2)
        print(f"[Success] Siphoned Epigenetic DNA from GGUF. Local agent physics overwritten.")

    def extract_skill(self, gguf_path: str, skill_name: str):
        """Siphons a specific embedded Python script and hot-loads it into the agent."""
        if not HAS_GGUF: return
        reader = GGUFReader(str(gguf_path))
        
        target_key = f"aas.skill.skill_{skill_name}"
        if target_key not in reader.fields:
            # Try without the 'skill_' prefix just in case
            target_key = f"aas.skill.{skill_name}"
            if target_key not in reader.fields:
                print(f"Error: Skill '{skill_name}' not found in partition table.")
                return
            
        field = reader.fields[target_key]
        python_code = self._extract_val(field)
        
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SKILLS_DIR / f"skill_{skill_name}.py"
        
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(python_code)
            
        print(f"[Success] Siphoned '{skill_name}' from GGUF without loading neural tensors.")
        print(f"Skill written to: {out_path.name}")

    def _extract_val(self, field):
        """Helper to get actual python value from GGUFField."""
        # GGUF fields usually contain arrays, even for single values
        val = field.parts[field.data[0]] if hasattr(field, 'parts') else field.parts[-1]
        if isinstance(val, (list, tuple)) and len(val) > 0:
            return val[0]
        return val

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamically partition and siphon data from a GGUF.")
    parser.add_argument("gguf_path", help="Path to the .gguf file")
    parser.add_argument("--inspect", action="store_true", help="List all available partitions")
    parser.add_argument("--extract-dna", action="store_true", help="Siphon Epigenetic DNA into local agent")
    parser.add_argument("--extract-skill", type=str, help="Siphon a specific python skill by name")
    
    args = parser.parse_args()
    partitioner = GGUFPartitioner()
    
    if args.inspect:
        partitioner.inspect(args.gguf_path)
    elif args.extract_dna:
        partitioner.extract_dna(args.gguf_path)
    elif args.extract_skill:
        partitioner.extract_skill(args.gguf_path, args.extract_skill)
    else:
        print("Please specify an action: --inspect, --extract-dna, or --extract-skill")

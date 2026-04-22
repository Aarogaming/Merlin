import json
import urllib.request
import urllib.error
import argparse
from pathlib import Path

TRAITS_DIR = Path(__file__).resolve().parents[1] / "genome" / "traits"

class OpenSourceHiveMiner:
    """
    Connects to the open-source ecosystem (HuggingFace Hub API) to dissect real, 
    live models. It parses their parameter counts, tags, and architectures, and 
    translates them into Agent-Zero Epigenetic DNA traits.
    """
    
    def __init__(self):
        self.api_base = "https://huggingface.co/api/models"

    def fetch_model_metadata(self, model_id: str) -> dict:
        url = f"{self.api_base}/{model_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'AaroneousAutomationSuite/1.0'})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            print(f"Failed to fetch {model_id}: {e}")
            return {}

    def extract_parameters(self, tags: list) -> float:
        """Heuristically extracts parameter count from tags (e.g., '7b', '70b')."""
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower.endswith('b') and tag_lower[:-1].replace('.', '').isdigit():
                return float(tag_lower[:-1])
        return 7.0  # Fallback assumption for an average local model

    def dissect(self, model_id: str):
        print(f"--- Live Open-Source Dissector ---")
        print(f"Connecting to global hive to fetch: {model_id}")
        
        metadata = self.fetch_model_metadata(model_id)
        if not metadata:
            return

        tags = metadata.get("tags", [])
        downloads = metadata.get("downloads", 0)
        
        # Determine architecture and scale
        is_instruct = "instruction-tuned" in tags or "chat" in [t.lower() for t in tags]
        is_coder = "code" in tags or "programming" in tags
        params_billions = self.extract_parameters(tags)
        
        print(f"Dissected: {params_billions}B Parameters | Instruct: {is_instruct} | Coder: {is_coder}")
        
        # Translate to Epigenetic Mathematics
        trait_id = model_id.split("/")[-1].lower().replace("-", "_").replace(".", "_")
        
        depth_score = min(100.0, max(10.0, (params_billions / 100.0) * 100.0))
        
        trait = {
            "trait_id": trait_id,
            "description": f"Harvested live from {model_id} ({params_billions}B params, {downloads} downloads).",
            "persona_modifiers": {
                "formality": round((depth_score * 0.7) + 30, 2),
            },
            "cognitive_modifiers": {
                "analytical_depth": round(depth_score, 2),
            },
            "domain_modifiers": {}
        }

        if is_instruct:
            trait["persona_modifiers"]["directive_authority"] = 90.0
            trait["persona_modifiers"]["verbosity"] = 40.0
            trait["cognitive_modifiers"]["delegation_bias"] = 20.0
            trait["domain_modifiers"]["Leadership"] = 80.0
        else:
            trait["persona_modifiers"]["directive_authority"] = 20.0
            trait["persona_modifiers"]["verbosity"] = 90.0
            trait["cognitive_modifiers"]["creative_variance"] = 85.0
            trait["domain_modifiers"]["Creation"] = 80.0

        if is_coder:
            trait["persona_modifiers"]["primary_archetype"] = "Software Architect"
            trait["domain_modifiers"]["Thought"] = 95.0
            trait["cognitive_modifiers"]["audit_strictness"] = 80.0
            
        out_path = TRAITS_DIR / f"{trait_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(trait, f, indent=2)
            
        print(f"[Success] Model DNA crystallized as genome/traits/{trait_id}.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id", help="HuggingFace Model ID (e.g., meta-llama/Meta-Llama-3-8B-Instruct)")
    args = parser.parse_args()
    
    miner = OpenSourceHiveMiner()
    miner.dissect(args.model_id)

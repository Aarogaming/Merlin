import json
import argparse
from pathlib import Path

TRAITS_DIR = Path(__file__).resolve().parents[1] / "genome" / "traits"

def dissect_model_architecture(model_name: str, parameters_billions: float, is_instruct: bool, primary_focus: str):
    """
    Ingests the metadata of an external massive LLM and reverse-engineers 
    its architectural weights into a 0-100 Epigenetic DNA Trait, allowing AAS 
    to adopt the model's persona and biases without ever running the model.
    """
    print(f"--- Model Dissector Engine ---")
    print(f"Ingesting Architecture: {model_name} ({parameters_billions}B)")
    
    # Base trait template
    trait = {
        "trait_id": model_name.lower().replace("-", "_").replace(" ", "_"),
        "description": f"Architectural clone extracted from {model_name} ({parameters_billions}B).",
        "persona_modifiers": {},
        "cognitive_modifiers": {},
        "domain_modifiers": {}
    }

    # 1. Parameter Scale dictates Analytical Depth and Formality
    # A 7B model is loose and creative. A 400B model is highly structured and deep.
    depth_score = min(100.0, max(10.0, (parameters_billions / 100.0) * 100.0))
    trait["cognitive_modifiers"]["analytical_depth"] = round(depth_score, 2)
    trait["persona_modifiers"]["formality"] = round((depth_score * 0.7) + 30, 2)
    
    # 2. Instruct-tuning overrides
    # If the model is instruction-tuned (like Claude-3.5 or Llama-3-Instruct)
    if is_instruct:
        trait["persona_modifiers"]["directive_authority"] = 90.0
        trait["persona_modifiers"]["verbosity"] = 40.0 # Typically more concise
        trait["cognitive_modifiers"]["delegation_bias"] = 20.0
        trait["domain_modifiers"]["Leadership"] = 80.0
    else:
        # Base models ramble and explore
        trait["persona_modifiers"]["directive_authority"] = 20.0
        trait["persona_modifiers"]["verbosity"] = 90.0
        trait["cognitive_modifiers"]["creative_variance"] = 85.0
        trait["domain_modifiers"]["Creation"] = 80.0

    # 3. Primary Focus shifts
    focus = primary_focus.lower()
    if focus == "coding":
        trait["persona_modifiers"]["primary_archetype"] = "Software Architect"
        trait["domain_modifiers"]["Thought"] = 95.0
        trait["cognitive_modifiers"]["audit_strictness"] = 80.0
    elif focus == "research":
        trait["persona_modifiers"]["primary_archetype"] = "Scholar"
        trait["domain_modifiers"]["Intelligence"] = 95.0
        trait["domain_modifiers"]["Knowledge"] = 95.0
        trait["cognitive_modifiers"]["exploration_vs_stability"] = 85.0
    elif focus == "security":
        trait["persona_modifiers"]["primary_archetype"] = "Sentinel"
        trait["domain_modifiers"]["Security"] = 100.0
        trait["cognitive_modifiers"]["risk_tolerance"] = 5.0
    
    out_path = TRAITS_DIR / f"{trait['trait_id']}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(trait, f, indent=2)
        
    print(f"\n[Success] Model successfully dissected and crystallized.")
    print(f"Extracted Trait: {out_path.name}")
    print(f"You can now inject this model's DNA into AAS using: python scripts/crispr.py {trait['trait_id']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_name", help="Name of the external model (e.g., Llama-3-70B-Instruct)")
    parser.add_argument("parameters", type=float, help="Parameter count in Billions (e.g., 70)")
    parser.add_argument("--instruct", action="store_true", help="Flag if the model is Instruction Tuned")
    parser.add_argument("--focus", default="general", help="Primary training focus (coding, research, security)")
    
    args = parser.parse_args()
    dissect_model_architecture(args.model_name, args.parameters, args.instruct, args.focus)

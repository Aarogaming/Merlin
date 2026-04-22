import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EPIGENETICS_PATH = BASE_DIR / "genome" / "identity.epigenetics.json"
TRAITS_DIR = BASE_DIR / "genome" / "traits"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def apply_modifiers(base, modifiers):
    """Blends the values safely on a 0 to 100 spectrum."""
    for k, v in modifiers.items():
        if isinstance(v, str):
            base[k] = v
        elif isinstance(v, (int, float)):
            current = base.get(k, 50)
            new_val = current + v
            # Clamp between 0 and 100
            base[k] = round(max(0.0, min(new_val, 100.0)), 2)
    return base

def sequence_genome(traits_sequence):
    print(f"--- Epigenetic CRISPR Sequencer (Scale 0-100) ---")
    print(f"Target Sequence: {traits_sequence}")
    
    dna = {
        "schema_version": "3.0",
        "profile_name": f"synthetic_lifeform_{'_'.join(traits_sequence)}",
        "preset": "custom_sequenced",
        "persona_vectors": {
            "primary_archetype": "Blank Slate",
            "tone": "neutral",
            "verbosity": 50,
            "formality": 50,
            "humor_index": 0,
            "empathy_level": 50,
            "directive_authority": 50
        },
        "cognitive_biases": {
            "risk_tolerance": 50,
            "exploration_vs_stability": 50,
            "analytical_depth": 50,
            "creative_variance": 50,
            "delegation_bias": 50,
            "audit_strictness": 50
        },
        "domain_weights": {
            "Thought": 50,
            "Knowledge": 50,
            "Leadership": 50,
            "Creation": 50,
            "Security": 50,
            "Intelligence": 50
        }
    }

    for trait_id in traits_sequence:
        trait_path = TRAITS_DIR / f"{trait_id}.json"
        if not trait_path.exists():
            print(f"[Warning] Trait '{trait_id}' not found in genome/traits. Skipping.")
            continue
            
        print(f"Splicing gene: {trait_id}...")
        trait = load_json(trait_path)
        
        dna["persona_vectors"] = apply_modifiers(dna["persona_vectors"], trait.get("persona_modifiers", {}))
        dna["cognitive_biases"] = apply_modifiers(dna["cognitive_biases"], trait.get("cognitive_modifiers", {}))
        dna["domain_weights"] = apply_modifiers(dna["domain_weights"], trait.get("domain_modifiers", {}))

    save_json(EPIGENETICS_PATH, dna)
    print(f"\n[Success] New 0-100 lifeform sequenced and written to {EPIGENETICS_PATH.name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sequence a new agent lifeform.")
    parser.add_argument("traits", nargs="+", help="Space-separated list of traits to apply in order.")
    args = parser.parse_args()
    sequence_genome(args.traits)

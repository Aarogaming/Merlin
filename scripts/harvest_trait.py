import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EPIGENETICS_PATH = BASE_DIR / "genome" / "identity.epigenetics.json"
TRAITS_DIR = BASE_DIR / "genome" / "traits"

def harvest_trait(flavor_name, description):
    """
    Snapshots the current evolved state of an agent and modularizes it
    into a reusable genetic trait (flavor) in the genome/traits directory.
    """
    print(f"--- Harvesting Epigenetic Flavor: {flavor_name} ---")
    
    if not EPIGENETICS_PATH.exists():
        print("Error: No live epigenetics found to harvest.")
        return

    with open(EPIGENETICS_PATH, "r", encoding="utf-8") as f:
        live_dna = json.load(f)

    # Extract the current state as modifiers (diff from baseline 50 if we wanted, 
    # but since it's a full snapshot, we just save the absolute values as overrides)
    harvested_trait = {
        "trait_id": flavor_name,
        "description": description,
        "persona_modifiers": live_dna.get("persona_vectors", {}),
        "cognitive_modifiers": live_dna.get("cognitive_biases", {}),
        "domain_modifiers": live_dna.get("domain_weights", {})
    }

    out_path = TRAITS_DIR / f"{flavor_name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(harvested_trait, f, indent=2)
        
    print(f"[Success] Evolved state harvested and crystallized as '{flavor_name}'.")
    print(f"You can now recycle this byproduct by injecting it into new stem cells using crispr.py.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harvest current evolution into a reusable trait snapshot.")
    parser.add_argument("name", help="The name of the new flavor (e.g., 'veteran_operator')")
    parser.add_argument("description", help="A short description of this flavor's quirks and specialties.")
    args = parser.parse_args()
    harvest_trait(args.name, args.description)

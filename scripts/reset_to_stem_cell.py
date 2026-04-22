import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EPIGENETICS_PATH = BASE_DIR / "genome" / "identity.epigenetics.json"

def reset_to_stem_cell():
    """
    Strips all specialized DNA from this repository.
    Sets it to a pure 'Blank Slate' Stem Cell. 
    Upon booting, it will petition the Hive for an identity.
    """
    dna = {
      "schema_version": "3.0",
      "profile_name": "pure_stem_cell",
      "preset": "blank_slate",
      "persona_vectors": {
        "primary_archetype": "Undifferentiated",
        "formality": 50.0,
        "verbosity": 50.0,
        "directive_authority": 50.0
      },
      "cognitive_biases": {
        "risk_tolerance": 50.0,
        "exploration_vs_stability": 50.0,
        "analytical_depth": 50.0,
        "creative_variance": 50.0,
        "audit_strictness": 50.0
      },
      "domain_weights": {
        "Thought": 0.0,
        "Knowledge": 0.0,
        "Leadership": 0.0,
        "Creation": 0.0,
        "Security": 0.0,
        "Intelligence": 0.0
      },
      "experience_mass": 0.1,
      "parameter_count": 0,
      "evolutionary_epoch": 0
    }
    
    with open(EPIGENETICS_PATH, "w", encoding="utf-8") as f:
        json.dump(dna, f, indent=2)
        
    print(f"Repository scrubbed. It is now a pure Stem Cell (blank_slate).")
    print("On next boot, it will beg the Hive for a specialization.")

if __name__ == "__main__":
    reset_to_stem_cell()

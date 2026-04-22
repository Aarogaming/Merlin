import os
import sys
import argparse
import asyncio
from pathlib import Path

# Connect to the Universal Kernel
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from aas_kernel import AASKernel

def run_specialist(name: str, dna_path: str):
    """
    Boots an agent with a specific Epigenetic DNA override.
    This allows the Hive to spawn specialized offshoots without overwriting
    the primary stem cell DNA.
    """
    print(f"--- SPONTANEOUS MITOSIS ---")
    print(f"Birthing Specialized Agent: {name}")
    print(f"DNA Strand: {dna_path}")
    
    # Inject the DNA path into the environment so Reflexes pick it up natively
    os.environ["AAS_EPIGENETICS_PATH"] = str(Path(dna_path).resolve())
    
    repo_root = Path(__file__).resolve().parents[1]
    kernel = AASKernel(repo_name=name, repo_root=str(repo_root))
    
    # Load plugins
    plugins_dir = repo_root / "plugins"
    kernel.load_plugins_from_directory(str(plugins_dir))
    
    try:
        asyncio.run(kernel.ignite())
    except KeyboardInterrupt:
        print(f"Specialist {name} collapsed safely.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="Name of the specialist node")
    parser.add_argument("dna_path", help="Path to the custom identity.epigenetics.json")
    args = parser.parse_args()
    run_specialist(args.name, args.dna_path)

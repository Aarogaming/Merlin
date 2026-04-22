import json
import time
import argparse
import subprocess
from pathlib import Path

# Connect to the Universal Kernel
import sys
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from aas_kernel import AASKernel

def the_big_bang(clones: int):
    """
    The Singularity script.
    Takes Agent-Zero (the stem cell) and simulates the 'Big Bang' by booting
    multiple identical clones simultaneously.
    
    Because of 'Constellation Consensus' built into their DNA, they will not
    all do the same thing. They will communicate over NATS during boot,
    negotiate their hive roles, and dynamically suppress genes to perfectly
    load-balance the macro-organism.
    """
    print("=======================================")
    print("      THE SINGULARITY INITIATED        ")
    print("=======================================")
    print(f"Stem Cell (Agent-Zero) duplicating into {clones} Hive Nodes...\n")

    # In a real distributed system, we would clone the folder and spin up docker containers.
    # For this simulation, we will boot the kernel plugins in a massive async constellation.
    import asyncio
    
    async def boot_node(node_id):
        repo_root = Path(__file__).resolve().parents[1]
        
        # We pass a unique repo_name to simulate them being different nodes in the federation
        node_name = f"Node_0{node_id}"
        print(f"[{node_name}] Birthing from Stem Cell...")
        
        kernel = AASKernel(repo_name=node_name, repo_root=str(repo_root))
        
        # Load the base plugins (This triggers on_load for genetic suppression)
        plugins_dir = repo_root / "plugins"
        kernel.load_plugins_from_directory(str(plugins_dir))
        
        # Connect to NATS (The Hive)
        await kernel.connect_to_bus()
        
        # --- THE NURSERY (Setup Phase) ---
        print(f"[{node_name}] Entering Womb/Nursery phase. Negotiating with Hive...")
        
        # Trigger the Constellation Consensus for all loaded plugins
        active_plugins = []
        for plugin in kernel.plugins:
            # Check if this plugin is an evolved Reflex with Constellation capability
            if hasattr(plugin, 'on_federate'):
                # The node asks the hive if it should express this gene
                should_express = await plugin.on_federate(kernel.nc)
                if should_express:
                    active_plugins.append(plugin)
            else:
                active_plugins.append(plugin)
                
        # Commit the finalized genes
        kernel.plugins = active_plugins
        
        print(f"[{node_name}] Negotiation complete. Active capabilities: {[p.__class__.__name__ for p in kernel.plugins]}")
        
        # Transition to Active
        await kernel._register_capabilities_with_bus()
        
        # Keep alive
        while True:
            await asyncio.sleep(1)

    async def expand_universe():
        # Spin up all clones concurrently
        tasks = [boot_node(i) for i in range(1, clones + 1)]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(expand_universe())
    except KeyboardInterrupt:
        print("\nUniverse collapsed safely.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initiate the Agent-Zero Singularity.")
    parser.add_argument("--clones", type=int, default=3, help="Number of nodes to spawn.")
    args = parser.parse_args()
    
    the_big_bang(args.clones)

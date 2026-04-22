import os
import sys
import json
import logging
import asyncio
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from aas_kernel import AASKernel

def run(singularity: bool = False, dry_run: bool = False, minimal: bool = False):
    repo_root = Path(__file__).resolve().parents[1]
    repo_name = repo_root.name

    if minimal:
        mode = "MINIMAL"
    elif singularity:
        mode = "SINGULARITY"
    else:
        mode = "NORMAL"
    print(f"--- INITIATING {repo_name} BOOT SEQUENCE [{mode}] ---")

    kernel = AASKernel(repo_name=repo_name, repo_root=str(repo_root), singularity_mode=singularity, dry_run=dry_run, minimal=minimal)

    plugins_dir = repo_root / "plugins"
    kernel.load_plugins_from_directory(str(plugins_dir))

    if singularity or dry_run:
        print(f"[SINGULARITY MODE] Verifying system without ignition...")
        asyncio.run(kernel.verify())
    else:
        try:
            asyncio.run(kernel.ignite())
        except KeyboardInterrupt:
            print(f"{repo_name} shutting down.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AAS Boot Sequence")
    parser.add_argument("--singularity", action="store_true", help="Run in Singularity Mode - system verification without building")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --singularity (legacy)")
    parser.add_argument("--minimal", action="store_true", help="Run in minimal mode - strip federation behaviors (hive mode)")
    args = parser.parse_args()
    run(singularity=args.singularity or args.dry_run, minimal=args.minimal)

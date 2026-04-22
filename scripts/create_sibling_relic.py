#!/usr/bin/env python3
"""
Create a Living GGUF Relic that aggregates artifacts from sibling AAS repos.

This script discovers sibling repositories in the workspace root, collects their
key artifacts (e.g., latest .relic.gguf, knowledge.sqlite, etc.), and crystallizes
them into a single GGUF relic representing the constellation of sibling repo data.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the scripts directory to the path to import the kernel and reliquary
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

try:
    from gguf_reliquary import GGUFArtifactReliquary
    from aas_kernel import AASKernel
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Ensure you are running from the AaroneousAutomationSuite root.")
    sys.exit(1)


def discover_sibling_repos(current_repo_name: str, workspace_root: Path) -> list[dict]:
    """
    Discover sibling AAS repositories in the workspace root.
    Returns a list of dicts with keys: repo_name, boot_script, manifest_path.
    Excludes the current repo.
    """
    agents = []
    for directory in workspace_root.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if directory.name == current_repo_name:
            continue  # Skip self
        manifest_path = directory / "mcp-manifest.json"
        boot_script = directory / "scripts" / "boot.py"
        if manifest_path.exists() and boot_script.exists():
            agents.append({
                "repo_name": directory.name,
                "boot_script": str(boot_script.absolute()),
                "manifest_path": str(manifest_path.absolute()),
                "repo_path": directory.absolute()
            })
    return agents


def find_primary_artifact(repo_path: Path) -> Path | None:
    """
    Find the primary artifact for a given repository.
    Looks for known artifact files in order of preference.
    """
    artifacts_dir = repo_path / "artifacts"
    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        return None

    # Define search patterns in order of preference
    patterns = [
        "*.relic.gguf",      # Living relics (highest priority)
        "knowledge.sqlite",   # Knowledge base
        "system_health_ledger.json", # Health ledger
        "*.gguf",            # Any other GGUF
        "*.json",            # Any JSON (lower priority)
    ]

    for pattern in patterns:
        matches = list(artifacts_dir.glob(pattern))
        if matches:
            # Return the most recently modified match
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Create a Living GGUF Relic from sibling repo artifacts."
    )
    parser.add_argument(
        "--relic-name",
        default="sibling_constellation",
        help="Name for the resulting relic (without extension)"
    )
    parser.add_argument(
        "--domain",
        default="knowledge",
        help="Domain alignment for the relic (knowledge, intelligence, security, leadership)"
    )
    parser.add_argument(
        "--entity-name",
        default="Sibling Constellation",
        help="Name of the Living Entity (e.g., Omni, Grimoire)"
    )
    parser.add_argument(
        "--repo-alliance",
        default="knowledge",
        help="Owning alliance/domain responsible for this entity"
    )
    parser.add_argument(
        "--supervisor",
        action="append",
        default=[],
        help="Supervisor agent granted direct telemetry/control access (repeatable)"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to output the relic (defaults to artifacts/ in current repo)"
    )
    args = parser.parse_args()

    # Determine current repo name from the directory containing this script
    # Assuming we are in AaroneousAutomationSuite/scripts
    current_repo_path = SCRIPTS_DIR.parent
    current_repo_name = current_repo_path.name
    workspace_root = current_repo_path.parent  # One level up from scripts/

    print(f"Current repo: {current_repo_name}")
    print(f"Workspace root: {workspace_root}")

    # Discover sibling repos
    siblings = discover_sibling_repos(current_repo_name, workspace_root)
    if not siblings:
        print("No sibling repositories found.")
        return

    print(f"Discovered {len(siblings)} sibling repository(ies):")
    for sib in siblings:
        print(f"  - {sib['repo_name']}")

    # For each sibling, find the primary artifact
    artifact_sources = {}
    for sib in siblings:
        repo_name = sib["repo_name"]
        repo_path = sib["repo_path"]
        artifact_path = find_primary_artifact(repo_path)
        if artifact_path:
            artifact_sources[repo_name] = str(artifact_path)
            print(f"  -> Using artifact for {repo_name}: {artifact_path.name}")
        else:
            print(f"  -> No artifact found for {repo_name} in {repo_path / 'artifacts'}")

    if not artifact_sources:
        print("No artifacts found in any sibling repositories.")
        return

    # Determine output path
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{args.relic_name}.relic.gguf"
    else:
        artifacts_dir = current_repo_path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        out_path = artifacts_dir / f"{args.relic_name}.relic.gguf"

    # Create the reliquary and crystallize the artifact
    reliquary = GGUFArtifactReliquary()
    print(f"\nCrystallizing sibling constellation relic: {out_path.name}")
    reliquary.crystallize_artifact(
        artifact_sources=artifact_sources,
        relic_name=args.relic_name,
        domain_alignment=args.domain,
        entity_name=args.entity_name,
        repo_alliance=args.repo_alliance,
        supervisors=args.supervisor,
    )

    print(f"\nSuccess! Relic created at: {out_path}")
    print(f"Contains artifacts from: {', '.join(artifact_sources.keys())}")


if __name__ == "__main__":
    main()
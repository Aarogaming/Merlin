import argparse
import json
from pathlib import Path


def _load(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _render_soul(identity: dict, epigenetics: dict) -> str:
    values = ", ".join(identity.get("core_values", []))
    quirks = epigenetics.get("profile_name", "balanced-profile")
    tone = f"Preset={epigenetics.get('preset', 'balanced_operator')}"
    return (
        f"# Entity Soul: {identity.get('designation', 'Unknown')}\n\n"
        "## 1. Core Identity\n"
        f"**Designation:** {identity.get('designation', 'Unknown')}\n"
        f"**Primary Directive:** {identity.get('primary_directive', '')}\n\n"
        "## 2. Psychological Profile\n"
        f"**Tone & Voice:** {tone}\n"
        f"**Behavioral Quirks:** Runtime epigenetic profile `{quirks}`\n"
        f"**Core Values / Decision Weights:** {values}\n\n"
        "## 3. Communication Protocol\n"
        "Generated from Life System v2 identity artifacts."
    )


def _render_agents(repo_name: str, identity: dict, epigenetics: dict, lifecycle: dict, genome_manifest: dict) -> str:
    autonomy = epigenetics.get("spectrums", {}).get("autonomy_level", 3)
    state_model = identity.get("specialization_track", "generalist")
    status = lifecycle.get("status", "quarantine_pending")
    invariants = identity.get("invariants", [])
    capabilities = genome_manifest.get("capability_catalog", {}).get("domain", [])

    lines = []
    lines.append(f"# {repo_name} Operational Agent Guide")
    lines.append("")
    lines.append("## Lifecycle Status")
    lines.append(f"**Status:** {status}")
    lines.append("")
    lines.append("## 1. Operational Parameters")
    lines.append(f"- **Autonomy Level:** {autonomy}/5")
    lines.append(f"- **Memory/State Model:** {state_model}")
    lines.append("")
    lines.append("## 2. Hard Boundaries (Constraints)")
    for item in invariants:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 3. Federation Dependencies")
    lines.append("Relies on: Library")
    lines.append("")
    lines.append("## 4. Capability Mapping")
    lines.append("Handles the following MCP event triggers:")
    for cap in capabilities:
        lines.append(f"- `{repo_name.lower()}.{cap.replace('domain.', '')}`")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Compile SOUL.md and AGENTS.md from Life System v2 artifacts.")
    parser.add_argument("--repo-path", required=True, help="Absolute repo path")
    args = parser.parse_args()

    repo_root = Path(args.repo_path).resolve()
    repo_name = repo_root.name

    identity_path = repo_root / "identity.genome.json"
    epigenetics_path = repo_root / "identity.epigenetics.json"
    lifecycle_path = repo_root / "lifecycle_state.json"
    genome_manifest_path = repo_root / "genome.manifest.json"

    required = [identity_path, epigenetics_path, lifecycle_path, genome_manifest_path]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("Missing required identity artifacts:")
        for m in missing:
            print(f"- {m}")
        raise SystemExit(1)

    identity = _load(identity_path)
    epigenetics = _load(epigenetics_path)
    lifecycle = _load(lifecycle_path)
    genome_manifest = _load(genome_manifest_path)

    soul_md = _render_soul(identity, epigenetics)
    agents_md = _render_agents(repo_name, identity, epigenetics, lifecycle, genome_manifest)

    (repo_root / "SOUL.md").write_text(soul_md + "\n", encoding="utf-8")
    (repo_root / "AGENTS.md").write_text(agents_md + "\n", encoding="utf-8")

    print(f"Compiled SOUL.md and AGENTS.md for {repo_name}")


if __name__ == "__main__":
    main()

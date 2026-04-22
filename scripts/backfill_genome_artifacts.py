import json
from datetime import datetime, UTC
from pathlib import Path

from genesis import (
    parse_entity,
    _build_genome_manifest,
    _build_identity_genome,
    _build_identity_epigenetics,
    _build_identity_memory,
    _compile_identity_docs,
    extract_field,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
DEFAULT_REPOS = [
    "Guild",
    "Library",
    "Maelstrom",
    "Merlin",
    "MyFortress",
    "Workbench",
]


def _capabilities_from_manifest(repo_name: str, manifest: dict) -> list[str]:
    items: list[str] = []
    prefix = f"{repo_name.lower()}_"
    for cap in manifest.get("capabilities", []):
        cap_id = str(cap.get("capability_id", "")).strip().lower()
        if cap_id.startswith(prefix):
            items.append(cap_id[len(prefix):])
        elif cap_id:
            items.append(cap_id.replace(".", "_").replace("-", "_"))
    if not items:
        items = ["status_ping"]
    return items


def _status_from_manifest(manifest: dict) -> str:
    caps = manifest.get("capabilities", [])
    if not caps:
        return "quarantine_pending"
    first = caps[0]
    conditions = first.get("confirmed_conditions", [])
    if "active" in conditions:
        return "active"
    return "quarantine_pending"


def _stage_mode_from_status(status: str) -> tuple[str, str]:
    if status == "active":
        return "federation", "federated"
    return "stabilization", "solo"


def _build_lifecycle(repo_name: str, status: str) -> dict:
    stage, mode = _stage_mode_from_status(status)
    gates = [
        "manifest_schema_valid",
        "capability_entrypoints_valid",
        "heartbeat_check_passed",
        "security_hooks_passed",
    ]
    return {
        "schema_version": "1.0",
        "repo": repo_name,
        "genome_version": "v1.0.0",
        "current_stage": stage,
        "status": status,
        "mode": mode,
        "promotion": {
            "gates_required": gates,
            "gates_passed": list(gates) if status == "active" else [],
            "auditor": "MyFortress" if status == "active" else "pending",
        },
        "updated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def process_repo(repo_root: Path) -> tuple[bool, str]:
    repo_name = repo_root.name
    manifest_path = repo_root / "mcp-manifest.json"
    if not manifest_path.exists():
        return False, f"Skipped {repo_name}: missing mcp-manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    entity = parse_entity(repo_root)
    if not entity:
        # Fallback: some repos store identity in .aas/SOUL.md
        soul_path = repo_root / ".aas" / "SOUL.md"
        agents_path = repo_root / "AGENTS.md"
        if soul_path.exists() and agents_path.exists():
            soul = soul_path.read_text(encoding="utf-8")
            agents = agents_path.read_text(encoding="utf-8")
            entity = {
                "directive": extract_field(soul, r"\*\*Primary Directive:\*\*\s*(.*)", default="To execute specialized tasks safely and evolve through federation standards."),
                "tone": extract_field(soul, r"\*\*Tone & Voice:\*\*\s*(.*)", default="Direct, concise, and highly professional"),
                "quirks": extract_field(soul, r"\*\*Behavioral Quirks:\*\*\s*(.*)", default="Focus on data over narrative."),
                "values": extract_field(soul, r"\*\*Core Values / Decision Weights:\*\*\s*(.*)", default="Accuracy, stability, and security."),
                "autonomy": extract_field(agents, r"Autonomy.*?(\d+)", default="3"),
                "state_model": extract_field(agents, r"Memory.*?Model:\*\*\s*(.*)", default="Stateless"),
                "boundaries": "Never execute destructive operations without approval.",
                "dependencies": "Library",
                "capabilities": "",
            }

    if not entity:
        return False, f"Skipped {repo_name}: missing SOUL.md/AGENTS.md/mcp-manifest.json"

    caps = _capabilities_from_manifest(repo_name, manifest)
    genome = _build_genome_manifest(repo_name, entity, caps)
    lifecycle = _build_lifecycle(repo_name, _status_from_manifest(manifest))
    identity_genome = _build_identity_genome(repo_name, entity)
    identity_epigenetics = _build_identity_epigenetics(entity)
    identity_memory = _build_identity_memory(entity)

    genome_path = repo_root / "genome.manifest.json"
    lifecycle_path = repo_root / "lifecycle_state.json"
    identity_genome_path = repo_root / "identity.genome.json"
    identity_epigenetics_path = repo_root / "identity.epigenetics.json"
    identity_memory_path = repo_root / "identity.memory.json"
    lifecycle_events_path = repo_root / "lifecycle.events.jsonl"

    with open(genome_path, "w", encoding="utf-8") as f:
        json.dump(genome, f, indent=2)
    with open(lifecycle_path, "w", encoding="utf-8") as f:
        json.dump(lifecycle, f, indent=2)
    with open(identity_genome_path, "w", encoding="utf-8") as f:
        json.dump(identity_genome, f, indent=2)
    with open(identity_epigenetics_path, "w", encoding="utf-8") as f:
        json.dump(identity_epigenetics, f, indent=2)
    with open(identity_memory_path, "w", encoding="utf-8") as f:
        json.dump(identity_memory, f, indent=2)

    lifecycle_event = {
        "schema_version": "1.0",
        "event_id": f"evt-backfill-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "repo": repo_name,
        "event_type": "evolution",
        "from_stage": "stabilization",
        "to_stage": lifecycle.get("current_stage", "federation"),
        "actor": "AaroneousAutomationSuite",
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": "Backfilled Life System v2 identity artifacts",
        "metadata": {"source": "backfill_genome_artifacts.py"},
    }
    with open(lifecycle_events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(lifecycle_event) + "\n")

    _compile_identity_docs(repo_root, repo_name)

    return True, f"Backfilled {repo_name}: genome/lifecycle/identity artifacts"


def main():
    updated = 0
    for repo in DEFAULT_REPOS:
        repo_root = WORKSPACE_ROOT / repo
        if not repo_root.exists():
            print(f"Skipped {repo}: repo not found")
            continue
        ok, msg = process_repo(repo_root)
        print(msg)
        if ok:
            updated += 1
    print(f"Backfill complete. Repos updated: {updated}")


if __name__ == "__main__":
    main()

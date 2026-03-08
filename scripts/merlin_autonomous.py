#!/usr/bin/env python3
"""
Merlin Autonomous Runner

Runs Merlin maintenance tasks continuously with resource-aware throttling.
"""
import sys
from pathlib import Path

# Import shared framework from AAS core
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))
from autonomous_runner import (
    TaskSpec,
    build_parser,
    execute_autonomous_loop,
)


def build_tasks(args) -> list[TaskSpec]:
    """Define Merlin maintenance tasks."""
    merlin_root = Path(__file__).resolve().parents[1]
    py = "python"
    scripts = merlin_root / "scripts"
    library_root = merlin_root.parent / "Library"
    chimera_consumer = library_root / "scripts" / "chimera_v2_merlin_research_manager_consumer.py"
    chimera_capabilities = (
        library_root
        / "docs"
        / "research"
        / "examples"
        / "merlin_research_manager_capabilities"
        / "core_present.example.json"
    )
    chimera_subscription = (
        library_root
        / "docs"
        / "research"
        / "examples"
        / "merlin_research_manager_subscription"
        / "healthy_consumption.example.json"
    )
    chimera_archive = merlin_root / "runs" / "autonomy" / "merlin_chimera_consumer_latest.json"
    
    tasks = [
        TaskSpec(
            name="Check governance guardrails",
            command=["bash", "scripts/check_governance_guardrails.sh"],
            heavy=False,
        ),
        TaskSpec(
            name="Emit federation heartbeat",
            command=[py, str(scripts / "emit_federation_heartbeat.py")],
            heavy=False,
        ),
        TaskSpec(
            name="Check secret hygiene",
            command=[py, str(scripts / "check_secret_hygiene.py")],
            heavy=False,
        ),
        TaskSpec(
            name="Check vector memory integrity",
            command=[py, str(scripts / "check_vector_memory_integrity.py")],
            heavy=False,
        ),
        TaskSpec(
            name="Verify contract schemas",
            command=[py, "-m", "pytest", "tests/test_contract_schemas.py", "-v"],
            heavy=False,
        ),
        TaskSpec(
            name="Verify discovery contract schemas",
            command=[py, "-m", "pytest", "tests/test_discovery_contract_schemas.py", "-v"],
            heavy=False,
        ),
        TaskSpec(
            name="Generate dependency audit report",
            command=[py, str(scripts / "generate_dependency_audit_report.py")],
            heavy=True,
        ),
        TaskSpec(
            name="Run Chimera research-manager consumer",
            command=[
                py,
                str(chimera_consumer),
                "--capabilities-json",
                str(chimera_capabilities),
                "--subscription-json",
                str(chimera_subscription),
                "--archive-json",
                str(chimera_archive),
                "--strict-state-machine",
            ],
            heavy=False,
            enabled=chimera_consumer.exists() and chimera_capabilities.exists() and chimera_subscription.exists(),
        ),
    ]
    
    return [t for t in tasks if t.enabled]


def main():
    parser = build_parser("Merlin")
    args = parser.parse_args()
    merlin_root = Path(__file__).resolve().parents[1]
    execute_autonomous_loop("Merlin", merlin_root, build_tasks, args)


if __name__ == "__main__":
    main()

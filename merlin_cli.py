import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from merlin_backup import (
    create_backup,
    restore_database_snapshot,
    run_restore_smoke_test,
    verify_backup_integrity,
)
from merlin_discovery_engine import build_engine
from merlin_plugin_manager import PluginManager
from merlin_research_manager import ResearchManager
from merlin_seed_access import build_seed_access
from merlin_system_info import get_system_info
from merlin_tasks import task_manager


def _emit_json(payload):
    print(json.dumps(payload, indent=2))


def _emit_error(message: str, code: int = 1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _format_research_brief_causal(brief: dict) -> str:
    lines = [
        f"session_id: {brief.get('session_id', '')}",
        f"objective: {brief.get('objective', '')}",
        f"probability_of_success: {brief.get('probability_of_success', 0)}",
        f"conflict_count: {brief.get('conflict_count', 0)}",
        "causal_chains:",
    ]

    for chain in brief.get("causal_chains", []):
        hypothesis_id = chain.get("hypothesis_id", "unknown")
        supporting_count = chain.get("supporting_count", 0)
        contradicting_count = chain.get("contradicting_count", 0)
        lines.append(
            f"- {hypothesis_id}: supports={supporting_count}, contradicts={contradicting_count}"
        )
        for evidence in chain.get("supporting_evidence", [])[:2]:
            lines.append(
                f"  support: {evidence.get('source', 'unknown')} -> {evidence.get('claim', '')}"
            )
        for evidence in chain.get("contradicting_evidence", [])[:2]:
            lines.append(
                f"  contradict: {evidence.get('source', 'unknown')} -> {evidence.get('claim', '')}"
            )

    return "\n".join(lines)


def _resolve_batch_values(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value == "$last_session_id":
            return context.get("last_session_id", "")
        return value
    if isinstance(value, list):
        return [_resolve_batch_values(item, context) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_batch_values(item, context) for key, item in value.items()
        }
    return value


def _render_research_cp_packet(
    *,
    brief: dict[str, Any],
    session: dict[str, Any],
    cycle_id: str,
    phase: str,
) -> str:
    linked_task_ids = brief.get("linked_task_ids", [])
    planner_artifacts = brief.get("planner_artifacts", [])
    next_actions = brief.get("next_actions", [])
    hypotheses = brief.get("hypotheses", [])

    packet_lines = [
        f"# CP Packet Skeleton - {brief.get('session_id', '')}",
        "",
        f"- generated_at_utc: {datetime.now(timezone.utc).isoformat()}",
        f"- cycle_id: {cycle_id}",
        f"- phase: {phase}",
        "",
        "FUNCTION_STATEMENT",
        (
            f"- Objective: {brief.get('objective', '')}; "
            f"status={brief.get('status', 'unknown')}; "
            f"probability_of_success={brief.get('probability_of_success', 0)}."
        ),
        "",
        "EVIDENCE_REFERENCES",
        f"- session_id: `{brief.get('session_id', '')}`",
        f"- brief_template: `{brief.get('brief_template_id', 'unknown')}`@`{brief.get('brief_template_version', 'unknown')}`",
        f"- conflict_count: `{brief.get('conflict_count', 0)}`",
        f"- linked_task_ids: `{linked_task_ids}`",
        f"- planner_artifacts: `{planner_artifacts}`",
        "",
        "CHANGES_APPLIED",
        "- [ ] Add concrete implementation deltas for this packet.",
        "",
        "VERIFICATION_COMMANDS_RUN",
        "- [ ] `<exact command>` -> PASS/FAIL (`<key output>`).",
        "",
        "ARTIFACTS_PRODUCED",
        "- [ ] `docs/research/<artifact>.md`",
        "",
        "RISKS_AND_NEXT_PASS",
    ]

    if isinstance(next_actions, list) and next_actions:
        for action in next_actions[:3]:
            packet_lines.append(f"- next_action: {action}")
    else:
        packet_lines.append(
            "- next_action: define follow-up evidence collection tasks."
        )

    if isinstance(hypotheses, list) and hypotheses:
        top_hypothesis = hypotheses[0]
        if isinstance(top_hypothesis, dict):
            packet_lines.append(
                "- top_hypothesis: "
                f"{top_hypothesis.get('id', 'unknown')} "
                f"(p={top_hypothesis.get('probability', 0)})"
            )

    session_tags = session.get("tags", [])
    packet_lines.append(f"- session_tags: `{session_tags}`")
    packet_lines.append("")
    return "\n".join(packet_lines)


def _execute_research_batch(
    manager: ResearchManager,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    context: dict[str, Any] = {"last_session_id": ""}
    results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    for index, step in enumerate(steps):
        action = str(step.get("action", "")).strip().lower()
        resolved = _resolve_batch_values(step, context)
        try:
            if action == "create":
                objective = str(resolved.get("objective", "")).strip()
                constraints = resolved.get("constraints")
                tags = resolved.get("tags")
                linked_task_ids = resolved.get("linked_task_ids")
                planner_artifacts = resolved.get("planner_artifacts")
                horizon_days = int(resolved.get("horizon_days", 14))
                session = manager.create_session(
                    objective=objective,
                    constraints=constraints if isinstance(constraints, list) else None,
                    horizon_days=horizon_days,
                    tags=tags if isinstance(tags, list) else None,
                    linked_task_ids=(
                        linked_task_ids if isinstance(linked_task_ids, list) else None
                    ),
                    planner_artifacts=(
                        planner_artifacts
                        if isinstance(planner_artifacts, list)
                        else None
                    ),
                )
                context["last_session_id"] = session["session_id"]
                result = {
                    "session": session,
                    "next_actions": manager.next_actions(session["session_id"]),
                }
            elif action == "signal":
                session_id = str(
                    resolved.get("session_id", context.get("last_session_id", ""))
                )
                result = manager.add_signal(
                    session_id=session_id,
                    source=str(resolved.get("source", "")),
                    claim=str(resolved.get("claim", "")),
                    confidence=float(resolved.get("confidence", 0.6)),
                    novelty=float(resolved.get("novelty", 0.5)),
                    risk=float(resolved.get("risk", 0.2)),
                    supports=(
                        resolved.get("supports")
                        if isinstance(resolved.get("supports"), list)
                        else None
                    ),
                    contradicts=(
                        resolved.get("contradicts")
                        if isinstance(resolved.get("contradicts"), list)
                        else None
                    ),
                )
            elif action == "brief":
                session_id = str(
                    resolved.get("session_id", context.get("last_session_id", ""))
                )
                result = {"brief": manager.get_brief(session_id)}
            elif action == "session":
                session_id = str(
                    resolved.get("session_id", context.get("last_session_id", ""))
                )
                result = {"session": manager.get_session(session_id)}
            elif action == "list":
                limit = max(1, int(resolved.get("limit", 20)))
                result = {
                    "sessions": manager.list_sessions(
                        limit=limit,
                        tag=resolved.get("tag"),
                        topic_query=resolved.get("topic"),
                    )
                }
            else:
                raise ValueError(
                    f"unsupported batch action '{action}' "
                    "(supported: create, signal, brief, session, list)"
                )

            results.append(
                {
                    "index": index,
                    "action": action,
                    "ok": True,
                    "result": result,
                }
            )
            success_count += 1
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            results.append(
                {
                    "index": index,
                    "action": action,
                    "ok": False,
                    "error": str(exc),
                }
            )
            failure_count += 1

    return {
        "schema_name": "AAS.ResearchBatchResult",
        "schema_version": "1.0.0",
        "step_count": len(steps),
        "success_count": success_count,
        "failure_count": failure_count,
        "last_session_id": context.get("last_session_id"),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Merlin Merlin CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Tasks
    task_parser = subparsers.add_parser("task", help="Manage tasks")
    task_subparsers = task_parser.add_subparsers(
        dest="subcommand", help="Task subcommands"
    )

    task_subparsers.add_parser("list", help="List all tasks")

    add_task_parser = task_subparsers.add_parser("add", help="Add a new task")
    add_task_parser.add_argument("title", help="Task title")
    add_task_parser.add_argument("--description", default="", help="Task description")
    add_task_parser.add_argument("--priority", default="Medium", help="Task priority")

    # Plugins
    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_subparsers = plugin_parser.add_subparsers(
        dest="subcommand", help="Plugin subcommands"
    )
    plugin_subparsers.add_parser("list", help="List all plugins")

    # Backup
    backup_parser = subparsers.add_parser("backup", help="Manage backups")
    backup_subparsers = backup_parser.add_subparsers(
        dest="subcommand", help="Backup subcommands"
    )

    backup_create_parser = backup_subparsers.add_parser("create", help="Create backup")
    backup_create_parser.add_argument(
        "--backup-dir",
        default="backups",
        help="Backup output directory",
    )

    backup_verify_parser = backup_subparsers.add_parser(
        "verify", help="Verify backup archive integrity"
    )
    backup_verify_parser.add_argument("backup_path", help="Backup archive path")
    backup_verify_parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional integrity manifest path",
    )
    backup_verify_parser.add_argument(
        "--sha256",
        default=None,
        help="Optional explicit SHA-256 to verify against",
    )

    backup_smoke_parser = backup_subparsers.add_parser(
        "smoke-test", help="Run restore smoke test for backup archive"
    )
    backup_smoke_parser.add_argument("backup_path", help="Backup archive path")

    backup_restore_db_parser = backup_subparsers.add_parser(
        "restore-db", help="Restore database from SQLite backup snapshot"
    )
    backup_restore_db_parser.add_argument("backup_path", help="SQLite backup file path")
    backup_restore_db_parser.add_argument(
        "--db-path",
        default="merlin.db",
        help="Target SQLite database path",
    )

    # System
    subparsers.add_parser("info", help="Show system info")

    # Research manager
    research_parser = subparsers.add_parser("research", help="Manage research sessions")
    research_subparsers = research_parser.add_subparsers(
        dest="subcommand", help="Research subcommands"
    )

    research_list_parser = research_subparsers.add_parser(
        "list", help="List research sessions"
    )
    research_list_parser.add_argument(
        "--limit", type=int, default=20, help="Max sessions"
    )
    research_list_parser.add_argument(
        "--tag",
        default=None,
        help="Filter sessions by tag",
    )
    research_list_parser.add_argument(
        "--topic",
        default=None,
        help="Filter sessions by objective keyword",
    )

    research_create_parser = research_subparsers.add_parser(
        "create", help="Create a research session"
    )
    research_create_parser.add_argument("objective", help="Research objective")
    research_create_parser.add_argument(
        "--constraint",
        dest="constraints",
        action="append",
        default=[],
        help="Constraint (repeatable)",
    )
    research_create_parser.add_argument(
        "--horizon-days", type=int, default=14, help="Planning horizon in days"
    )
    research_create_parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Session tag (repeatable)",
    )
    research_create_parser.add_argument(
        "--task-id",
        dest="linked_task_ids",
        action="append",
        type=int,
        default=[],
        help="Task ID to link for traceability (repeatable)",
    )
    research_create_parser.add_argument(
        "--planner-artifact",
        dest="planner_artifacts",
        action="append",
        default=[],
        help="Planner artifact path/ref to link (repeatable)",
    )

    research_session_parser = research_subparsers.add_parser(
        "session", help="Get full session state"
    )
    research_session_parser.add_argument("session_id", help="Session ID")

    research_brief_parser = research_subparsers.add_parser(
        "brief", help="Get session decision brief"
    )
    research_brief_parser.add_argument("session_id", help="Session ID")
    research_brief_parser.add_argument(
        "--render",
        choices=["json", "causal"],
        default="json",
        help="Output mode for research brief",
    )

    research_signal_parser = research_subparsers.add_parser(
        "signal", help="Add evidence signal to a session"
    )
    research_signal_parser.add_argument("session_id", help="Session ID")
    research_signal_parser.add_argument("--source", required=True, help="Signal source")
    research_signal_parser.add_argument("--claim", required=True, help="Signal claim")
    research_signal_parser.add_argument(
        "--confidence", type=float, default=0.6, help="Signal confidence (0..1)"
    )
    research_signal_parser.add_argument(
        "--novelty", type=float, default=0.5, help="Signal novelty (0..1)"
    )
    research_signal_parser.add_argument(
        "--risk", type=float, default=0.2, help="Signal risk (0..1)"
    )
    research_signal_parser.add_argument(
        "--supports",
        action="append",
        default=[],
        help="Hypothesis ID supported by this signal (repeatable)",
    )
    research_signal_parser.add_argument(
        "--contradicts",
        action="append",
        default=[],
        help="Hypothesis ID contradicted by this signal (repeatable)",
    )

    research_export_parser = research_subparsers.add_parser(
        "export", help="Export a research session snapshot to JSON"
    )
    research_export_parser.add_argument("session_id", help="Session ID")
    research_export_parser.add_argument("output_path", help="Output snapshot JSON path")

    research_import_parser = research_subparsers.add_parser(
        "import", help="Import a research session snapshot from JSON"
    )
    research_import_parser.add_argument("input_path", help="Input snapshot JSON path")
    research_import_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing session with the same session_id",
    )

    research_packet_parser = research_subparsers.add_parser(
        "packet", help="Generate CP packet skeleton markdown from a session brief"
    )
    research_packet_parser.add_argument("session_id", help="Session ID")
    research_packet_parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output markdown path (default: docs/research/"
            "CHIMERA_V2_CP_PACKET_SKELETON_<session_id>.md)"
        ),
    )
    research_packet_parser.add_argument(
        "--cycle-id",
        default="CHIMERA-V2-RESEARCH-AND-EXECUTION-2026-02-15",
        help="Cycle identifier to stamp in the packet",
    )
    research_packet_parser.add_argument(
        "--phase",
        default="CP",
        help="Phase identifier to stamp in the packet",
    )

    research_batch_parser = research_subparsers.add_parser(
        "batch", help="Execute a batch of research operations from JSON"
    )
    research_batch_parser.add_argument(
        "--file",
        required=True,
        help="Path to JSON file containing a list of batch steps",
    )
    research_batch_parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with code 1 when one or more batch steps fail",
    )

    # Discovery engine
    discovery_parser = subparsers.add_parser(
        "discovery", help="Run DiscoveryEngine pipeline"
    )
    discovery_subparsers = discovery_parser.add_subparsers(
        dest="subcommand", help="Discovery subcommands"
    )

    discovery_run_parser = discovery_subparsers.add_parser(
        "run", help="Run discovery pipeline"
    )
    discovery_run_parser.add_argument(
        "--profile",
        choices=["public", "experimental"],
        default="public",
        help="Policy profile for capability gating",
    )
    discovery_run_parser.add_argument(
        "--out",
        default=None,
        help="Output root for queue/knowledge/runs paths",
    )
    live_automation_group = discovery_run_parser.add_mutually_exclusive_group()
    live_automation_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Enable live collectors/publishers (default behavior; still profile-gated)",
    )
    live_automation_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Disable live collectors/publishers",
    )
    discovery_run_parser.set_defaults(allow_live_automation=None)
    discovery_run_parser.add_argument(
        "--seeds-file",
        default=None,
        help="JSON/JSONL seed input file",
    )
    discovery_run_parser.add_argument(
        "--fixture-feed",
        default=None,
        help="JSONL fixture feed path for offline collection",
    )
    discovery_run_parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Max number of selected topics",
    )
    discovery_run_parser.add_argument(
        "--min-score",
        type=float,
        default=0.35,
        help="Minimum score threshold for selection",
    )
    discovery_run_parser.add_argument(
        "--max-bundle-size",
        type=int,
        default=4,
        help="Max supporting items per synthesized topic bundle",
    )
    discovery_run_parser.add_argument(
        "--max-items-per-seed",
        type=int,
        default=10,
        help="Max collector items per claimed seed/work item",
    )
    discovery_run_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
        help="Merlin adapter mode for scoring/summarization",
    )
    discovery_run_parser.add_argument(
        "--publisher-mode",
        choices=["stage_only", "pr", "git", "push", "none"],
        default="stage_only",
        help="Publisher mode (policy-gated)",
    )
    discovery_run_parser.add_argument(
        "--lease-ttl-seconds",
        type=int,
        default=300,
        help="Lease TTL for queue claims",
    )
    discovery_run_parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max retries before deadletter",
    )
    discovery_run_parser.add_argument(
        "--worker-id",
        default="discovery-engine-v1",
        help="Worker identifier stored in leases",
    )
    discovery_run_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing artifact files",
    )
    discovery_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline with explicit output root semantics",
    )
    discovery_run_parser.add_argument(
        "--no-write",
        action="store_true",
        help="Compute plan/report only (no file writes)",
    )

    discovery_queue_parser = discovery_subparsers.add_parser(
        "queue", help="Discovery queue operations"
    )
    discovery_queue_subparsers = discovery_queue_parser.add_subparsers(
        dest="queue_command",
        help="Discovery queue subcommands",
    )

    discovery_queue_status_parser = discovery_queue_subparsers.add_parser(
        "status", help="Show queue status"
    )
    discovery_queue_status_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing queue/",
    )
    discovery_queue_status_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    discovery_queue_drain_parser = discovery_queue_subparsers.add_parser(
        "drain", help="Promote seeds to work queue"
    )
    discovery_queue_drain_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing queue/",
    )
    discovery_queue_drain_parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run ID to stamp promoted work items",
    )
    discovery_queue_drain_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    discovery_queue_purge_parser = discovery_queue_subparsers.add_parser(
        "purge-deadletter",
        help="Delete all deadletter queue entries",
    )
    discovery_queue_purge_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing queue/",
    )
    discovery_queue_purge_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    discovery_queue_pause_parser = discovery_queue_subparsers.add_parser(
        "pause",
        help="Pause queue processing",
    )
    discovery_queue_pause_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing queue/",
    )
    discovery_queue_pause_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    discovery_queue_resume_parser = discovery_queue_subparsers.add_parser(
        "resume",
        help="Resume queue processing",
    )
    discovery_queue_resume_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing queue/",
    )
    discovery_queue_resume_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    # Knowledge search
    knowledge_parser = subparsers.add_parser(
        "knowledge", help="Search discovery knowledge index"
    )
    knowledge_subparsers = knowledge_parser.add_subparsers(
        dest="subcommand", help="Knowledge subcommands"
    )
    knowledge_search_parser = knowledge_subparsers.add_parser(
        "search", help="Search knowledge/index.json"
    )
    knowledge_search_parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query (empty query returns newest entries)",
    )
    knowledge_search_parser.add_argument(
        "--tag",
        default=None,
        help="Optional tag filter",
    )
    knowledge_search_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum result count",
    )
    knowledge_search_parser.add_argument(
        "--out",
        default=None,
        help="Output root containing knowledge/index.json",
    )
    knowledge_search_parser.add_argument(
        "--merlin-mode",
        choices=["local", "null"],
        default="local",
    )

    # Merlin seed runtime controls
    seed_parser = subparsers.add_parser(
        "seed", help="Manage Merlin LLM/LLM-lite seed runtime"
    )
    seed_subparsers = seed_parser.add_subparsers(
        dest="subcommand", help="Seed subcommands"
    )

    seed_status_parser = seed_subparsers.add_parser(
        "status", help="Show seed runtime status"
    )
    seed_status_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_status_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_status_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_status_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_status_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_status_parser.add_argument(
        "--tail-lines",
        type=int,
        default=40,
        help="Number of trailing log lines to include",
    )
    seed_status_log_group = seed_status_parser.add_mutually_exclusive_group()
    seed_status_log_group.add_argument(
        "--include-log-tail",
        dest="include_log_tail",
        action="store_true",
        help="Include log tail payload (default)",
    )
    seed_status_log_group.add_argument(
        "--no-log-tail",
        dest="include_log_tail",
        action="store_false",
        help="Skip log tail payload",
    )
    seed_status_parser.set_defaults(include_log_tail=True)
    seed_status_live_group = seed_status_parser.add_mutually_exclusive_group()
    seed_status_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true for policy telemetry",
    )
    seed_status_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false for policy telemetry",
    )
    seed_status_parser.set_defaults(allow_live_automation=None)

    seed_health_parser = seed_subparsers.add_parser(
        "health", help="Show seed runtime health/watchdog summary"
    )
    seed_health_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_health_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_health_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_health_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_health_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_health_parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status telemetry is treated as stale",
    )
    seed_health_live_group = seed_health_parser.add_mutually_exclusive_group()
    seed_health_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true for policy telemetry",
    )
    seed_health_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false for policy telemetry",
    )
    seed_health_parser.set_defaults(allow_live_automation=None)

    seed_heartbeat_parser = seed_subparsers.add_parser(
        "heartbeat",
        help="Emit a seed health heartbeat event",
    )
    seed_heartbeat_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_heartbeat_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_heartbeat_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_heartbeat_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_heartbeat_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_heartbeat_parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status telemetry is treated as stale",
    )
    seed_heartbeat_parser.add_argument(
        "--heartbeat-file",
        default=None,
        help="Heartbeat JSONL output path (defaults under artifacts/diagnostics)",
    )
    seed_heartbeat_write_group = seed_heartbeat_parser.add_mutually_exclusive_group()
    seed_heartbeat_write_group.add_argument(
        "--write-event",
        dest="write_event",
        action="store_true",
        help="Persist heartbeat event to file (default)",
    )
    seed_heartbeat_write_group.add_argument(
        "--no-write-event",
        dest="write_event",
        action="store_false",
        help="Return heartbeat payload without writing event file",
    )
    seed_heartbeat_parser.set_defaults(write_event=True)
    seed_heartbeat_live_group = seed_heartbeat_parser.add_mutually_exclusive_group()
    seed_heartbeat_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true for policy telemetry",
    )
    seed_heartbeat_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false for policy telemetry",
    )
    seed_heartbeat_parser.set_defaults(allow_live_automation=None)

    seed_watchdog_parser = seed_subparsers.add_parser(
        "watchdog",
        help="Evaluate seed health guidance and optionally execute control action",
    )
    seed_watchdog_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_watchdog_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_watchdog_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_watchdog_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_watchdog_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_watchdog_parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status telemetry is treated as stale",
    )
    seed_watchdog_apply_group = seed_watchdog_parser.add_mutually_exclusive_group()
    seed_watchdog_apply_group.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Apply recommended control action when policy allows",
    )
    seed_watchdog_apply_group.add_argument(
        "--no-apply",
        dest="apply",
        action="store_false",
        help="Preview recommendation only (default)",
    )
    seed_watchdog_parser.set_defaults(apply=False)
    seed_watchdog_parser.add_argument(
        "--force",
        action="store_true",
        help="Force control action when watchdog applies start/restart",
    )
    seed_watchdog_parser.add_argument(
        "--dry-run-control",
        action="store_true",
        help="Run control action in dry-run mode when --apply is used",
    )
    seed_watchdog_live_group = seed_watchdog_parser.add_mutually_exclusive_group()
    seed_watchdog_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true for policy telemetry",
    )
    seed_watchdog_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false for policy telemetry",
    )
    seed_watchdog_parser.set_defaults(allow_live_automation=None)

    seed_watchdog_runtime_parser = seed_subparsers.add_parser(
        "watchdog-runtime",
        help="Manage continuous seed watchdog runtime loop",
    )
    seed_watchdog_runtime_subparsers = seed_watchdog_runtime_parser.add_subparsers(
        dest="watchdog_runtime_command",
        help="Watchdog runtime subcommands",
    )

    seed_watchdog_runtime_status_parser = seed_watchdog_runtime_subparsers.add_parser(
        "status",
        help="Show watchdog runtime process/telemetry status",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--watchdog-log-file",
        default=None,
        help="Override watchdog runtime process log path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--append-jsonl",
        default=None,
        help="Override watchdog runtime tick JSONL path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--output-json",
        default=None,
        help="Override watchdog runtime report JSON path",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--heartbeat-file",
        default=None,
        help="Override heartbeat JSONL path used by runtime",
    )
    seed_watchdog_runtime_status_parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status telemetry is treated as stale",
    )
    seed_watchdog_runtime_status_live_group = (
        seed_watchdog_runtime_status_parser.add_mutually_exclusive_group()
    )
    seed_watchdog_runtime_status_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true for policy telemetry",
    )
    seed_watchdog_runtime_status_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false for policy telemetry",
    )
    seed_watchdog_runtime_status_parser.set_defaults(allow_live_automation=None)

    seed_watchdog_runtime_control_parser = seed_watchdog_runtime_subparsers.add_parser(
        "control",
        help="Start/stop/restart watchdog runtime loop process",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "action",
        choices=["start", "stop", "restart"],
        help="Control action to apply",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--watchdog-log-file",
        default=None,
        help="Override watchdog runtime process log path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--append-jsonl",
        default=None,
        help="Override watchdog runtime tick JSONL path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--output-json",
        default=None,
        help="Override watchdog runtime report JSON path",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--heartbeat-file",
        default=None,
        help="Override heartbeat JSONL path used by runtime",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=3600.0,
        help="Seconds before status telemetry is treated as stale",
    )
    seed_watchdog_runtime_apply_group = (
        seed_watchdog_runtime_control_parser.add_mutually_exclusive_group()
    )
    seed_watchdog_runtime_apply_group.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help="Apply recommended control action in runtime ticks",
    )
    seed_watchdog_runtime_apply_group.add_argument(
        "--no-apply",
        dest="apply",
        action="store_false",
        help="Preview-only runtime ticks (default)",
    )
    seed_watchdog_runtime_control_parser.set_defaults(apply=False)
    seed_watchdog_runtime_control_parser.add_argument(
        "--dry-run-control",
        action="store_true",
        help="Run control action in dry-run mode during runtime ticks",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--interval-seconds",
        type=float,
        default=60.0,
        help="Sleep interval between runtime ticks",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Runtime tick count (0 means continuous)",
    )
    seed_watchdog_runtime_heartbeat_group = (
        seed_watchdog_runtime_control_parser.add_mutually_exclusive_group()
    )
    seed_watchdog_runtime_heartbeat_group.add_argument(
        "--emit-heartbeat",
        dest="emit_heartbeat",
        action="store_true",
        help="Emit heartbeat events in runtime loop (default)",
    )
    seed_watchdog_runtime_heartbeat_group.add_argument(
        "--no-heartbeat",
        dest="emit_heartbeat",
        action="store_false",
        help="Disable heartbeat emission in runtime loop",
    )
    seed_watchdog_runtime_control_parser.set_defaults(emit_heartbeat=True)
    seed_watchdog_runtime_control_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview action without mutating runtime state",
    )
    seed_watchdog_runtime_control_parser.add_argument(
        "--force",
        action="store_true",
        help="Force restart/start even if a runtime process is active",
    )
    seed_watchdog_runtime_control_live_group = (
        seed_watchdog_runtime_control_parser.add_mutually_exclusive_group()
    )
    seed_watchdog_runtime_control_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true",
    )
    seed_watchdog_runtime_control_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false",
    )
    seed_watchdog_runtime_control_parser.set_defaults(allow_live_automation=None)

    seed_control_parser = seed_subparsers.add_parser(
        "control", help="Start/stop/restart seed runtime"
    )
    seed_control_parser.add_argument(
        "action",
        choices=["start", "stop", "restart"],
        help="Control action to apply",
    )
    seed_control_parser.add_argument(
        "--workspace-root",
        default=None,
        help="Workspace root containing artifacts/guild/scripts",
    )
    seed_control_parser.add_argument(
        "--status-file",
        default=None,
        help="Override status file path",
    )
    seed_control_parser.add_argument(
        "--merged-jsonl",
        default=None,
        help="Override merged dataset JSONL path",
    )
    seed_control_parser.add_argument(
        "--merged-parquet",
        default=None,
        help="Override merged dataset parquet path",
    )
    seed_control_parser.add_argument(
        "--log-file",
        default=None,
        help="Override seed runtime log path",
    )
    seed_control_live_group = seed_control_parser.add_mutually_exclusive_group()
    seed_control_live_group.add_argument(
        "--allow-live-automation",
        dest="allow_live_automation",
        action="store_true",
        help="Force allow_live_automation=true",
    )
    seed_control_live_group.add_argument(
        "--no-live-automation",
        dest="allow_live_automation",
        action="store_false",
        help="Force allow_live_automation=false",
    )
    seed_control_parser.set_defaults(allow_live_automation=None)
    seed_control_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview action without mutating runtime state",
    )
    seed_control_parser.add_argument(
        "--force",
        action="store_true",
        help="Force restart/start even if a worker is already active",
    )
    seed_control_parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:1234",
        help="LM Studio endpoint",
    )
    seed_control_parser.add_argument(
        "--prompt-set",
        default="scripts/eval/prompts_guild.json",
        help="Prompt set path for seed runner",
    )
    seed_control_parser.add_argument(
        "--target",
        type=int,
        default=50000,
        help="Target merged dataset row count",
    )
    seed_control_parser.add_argument(
        "--increment",
        type=int,
        default=500,
        help="Progress checkpoint increment",
    )
    seed_control_parser.add_argument(
        "--repeat",
        type=int,
        default=13,
        help="Repeat count per batch loop",
    )
    seed_control_parser.add_argument(
        "--eta-window",
        type=int,
        default=5,
        help="Rolling ETA history window",
    )
    seed_control_parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.1,
        help="Sleep delay between prompts",
    )
    seed_control_parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between teachers/batches",
    )
    seed_control_resource_group = seed_control_parser.add_mutually_exclusive_group()
    seed_control_resource_group.add_argument(
        "--resource-aware",
        dest="resource_aware",
        action="store_true",
        help="Enable resource-aware throttling (default)",
    )
    seed_control_resource_group.add_argument(
        "--no-resource-aware",
        dest="resource_aware",
        action="store_false",
        help="Disable resource-aware throttling",
    )
    seed_control_parser.set_defaults(resource_aware=True)
    seed_control_parser.add_argument(
        "--cpu-max",
        type=float,
        default=85.0,
        help="CPU threshold when resource-aware",
    )
    seed_control_parser.add_argument(
        "--mem-max",
        type=float,
        default=85.0,
        help="Memory threshold when resource-aware",
    )
    seed_control_parser.add_argument(
        "--resource-wait",
        type=float,
        default=5.0,
        help="Seconds to wait when resources exceed thresholds",
    )
    seed_control_parser.add_argument(
        "--notify-on-complete",
        action="store_true",
        help="Enable notification flag for runner completion",
    )
    seed_control_parser.add_argument(
        "--teachers",
        default=None,
        help="Teacher model list (comma separated) or from-config",
    )
    seed_control_parser.add_argument(
        "--config",
        default=None,
        help="Model routing config path",
    )

    args = parser.parse_args()

    if args.command == "task":
        if args.subcommand == "list":
            print(json.dumps(task_manager.list_tasks(), indent=2))
        elif args.subcommand == "add":
            task = task_manager.add_task(args.title, args.description, args.priority)
            print(f"Added task: {task['id']}")

    elif args.command == "plugin":
        if args.subcommand == "list":
            pm = PluginManager(strict_packaged_load=True)
            try:
                pm.load_plugins()
            except RuntimeError as exc:
                _emit_error(str(exc))
            print(json.dumps(pm.list_plugin_info(), indent=2))

    elif args.command == "backup":
        if args.subcommand == "create":
            backup_path = create_backup(backup_dir=args.backup_dir)
            if backup_path is None:
                _emit_error("Backup creation failed")
            _emit_json({"status": "created", "backup_path": backup_path})
            return

        if args.subcommand == "verify":
            result = verify_backup_integrity(
                args.backup_path,
                manifest_path=args.manifest_path,
                expected_sha256=args.sha256,
            )
            _emit_json(result)
            if not result.get("ok"):
                raise SystemExit(1)
            return

        if args.subcommand == "smoke-test":
            result = run_restore_smoke_test(args.backup_path)
            _emit_json(result)
            if not result.get("ok"):
                raise SystemExit(1)
            return

        if args.subcommand == "restore-db":
            result = restore_database_snapshot(
                args.backup_path,
                db_path=args.db_path,
            )
            _emit_json(result)
            if not result.get("ok"):
                raise SystemExit(1)
            return

    elif args.command == "info":
        print(json.dumps(get_system_info(), indent=2))

    elif args.command == "research":
        manager = ResearchManager()

        try:
            if args.subcommand == "list":
                _emit_json(
                    {
                        "sessions": manager.list_sessions(
                            limit=max(1, args.limit),
                            tag=args.tag,
                            topic_query=args.topic,
                        )
                    }
                )
                return

            if args.subcommand == "create":
                session = manager.create_session(
                    objective=args.objective,
                    constraints=args.constraints,
                    horizon_days=args.horizon_days,
                    tags=args.tags,
                    linked_task_ids=args.linked_task_ids,
                    planner_artifacts=args.planner_artifacts,
                )
                _emit_json(
                    {
                        "session": session,
                        "next_actions": manager.next_actions(session["session_id"]),
                    }
                )
                return

            if args.subcommand == "session":
                _emit_json({"session": manager.get_session(args.session_id)})
                return

            if args.subcommand == "brief":
                brief = manager.get_brief(args.session_id)
                if args.render == "causal":
                    print(_format_research_brief_causal(brief))
                else:
                    _emit_json({"brief": brief})
                return

            if args.subcommand == "signal":
                _emit_json(
                    manager.add_signal(
                        session_id=args.session_id,
                        source=args.source,
                        claim=args.claim,
                        confidence=args.confidence,
                        novelty=args.novelty,
                        risk=args.risk,
                        supports=args.supports,
                        contradicts=args.contradicts,
                    )
                )
                return

            if args.subcommand == "export":
                snapshot = manager.export_session_snapshot(args.session_id)
                output_path = Path(args.output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(snapshot, indent=2) + "\n",
                    encoding="utf-8",
                )
                _emit_json(
                    {
                        "status": "exported",
                        "session_id": args.session_id,
                        "output_path": str(output_path),
                    }
                )
                return

            if args.subcommand == "import":
                input_path = Path(args.input_path)
                snapshot = json.loads(input_path.read_text(encoding="utf-8"))
                session = manager.import_session_snapshot(
                    snapshot,
                    overwrite=args.overwrite,
                )
                _emit_json(
                    {
                        "status": "imported",
                        "session": session,
                    }
                )
                return

            if args.subcommand == "packet":
                brief = manager.get_brief(args.session_id)
                session = manager.get_session(args.session_id)
                packet_markdown = _render_research_cp_packet(
                    brief=brief,
                    session=session,
                    cycle_id=args.cycle_id,
                    phase=args.phase,
                )
                output_path = (
                    Path(args.output)
                    if args.output
                    else (
                        Path("docs")
                        / "research"
                        / f"CHIMERA_V2_CP_PACKET_SKELETON_{args.session_id}.md"
                    )
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(packet_markdown + "\n", encoding="utf-8")
                _emit_json(
                    {
                        "status": "generated",
                        "session_id": args.session_id,
                        "output_path": str(output_path),
                    }
                )
                return

            if args.subcommand == "batch":
                batch_path = Path(args.file)
                parsed = json.loads(batch_path.read_text(encoding="utf-8"))
                if not isinstance(parsed, list):
                    raise ValueError("batch file root must be a JSON array of steps")
                steps = [item for item in parsed if isinstance(item, dict)]
                if len(steps) != len(parsed):
                    raise ValueError("every batch step must be a JSON object")
                summary = _execute_research_batch(manager, steps)
                _emit_json(summary)
                if args.fail_on_error and summary["failure_count"] > 0:
                    raise SystemExit(1)
                return

            parser.print_help()
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            _emit_error(str(exc))

    elif args.command == "discovery":
        engine = build_engine(
            workspace_root=Path.cwd(),
            merlin_mode=getattr(args, "merlin_mode", "local"),
        )
        try:
            if args.subcommand == "run":
                _emit_json(
                    engine.run(
                        profile=args.profile,
                        out=args.out,
                        allow_live_automation=args.allow_live_automation,
                        seeds_file=args.seeds_file,
                        fixture_feed=args.fixture_feed,
                        top_k=max(1, args.top_k),
                        min_score=args.min_score,
                        max_bundle_size=max(1, args.max_bundle_size),
                        max_items_per_seed=max(1, args.max_items_per_seed),
                        dry_run=args.dry_run,
                        no_write=args.no_write,
                        overwrite=args.overwrite,
                        publisher_mode=args.publisher_mode,
                        lease_ttl_seconds=max(1, args.lease_ttl_seconds),
                        max_retries=max(0, args.max_retries),
                        worker_id=args.worker_id,
                    )
                )
                return

            if args.subcommand == "queue":
                if args.queue_command == "status":
                    _emit_json(engine.queue_status(out=args.out))
                    return
                if args.queue_command == "drain":
                    _emit_json(engine.queue_drain(out=args.out, run_id=args.run_id))
                    return
                if args.queue_command == "purge-deadletter":
                    _emit_json(engine.queue_purge_deadletter(out=args.out))
                    return
                if args.queue_command == "pause":
                    _emit_json(engine.queue_pause(out=args.out))
                    return
                if args.queue_command == "resume":
                    _emit_json(engine.queue_resume(out=args.out))
                    return

            parser.print_help()
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            _emit_error(str(exc))

    elif args.command == "knowledge":
        engine = build_engine(
            workspace_root=Path.cwd(),
            merlin_mode=getattr(args, "merlin_mode", "local"),
        )
        try:
            if args.subcommand == "search":
                _emit_json(
                    engine.knowledge_search(
                        query=args.query,
                        out=args.out,
                        limit=max(1, args.limit),
                        tag=args.tag,
                    )
                )
                return
            parser.print_help()
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            _emit_error(str(exc))

    elif args.command == "seed":
        seed_access = build_seed_access(
            workspace_root=getattr(args, "workspace_root", None)
        )
        try:
            if args.subcommand == "status":
                _emit_json(
                    seed_access.status(
                        status_file=args.status_file,
                        merged_jsonl=args.merged_jsonl,
                        merged_parquet=args.merged_parquet,
                        log_file=args.log_file,
                        include_log_tail=args.include_log_tail,
                        tail_lines=max(1, args.tail_lines),
                        allow_live_automation=args.allow_live_automation,
                    )
                )
                return

            if args.subcommand == "health":
                _emit_json(
                    seed_access.health(
                        status_file=args.status_file,
                        merged_jsonl=args.merged_jsonl,
                        merged_parquet=args.merged_parquet,
                        log_file=args.log_file,
                        allow_live_automation=args.allow_live_automation,
                        stale_after_seconds=max(1.0, args.stale_after_seconds),
                    )
                )
                return

            if args.subcommand == "heartbeat":
                _emit_json(
                    seed_access.heartbeat(
                        status_file=args.status_file,
                        merged_jsonl=args.merged_jsonl,
                        merged_parquet=args.merged_parquet,
                        log_file=args.log_file,
                        allow_live_automation=args.allow_live_automation,
                        stale_after_seconds=max(1.0, args.stale_after_seconds),
                        heartbeat_file=args.heartbeat_file,
                        write_event=args.write_event,
                    )
                )
                return

            if args.subcommand == "watchdog":
                _emit_json(
                    seed_access.watchdog(
                        status_file=args.status_file,
                        merged_jsonl=args.merged_jsonl,
                        merged_parquet=args.merged_parquet,
                        log_file=args.log_file,
                        allow_live_automation=args.allow_live_automation,
                        stale_after_seconds=max(1.0, args.stale_after_seconds),
                        apply=args.apply,
                        force=args.force,
                        dry_run_control=args.dry_run_control,
                    )
                )
                return

            if args.subcommand == "watchdog-runtime":
                if args.watchdog_runtime_command == "status":
                    _emit_json(
                        seed_access.watchdog_runtime_status(
                            status_file=args.status_file,
                            merged_jsonl=args.merged_jsonl,
                            merged_parquet=args.merged_parquet,
                            log_file=args.log_file,
                            watchdog_log_file=args.watchdog_log_file,
                            append_jsonl=args.append_jsonl,
                            output_json=args.output_json,
                            heartbeat_file=args.heartbeat_file,
                            allow_live_automation=args.allow_live_automation,
                            stale_after_seconds=max(1.0, args.stale_after_seconds),
                        )
                    )
                    return
                if args.watchdog_runtime_command == "control":
                    _emit_json(
                        seed_access.watchdog_runtime_control(
                            action=args.action,
                            allow_live_automation=args.allow_live_automation,
                            dry_run=args.dry_run,
                            force=args.force,
                            status_file=args.status_file,
                            merged_jsonl=args.merged_jsonl,
                            merged_parquet=args.merged_parquet,
                            log_file=args.log_file,
                            watchdog_log_file=args.watchdog_log_file,
                            append_jsonl=args.append_jsonl,
                            output_json=args.output_json,
                            heartbeat_file=args.heartbeat_file,
                            stale_after_seconds=max(1.0, args.stale_after_seconds),
                            apply=args.apply,
                            dry_run_control=args.dry_run_control,
                            interval_seconds=max(0.0, args.interval_seconds),
                            max_iterations=max(0, args.max_iterations),
                            emit_heartbeat=args.emit_heartbeat,
                        )
                    )
                    return
                parser.print_help()
                return

            if args.subcommand == "control":
                _emit_json(
                    seed_access.control(
                        action=args.action,
                        allow_live_automation=args.allow_live_automation,
                        dry_run=args.dry_run,
                        force=args.force,
                        status_file=args.status_file,
                        merged_jsonl=args.merged_jsonl,
                        merged_parquet=args.merged_parquet,
                        log_file=args.log_file,
                        endpoint=args.endpoint,
                        prompt_set=args.prompt_set,
                        target=max(1, args.target),
                        increment=max(1, args.increment),
                        repeat=max(1, args.repeat),
                        eta_window=max(1, args.eta_window),
                        sleep_seconds=max(0.0, args.sleep_seconds),
                        delay_seconds=max(0.0, args.delay_seconds),
                        resource_aware=args.resource_aware,
                        cpu_max=max(1.0, args.cpu_max),
                        mem_max=max(1.0, args.mem_max),
                        resource_wait=max(0.1, args.resource_wait),
                        notify_on_complete=args.notify_on_complete,
                        teachers=args.teachers,
                        config=args.config,
                    )
                )
                return

            parser.print_help()
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            _emit_error(str(exc))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

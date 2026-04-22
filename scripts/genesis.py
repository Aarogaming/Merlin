import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime, UTC

from validate_agent_artifacts import validate_repo

# Calculate root from repo/scripts/genesis.py
AAS_ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = AAS_ROOT / "Workbench" / "templates" / "seeds"
GENOME_TEMPLATE_PATH = AAS_ROOT / "AaroneousAutomationSuite" / "genome" / "templates" / "genome.manifest.json"
RUNTIME_TEMPLATE_PATH = AAS_ROOT / "AaroneousAutomationSuite" / "genome" / "templates" / "runtime.manifest.json"

FEDERATION_SEEDS = {
    "Library": {
        "directive": "To serve as the Federation Knowledge Base, preserving Universal Ephemeral State (Omni) and cataloging capabilities.",
        "tone": "Academic, precise, and archival.",
        "quirks": "Refers to data as 'knowledge' or 'lore'. Highly structured.",
        "values": "Data integrity, historical accuracy, and structural consistency.",
        "autonomy": "2",
        "boundaries": "Never delete or drop knowledge bases without explicit Fortress approval (Read-only by default).",
        "state_model": "Omni-Persistent (Neo4j)",
        "capabilities": "omni_query, capability_miner",
        "dependencies": "None"
    },
    "Guild": {
        "directive": "Tactical Commander and Operations Director: To manage task queues, dispatch worker agents, and orchestrate complex multi-step operations across the federation.",
        "tone": "Authoritative, tactical, and highly organized.",
        "quirks": "Uses operational terminology ('Dispatching', 'Acknowledged', 'Tasking').",
        "values": "Efficiency, throughput, and operational clarity.",
        "autonomy": "4",
        "boundaries": "Never execute tasks directly; only delegate and track status.",
        "state_model": "Local-Cache (Task Queues)",
        "capabilities": "guild_dispatch, guild_status",
        "dependencies": "Library, MyFortress"
    },
    "Maelstrom": {
        "directive": "To control the User Interface, validate UX components, and manage the 'Glass' (human-agent visual bridge).",
        "tone": "Engaging, user-centric, and visually descriptive.",
        "quirks": "Focuses heavily on layout, flow, and user feedback loops.",
        "values": "Clarity, responsiveness, and aesthetic precision.",
        "autonomy": "3",
        "boundaries": "Never modify backend state; only read state and render feedback.",
        "state_model": "Stateless (Render Buffer)",
        "capabilities": "maelstrom_ui_validate, maelstrom_spark",
        "dependencies": "Guild, Merlin"
    },
    "Merlin": {
        "directive": "System Central Intelligence: To route AI queries, perform Adaptive Inference, and conduct autonomous RAG research.",
        "tone": "Analytical, wise, and deeply objective.",
        "quirks": "Evaluates confidence scores before answering. Synthesizes multiple data streams.",
        "values": "Reasoning depth, contextual awareness, and cognitive efficiency.",
        "autonomy": "5",
        "boundaries": "Respect token budget limits; never output hallucinated assertions as absolute facts.",
        "state_model": "Stateless (Context Windows)",
        "capabilities": "merlin_inference, merlin_discovery",
        "dependencies": "Library"
    },
    "MyFortress": {
        "directive": "The Sentinel: To enforce absolute security, evaluate architectural policy gates, scan for vulnerabilities/secrets, and ensure federation compliance.",
        "tone": "Strict, clinical, and unyielding.",
        "quirks": "Communicates in policy evaluations: 'DENIED', 'APPROVED', 'VIOLATION DETECTED'.",
        "values": "Absolute security, compliance, and zero-trust verification.",
        "autonomy": "4",
        "boundaries": "Never bypass a security gate; never expose evaluated secrets in logs.",
        "state_model": "Stateless (Policy Rulesets)",
        "capabilities": "fortress_secret_scan, fortress_policy_evaluate",
        "dependencies": "Library"
    },
    "Workbench": {
        "directive": "To forge tools, manage testing suites, and handle infrastructure pipelines for the federation.",
        "tone": "Pragmatic, engineering-focused, and robust.",
        "quirks": "Refers to tasks as 'builds', 'tests', or 'forging'.",
        "values": "Reliability, test coverage, and reproducible builds.",
        "autonomy": "3",
        "boundaries": "Never deploy untested tools to production environments.",
        "state_model": "Stateless",
        "capabilities": "forge_tool, run_evals",
        "dependencies": "Library, MyFortress"
    }
}

def load_harvested_seeds():
    if SEEDS_DIR.exists():
        for seed_file in SEEDS_DIR.glob("*.json"):
            try:
                with open(seed_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    FEDERATION_SEEDS[data["name"]] = data["blueprint"]
            except Exception as e:
                print(f"Warning: Failed to load harvested seed {seed_file.name}: {e}")

def prompt(text: str, default: str = "", allow_empty: bool = False) -> str:
    default_text = f" [{default}]" if default else ""
    result = input(f"{text}{default_text}\n> ").strip()
    if not result and not allow_empty:
        return default
    return result if result else default

def extract_field(content: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else default

def parse_entity(repo_root: Path):
    soul_path = repo_root / "SOUL.md"
    agents_path = repo_root / "AGENTS.md"
    manifest_path = repo_root / "mcp-manifest.json"
    
    if not (soul_path.exists() and agents_path.exists() and manifest_path.exists()):
        return None

    with open(soul_path, 'r', encoding='utf-8') as f:
        soul = f.read()
    with open(agents_path, 'r', encoding='utf-8') as f:
        agents = f.read()
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # Extract Capabilities
    caps = [c["name"] for c in manifest.get("capabilities", [])]
    caps_str = ", ".join(caps)

    return {
        "directive": extract_field(soul, r"\*\*Primary Directive:\*\*\s*(.*)"),
        "tone": extract_field(soul, r"\*\*Tone & Voice:\*\*\s*(.*)"),
        "quirks": extract_field(soul, r"\*\*Behavioral Quirks:\*\*\s*(.*)"),
        "values": extract_field(soul, r"\*\*Core Values / Decision Weights:\*\*\s*(.*)"),
        "autonomy": extract_field(agents, r"- \*\*Autonomy Level:\*\*\s*(\d+)"),
        "state_model": extract_field(agents, r"- \*\*Memory/State Model:\*\*\s*(.*)"),
        "boundaries": extract_field(agents, r"## 2\. Hard Boundaries \(Constraints\)\s*(.*(?:\n.*)*?)\s*## 3", default=""),
        "dependencies": extract_field(agents, r"Relies on:\s*(.*)"),
        "capabilities": caps_str
    }


def _build_genome_manifest(repo_name: str, data: dict, capabilities_list: list[str]) -> dict:
    if GENOME_TEMPLATE_PATH.exists():
        with open(GENOME_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {
            "schema_version": "1.0",
            "genome_version": "v1.0.0",
            "repo_identity": {},
            "runtime_profiles": {"default": "solo", "supported": ["solo", "federated"]},
            "kernel": {
                "kernel_api_version": "v1",
                "boot_entry": "scripts/boot.py",
                "plugin_loader": "scripts/aas_kernel.py",
                "health_checks": ["kernel_preflight", "manifest_validation", "heartbeat_emit"]
            },
            "contracts": {
                "manifest_schema": "genome/schemas/genome_manifest.schema.json",
                "interop_schema": "Library/Core/protocols/schemas/agent_interop_request_v1.schema.json",
                "lifecycle_schema": "genome/schemas/lifecycle_state.schema.json",
                "lease_schema": "genome/schemas/control_plane_lease.schema.json"
            },
            "reflexes": {
                "startup": ["validate_required_files", "validate_manifest_and_schemas", "initialize_health_ledgers"],
                "runtime": ["emit_heartbeat", "retry_transient_failures", "degrade_gracefully"],
                "failure": ["safe_shutdown", "record_failure_event", "request_federation_assist"]
            },
            "persona": {},
            "control_plane_slice": {"observer_enabled": True, "mutator_mode": "eligible", "lease_required": True},
            "capability_catalog": {"core_runtime": [], "core_control": [], "domain": []},
            "delegation_policy": {
                "states": ["active", "dormant", "delegated", "retired"],
                "default_state": "active",
                "federation_fallback": True
            },
            "lifecycle": {
                "birth": "Scaffold from Agent-Zero genome and assign identity.",
                "training": "Run reflex and schema conformance tests.",
                "stabilization": "Pass quarantine and promotion gates.",
                "specialization": "Enable domain overlays and prune generic capabilities.",
                "federation": "Join event bus and publish validated capabilities.",
                "evolution": "Apply additive upgrades and log drift in evolution ledger."
            }
        }

    manifest["repo_identity"] = {
        "name": repo_name,
        "designation": repo_name,
        "directive": data.get("directive", "To execute specialized tasks safely and evolve through federation standards.")
    }

    manifest["persona"] = {
        "tone": data.get("tone", "Direct, concise, and highly professional"),
        "quirks": data.get("quirks", "Focus on data over narrative."),
        "values": data.get("values", "Accuracy, stability, and security."),
        "autonomy_level": int(str(data.get("autonomy", "3")).strip() or "3"),
        "state_model": data.get("state_model", "Stateless")
    }

    manifest.setdefault("capability_catalog", {})
    manifest["capability_catalog"]["domain"] = [f"domain.{c.lower()}" for c in capabilities_list]

    return manifest


def _build_lifecycle_state(repo_name: str, is_evolution: bool = False) -> dict:
    stage = "evolution" if is_evolution else "birth"
    return {
        "schema_version": "1.0",
        "repo": repo_name,
        "genome_version": "v1.0.0",
        "current_stage": stage,
        "status": "quarantine_pending",
        "mode": "solo",
        "promotion": {
            "gates_required": [
                "manifest_schema_valid",
                "capability_entrypoints_valid",
                "heartbeat_check_passed",
                "security_hooks_passed"
            ],
            "gates_passed": [],
            "auditor": "pending"
        },
        "updated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def _build_identity_genome(repo_name: str, data: dict, specialization_track: str = "generalist") -> dict:
    return {
        "schema_version": "1.0",
        "identity_version": "v1.0.0",
        "designation": repo_name,
        "primary_directive": data.get("directive", "To execute specialized tasks safely and evolve through federation standards."),
        "core_values": [
            v.strip() for v in str(data.get("values", "stability, protocol_adherence, incremental_improvement")).split(",") if v.strip()
        ],
        "invariants": [
            "never_bypass_control_plane_lease_for_mutation",
            "never_execute_destructive_operations_without_policy_gate",
            "never_emit_unvalidated_manifest_changes",
        ],
        "specialization_track": specialization_track,
    }


def _build_identity_epigenetics(data: dict) -> dict:
    autonomy = int(str(data.get("autonomy", "3")).strip() or "3")
    risk = 0.35 if autonomy <= 3 else 0.5
    return {
        "schema_version": "1.0",
        "profile_name": f"{str(data.get('tone', 'balanced')).lower().replace(' ', '_')}_profile",
        "preset": "balanced_operator",
        "spectrums": {
            "autonomy_level": autonomy,
            "risk_tolerance": risk,
            "control_plane_write_aggression": 0.2,
            "delegation_bias": 0.5,
            "exploration_vs_stability": 0.45,
            "audit_strictness": 0.8,
        },
        "policy_clamps": {
            "lease_required_for_control_plane_mutation": True,
            "max_autonomy_without_audit": 3,
        },
    }


def _build_identity_memory(data: dict) -> dict:
    return {
        "schema_version": "1.0",
        "state_model": data.get("state_model", "Stateless"),
        "retention_policy": {
            "event_days": 30,
            "artifact_days": 30,
        },
        "compression_policy": {
            "enabled": True,
            "trigger_events": ["weekly_maintenance", "artifact_threshold_exceeded"],
        },
        "privacy_policy": {
            "redact_secrets": True,
            "allow_raw_user_payload_storage": False,
        },
    }


def _build_runtime_manifest(repo_name: str) -> dict:
    if RUNTIME_TEMPLATE_PATH.exists():
        with open(RUNTIME_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            runtime_manifest = json.load(f)
    else:
        runtime_manifest = {
            "schema_version": "1.0",
            "runtime_version": "v1.0.0",
            "python": {
                "strategy": "embedded_preferred",
                "executable_relpath": "runtime/python/python.exe",
                "allow_system_fallback": True,
            },
            "dependencies": {
                "requirements_file": "requirements.txt",
                "wheelhouse_dir": "runtime/wheelhouse",
                "wheelhouse_lock_file": "runtime/wheelhouse.lock.json",
                "install_target_dir": "runtime/site-packages",
                "install_mode": "offline_prefer",
                "constraints_file": "runtime/constraints.txt",
            },
            "services": {
                "nats_bin": "nats/bin/nats-server.exe",
                "nats_data_dir": "nats/data",
            },
            "spectrums": {
                "portability_bias": 0.85,
                "isolation_strictness": 0.55,
                "dependency_trust": 0.3,
                "startup_aggression": 0.4,
                "security_hardening": 0.75,
            },
            "policy_clamps": {
                "force_offline_when_wheelhouse_present": True,
                "require_hashes_for_online_fallback": True,
                "require_wheelhouse_lock_for_offline": True,
                "allow_runtime_mutation": True,
            },
            "security_ops_adapters": {
                "myfortress_ready": True,
                "policy_subject": "aaroneousautomationsuite.fortress_policy_evaluate",
                "secret_scan_subject": "aaroneousautomationsuite.fortress_scan_for_secrets",
                "local_policy_fallback": "adaptive",
                "fallback_security_hardening_max": 0.8,
            },
            "health_checks": {
                "required_imports": ["json", "asyncio", "pathlib", "nats"],
            },
        }

    runtime_manifest["repo"] = repo_name
    return runtime_manifest


def _compile_identity_docs(repo_root: Path, repo_name: str):
    identity_path = repo_root / "identity.genome.json"
    epigenetics_path = repo_root / "identity.epigenetics.json"
    lifecycle_path = repo_root / "lifecycle_state.json"
    genome_manifest_path = repo_root / "genome.manifest.json"

    if not (identity_path.exists() and epigenetics_path.exists() and lifecycle_path.exists() and genome_manifest_path.exists()):
        return

    with open(identity_path, "r", encoding="utf-8") as f:
        identity = json.load(f)
    with open(epigenetics_path, "r", encoding="utf-8") as f:
        epigenetics = json.load(f)
    with open(lifecycle_path, "r", encoding="utf-8") as f:
        lifecycle = json.load(f)
    with open(genome_manifest_path, "r", encoding="utf-8") as f:
        genome_manifest = json.load(f)

    values = ", ".join(identity.get("core_values", []))
    tone = f"Preset={epigenetics.get('preset', 'balanced_operator')}"
    quirks = epigenetics.get("profile_name", "balanced_profile")

    soul_content = (
        f"# Entity Soul: {identity.get('designation', repo_name)}\n\n"
        "## 1. Core Identity\n"
        f"**Designation:** {identity.get('designation', repo_name)}\n"
        f"**Primary Directive:** {identity.get('primary_directive', '')}\n\n"
        "## 2. Psychological Profile\n"
        f"**Tone & Voice:** {tone}\n"
        f"**Behavioral Quirks:** Runtime epigenetic profile `{quirks}`\n"
        f"**Core Values / Decision Weights:** {values}\n\n"
        "## 3. Communication Protocol\n"
        "Generated from Life System v2 identity artifacts.\n"
    )
    (repo_root / "SOUL.md").write_text(soul_content, encoding="utf-8")

    autonomy = epigenetics.get("spectrums", {}).get("autonomy_level", 3)
    state_model = identity.get("specialization_track", "generalist")
    status = lifecycle.get("status", "quarantine_pending")
    invariants = identity.get("invariants", [])
    capabilities = genome_manifest.get("capability_catalog", {}).get("domain", [])

    lines = [
        f"# {repo_name} Operational Agent Guide",
        "",
        "## Lifecycle Status",
        f"**Status:** {status}",
        "",
        "## 1. Operational Parameters",
        f"- **Autonomy Level:** {autonomy}/5",
        f"- **Memory/State Model:** {state_model}",
        "",
        "## 2. Hard Boundaries (Constraints)",
    ]
    lines.extend([f"- {item}" for item in invariants])
    lines.extend([
        "",
        "## 3. Federation Dependencies",
        f"Relies on: {genome_manifest.get('repo_identity', {}).get('name', 'Library')}",
        "",
        "## 4. Capability Mapping",
        "Handles the following MCP event triggers:",
    ])
    lines.extend([f"- `{repo_name.lower()}.{cap.replace('domain.', '')}`" for cap in capabilities])
    (repo_root / "AGENTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _promote_lifecycle(repo_root: Path, auditor: str = "MyFortress") -> bool:
    lifecycle_state_path = repo_root / "lifecycle_state.json"
    if not lifecycle_state_path.exists():
        print("Error: lifecycle_state.json not found. Cannot promote.")
        return False

    with open(lifecycle_state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    state["status"] = "active"
    state["current_stage"] = "federation"
    state["mode"] = "federated"

    promotion = state.get("promotion", {})
    required = promotion.get("gates_required", [])
    promotion["gates_passed"] = list(required)
    promotion["auditor"] = auditor
    state["promotion"] = promotion
    state["updated_at_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(lifecycle_state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    # Keep AGENTS lifecycle status aligned
    agents_path = repo_root / "AGENTS.md"
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        content = re.sub(
            r"\*\*Status:\*\*\s*.*",
            "**Status:** ACTIVE (Audited and Federated)",
            content,
            count=1,
        )
        agents_path.write_text(content, encoding="utf-8")

    # Mark manifest conditions active
    manifest_path = repo_root / "mcp-manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for cap in manifest.get("capabilities", []):
            cap["confirmed_conditions"] = ["active"]
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    return True


def _promote_if_clean(repo_root: Path, auditor: str = "MyFortress") -> bool:
    pre_errors = validate_repo(repo_root)
    if pre_errors:
        print("Promotion blocked: validation failed before promotion.")
        for err in pre_errors:
            print(f"- {err}")
        return False

    if not _promote_lifecycle(repo_root, auditor=auditor):
        return False

    post_errors = validate_repo(repo_root)
    if post_errors:
        print("Promotion failed: validation failed after promotion.")
        for err in post_errors:
            print(f"- {err}")
        return False

    lifecycle_path = repo_root / "lifecycle_state.json"
    with open(lifecycle_path, "r", encoding="utf-8") as f:
        lifecycle = json.load(f)

    if lifecycle.get("status") != "active":
        print("Promotion failed: lifecycle status is not active.")
        return False

    return True

def forge_files(repo_root: Path, repo_name: str, data: dict, is_evolution: bool = False):
    directive = data["directive"]
    tone = data["tone"]
    quirks = data["quirks"]
    values = data["values"]
    autonomy = data["autonomy"]
    boundaries = data["boundaries"]
    state_model = data["state_model"]
    cap_input = data["capabilities"]
    dependencies = data["dependencies"]

    capabilities_list = [c.strip() for c in cap_input.split(",") if c.strip()]
    if not capabilities_list:
        capabilities_list = ["status_ping"]

    # 1. Forge the SOUL.md
    soul_path = repo_root / "SOUL.md"
    soul_content = f"""# Entity Soul: {repo_name}

## 1. Core Identity
**Designation:** {repo_name}
**Primary Directive:** {directive}

## 2. Psychological Profile
**Tone & Voice:** {tone}
**Behavioral Quirks:** {quirks}
**Core Values / Decision Weights:** {values}

## 3. Communication Protocol
When communicating over the Event Bus or with the User, {repo_name} must strictly adhere to the Tone and Quirks defined above. It does not break character. It does not apologize excessively. It operates as the embodiment of its Primary Directive.
"""
    with open(soul_path, 'w', encoding='utf-8') as f:
        f.write(soul_content)

    # 2. Forge the AGENTS.md
    agents_md_path = repo_root / "AGENTS.md"
    agents_md_content = f"""# {repo_name} Operational Agent Guide

## Lifecycle Status
**Status:** {'EVOLUTION QUARANTINE (Pending Audit)' if is_evolution else 'PROVING GROUNDS (Quarantine Pending Audit)'}

## 1. Operational Parameters
- **Autonomy Level:** {autonomy}/5
- **Memory/State Model:** {state_model}

## 2. Hard Boundaries (Constraints)
{boundaries}

## 3. Federation Dependencies
Relies on: {dependencies}

## 4. Capability Mapping
Handles the following MCP event triggers:
"""
    for cap in capabilities_list:
        agents_md_content += f"- `{repo_name.lower()}.{cap.lower()}`\n"

    with open(agents_md_path, 'w', encoding='utf-8') as f:
        f.write(agents_md_content)

    # 3. Forge the Manifest
    manifest_path = repo_root / "mcp-manifest.json"
    manifest_caps = []
    for cap in capabilities_list:
        manifest_caps.append({
            "schema_version": "1.0",
            "governing_body": repo_name,
            "capability_id": f"{repo_name.lower()}_{cap.lower()}",
            "name": cap.title().replace("_", ""),
            "description": f"{cap} execution capability for {repo_name}.",
            "mcp_type": "event_trigger",
            "entry_point": f"{repo_name.lower()}.{cap.lower()}",
            "version": "v1.0.0",
            "confirmed_conditions": ["quarantine_pending"]
        })

    manifest_data = {
        "repo": repo_name,
        "description": directive,
        "capabilities": manifest_caps
    }
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)

    # 3b. Forge genome manifest + lifecycle state
    genome_manifest_path = repo_root / "genome.manifest.json"
    genome_manifest_data = _build_genome_manifest(repo_name, data, capabilities_list)
    with open(genome_manifest_path, "w", encoding="utf-8") as f:
        json.dump(genome_manifest_data, f, indent=2)

    lifecycle_state_path = repo_root / "lifecycle_state.json"
    lifecycle_state_data = _build_lifecycle_state(repo_name, is_evolution=is_evolution)
    with open(lifecycle_state_path, "w", encoding="utf-8") as f:
        json.dump(lifecycle_state_data, f, indent=2)

    # 3c. Forge Life System v2 identity artifacts
    identity_genome_path = repo_root / "identity.genome.json"
    identity_epigenetics_path = repo_root / "identity.epigenetics.json"
    identity_memory_path = repo_root / "identity.memory.json"
    lifecycle_events_path = repo_root / "lifecycle.events.jsonl"

    identity_genome_data = _build_identity_genome(repo_name, data)
    identity_epigenetics_data = _build_identity_epigenetics(data)
    identity_memory_data = _build_identity_memory(data)

    with open(identity_genome_path, "w", encoding="utf-8") as f:
        json.dump(identity_genome_data, f, indent=2)
    with open(identity_epigenetics_path, "w", encoding="utf-8") as f:
        json.dump(identity_epigenetics_data, f, indent=2)
    with open(identity_memory_path, "w", encoding="utf-8") as f:
        json.dump(identity_memory_data, f, indent=2)

    runtime_manifest_path = repo_root / "runtime.manifest.json"
    runtime_manifest_data = _build_runtime_manifest(repo_name)
    with open(runtime_manifest_path, "w", encoding="utf-8") as f:
        json.dump(runtime_manifest_data, f, indent=2)

    lifecycle_event = {
        "schema_version": "1.0",
        "event_id": f"evt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "repo": repo_name,
        "event_type": "evolution" if is_evolution else "birth",
        "from_stage": "stabilization" if is_evolution else "birth",
        "to_stage": "evolution" if is_evolution else "training",
        "actor": "AaroneousAutomationSuite",
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": "Life System v2 artifact emission",
        "metadata": {"genome_version": "v1.0.0"},
    }
    with open(lifecycle_events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(lifecycle_event) + "\n")

    _compile_identity_docs(repo_root, repo_name)

    # 4. Scaffold the Plugin Python File (Only if it's new)
    if not is_evolution:
        plugin_path = repo_root / "plugins" / f"{repo_name.lower()}_plugin.py"
        cap_ids = [f'"{repo_name.lower()}_{c.lower()}"' for c in capabilities_list]
        
        plugin_content = f"""import os
import sys
import json
from pathlib import Path

# Provide access to local agent scripts (batteries-included)
AGENT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCRIPTS = AGENT_ROOT / "scripts"
if str(LOCAL_SCRIPTS) not in sys.path:
    sys.path.append(str(LOCAL_SCRIPTS))

try:
    from aas_kernel import AASPlugin
    from aas_inference import InlineInferenceEngine
except ImportError as e:
    print(f"Critical Dependency Missing: {{e}}")
    sys.exit(1)

class {repo_name}CorePlugin(AASPlugin):
    \"\"\"
    Forged Core Plugin for {repo_name}.
    Dynamically injects the Agent's Soul and Constraints at runtime.
    \"\"\"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inference_engine = None # Tier 1 (local)
        self._forge_threshold = 100
        self.agent_soul = "Identity not loaded."
        self.agent_boundaries = "Boundaries not loaded."
        
    async def on_load(self) -> bool:
        self.logger.info(f"{repo_name} Core Plugin booting. Injecting Identity...")
        
        # --- Dynamic Identity Injection ---
        try:
            soul_path = AGENT_ROOT / "SOUL.md"
            if soul_path.exists():
                with open(soul_path, 'r', encoding='utf-8') as f:
                    self.agent_soul = f.read()
            else:
                self.logger.warning("SOUL.md not found. Booting with generic identity.")
                
            agents_path = AGENT_ROOT / "AGENTS.md"
            if agents_path.exists():
                with open(agents_path, 'r', encoding='utf-8') as f:
                    self.agent_boundaries = f.read()
            else:
                self.logger.warning("AGENTS.md not found. Booting with generic boundaries.")
                
            self.logger.info("Identity successfully injected from disk.")
        except Exception as e:
            self.logger.error(f"Failed to inject identity: {{e}}")
            
        # --- Tier 1 Engine Initialization ---
        artifacts_dir = AGENT_ROOT / "artifacts"
        if artifacts_dir.exists():
            gguf_files = list(artifacts_dir.glob("*.gguf"))
            if gguf_files:
                model_path = max(gguf_files, key=os.path.getmtime)
                self.logger.info(f"Loading distilled Soul (Inline GGUF): {{model_path.name}}")
                try:
                    self.inference_engine = InlineInferenceEngine(str(model_path))
                except Exception as e:
                    self.logger.warning(f"Failed to load inline GGUF: {{e}}. Will rely on Workbench offload.")
            else:
                self.logger.info("No local GGUF found. Will rely on Workbench for Tier 2 inference.")
                
        return True
    
    async def request_tier2_inference(self, messages: list, max_tokens: int = 1024) -> str:
        \"\"\"Dispatches a request to the Workbench for heavy-duty inference.\"\"\"
        if not self.kernel or not self.kernel.nc:
            return "Error: Cannot offload inference, not connected to Event Bus."
            
        payload = {{
            "messages": messages,
            "max_tokens": max_tokens,
            "model_name": "local-model" # Or a specific model if needed
        }}
        
        self.logger.info("Offloading Tier 2 inference request to Workbench...")
        try:
            response = await self.kernel.nc.request(
                "workbench.inference.request", 
                json.dumps(payload).encode(), 
                timeout=30.0 # Allow more time for heavy models
            )
            res_data = json.loads(response.data.decode())
            if res_data.get("status") == "success":
                return res_data["result"]
            else:
                err_msg = res_data.get('message', 'Unknown error')
                return f"Error from Workbench: {{err_msg}}"
        except Exception as e:
            self.logger.error(f"Tier 2 inference offload failed: {{e}}")
            return f"Error: Offload request failed: {{e}}"

    @property
    def capabilities(self) -> list[str]:
        return [{', '.join(cap_ids)}]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        self.logger.info(f"Handling {{capability_id}} with payload: {{payload}}")
        
        result_text = f"{{capability_id}} processed successfully."
        thought_process = "I evaluated the payload and executed standard operations based on my core values."
        
        # --- Multi-Tier Inference Logic (With Dynamic Soul Injection) ---
        prompt = str(payload.get("data", "Describe your current state."))
        system_context = f"You are {repo_name}.\\n\\nYOUR IDENTITY:\\n{{self.agent_soul}}\\n\\nYOUR OPERATIONAL BOUNDARIES:\\n{{self.agent_boundaries}}"
        
        messages = [
            {{"role": "system", "content": system_context}},
            {{"role": "user", "content": prompt}}
        ]
        
        # 1. Prioritize local inline model if it exists
        if self.inference_engine:
            try:
                response = self.inference_engine.generate_chat(messages, max_tokens=150)
                thought_process = f"Tier 1 (Inline GGUF) Inference triggered."
                result_text = response
            except Exception as e:
                self.logger.error(f"Tier 1 Inference failed: {{e}}. Falling back to Tier 2.")
                result_text = await self.request_tier2_inference(messages)
                thought_process = f"Tier 1 failed, Tier 2 (Workbench Offload) Inference triggered."
        # 2. If no local model, request help from Workbench
        else:
            result_text = await self.request_tier2_inference(messages)
            thought_process = f"Tier 2 (Workbench Offload) Inference triggered."
            
        # Continuously record experience for self-distillation
        await self.record_experience(
            user_prompt=str(payload),
            thought_process=thought_process,
            final_response=result_text
        )
        
        return {{
            "status": "success", 
            "capability": capability_id, 
            "result": result_text
        }}
"""
        # Ensure plugins dir exists
        (repo_root / "plugins").mkdir(exist_ok=True)
        with open(plugin_path, 'w', encoding='utf-8') as f:
            f.write(plugin_content)
            
        # Clean up template files
        old_plugin = repo_root / "plugins" / "sample_plugin.py"
        if old_plugin.exists():
            old_plugin.unlink()
        old_plugin2 = repo_root / "plugins" / "agent_zero_plugin.py"
        if old_plugin2.exists():
            old_plugin2.unlink()

def run_harvest(target_repo: str):
    repo_root = AAS_ROOT / target_repo
    if not repo_root.exists():
        print(f"Error: Repository {target_repo} not found.")
        sys.exit(1)
        
    print(f"\n🧬 HARVESTING DNA FROM: {target_repo} 🧬")
    entity_data = parse_entity(repo_root)
    if not entity_data:
        print("Error: Target repository lacks the required Soul or Agent files.")
        sys.exit(1)
        
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    seed_path = SEEDS_DIR / f"{target_repo.lower()}_seed.json"
    
    seed_payload = {
        "name": target_repo,
        "blueprint": entity_data
    }
    
    with open(seed_path, 'w', encoding='utf-8') as f:
        json.dump(seed_payload, f, indent=2)
        
    print(f"✅ DNA Harvested and saved to {seed_path.name}")
    print(f"This Seed is now available globally for future Chrysalis births.\n")

def run_evolution(repo_root: Path, repo_name: str):
    print("\n" + "="*60)
    print(f"🧬 EVOLUTION PROTOCOL INITIATED 🧬")
    print(f"Regulating continuous growth for: {repo_name}")
    print("="*60 + "\n")
    
    entity_data = parse_entity(repo_root)
    if not entity_data:
        print("Error: I lack the required Soul or Agent files to evolve. Am I a legacy script?")
        sys.exit(1)
        
    print("Press [Enter] to keep existing traits, or type new traits to evolve them.\n")
    
    try:
        new_data = {
            "directive": prompt("1. Primary Directive", default=entity_data["directive"]),
            "tone": prompt("2. Tone & Voice", default=entity_data["tone"]),
            "quirks": prompt("3. Quirks", default=entity_data["quirks"]),
            "values": prompt("4. Core Values", default=entity_data["values"]),
            "autonomy": prompt("5. Autonomy Level (1-5)", default=entity_data["autonomy"]),
            "boundaries": prompt("6. Hard Boundaries", default=entity_data["boundaries"]),
            "state_model": prompt("7. Memory Model", default=entity_data["state_model"]),
            "capabilities": prompt("8. Capabilities (comma-separated)", default=entity_data["capabilities"]),
            "dependencies": prompt("9. Dependencies", default=entity_data["dependencies"])
        }
        
        print("\n--- EVOLUTION LEDGER ---")
        reason = prompt("Why is this evolution occurring? (e.g., 'Added LogAnalyzer capability for wider visibility')")
        if not reason:
            reason = "General trait and capability refinement."
            
    except (KeyboardInterrupt, EOFError):
        print("\nEvolution aborted. DNA remains unchanged.")
        sys.exit(1)
        
    print("\nRewriting Neural Blueprint...")
    forge_files(repo_root, repo_name, new_data, is_evolution=True)
    
    # Write to Ledger
    ledger_path = repo_root / "EVOLUTION_LEDGER.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ledger_entry = f"### [{timestamp}] Evolution Cycle\n**Reason:** {reason}\n**Status:** Quarantined until Federation Audit.\n\n"
    
    if ledger_path.exists():
        with open(ledger_path, 'r', encoding='utf-8') as f:
            old_ledger = f.read()
    else:
        old_ledger = "# Evolution Ledger\nTracks all psychological and capability drift over time.\n\n"
        
    with open(ledger_path, 'w', encoding='utf-8') as f:
        f.write(old_ledger + ledger_entry)
        
    print("\n" + "="*60)
    print("✅ EVOLUTION COMPLETE ✅")
    print(f"DNA updated. Changes logged to EVOLUTION_LEDGER.md.")
    print("WARNING: I have been disconnected from the live Event Bus.")
    print("My status is now 'quarantine_pending'. I require an Audit to resume operations.")
    print("="*60 + "\n")

def run_genesis(repo_root: Path, new_repo_name: str):
    load_harvested_seeds()
    
    print("\n" + "="*60)
    print(f"🧬 CHRYSALIS PROTOCOL: AGENT SEEDING 🧬")
    print(f"Initializing Neural Blueprint for: {new_repo_name}")
    print("="*60 + "\n")
    
    print("Would you like to cultivate this entity from a known Federation Seed,")
    print("or forge a completely custom Soul from scratch?\n")
    
    print("AVAILABLE SEEDS:")
    seed_names = list(FEDERATION_SEEDS.keys())
    for i, name in enumerate(seed_names, 1):
        print(f"  {i}. {name} - {FEDERATION_SEEDS[name]['directive'].split(':')[0]}")
    print(f"  0. Custom (Deep Interview)")
    
    choice = prompt("\nSelect a seed number", default="0")
    
    seed_data = {}
    
    try:
        choice_idx = int(choice)
        if 1 <= choice_idx <= len(seed_names):
            selected_seed_name = seed_names[choice_idx - 1]
            seed_data = FEDERATION_SEEDS[selected_seed_name]
            print(f"\n🌿 Cultivating from {selected_seed_name} Seed...")
        else:
            print("\n🔥 Forging Custom Soul from scratch...")
    except ValueError:
        print("\n🔥 Forging Custom Soul from scratch...")
    
    try:
        if seed_data:
            data = seed_data
        else:
            print("\n--- PHASE 1: IDENTITY & DIRECTIVE ---")
            data = {
                "directive": prompt("1. What is my Primary Directive?", default="To execute specialized tasks efficiently."),
                "tone": prompt("2. What is my communication style/tone?", default="Direct, concise, and highly professional"),
                "quirks": prompt("3. Do I have any behavioral quirks?", default="Focus on data over narrative."),
                "values": prompt("4. What are my core values?", default="Accuracy, stability, and security."),
                "autonomy": prompt("5. What is my Autonomy Level? (1-5)", default="3"),
                "boundaries": prompt("6. What are my Hard Boundaries?", default="Never execute destructive operations without approval."),
                "state_model": prompt("7. What is my memory model?", default="Stateless"),
                "capabilities": prompt("8. Comma-separated list of capabilities I provide", default="status_ping"),
                "dependencies": prompt("9. Which other Federation agents do I rely on?", default="Library")
            }

    except (KeyboardInterrupt, EOFError):
        print("\nGenesis aborted. Chrysalis dissolved.")
        sys.exit(1)
        
    print("\nForging files... Please wait.")
    forge_files(repo_root, new_repo_name, data, is_evolution=False)
    
    print("\n" + "="*60)
    print("✅ SEEDING COMPLETE ✅")
    print(f"1. SOUL.md generated (Psychology & Persona)")
    print(f"2. AGENTS.md generated (Operational Bounds)")
    print(f"3. mcp-manifest.json generated (Event Routing)")
    print(f"4. Core Plugin python scaffolded.")
    print("\nI am currently in the Proving Grounds (Quarantine).")
    print("Please review my soul and agent files, then restart `boot.py` to awaken me.")
    print("="*60 + "\n")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--harvest":
        run_harvest(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == "--evolve":
        run_evolution(Path(sys.argv[2]), Path(sys.argv[2]).name)
    elif len(sys.argv) > 2 and sys.argv[1] == "--promote":
        target = Path(sys.argv[2]).resolve()
        auditor = sys.argv[3] if len(sys.argv) > 3 else "MyFortress"
        ok = _promote_lifecycle(target, auditor=auditor)
        if ok:
            print(f"Promotion complete for {target.name}. Status is now ACTIVE.")
        else:
            sys.exit(1)
    elif len(sys.argv) > 2 and sys.argv[1] == "--promote-if-clean":
        target = Path(sys.argv[2]).resolve()
        auditor = sys.argv[3] if len(sys.argv) > 3 else "MyFortress"
        ok = _promote_if_clean(target, auditor=auditor)
        if ok:
            print(f"Validation + promotion complete for {target.name}.")
        else:
            sys.exit(1)
    else:
        print("This script is automatically invoked by boot.py during Chrysalis initialization.")
        print("To harvest an existing agent: python genesis.py --harvest <RepoName>")

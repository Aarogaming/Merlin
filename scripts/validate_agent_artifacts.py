import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
SCHEMA_ROOT = ROOT / "genome" / "schemas"


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: Path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                items.append((idx, json.loads(line)))
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at line {idx}: {exc}") from exc
    return items


def _type_ok(value, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate_by_schema(value, schema: dict, context: str, errors: list[str]):
    s_type = schema.get("type")
    if isinstance(s_type, str) and not _type_ok(value, s_type):
        errors.append(f"Schema violation at {context}: expected type {s_type}")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"Schema violation at {context}: value not in enum")

    if isinstance(value, str):
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            errors.append(f"Schema violation at {context}: minLength {min_len}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if not re.match(pattern, value):
                    errors.append(f"Schema violation at {context}: pattern mismatch")
            except re.error as exc:
                errors.append(f"Invalid schema regex at {context}: {exc}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"Schema violation at {context}: minimum {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"Schema violation at {context}: maximum {maximum}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"Schema violation at {context}: minItems {min_items}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                _validate_by_schema(item, item_schema, f"{context}[{idx}]", errors)

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    errors.append(f"Schema violation at {context}: missing required '{key}'")

        props = schema.get("properties", {})
        if isinstance(props, dict):
            for key, prop_schema in props.items():
                if key in value and isinstance(prop_schema, dict):
                    _validate_by_schema(value[key], prop_schema, f"{context}.{key}", errors)

        if schema.get("additionalProperties") is False and isinstance(props, dict):
            allowed = set(props.keys())
            for key in value.keys():
                if key not in allowed:
                    errors.append(f"Schema violation at {context}: additional property '{key}' not allowed")


def _validate_json_file_against_schema(data_path: Path, schema_path: Path, errors: list[str], label: str):
    try:
        data = _load_json(data_path)
    except Exception as exc:
        errors.append(f"Failed to parse {label} {data_path}: {exc}")
        return
    try:
        schema = _load_json(schema_path)
    except Exception as exc:
        errors.append(f"Failed to parse schema {schema_path} for {label}: {exc}")
        return
    _validate_by_schema(data, schema, label, errors)


def _require(path: Path, errors: list[str]):
    if not path.exists():
        errors.append(f"Missing required file: {path}")
        return False
    return True


def _validate_mcp_manifest(path: Path, errors: list[str]):
    data = _load_json(path)
    if not isinstance(data, dict):
        errors.append(f"Invalid MCP manifest object: {path}")
        return
    if "repo" not in data or not str(data.get("repo", "")).strip():
        errors.append(f"MCP manifest missing 'repo': {path}")
    caps = data.get("capabilities")
    if not isinstance(caps, list) or not caps:
        errors.append(f"MCP manifest missing capability list: {path}")
        return
    for i, cap in enumerate(caps):
        if not isinstance(cap, dict):
            errors.append(f"Capability #{i} is not an object in {path}")
            continue
        for field in ["capability_id", "entry_point", "version", "mcp_type"]:
            if not str(cap.get(field, "")).strip():
                errors.append(f"Capability #{i} missing '{field}' in {path}")


def _validate_genome_manifest(path: Path, errors: list[str]):
    data = _load_json(path)
    required = [
        "schema_version",
        "genome_version",
        "repo_identity",
        "runtime_profiles",
        "kernel",
        "contracts",
        "reflexes",
        "persona",
        "control_plane_slice",
        "capability_catalog",
        "delegation_policy",
        "lifecycle",
    ]
    for field in required:
        if field not in data:
            errors.append(f"Genome manifest missing '{field}': {path}")
    if data.get("runtime_profiles", {}).get("default") not in {"solo", "federated"}:
        errors.append(f"Genome runtime_profiles.default must be solo|federated: {path}")


def _validate_lifecycle_state(path: Path, errors: list[str]):
    data = _load_json(path)
    required = [
        "schema_version",
        "repo",
        "genome_version",
        "current_stage",
        "status",
        "mode",
        "promotion",
        "updated_at_utc",
    ]
    for field in required:
        if field not in data:
            errors.append(f"Lifecycle state missing '{field}': {path}")
    if data.get("status") not in {"quarantine_pending", "active", "degraded", "retired"}:
        errors.append(f"Invalid lifecycle status in {path}")
    if data.get("mode") not in {"solo", "federated"}:
        errors.append(f"Invalid lifecycle mode in {path}")


def validate_repo(repo_root: Path) -> list[str]:
    errors: list[str] = []
    mcp = repo_root / "mcp-manifest.json"
    genome = repo_root / "genome.manifest.json"
    lifecycle = repo_root / "lifecycle_state.json"
    identity_genome = repo_root / "identity.genome.json"
    identity_epigenetics = repo_root / "identity.epigenetics.json"
    identity_memory = repo_root / "identity.memory.json"
    lifecycle_events = repo_root / "lifecycle.events.jsonl"
    runtime_manifest = repo_root / "runtime.manifest.json"

    mcp_ok = _require(mcp, errors)
    genome_ok = _require(genome, errors)
    lifecycle_ok = _require(lifecycle, errors)
    identity_genome_ok = _require(identity_genome, errors)
    identity_epigenetics_ok = _require(identity_epigenetics, errors)
    identity_memory_ok = _require(identity_memory, errors)
    lifecycle_events_ok = _require(lifecycle_events, errors)

    if mcp_ok:
        try:
            _validate_mcp_manifest(mcp, errors)
        except Exception as exc:
            errors.append(f"Failed to parse MCP manifest {mcp}: {exc}")
    if genome_ok:
        try:
            _validate_genome_manifest(genome, errors)
        except Exception as exc:
            errors.append(f"Failed to parse genome manifest {genome}: {exc}")
    if lifecycle_ok:
        try:
            _validate_lifecycle_state(lifecycle, errors)
        except Exception as exc:
            errors.append(f"Failed to parse lifecycle state {lifecycle}: {exc}")
    if identity_genome_ok:
        _validate_json_file_against_schema(
            identity_genome,
            SCHEMA_ROOT / "identity_genome.schema.json",
            errors,
            "identity.genome",
        )
    if identity_epigenetics_ok:
        _validate_json_file_against_schema(
            identity_epigenetics,
            SCHEMA_ROOT / "epigenetic_profile.schema.json",
            errors,
            "identity.epigenetics",
        )
    if identity_memory_ok:
        _validate_json_file_against_schema(
            identity_memory,
            SCHEMA_ROOT / "memory_model.schema.json",
            errors,
            "identity.memory",
        )

    if lifecycle_events_ok:
        try:
            rows = _load_jsonl(lifecycle_events)
            schema = _load_json(SCHEMA_ROOT / "lifecycle_event.schema.json")
            if not rows:
                errors.append(f"Lifecycle events file is empty: {lifecycle_events}")
            for idx, row in rows:
                _validate_by_schema(row, schema, f"lifecycle.event[line={idx}]", errors)
        except Exception as exc:
            errors.append(f"Failed to parse lifecycle events {lifecycle_events}: {exc}")

    if runtime_manifest.exists():
        _validate_json_file_against_schema(
            runtime_manifest,
            SCHEMA_ROOT / "runtime_bundle.schema.json",
            errors,
            "runtime.bundle",
        )

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate required AAS agent birth artifacts.")
    parser.add_argument("--repo", help="Repo name under workspace root (e.g. Merlin)")
    parser.add_argument("--repo-path", help="Absolute path to repo root")
    args = parser.parse_args()

    if args.repo_path:
        repo_root = Path(args.repo_path).resolve()
    elif args.repo:
        repo_root = (WORKSPACE_ROOT / args.repo).resolve()
    else:
        repo_root = ROOT

    errors = validate_repo(repo_root)
    if errors:
        print("VALIDATION FAILED")
        for e in errors:
            print(f"- {e}")
        raise SystemExit(1)

    print(f"VALIDATION OK: {repo_root}")


if __name__ == "__main__":
    main()

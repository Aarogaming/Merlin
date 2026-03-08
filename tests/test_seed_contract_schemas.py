from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
EXAMPLES_SEED_DIR = CONTRACTS_DIR / "examples" / "seed"
SEED_SCHEMAS_DIR = CONTRACTS_DIR / "seed"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _schema_errors(schema: dict, payload: dict) -> list[str]:
    resolver = RefResolver(
        base_uri=(SEED_SCHEMAS_DIR.resolve().as_uri() + "/"),
        referrer=schema,
    )
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        resolver=resolver,
    )
    return [error.message for error in validator.iter_errors(payload)]


def test_seed_schema_examples_validate():
    pairs = [
        (
            CONTRACTS_DIR / "seed" / "seed_guidance.schema.json",
            EXAMPLES_SEED_DIR / "seed_guidance.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_health.schema.json",
            EXAMPLES_SEED_DIR / "seed_health.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_health_heartbeat.schema.json",
            EXAMPLES_SEED_DIR / "seed_health_heartbeat.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_watchdog_tick.schema.json",
            EXAMPLES_SEED_DIR / "seed_watchdog_tick.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_watchdog_runtime_status.schema.json",
            EXAMPLES_SEED_DIR / "seed_watchdog_runtime_status.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_watchdog_runtime_control.schema.json",
            EXAMPLES_SEED_DIR / "seed_watchdog_runtime_control.example.json",
        ),
        (
            CONTRACTS_DIR / "seed" / "seed_status.schema.json",
            EXAMPLES_SEED_DIR / "seed_status.example.json",
        ),
    ]

    for schema_path, example_path in pairs:
        schema = _load_json(schema_path)
        payload = _load_json(example_path)
        errors = _schema_errors(schema, payload)
        assert not errors, f"{example_path.name} failed {schema_path.name}: {errors}"


def test_seed_contract_registry_contains_seed_entries():
    registry_path = CONTRACTS_DIR / "registry.json"
    payload = _load_json(registry_path)
    entries = payload.get("entries")
    assert isinstance(entries, list)

    expected_paths = {
        "contracts/seed/seed_guidance.schema.json",
        "contracts/seed/seed_health.schema.json",
        "contracts/seed/seed_health_heartbeat.schema.json",
        "contracts/seed/seed_watchdog_tick.schema.json",
        "contracts/seed/seed_watchdog_runtime_status.schema.json",
        "contracts/seed/seed_watchdog_runtime_control.schema.json",
        "contracts/seed/seed_status.schema.json",
    }
    found_paths = {
        str(item.get("path", "")) for item in entries if isinstance(item, dict)
    }

    assert expected_paths.issubset(found_paths)
    for rel_path in expected_paths:
        assert (ROOT_DIR / rel_path).exists(), f"missing contract at {rel_path}"

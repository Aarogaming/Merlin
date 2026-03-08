from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
EXAMPLES_DISCOVERY_DIR = CONTRACTS_DIR / "examples" / "discovery"
EXAMPLES_EVENTS_DIR = CONTRACTS_DIR / "examples" / "events"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _schema_errors(schema: dict, payload: dict) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(payload)]


def test_discovery_schema_examples_validate():
    pairs = [
        (
            CONTRACTS_DIR / "discovery" / "seed.schema.json",
            EXAMPLES_DISCOVERY_DIR / "seed.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "collected_item.schema.json",
            EXAMPLES_DISCOVERY_DIR / "collected_item.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "score_result.schema.json",
            EXAMPLES_DISCOVERY_DIR / "score_result.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "topic_selection.schema.json",
            EXAMPLES_DISCOVERY_DIR / "topic_selection.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "artifact.schema.json",
            EXAMPLES_DISCOVERY_DIR / "artifact.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "publish_result.schema.json",
            EXAMPLES_DISCOVERY_DIR / "publish_result.example.json",
        ),
        (
            CONTRACTS_DIR / "discovery" / "run_report.schema.json",
            EXAMPLES_DISCOVERY_DIR / "run_report.example.json",
        ),
    ]

    for schema_path, example_path in pairs:
        schema = _load_json(schema_path)
        payload = _load_json(example_path)
        errors = _schema_errors(schema, payload)
        assert not errors, f"{example_path.name} failed {schema_path.name}: {errors}"


def test_discovery_event_envelope_example_validates():
    schema = _load_json(CONTRACTS_DIR / "events" / "event_envelope.schema.json")
    payload = _load_json(EXAMPLES_EVENTS_DIR / "event_envelope.example.json")
    errors = _schema_errors(schema, payload)

    assert not errors, f"event envelope example failed schema validation: {errors}"


def test_discovery_contract_registry_contains_all_discovery_entries():
    registry_path = CONTRACTS_DIR / "registry.json"
    payload = _load_json(registry_path)
    entries = payload.get("entries")
    assert isinstance(entries, list)

    expected_paths = {
        "contracts/discovery/seed.schema.json",
        "contracts/discovery/collected_item.schema.json",
        "contracts/discovery/score_result.schema.json",
        "contracts/discovery/topic_selection.schema.json",
        "contracts/discovery/artifact.schema.json",
        "contracts/discovery/publish_result.schema.json",
        "contracts/discovery/run_report.schema.json",
        "contracts/events/event_envelope.schema.json",
    }

    found_paths = {
        str(item.get("path", ""))
        for item in entries
        if isinstance(item, dict)
    }

    assert expected_paths.issubset(found_paths)
    for rel_path in expected_paths:
        assert (ROOT_DIR / rel_path).exists(), f"missing contract at {rel_path}"

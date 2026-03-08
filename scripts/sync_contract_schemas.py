#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
STANDALONE_ROUTING_SCHEMA = (
    CONTRACTS_DIR / "assistant.chat.routing-metadata.v1.schema.json"
)
OPERATION_ENVELOPE_SCHEMA = CONTRACTS_DIR / "aas.operation-envelope.v1.schema.json"
EMBEDDED_SCHEMA_KEY = "assistant_chat_routing_metadata"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def _normalize_routing_schema(schema: dict) -> dict:
    normalized = deepcopy(schema)
    normalized.pop("$schema", None)
    normalized.pop("$id", None)
    normalized.pop("title", None)
    normalized.pop("description", None)
    return normalized


def _embedded_schema(envelope_schema: dict) -> dict | None:
    defs = envelope_schema.get("$defs")
    if not isinstance(defs, dict):
        return None
    embedded = defs.get(EMBEDDED_SCHEMA_KEY)
    return embedded if isinstance(embedded, dict) else None


def _sync_embedded_schema(envelope_schema: dict, normalized_schema: dict) -> dict:
    synced = deepcopy(envelope_schema)
    defs = synced.setdefault("$defs", {})
    if not isinstance(defs, dict):
        defs = {}
        synced["$defs"] = defs
    defs[EMBEDDED_SCHEMA_KEY] = normalized_schema
    return synced


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sync assistant routing metadata schema into the operation envelope schema."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if embedded schema is out of sync.",
    )
    mode.add_argument(
        "--precommit",
        action="store_true",
        help="Pre-commit friendly check mode with deterministic PASS/FAIL messaging.",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write embedded schema updates into the operation envelope schema.",
    )
    parser.add_argument(
        "--standalone-path",
        default=str(STANDALONE_ROUTING_SCHEMA),
        help="Path to standalone assistant routing metadata schema file.",
    )
    parser.add_argument(
        "--envelope-path",
        default=str(OPERATION_ENVELOPE_SCHEMA),
        help="Path to operation envelope schema file containing embedded metadata schema.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    standalone_path = Path(args.standalone_path)
    envelope_path = Path(args.envelope_path)

    standalone = _load_json(standalone_path)
    envelope = _load_json(envelope_path)

    normalized = _normalize_routing_schema(standalone)
    embedded = _embedded_schema(envelope)
    in_sync = embedded == normalized

    if args.write:
        if in_sync:
            print("contract schemas are already in sync")
            return 0
        updated = _sync_embedded_schema(envelope, normalized)
        _write_json(envelope_path, updated)
        print(f"updated {envelope_path}")
        return 0

    if args.check:
        if in_sync:
            print("contract schemas are in sync")
            return 0
        print("contract schema drift detected:")
        print(f"- standalone: {standalone_path}")
        print(f"- embedded: {envelope_path} -> $defs.{EMBEDDED_SCHEMA_KEY}")
        return 1

    if args.precommit:
        if in_sync:
            print("contract-schema-sync: PASS")
            return 0
        print("contract-schema-sync: FAIL")
        print(f"- standalone: {standalone_path}")
        print(f"- embedded: {envelope_path} -> $defs.{EMBEDDED_SCHEMA_KEY}")
        print(
            "run `python3 scripts/sync_contract_schemas.py --write` to update embedded schema"
        )
        return 1

    # Default mode: report status without mutating files.
    if in_sync:
        print("contract schemas are in sync")
        return 0
    print("contract schemas are out of sync (run with --write to update)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

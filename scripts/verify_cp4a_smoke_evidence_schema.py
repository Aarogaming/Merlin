#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT_DIR / "contracts"
DEFAULT_SCHEMA_PATH = CONTRACTS_DIR / "cp4a.smoke-evidence.v1.schema.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CP4-A smoke evidence JSON against schema contract."
    )
    parser.add_argument(
        "--evidence",
        required=True,
        help="Path to cp4a smoke evidence JSON file.",
    )
    parser.add_argument(
        "--schema-path",
        default=str(DEFAULT_SCHEMA_PATH),
        help="Path to CP4-A smoke evidence schema JSON file.",
    )
    return parser


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _format_error_path(parts: list[object]) -> str:
    if not parts:
        return "<root>"
    return ".".join(str(part) for part in parts)


def main() -> int:
    args = _build_parser().parse_args()
    evidence_path = Path(args.evidence)
    schema_path = Path(args.schema_path)

    if not evidence_path.exists():
        print(f"evidence file missing: {evidence_path}")
        return 1
    if not schema_path.exists():
        print(f"schema file missing: {schema_path}")
        return 1

    evidence = _load_json(evidence_path)
    schema = _load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(evidence), key=lambda err: list(err.path))

    if errors:
        print("cp4a smoke evidence schema validation failed:")
        for error in errors:
            path = _format_error_path(list(error.absolute_path))
            print(f"- {path}: {error.message}")
        return 1

    print("cp4a smoke evidence schema verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

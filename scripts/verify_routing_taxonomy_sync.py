#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from merlin_routing_contract import (
    FALLBACK_REASON_CODES,
    RETRYABLE_FALLBACK_CODES,
    ROUTING_DECISION_FIELDS,
)

CONTRACTS_DIR = ROOT_DIR / "contracts"
ROUTING_METADATA_SCHEMA = (
    CONTRACTS_DIR / "assistant.chat.routing-metadata.v1.schema.json"
)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_reason_codes(schema: dict) -> tuple[set[str], bool]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set(), False
    reason_schema = properties.get("fallback_reason_code")
    if not isinstance(reason_schema, dict):
        return set(), False
    enum_values = reason_schema.get("enum")
    if not isinstance(enum_values, list):
        return set(), False

    codes = {value for value in enum_values if isinstance(value, str)}
    has_null = None in enum_values
    return codes, has_null


def _extract_required_fields(schema: dict) -> set[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return set()
    return {field for field in required if isinstance(field, str)}


def _extract_rule_partitions(schema: dict) -> tuple[set[str], set[str], bool]:
    all_of = schema.get("allOf")
    if not isinstance(all_of, list):
        return set(), set(), False

    retryable_true_codes: set[str] = set()
    retryable_false_codes: set[str] = set()
    has_null_rule = False

    for rule in all_of:
        if not isinstance(rule, dict):
            continue

        if_clause = rule.get("if")
        then_clause = rule.get("then")
        if not isinstance(if_clause, dict) or not isinstance(then_clause, dict):
            continue

        if_props = if_clause.get("properties")
        then_props = then_clause.get("properties")
        if not isinstance(if_props, dict) or not isinstance(then_props, dict):
            continue

        fallback_reason = if_props.get("fallback_reason_code")
        fallback_retryable = then_props.get("fallback_retryable")
        if not isinstance(fallback_reason, dict) or not isinstance(
            fallback_retryable, dict
        ):
            continue

        if fallback_reason.get("const", "__missing__") is None:
            declared_type = fallback_retryable.get("type")
            if declared_type == "null":
                has_null_rule = True
            elif isinstance(declared_type, list) and "null" in declared_type:
                has_null_rule = True
            continue

        enum_values = fallback_reason.get("enum")
        if not isinstance(enum_values, list):
            continue

        codes = {value for value in enum_values if isinstance(value, str)}
        const_retryable = fallback_retryable.get("const")
        if const_retryable is True:
            retryable_true_codes.update(codes)
        elif const_retryable is False:
            retryable_false_codes.update(codes)

    return retryable_true_codes, retryable_false_codes, has_null_rule


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify fallback taxonomy and telemetry field sync between Python routing"
            " contract constants and routing metadata schema."
        )
    )
    parser.add_argument(
        "--schema-path",
        default=str(ROUTING_METADATA_SCHEMA),
        help="Path to assistant routing metadata schema file.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    schema_path = Path(args.schema_path)
    schema = _load_json(schema_path)

    errors: list[str] = []

    required_fields = _extract_required_fields(schema)
    expected_required_fields = set(ROUTING_DECISION_FIELDS)
    if required_fields != expected_required_fields:
        missing = sorted(expected_required_fields - required_fields)
        extra = sorted(required_fields - expected_required_fields)
        errors.append(
            f"required field mismatch: missing={missing or '[]'} extra={extra or '[]'}"
        )

    reason_codes, has_null_reason_code = _extract_reason_codes(schema)
    if not has_null_reason_code:
        errors.append("fallback_reason_code enum must include null")
    if reason_codes != FALLBACK_REASON_CODES:
        errors.append(
            "fallback_reason_code enum mismatch: "
            f"schema={sorted(reason_codes)} python={sorted(FALLBACK_REASON_CODES)}"
        )

    retryable_true_codes, retryable_false_codes, has_null_rule = (
        _extract_rule_partitions(schema)
    )
    if not has_null_rule:
        errors.append(
            "missing null-rule for fallback_reason_code=null -> fallback_retryable=null"
        )
    if retryable_true_codes != RETRYABLE_FALLBACK_CODES:
        errors.append(
            "retryable(true) partition mismatch: "
            f"schema={sorted(retryable_true_codes)} python={sorted(RETRYABLE_FALLBACK_CODES)}"
        )

    expected_non_retryable_codes = FALLBACK_REASON_CODES - RETRYABLE_FALLBACK_CODES
    if retryable_false_codes != expected_non_retryable_codes:
        errors.append(
            "retryable(false) partition mismatch: "
            f"schema={sorted(retryable_false_codes)} python={sorted(expected_non_retryable_codes)}"
        )

    overlap = retryable_true_codes & retryable_false_codes
    if overlap:
        errors.append(f"retryable partition overlap detected: {sorted(overlap)}")

    covered_codes = retryable_true_codes | retryable_false_codes
    if covered_codes != FALLBACK_REASON_CODES:
        errors.append(
            "retryable partition coverage mismatch: "
            f"schema={sorted(covered_codes)} python={sorted(FALLBACK_REASON_CODES)}"
        )

    if errors:
        print("routing taxonomy sync drift detected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("routing taxonomy is in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

BOOLEAN_FIELDS = (
    "six_block",
    "success_flow",
    "expected_failure_branch",
    "artifact_present",
    "live_probe",
    "live_chain_proof",
)

BASE_REQUIRED_FIELDS = (
    "six_block",
    "success_flow",
    "expected_failure_branch",
    "artifact_present",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        repos = payload.get("repos")
        if isinstance(repos, list):
            return [record for record in repos if isinstance(record, dict)]
        if "repo" in payload:
            return [payload]
        return []
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    return []


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "pass"}:
            return True
        if lowered in {"false", "0", "no", "n", "fail"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return None


def _default_entry(repo: str) -> dict[str, Any]:
    entry = {
        "repo": repo,
        "gate_verdict": "FAIL",
        "blocking_reasons": [],
    }
    for field in BOOLEAN_FIELDS:
        entry[field] = False
    return entry


def _build_blocking_reasons(entry: dict[str, Any]) -> list[str]:
    reasons: list[str] = []

    if not entry.get("six_block", False):
        reasons.append("Missing required 6-block return format.")
    if not entry.get("success_flow", False):
        reasons.append("Missing success flow evidence for research-manager operations.")
    if not entry.get("expected_failure_branch", False):
        reasons.append("Missing deterministic expected-failure branch evidence.")
    if not entry.get("artifact_present", False):
        reasons.append("Missing required CP6 artifact in repo-local docs/research path.")

    base_ready = all(entry.get(field, False) for field in BASE_REQUIRED_FIELDS)
    if base_ready and not entry.get("live_probe", False):
        reasons.append("Live Merlin capability probe has not passed yet.")
    if base_ready and not entry.get("live_chain_proof", False):
        reasons.append("Live create->signal->brief proof is missing.")

    return reasons


def _compute_verdict(entry: dict[str, Any]) -> str:
    all_base = all(entry.get(field, False) for field in BASE_REQUIRED_FIELDS)
    live_probe = bool(entry.get("live_probe", False))
    live_chain = bool(entry.get("live_chain_proof", False))

    if all_base and live_probe and live_chain:
        return "PASS"
    if all_base:
        return "CONDITIONAL_PASS"
    return "FAIL"


def _merge_records(
    matrix_payload: dict[str, Any],
    intake_records: list[dict[str, Any]],
    source_name: str,
) -> None:
    repos = matrix_payload.setdefault("repos", [])
    repo_map: dict[str, dict[str, Any]] = {}

    for entry in repos:
        repo_name = str(entry.get("repo", "")).strip()
        if not repo_name:
            continue
        repo_map[repo_name.upper()] = entry

    for record in intake_records:
        repo_raw = record.get("repo")
        if not isinstance(repo_raw, str) or not repo_raw.strip():
            continue

        repo_key = repo_raw.strip().upper()
        target = repo_map.get(repo_key)
        if target is None:
            target = _default_entry(repo_raw.strip())
            repos.append(target)
            repo_map[repo_key] = target

        for field in BOOLEAN_FIELDS:
            if field not in record:
                continue
            parsed = _bool_value(record[field])
            if parsed is not None:
                target[field] = parsed

        retry_packet = record.get("retry_packet")
        if isinstance(retry_packet, str) and retry_packet.strip():
            target["retry_packet"] = retry_packet.strip()

        notes = record.get("notes")
        if isinstance(notes, list):
            normalized_notes = [str(note).strip() for note in notes if str(note).strip()]
            if normalized_notes:
                target["intake_notes"] = normalized_notes

        target["last_update_source"] = source_name
        target["gate_verdict"] = _compute_verdict(target)
        target["blocking_reasons"] = _build_blocking_reasons(target)


def _recompute_summary(matrix_payload: dict[str, Any]) -> None:
    summary = {
        "pass": 0,
        "conditional_pass": 0,
        "fail": 0,
        "total": 0,
    }

    for entry in matrix_payload.get("repos", []):
        verdict = str(entry.get("gate_verdict", "FAIL")).upper()
        summary["total"] += 1

        if verdict == "PASS":
            summary["pass"] += 1
        elif verdict == "CONDITIONAL_PASS":
            summary["conditional_pass"] += 1
        else:
            summary["fail"] += 1

    matrix_payload["summary"] = summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge CP6 intake updates into a gate matrix and recompute verdicts."
    )
    parser.add_argument(
        "--matrix",
        required=True,
        help="Path to existing CP6 gate matrix JSON.",
    )
    parser.add_argument(
        "--intake",
        action="append",
        required=True,
        help=(
            "Path to intake JSON payload. May be specified multiple times. "
            "Each file can contain {'repos': [...]}, a list, or a single repo record."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path. Defaults to overwriting --matrix.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    matrix_path = Path(args.matrix)
    output_path = Path(args.out) if args.out else matrix_path

    if not matrix_path.exists():
        print(f"matrix file missing: {matrix_path}")
        return 1

    try:
        matrix_payload = _load_json(matrix_path)
    except json.JSONDecodeError as exc:
        print(f"failed to parse matrix json: {matrix_path}: {exc}")
        return 1

    if not isinstance(matrix_payload, dict):
        print("matrix json must be an object")
        return 1

    for intake_raw in args.intake:
        intake_path = Path(intake_raw)
        if not intake_path.exists():
            print(f"intake file missing: {intake_path}")
            return 1

        try:
            intake_payload = _load_json(intake_path)
        except json.JSONDecodeError as exc:
            print(f"failed to parse intake json: {intake_path}: {exc}")
            return 1

        records = _extract_records(intake_payload)
        if not records:
            print(f"intake file has no repo records: {intake_path}")
            return 1

        _merge_records(matrix_payload, records, str(intake_path))

    matrix_payload["generated_on"] = date.today().isoformat()
    _recompute_summary(matrix_payload)

    output_path.write_text(
        json.dumps(matrix_payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    summary = matrix_payload.get("summary", {})
    print(
        "updated gate matrix: "
        f"pass={summary.get('pass', 0)} "
        f"conditional_pass={summary.get('conditional_pass', 0)} "
        f"fail={summary.get('fail', 0)} "
        f"total={summary.get('total', 0)} "
        f"output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

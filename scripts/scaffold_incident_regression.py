#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "incident"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate incident-to-regression scaffold files (fixture + pytest template) "
            "for follow-up deterministic regression coverage."
        )
    )
    parser.add_argument("--incident-id", required=True, help="Incident identifier.")
    parser.add_argument("--operation-name", required=True, help="Impacted operation name.")
    parser.add_argument("--error-code", required=True, help="Primary observed error code.")
    parser.add_argument("--summary", default="", help="Short incident summary.")
    parser.add_argument(
        "--fixture-dir",
        default=str(ROOT_DIR / "tests" / "fixtures" / "incidents"),
        help="Directory for scaffold JSON fixture output.",
    )
    parser.add_argument(
        "--tests-dir",
        default=str(ROOT_DIR / "tests"),
        help="Directory for scaffold pytest file output.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing scaffold files if they already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned output paths without writing files.",
    )
    return parser


def _build_fixture_payload(
    *,
    incident_id: str,
    operation_name: str,
    error_code: str,
    summary: str,
    fixture_filename: str,
) -> dict[str, object]:
    return {
        "schema_name": "AAS.IncidentRegressionScaffold",
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "incident": {
            "incident_id": incident_id,
            "summary": summary,
            "operation_name": operation_name,
            "primary_error_code": error_code,
        },
        "regression_plan": {
            "request_fixture_ref": f"scaffold:tests/fixtures/contracts/{operation_name}.request.json",
            "expected_response_ref": f"scaffold:tests/fixtures/contracts/{operation_name}.expected_response.json",
            "expected_error_code": error_code,
            "notes": [
                "Replace scaffold fixture refs with concrete repro payloads.",
                "Remove pytest skip marker once assertions are implemented.",
            ],
        },
        "artifact_refs": {
            "scaffold_fixture": fixture_filename,
        },
    }


def _build_test_template(*, slug: str, fixture_filename: str, incident_id: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import json\n"
        "from pathlib import Path\n\n"
        "import pytest\n\n"
        f'FIXTURE_PATH = Path(__file__).parent / "fixtures" / "incidents" / "{fixture_filename}"\n\n'
        f'@pytest.mark.skip(reason="Scaffold placeholder for incident {incident_id}; add concrete assertions before enabling.")\n'
        f"def test_incident_regression_{slug}():\n"
        '    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))\n'
        f'    assert payload["incident"]["incident_id"] == "{incident_id}"\n'
    )


def _write_file(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = _build_parser().parse_args()
    incident_id = args.incident_id.strip()
    operation_name = args.operation_name.strip()
    error_code = args.error_code.strip()
    summary = args.summary.strip()

    if not incident_id:
        raise SystemExit("incident-id must be non-empty")
    if not operation_name:
        raise SystemExit("operation-name must be non-empty")
    if not error_code:
        raise SystemExit("error-code must be non-empty")

    slug = _slugify(incident_id)
    fixture_filename = f"{slug}.incident_regression.scaffold.json"
    fixture_path = Path(args.fixture_dir) / fixture_filename
    test_path = Path(args.tests_dir) / f"test_incident_regression_{slug}.py"

    if args.dry_run:
        print(f"[dry-run] fixture_path={fixture_path}")
        print(f"[dry-run] test_path={test_path}")
        return 0

    fixture_payload = _build_fixture_payload(
        incident_id=incident_id,
        operation_name=operation_name,
        error_code=error_code,
        summary=summary,
        fixture_filename=fixture_filename,
    )
    fixture_content = json.dumps(fixture_payload, indent=2) + "\n"
    test_content = _build_test_template(
        slug=slug,
        fixture_filename=fixture_filename,
        incident_id=incident_id,
    )

    try:
        _write_file(fixture_path, fixture_content, force=bool(args.force))
        _write_file(test_path, test_content, force=bool(args.force))
    except FileExistsError as exc:
        print(str(exc))
        return 1

    print(f"Created incident scaffold fixture: {fixture_path}")
    print(f"Created incident scaffold test: {test_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

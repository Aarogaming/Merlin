#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures" / "contracts"
DEFAULT_OUTPUT_PATH = (
    ROOT_DIR / "frontend" / "src" / "services" / "operationContracts.generated.ts"
)


def _collect_operation_fixtures(fixtures_dir: Path) -> dict[str, dict[str, str]]:
    contracts: dict[str, dict[str, str]] = {}
    expected_operations: set[str] = set()

    for path in sorted(fixtures_dir.glob("*.expected_response.json")):
        operation = path.name[: -len(".expected_response.json")]
        expected_operations.add(operation)
        contracts.setdefault(operation, {})["responseFixture"] = str(
            path.relative_to(ROOT_DIR).as_posix()
        )

    for path in sorted(fixtures_dir.glob("*.json")):
        name = path.name
        if name.endswith(".request.json"):
            full_base = name[: -len(".json")]
            stripped_base = name[: -len(".request.json")]
            if full_base in expected_operations:
                operation = full_base
            elif stripped_base in expected_operations:
                operation = stripped_base
            else:
                operation = stripped_base
            contracts.setdefault(operation, {})["requestFixture"] = str(
                path.relative_to(ROOT_DIR).as_posix()
            )
        elif (
            name.endswith(".json")
            and not name.endswith(".expected_response.json")
            and not name.endswith(".cases.json")
            and not name.endswith(".contract.json")
        ):
            operation = name[: -len(".json")]
            if operation in expected_operations:
                contracts.setdefault(operation, {})["requestFixture"] = str(
                    path.relative_to(ROOT_DIR).as_posix()
                )
    return contracts


def _render_ts(contracts: dict[str, dict[str, str]]) -> str:
    operations = sorted(contracts.keys())
    lines = [
        "/*",
        " * AUTO-GENERATED FILE - DO NOT EDIT.",
        " * Source: tests/fixtures/contracts/*.request.json + *.expected_response.json",
        " * Generator: scripts/generate_frontend_operation_contracts.py",
        " */",
        "",
        "export const OPERATION_NAMES = [",
    ]
    for operation in operations:
        lines.append(f"  '{operation}',")
    lines.extend(
        [
            "] as const;",
            "",
            "export type OperationName = (typeof OPERATION_NAMES)[number];",
            "",
            "export interface OperationContractFixture {",
            "  requestFixture?: string;",
            "  responseFixture?: string;",
            "}",
            "",
            "export const OPERATION_CONTRACT_FIXTURES: Record<OperationName, OperationContractFixture> = {",
        ]
    )
    for operation in operations:
        fixture = contracts[operation]
        lines.extend(
            [
                f"  '{operation}': {{",
                (
                    f"    requestFixture: '{fixture['requestFixture']}',"
                    if "requestFixture" in fixture
                    else "    requestFixture: undefined,"
                ),
                (
                    f"    responseFixture: '{fixture['responseFixture']}',"
                    if "responseFixture" in fixture
                    else "    responseFixture: undefined,"
                ),
                "  },",
            ]
        )
    lines.extend(
        [
            "};",
            "",
            "export function isKnownOperationName(name: string): name is OperationName {",
            "  return (OPERATION_NAMES as readonly string[]).includes(name);",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate typed frontend operation contract mapping from fixture files."
    )
    parser.add_argument(
        "--fixtures-dir",
        default=str(DEFAULT_FIXTURES_DIR),
        help="Path to contracts fixture directory.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Generated TypeScript output file path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if generated output differs from existing file.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    fixtures_dir = Path(args.fixtures_dir)
    output_path = Path(args.output)

    contracts = _collect_operation_fixtures(fixtures_dir)
    rendered = _render_ts(contracts)

    if args.check:
        if not output_path.exists():
            print(f"missing generated file: {output_path}")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != rendered:
            print(f"generated contracts are out of date: {output_path}")
            return 1
        print(f"generated contracts are up to date: {output_path}")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"generated frontend operation contracts: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
MATURITY_TIERS: tuple[str, ...] = ("M0", "M1", "M2", "M3", "M4")


def _normalize_tier(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in MATURITY_TIERS:
        return normalized
    return "M0"


def _next_tier(current_tier: str) -> str:
    index = MATURITY_TIERS.index(current_tier)
    if index >= len(MATURITY_TIERS) - 1:
        return current_tier
    return MATURITY_TIERS[index + 1]


def _previous_tier(current_tier: str) -> str:
    index = MATURITY_TIERS.index(current_tier)
    if index <= 0:
        return current_tier
    return MATURITY_TIERS[index - 1]


def _load_json_report(path_value: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not path_value:
        return None, None

    report_path = Path(path_value)
    if not report_path.is_file():
        return None, f"report path does not exist: {report_path}"

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"report is not valid JSON: {report_path} ({exc})"
    return payload, None


def _release_checklist_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "unknown"
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return "unknown"
    ok = summary.get("ok")
    if isinstance(ok, bool):
        return "pass" if ok else "fail"
    return "unknown"


def _smoke_evidence_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "unknown"
    status = payload.get("status")
    if not isinstance(status, str):
        return "unknown"
    normalized = status.strip().lower()
    if normalized == "pass":
        return "pass"
    if normalized == "fail":
        return "fail"
    return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Merlin maturity promotion/demotion readiness and produce a "
            "JSON report artifact."
        )
    )
    parser.add_argument(
        "--current-tier",
        default=os.environ.get("MERLIN_MATURITY_TIER", "M0"),
        help="Current maturity tier (M0-M4).",
    )
    parser.add_argument(
        "--policy-version",
        default=os.environ.get("MERLIN_MATURITY_POLICY_VERSION", "mdmm-2026-02-22"),
        help="Policy version to stamp in the evaluator report.",
    )
    parser.add_argument(
        "--contract-suite-status",
        choices=("pass", "fail", "unknown"),
        default="unknown",
        help="Contract/operation suite status used for promotion and demotion decisions.",
    )
    parser.add_argument(
        "--release-checklist-report",
        default=None,
        help="Optional JSON report from scripts/run_release_checklist.py.",
    )
    parser.add_argument(
        "--smoke-evidence-report",
        default=None,
        help="Optional CP4A smoke-evidence JSON report.",
    )
    parser.add_argument(
        "--regression-failures",
        type=int,
        default=0,
        help="Count of regression failures in the evaluation window.",
    )
    parser.add_argument(
        "--policy-violations",
        type=int,
        default=0,
        help="Count of policy violations in the evaluation window.",
    )
    parser.add_argument(
        "--error-budget-breached",
        action="store_true",
        help="Set when error budget breach occurred in the evaluation window.",
    )
    parser.add_argument(
        "--fallback-error-rate",
        type=float,
        default=0.0,
        help="Observed fallback/error rate for the evaluation window.",
    )
    parser.add_argument(
        "--max-fallback-error-rate",
        type=float,
        default=0.05,
        help="Maximum tolerated fallback/error rate for promotion readiness.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when evaluator recommends demotion.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional output path for evaluator JSON report.",
    )
    return parser


def _evaluate_report(args: argparse.Namespace) -> dict[str, Any]:
    current_tier = _normalize_tier(args.current_tier)
    fallback_error_rate = max(0.0, float(args.fallback_error_rate))
    max_fallback_error_rate = max(0.0, float(args.max_fallback_error_rate))
    regression_failures = max(0, int(args.regression_failures))
    policy_violations = max(0, int(args.policy_violations))

    release_payload, release_error = _load_json_report(args.release_checklist_report)
    smoke_payload, smoke_error = _load_json_report(args.smoke_evidence_report)
    release_status = _release_checklist_status(release_payload)
    smoke_status = _smoke_evidence_status(smoke_payload)
    contract_status = str(args.contract_suite_status).strip().lower()
    fallback_exceeded = fallback_error_rate > max_fallback_error_rate
    error_budget_breached = bool(args.error_budget_breached)

    critical_failures: list[str] = []
    if contract_status == "fail":
        critical_failures.append("contract suite status is fail")
    if release_status == "fail":
        critical_failures.append("release checklist report status is fail")
    if smoke_status == "fail":
        critical_failures.append("smoke evidence report status is fail")
    if regression_failures > 0:
        critical_failures.append(f"regression failures detected ({regression_failures})")
    if policy_violations > 0:
        critical_failures.append(f"policy violations detected ({policy_violations})")
    if error_budget_breached:
        critical_failures.append("error budget breached")
    if fallback_exceeded:
        critical_failures.append(
            f"fallback_error_rate {fallback_error_rate:.4f} exceeds {max_fallback_error_rate:.4f}"
        )

    missing_promotion_gates: list[str] = []
    if contract_status != "pass":
        missing_promotion_gates.append("contract suite status must be pass")
    if release_status != "pass":
        missing_promotion_gates.append("release checklist report status must be pass")
    if smoke_status != "pass":
        missing_promotion_gates.append("smoke evidence report status must be pass")
    if regression_failures != 0:
        missing_promotion_gates.append("regression_failures must be 0")
    if policy_violations != 0:
        missing_promotion_gates.append("policy_violations must be 0")
    if error_budget_breached:
        missing_promotion_gates.append("error_budget_breached must be false")
    if fallback_exceeded:
        missing_promotion_gates.append("fallback_error_rate must be <= max_fallback_error_rate")
    if release_error:
        missing_promotion_gates.append(release_error)
    if smoke_error:
        missing_promotion_gates.append(smoke_error)

    demotion_required = len(critical_failures) > 0
    promotion_ready = not demotion_required and len(missing_promotion_gates) == 0

    if demotion_required and current_tier != "M0":
        recommended_action = "demote"
        recommended_tier = _previous_tier(current_tier)
        rationale = list(critical_failures)
    elif promotion_ready and current_tier != "M4":
        recommended_action = "promote"
        recommended_tier = _next_tier(current_tier)
        rationale = ["all promotion gates passed"]
    else:
        recommended_action = "hold"
        recommended_tier = current_tier
        if critical_failures:
            rationale = list(critical_failures)
        elif missing_promotion_gates:
            rationale = list(missing_promotion_gates)
        else:
            rationale = ["no tier change required"]

    return {
        "schema_name": "AAS.MaturityPromotionDemotionReport",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": str(args.policy_version or "").strip() or "mdmm-2026-02-22",
        "current_tier": current_tier,
        "recommended_action": recommended_action,
        "recommended_tier": recommended_tier,
        "summary": {
            "promotion_ready": promotion_ready,
            "demotion_required": demotion_required,
            "critical_failure_count": len(critical_failures),
            "missing_promotion_gate_count": len(missing_promotion_gates),
        },
        "evidence": {
            "contract_suite_status": contract_status,
            "release_checklist_status": release_status,
            "smoke_evidence_status": smoke_status,
            "regression_failures": regression_failures,
            "policy_violations": policy_violations,
            "error_budget_breached": error_budget_breached,
            "fallback_error_rate": round(fallback_error_rate, 6),
            "release_checklist_report": args.release_checklist_report,
            "smoke_evidence_report": args.smoke_evidence_report,
            "release_checklist_report_error": release_error,
            "smoke_evidence_report_error": smoke_error,
        },
        "thresholds": {
            "max_fallback_error_rate": max_fallback_error_rate,
            "max_regression_failures": 0,
            "max_policy_violations": 0,
        },
        "rationale": rationale,
    }


def main() -> int:
    args = _build_parser().parse_args()
    report = _evaluate_report(args)

    output_path = (
        Path(args.output_json)
        if args.output_json
        else (
            ROOT_DIR
            / "artifacts"
            / "release"
            / f"maturity_evaluator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Saved maturity evaluator report: {output_path}")
    print(f"recommended_action: {report['recommended_action']}")
    print(f"recommended_tier: {report['recommended_tier']}")

    if args.strict and report["recommended_action"] == "demote":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

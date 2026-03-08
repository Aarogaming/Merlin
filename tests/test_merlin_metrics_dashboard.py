from __future__ import annotations

import json
from pathlib import Path

from merlin_metrics_dashboard import MetricsDashboard


class _AdaptiveStub:
    strategy = "auto"
    learning_mode = True

    @staticmethod
    def get_status():
        return {
            "metrics": {
                "m1": {
                    "total_requests": 5,
                    "success_rate": 0.8,
                    "avg_latency": 1.2,
                    "avg_rating": 4.0,
                }
            },
            "routing_metrics": {
                "throughput_rpm": 7.0,
                "usage_economics": {
                    "selected_avg_total_tokens": 142.0,
                    "shadow_dms_minus_control_avg_total_tokens": 19.0,
                },
            },
        }


class _ParallelStub:
    @staticmethod
    def get_status():
        return {
            "routing_metrics": {
                "usage_economics": {
                    "selected_avg_total_tokens": 118.0,
                    "by_ab_variant": {"dms": {"avg_total_tokens": 166.0}},
                }
            }
        }


class _StreamingStub:
    @staticmethod
    def get_status():
        return {
            "routing_metrics": {
                "stream_latency": {
                    "avg_ttft_seconds": 0.12,
                    "avg_completion_seconds": 1.8,
                },
                "usage_economics": {
                    "selected_avg_total_tokens": 133.0,
                    "by_ab_variant": {"dms": {"avg_total_tokens": 171.0}},
                },
            }
        }


class _CacheStub:
    @staticmethod
    def get_metrics():
        return {
            "backend": "memory",
            "namespaces": {
                "alpha": {
                    "hits": 3,
                    "misses": 1,
                    "requests": 4,
                    "hit_rate": 0.75,
                    "sets": 4,
                    "deletes": 1,
                    "evictions": 1,
                }
            },
            "overall": {
                "hits": 3,
                "misses": 1,
                "requests": 4,
                "hit_rate": 0.75,
                "sets": 4,
                "deletes": 1,
                "evictions": 1,
            },
        }


def test_dashboard_status_includes_streaming_latency_summary(monkeypatch):
    monkeypatch.setattr("merlin_metrics_dashboard.adaptive_llm_backend", _AdaptiveStub())
    monkeypatch.setattr("merlin_metrics_dashboard.parallel_llm_backend", _ParallelStub())
    monkeypatch.setattr(
        "merlin_metrics_dashboard.streaming_llm_backend", _StreamingStub()
    )
    monkeypatch.setattr("merlin_metrics_dashboard.merlin_cache", _CacheStub())
    dashboard = MetricsDashboard()
    dashboard.history = []

    status = dashboard.get_dashboard_status()
    summary = status["summary"]

    assert summary["routing_throughput_rpm"] == 7.0
    assert summary["stream_avg_ttft_seconds"] == 0.12
    assert summary["stream_avg_completion_seconds"] == 1.8
    assert summary["adaptive_selected_avg_total_tokens"] == 142.0
    assert summary["adaptive_shadow_delta_avg_total_tokens"] == 19.0
    assert summary["parallel_selected_avg_total_tokens"] == 118.0
    assert summary["parallel_dms_avg_total_tokens"] == 166.0
    assert summary["stream_selected_avg_total_tokens"] == 133.0
    assert summary["stream_dms_avg_total_tokens"] == 171.0
    assert summary["cache_hit_rate"] == 0.75
    assert summary["cache_evictions"] == 1
    assert summary["cache_namespace_count"] == 1
    assert summary["maturity_tier"] == "M0"
    assert summary["maturity_readiness_status"] in {"unknown", "hold"}
    assert summary["maturity_regression_status"] in {"unknown", "stable"}
    assert status["cache"]["backend"] == "memory"


def test_dashboard_status_includes_maturity_status_card(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("merlin_metrics_dashboard.adaptive_llm_backend", _AdaptiveStub())
    monkeypatch.setattr("merlin_metrics_dashboard.parallel_llm_backend", _ParallelStub())
    monkeypatch.setattr(
        "merlin_metrics_dashboard.streaming_llm_backend", _StreamingStub()
    )
    monkeypatch.setattr("merlin_metrics_dashboard.merlin_cache", _CacheStub())
    monkeypatch.setattr("merlin_metrics_dashboard.settings.MERLIN_MATURITY_TIER", "M2")
    monkeypatch.setattr(
        "merlin_metrics_dashboard.settings.MERLIN_MATURITY_POLICY_VERSION",
        "mdmm-test-policy-v2",
    )

    report_path = tmp_path / "maturity_evaluator_20260222_080000.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "promotion_ready": False,
                    "demotion_required": True,
                    "critical_failure_count": 2,
                    "missing_promotion_gate_count": 1,
                },
                "recommended_action": "demote",
                "recommended_tier": "M1",
                "generated_at": "2026-02-22T08:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    dashboard = MetricsDashboard()
    dashboard.history = []
    dashboard.maturity_reports_dir = tmp_path

    status = dashboard.get_dashboard_status()
    card = status["maturity_status_card"]
    summary = status["summary"]

    assert card["tier"] == "M2"
    assert card["policy_version"] == "mdmm-test-policy-v2"
    assert card["readiness_status"] == "demotion_required"
    assert card["regression_status"] == "regressions_detected"
    assert card["recommended_action"] == "demote"
    assert card["recommended_tier"] == "M1"
    assert card["critical_failure_count"] == 2
    assert card["missing_promotion_gate_count"] == 1
    assert card["report_path"] == str(report_path)

    assert summary["maturity_tier"] == "M2"
    assert summary["maturity_readiness_status"] == "demotion_required"
    assert summary["maturity_regression_status"] == "regressions_detected"

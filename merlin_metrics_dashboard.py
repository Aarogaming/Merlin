# LLM Metrics Dashboard - Real-time Model Performance Visualization
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from merlin_logger import merlin_logger
from merlin_adaptive_llm import adaptive_llm_backend
from merlin_parallel_llm import parallel_llm_backend
from merlin_cache import merlin_cache
from merlin_streaming_llm import streaming_llm_backend
import merlin_settings as settings


class MetricsDashboard:
    def __init__(self):
        self.metrics_file = "artifacts/adaptive_metrics.json"
        self.maturity_reports_dir = Path("artifacts") / "release"
        self.active_connections: List[WebSocket] = []
        self.history = []
        self.max_history = 1000
        self.load_history()

    def load_history(self):
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                    for model_name, metrics in data.items():
                        self.history.append(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "model": model_name,
                                "total_requests": metrics.get("total_requests", 0),
                                "success_rate": metrics.get("success_rate", 0),
                                "avg_latency": metrics.get("avg_latency", 0),
                                "avg_rating": metrics.get("avg_rating", 0),
                            }
                        )
                merlin_logger.info(f"Loaded {len(self.history)} historical metrics")
            except Exception as e:
                merlin_logger.error(f"Failed to load history: {e}")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        merlin_logger.info(
            f"Dashboard client connected. Total: {len(self.active_connections)}"
        )
        await self.send_initial_status(websocket)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            merlin_logger.info(
                f"Dashboard client disconnected. Total: {len(self.active_connections)}"
            )

    async def send_initial_status(self, websocket: WebSocket):
        status = self.get_dashboard_status()
        await websocket.send_json(status)

    def get_dashboard_status(self) -> Dict:
        adaptive_status = adaptive_llm_backend.get_status()
        metrics = adaptive_status.get("metrics", {})
        parallel_status = parallel_llm_backend.get_status()
        streaming_status = streaming_llm_backend.get_status()
        cache_metrics = merlin_cache.get_metrics()
        maturity_status_card = self.get_maturity_status_card()

        model_performance = {}
        for model_name, model_metrics in metrics.items():
            model_performance[model_name] = {
                "total_requests": model_metrics.get("total_requests", 0),
                "success_rate": model_metrics.get("success_rate", 0),
                "avg_latency": model_metrics.get("avg_latency", 0),
                "avg_rating": model_metrics.get("avg_rating", 0),
                "recent_history": self.get_recent_history(model_name, 20),
            }

        return {
            "type": "status",
            "timestamp": datetime.now().isoformat(),
            "strategy": adaptive_llm_backend.strategy,
            "learning_mode": adaptive_llm_backend.learning_mode,
            "models": model_performance,
            "summary": self.get_summary_stats(
                metrics,
                streaming_status=streaming_status,
                parallel_status=parallel_status,
                adaptive_status=adaptive_status,
                cache_metrics=cache_metrics,
                maturity_status_card=maturity_status_card,
            ),
            "maturity_status_card": maturity_status_card,
            "cache": cache_metrics,
        }

    def get_recent_history(self, model_name: str, limit: int) -> List[Dict]:
        return [
            entry
            for entry in self.history[-self.max_history :]
            if entry.get("model") == model_name
        ][:limit]

    def get_summary_stats(
        self,
        metrics: Dict,
        *,
        streaming_status: Dict,
        parallel_status: Dict,
        adaptive_status: Dict,
        cache_metrics: Dict,
        maturity_status_card: Dict,
    ) -> Dict:
        total_requests = sum(m.get("total_requests", 0) for m in metrics.values())
        total_success = sum(
            m.get("success_rate", 0) * m.get("total_requests", 0)
            for m in metrics.values()
        )
        overall_success = total_success / max(1, total_requests)

        avg_latency = sum(
            m.get("avg_latency", 0)
            for m in metrics.values()
            if m.get("avg_latency") != float("inf")
        )
        avg_latency = avg_latency / max(
            1,
            len([m for m in metrics.values() if m.get("avg_latency") != float("inf")]),
        )

        best_model = None
        best_score = -1.0
        for model_name, model_metrics in metrics.items():
            score = (
                model_metrics.get("success_rate", 0) * 0.5
                + (10.0 / max(1.0, model_metrics.get("avg_latency", 100))) * 0.3
                + model_metrics.get("avg_rating", 0) / 5.0 * 0.2
            )
            if score > best_score:
                best_score = score
                best_model = model_name

        adaptive_routing = adaptive_status.get("routing_metrics", {})
        parallel_routing = parallel_status.get("routing_metrics", {})
        streaming_routing = streaming_status.get("routing_metrics", {})
        streaming_latency = streaming_routing.get("stream_latency", {})
        adaptive_usage = adaptive_routing.get("usage_economics", {})
        parallel_usage = parallel_routing.get("usage_economics", {})
        streaming_usage = streaming_routing.get("usage_economics", {})
        if not isinstance(adaptive_usage, dict):
            adaptive_usage = {}
        if not isinstance(parallel_usage, dict):
            parallel_usage = {}
        if not isinstance(streaming_usage, dict):
            streaming_usage = {}
        parallel_usage_by_variant = parallel_usage.get("by_ab_variant", {})
        if not isinstance(parallel_usage_by_variant, dict):
            parallel_usage_by_variant = {}
        parallel_dms_usage = parallel_usage_by_variant.get("dms", {})
        if not isinstance(parallel_dms_usage, dict):
            parallel_dms_usage = {}
        streaming_usage_by_variant = streaming_usage.get("by_ab_variant", {})
        if not isinstance(streaming_usage_by_variant, dict):
            streaming_usage_by_variant = {}
        streaming_dms_usage = streaming_usage_by_variant.get("dms", {})
        if not isinstance(streaming_dms_usage, dict):
            streaming_dms_usage = {}
        cache_overall = cache_metrics.get("overall", {})
        cache_namespaces = cache_metrics.get("namespaces", {})

        return {
            "total_requests": total_requests,
            "overall_success_rate": overall_success,
            "overall_avg_latency": avg_latency,
            "best_model": best_model,
            "model_count": len(metrics),
            "active_models": len(
                [m for m in metrics.values() if m.get("total_requests", 0) > 0]
            ),
            "routing_throughput_rpm": adaptive_routing.get("throughput_rpm", 0.0),
            "stream_avg_ttft_seconds": streaming_latency.get("avg_ttft_seconds", 0.0),
            "stream_avg_completion_seconds": streaming_latency.get(
                "avg_completion_seconds", 0.0
            ),
            "adaptive_selected_avg_total_tokens": adaptive_usage.get(
                "selected_avg_total_tokens", 0.0
            ),
            "adaptive_shadow_delta_avg_total_tokens": adaptive_usage.get(
                "shadow_dms_minus_control_avg_total_tokens", 0.0
            ),
            "parallel_selected_avg_total_tokens": parallel_usage.get(
                "selected_avg_total_tokens", 0.0
            ),
            "parallel_dms_avg_total_tokens": parallel_dms_usage.get(
                "avg_total_tokens", 0.0
            ),
            "stream_selected_avg_total_tokens": streaming_usage.get(
                "selected_avg_total_tokens", 0.0
            ),
            "stream_dms_avg_total_tokens": streaming_dms_usage.get(
                "avg_total_tokens", 0.0
            ),
            "cache_hit_rate": cache_overall.get("hit_rate", 0.0),
            "cache_evictions": cache_overall.get("evictions", 0),
            "cache_namespace_count": len(cache_namespaces),
            "maturity_tier": maturity_status_card.get("tier", "M0"),
            "maturity_readiness_status": maturity_status_card.get(
                "readiness_status", "unknown"
            ),
            "maturity_regression_status": maturity_status_card.get(
                "regression_status", "unknown"
            ),
        }

    def _safe_int(self, value, default: int = 0) -> int:
        if isinstance(value, bool):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _latest_maturity_report(self) -> tuple[dict | None, str | None]:
        report_dir = self.maturity_reports_dir
        if not report_dir.exists():
            return None, None

        candidates = sorted(
            report_dir.glob("maturity_evaluator_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload, str(candidate)
        return None, None

    def get_maturity_status_card(self) -> Dict:
        report, report_path = self._latest_maturity_report()
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        if not isinstance(summary, dict):
            summary = {}

        promotion_ready = bool(summary.get("promotion_ready", False))
        demotion_required = bool(summary.get("demotion_required", False))
        if demotion_required:
            readiness_status = "demotion_required"
        elif promotion_ready:
            readiness_status = "promotion_ready"
        elif report is None:
            readiness_status = "unknown"
        else:
            readiness_status = "hold"

        critical_failure_count = self._safe_int(summary.get("critical_failure_count"), 0)
        if critical_failure_count > 0:
            regression_status = "regressions_detected"
        elif report is None:
            regression_status = "unknown"
        else:
            regression_status = "stable"

        if isinstance(report, dict):
            recommended_action = str(report.get("recommended_action", "hold"))
            recommended_tier = str(
                report.get("recommended_tier", settings.MERLIN_MATURITY_TIER)
            )
            report_generated_at = report.get("generated_at")
            if not isinstance(report_generated_at, str):
                report_generated_at = None
        else:
            recommended_action = "hold"
            recommended_tier = settings.MERLIN_MATURITY_TIER
            report_generated_at = None

        return {
            "tier": settings.MERLIN_MATURITY_TIER,
            "policy_version": settings.MERLIN_MATURITY_POLICY_VERSION,
            "readiness_status": readiness_status,
            "regression_status": regression_status,
            "recommended_action": recommended_action,
            "recommended_tier": recommended_tier,
            "critical_failure_count": critical_failure_count,
            "missing_promotion_gate_count": self._safe_int(
                summary.get("missing_promotion_gate_count"), 0
            ),
            "report_generated_at": report_generated_at,
            "report_path": report_path,
        }

    async def broadcast_update(self):
        status = self.get_dashboard_status()
        for connection in self.active_connections:
            try:
                await connection.send_json(status)
            except Exception as e:
                merlin_logger.error(f"Failed to send dashboard update: {e}")

    def record_event(self, event_type: str, model_name: str, data: Dict = None):
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "model": model_name,
            "data": data or {},
        }
        self.history.append(event)

        if len(self.history) > self.max_history * 2:
            self.history = self.history[-self.max_history :]


metrics_dashboard = MetricsDashboard()


async def handle_dashboard_websocket(websocket: WebSocket):
    await metrics_dashboard.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "refresh":
                await metrics_dashboard.send_initial_status(websocket)
            elif data == "disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await metrics_dashboard.disconnect(websocket)

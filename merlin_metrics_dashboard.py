# LLM Metrics Dashboard - Real-time Model Performance Visualization
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from merlin_logger import merlin_logger
from merlin_adaptive_llm import adaptive_llm_backend


class MetricsDashboard:
    def __init__(self):
        self.metrics_file = "artifacts/adaptive_metrics.json"
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
        metrics = adaptive_llm_backend.get_status().get("metrics", {})

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
            "summary": self.get_summary_stats(metrics),
        }

    def get_recent_history(self, model_name: str, limit: int) -> List[Dict]:
        return [
            entry
            for entry in self.history[-self.max_history :]
            if entry.get("model") == model_name
        ][:limit]

    def get_summary_stats(self, metrics: Dict) -> Dict:
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

        return {
            "total_requests": total_requests,
            "overall_success_rate": overall_success,
            "overall_avg_latency": avg_latency,
            "best_model": best_model,
            "model_count": len(metrics),
            "active_models": len(
                [m for m in metrics.values() if m.get("total_requests", 0) > 0]
            ),
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

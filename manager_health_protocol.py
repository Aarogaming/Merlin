from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class LifecycleState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class HealthCheckResult:
    status: HealthStatus
    is_healthy: bool
    message: str
    checks: dict[str, bool] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LifecycleStateMixin:
    def __init__(self) -> None:
        self._lifecycle_state = LifecycleState.STOPPED.value
        self._lifecycle_events: list[dict[str, str | None]] = []

    @property
    def lifecycle_state(self) -> str:
        return self._lifecycle_state

    def is_running(self) -> bool:
        return self._lifecycle_state == LifecycleState.RUNNING.value

    def _transition_state(self, next_state: LifecycleState | str) -> None:
        old_state = self._lifecycle_state
        resolved_state = (
            next_state.value
            if isinstance(next_state, LifecycleState)
            else str(next_state)
        )
        self._lifecycle_state = resolved_state
        self._lifecycle_events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "old_state": old_state,
                "new_state": resolved_state,
            }
        )


class StatusPayloadBuilder:
    def __init__(self, service_name: str):
        self._payload: dict[str, Any] = {
            "service_name": service_name,
            "lifecycle_state": LifecycleState.STOPPED.value,
            "health_status": HealthStatus.DEGRADED.value,
            "metrics": {},
        }

    def with_lifecycle_state(
        self, state: LifecycleState | str
    ) -> "StatusPayloadBuilder":
        self._payload["lifecycle_state"] = (
            state.value if isinstance(state, LifecycleState) else str(state)
        )
        return self

    def with_health_status(self, status: HealthStatus | str) -> "StatusPayloadBuilder":
        self._payload["health_status"] = (
            status.value if isinstance(status, HealthStatus) else str(status)
        )
        return self

    def with_metrics(self, metrics: dict[str, Any]) -> "StatusPayloadBuilder":
        self._payload["metrics"] = dict(metrics or {})
        return self

    def build(self) -> dict[str, Any]:
        payload = dict(self._payload)
        payload["metrics"] = dict(self._payload.get("metrics", {}))
        return payload

import subprocess
import sys
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable

import requests

from merlin_logger import merlin_logger


@dataclass
class _CircuitState:
    state: str = "closed"
    consecutive_failures: int = 0
    opened_at_monotonic: float | None = None
    last_failure_reason: str | None = None


class EndpointCircuitBreaker:
    """Track dependency health and short-circuit unstable endpoints."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
        time_fn: Callable[[], float] | None = None,
    ):
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_timeout_seconds = max(0.01, float(recovery_timeout_seconds))
        self._time_fn = time_fn or time.monotonic
        self._lock = Lock()
        self._states: dict[str, _CircuitState] = {}

    def _state_for(self, endpoint: str) -> _CircuitState:
        state = self._states.get(endpoint)
        if state is None:
            state = _CircuitState()
            self._states[endpoint] = state
        return state

    def allow_request(self, endpoint: str) -> bool:
        """Return True when dependency calls should proceed."""
        now = self._time_fn()
        with self._lock:
            state = self._state_for(endpoint)
            if state.state != "open":
                return True
            opened_at = state.opened_at_monotonic if state.opened_at_monotonic else now
            if (now - opened_at) >= self.recovery_timeout_seconds:
                state.state = "half_open"
                return True
            return False

    def record_success(self, endpoint: str) -> None:
        with self._lock:
            state = self._state_for(endpoint)
            state.state = "closed"
            state.consecutive_failures = 0
            state.opened_at_monotonic = None
            state.last_failure_reason = None

    def record_failure(self, endpoint: str, reason: str | None = None) -> None:
        now = self._time_fn()
        with self._lock:
            state = self._state_for(endpoint)
            state.last_failure_reason = reason

            if state.state == "half_open":
                state.state = "open"
                state.consecutive_failures = self.failure_threshold
                state.opened_at_monotonic = now
                return

            state.consecutive_failures += 1
            if state.consecutive_failures >= self.failure_threshold:
                state.state = "open"
                state.opened_at_monotonic = now

    def clear(self, endpoint: str | None = None) -> None:
        with self._lock:
            if endpoint is None:
                self._states.clear()
                return
            self._states.pop(endpoint, None)

    def get_state(self, endpoint: str) -> dict[str, object]:
        with self._lock:
            state = self._state_for(endpoint)
            now = self._time_fn()
            opened_for_seconds = 0.0
            if state.opened_at_monotonic is not None:
                opened_for_seconds = max(0.0, now - state.opened_at_monotonic)
            return {
                "state": state.state,
                "consecutive_failures": state.consecutive_failures,
                "opened_for_seconds": round(opened_for_seconds, 3),
                "last_failure_reason": state.last_failure_reason,
            }

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            now = self._time_fn()
            rows: dict[str, dict[str, object]] = {}
            for endpoint, state in self._states.items():
                opened_for_seconds = 0.0
                if state.opened_at_monotonic is not None:
                    opened_for_seconds = max(0.0, now - state.opened_at_monotonic)
                rows[endpoint] = {
                    "state": state.state,
                    "consecutive_failures": state.consecutive_failures,
                    "opened_for_seconds": round(opened_for_seconds, 3),
                    "last_failure_reason": state.last_failure_reason,
                }
            return rows


class RestartBudget:
    """Track capped restart attempts per key."""

    def __init__(self, max_attempts: int = 2):
        self.max_attempts = max(0, int(max_attempts))
        self._lock = Lock()
        self._attempts: dict[str, int] = {}

    def attempts(self, key: str) -> int:
        with self._lock:
            return int(self._attempts.get(key, 0))

    def can_attempt(self, key: str) -> bool:
        with self._lock:
            return int(self._attempts.get(key, 0)) < self.max_attempts

    def record_attempt(self, key: str) -> int:
        with self._lock:
            next_attempt = int(self._attempts.get(key, 0)) + 1
            self._attempts[key] = next_attempt
            return next_attempt

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


class MerlinSelfHealing:
    def __init__(self, api_url="http://localhost:8000/health"):
        self.api_url = api_url
        self.check_interval = 30
        self.restart_count = 0

    def check_health(self) -> bool:
        try:
            response = requests.get(self.api_url, timeout=5)
            if response.status_code == 200:
                return True
            return False
        except Exception:
            return False

    def restart_service(self):
        merlin_logger.warning(
            "Self-Healing: API Server appears down. Attempting restart..."
        )
        try:
            # In a real scenario, we might use systemd or a process manager
            # Here we'll try to launch it via the unified launcher
            subprocess.Popen([sys.executable, "merlin_launcher.py"])
            self.restart_count += 1
            merlin_logger.info(
                f"Self-Healing: Restart attempt {self.restart_count} initiated."
            )
        except Exception as e:
            merlin_logger.error(f"Self-Healing: Restart failed: {e}")

    def run_forever(self):
        merlin_logger.info("Starting Merlin Self-Healing Service...")
        while True:
            if not self.check_health():
                self.restart_service()
            else:
                if self.restart_count > 0:
                    merlin_logger.info("Self-Healing: Service is back online.")
                    self.restart_count = 0
            time.sleep(self.check_interval)


if __name__ == "__main__":
    healer = MerlinSelfHealing()
    healer.run_forever()

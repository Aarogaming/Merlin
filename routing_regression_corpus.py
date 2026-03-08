from __future__ import annotations

from typing import Any

SIMPLE_LONG_PROMPT_QUERY = "A" * 220
UNCERTAIN_REASONING_QUERY = (
    "I am uncertain about the trade-off risk and assumptions. "
    "How should we plan this?"
)

UNCERTAINTY_ENABLED_SETTINGS: dict[str, Any] = {
    "DMS_UNCERTAINTY_ROUTING_ENABLED": True,
    "DMS_UNCERTAINTY_SCORE_THRESHOLD": 0.55,
}
UNCERTAINTY_DISABLED_SETTINGS: dict[str, Any] = {
    "DMS_UNCERTAINTY_ROUTING_ENABLED": False,
}


def with_uncertainty_enabled(settings: dict[str, Any]) -> dict[str, Any]:
    return {**settings, **UNCERTAINTY_ENABLED_SETTINGS}


def with_uncertainty_disabled(settings: dict[str, Any]) -> dict[str, Any]:
    return {**settings, **UNCERTAINTY_DISABLED_SETTINGS}

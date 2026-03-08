from __future__ import annotations

from typing import Any

from merlin_logger import merlin_logger
from merlin_research_manager import ResearchManager


class ResearchManagerPlugin:
    def __init__(self):
        self.name = "research_manager"
        self.description = (
            "Hypothesis-driven research manager with probability updates and foresight briefs."
        )
        self.version = "1.0.0"
        self.author = "Merlin"
        self.category = "orchestration"
        self.manager = ResearchManager()

    def get_info(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
        }

    def execute(self, action: str = "create", **kwargs: Any) -> dict[str, Any]:
        normalized = (action or "create").strip().lower()
        merlin_logger.info(f"ResearchManagerPlugin action={normalized}")

        try:
            if normalized == "create":
                objective = str(kwargs.get("objective", "")).strip()
                constraints = kwargs.get("constraints")
                horizon_days = int(kwargs.get("horizon_days", 14))
                session = self.manager.create_session(
                    objective=objective,
                    constraints=constraints if isinstance(constraints, list) else None,
                    horizon_days=horizon_days,
                )
                return {
                    "ok": True,
                    "action": "create",
                    "session": session,
                    "next_actions": self.manager.next_actions(session["session_id"]),
                }

            if normalized == "signal":
                session_id = str(kwargs.get("session_id", "")).strip()
                source = str(kwargs.get("source", "")).strip()
                claim = str(kwargs.get("claim", "")).strip()
                confidence = float(kwargs.get("confidence", 0.6))
                novelty = float(kwargs.get("novelty", 0.5))
                risk = float(kwargs.get("risk", 0.2))
                supports = kwargs.get("supports")
                contradicts = kwargs.get("contradicts")
                result = self.manager.add_signal(
                    session_id=session_id,
                    source=source,
                    claim=claim,
                    confidence=confidence,
                    novelty=novelty,
                    risk=risk,
                    supports=supports if isinstance(supports, list) else None,
                    contradicts=contradicts if isinstance(contradicts, list) else None,
                )
                return {"ok": True, "action": "signal", **result}

            if normalized == "brief":
                session_id = str(kwargs.get("session_id", "")).strip()
                brief = self.manager.get_brief(session_id)
                return {"ok": True, "action": "brief", "brief": brief}

            if normalized == "session":
                session_id = str(kwargs.get("session_id", "")).strip()
                session = self.manager.get_session(session_id)
                return {"ok": True, "action": "session", "session": session}

            if normalized == "list":
                limit = int(kwargs.get("limit", 20))
                return {
                    "ok": True,
                    "action": "list",
                    "sessions": self.manager.list_sessions(limit=limit),
                }

            return {
                "ok": False,
                "error": "unknown_action",
                "detail": "Supported actions: create, signal, brief, session, list",
            }
        except PermissionError as exc:
            return {"ok": False, "error": "read_only", "detail": str(exc)}
        except FileNotFoundError:
            return {"ok": False, "error": "session_not_found"}
        except ValueError as exc:
            return {"ok": False, "error": "validation_error", "detail": str(exc)}


def get_plugin() -> ResearchManagerPlugin:
    return ResearchManagerPlugin()

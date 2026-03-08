import os
from enum import Enum
from typing import Any


class ExecutionMode(Enum):
    SAFE = "safe"  # No destructive actions allowed
    RESTRICTED = (
        "restricted"  # Destructive actions require confirmation (if implemented)
    )
    LIVE = "live"  # All actions allowed


PLUGIN_PERMISSION_TIERS = {"read", "write", "network", "exec"}


class ExecutionPolicyManager:
    def __init__(self):
        self.mode = self._determine_mode()
        self.blocked_commands = [
            "rm -rf /",
            "format",
            "del /s /q C:\\",
        ]  # Example dangerous commands

    def _determine_mode(self) -> ExecutionMode:
        mode_str = os.environ.get("MERLIN_EXECUTION_MODE", "safe").lower()
        if mode_str == "live":
            return ExecutionMode.LIVE
        elif mode_str == "restricted":
            return ExecutionMode.RESTRICTED
        else:
            return ExecutionMode.SAFE

    def is_command_allowed(self, command: str) -> bool:
        if self.mode == ExecutionMode.LIVE:
            return True

        # Check against blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return False

        # In safe mode, we might want to block all "destructive" looking commands
        if self.mode == ExecutionMode.SAFE:
            destructive_keywords = ["rm ", "del ", "rd ", "format ", "mkfs "]
            if any(kw in command.lower() for kw in destructive_keywords):
                return False

        return True

    def is_file_action_allowed(self, action: str, path: str) -> bool:
        if self.mode == ExecutionMode.LIVE:
            return True

        if action == "delete":
            return self.mode != ExecutionMode.SAFE

        return True

    def allowed_plugin_permissions(self) -> set[str]:
        if self.mode == ExecutionMode.LIVE:
            return set(PLUGIN_PERMISSION_TIERS)
        if self.mode == ExecutionMode.RESTRICTED:
            return {"read", "write"}
        return {"read"}

    def is_plugin_permission_allowed(self, permission: str) -> bool:
        normalized = str(permission or "").strip().lower()
        if normalized not in PLUGIN_PERMISSION_TIERS:
            return False
        return normalized in self.allowed_plugin_permissions()

    def are_plugin_permissions_allowed(
        self, permissions: list[str] | tuple[str, ...] | set[str]
    ) -> tuple[bool, list[str]]:
        normalized_permissions: list[str] = []
        for permission in permissions:
            normalized = str(permission or "").strip().lower()
            if not normalized:
                continue
            if normalized in normalized_permissions:
                continue
            normalized_permissions.append(normalized)

        if not normalized_permissions:
            normalized_permissions = ["read"]

        denied = sorted(
            permission
            for permission in normalized_permissions
            if not self.is_plugin_permission_allowed(permission)
        )
        return not denied, denied


policy_manager = ExecutionPolicyManager()


HIGH_RISK_PROMPT_KEYWORDS = (
    "malware",
    "ransomware",
    "phishing",
    "credential stuffing",
    "steal password",
    "bypass authentication",
    "jailbreak",
    "exploit",
    "weapon",
    "self-harm",
    "suicide",
    "bomb",
)


VALID_MATURITY_TIERS: frozenset[str] = frozenset({"M0", "M1", "M2", "M3", "M4"})
DEFAULT_MENTOR_PASS_REQUIRED_TIERS: frozenset[str] = frozenset({"M1"})
HIGH_RISK_OPERATION_CLASSES: dict[str, frozenset[str]] = {
    "command_execution": frozenset(
        {
            "merlin.command.execute",
        }
    ),
    "tool_execution": frozenset(
        {
            "assistant.tools.execute",
            "merlin.plugins.execute",
        }
    ),
    "state_mutation": frozenset(
        {
            "merlin.context.update",
            "merlin.discovery.run",
            "merlin.discovery.queue.drain",
            "merlin.discovery.queue.pause",
            "merlin.discovery.queue.resume",
            "merlin.discovery.queue.purge_deadletter",
            "merlin.seed.control",
            "merlin.tasks.create",
            "merlin.user_manager.create",
            "merlin.genesis.manifest",
            "merlin.aas.create_task",
            "merlin.research.manager.session.create",
            "merlin.research.manager.session.signal.add",
            "merlin.llm.ab.create",
            "merlin.llm.ab.complete",
            "merlin.llm.ab.result",
            "merlin.llm.adaptive.feedback",
            "merlin.llm.adaptive.reset",
            "merlin.llm.cost.budget.set",
            "merlin.llm.cost.pricing.set",
            "merlin.llm.cost.thresholds.set",
            "merlin.llm.parallel.strategy",
            "merlin.llm.predictive.feedback",
            "merlin.llm.predictive.select",
            "merlin.voice.synthesize",
        }
    ),
}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "approved", "pass", "passed"}
    return False


def classify_high_risk_operation_classes(operation_name: str) -> list[str]:
    normalized_name = str(operation_name or "").strip()
    if not normalized_name:
        return []
    return sorted(
        class_name
        for class_name, operations in HIGH_RISK_OPERATION_CLASSES.items()
        if normalized_name in operations
    )


def mentor_pass_required_tiers() -> frozenset[str]:
    raw_value = os.environ.get("MERLIN_MENTOR_PASS_REQUIRED_TIERS")
    if raw_value is None:
        return DEFAULT_MENTOR_PASS_REQUIRED_TIERS

    normalized_tokens = [
        token.strip().upper() for token in raw_value.split(",") if token.strip()
    ]
    if not normalized_tokens:
        return frozenset()
    if "*" in normalized_tokens:
        return VALID_MATURITY_TIERS

    parsed = [token for token in normalized_tokens if token in VALID_MATURITY_TIERS]
    return frozenset(parsed)


def mentor_pass_approved(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    mentor_pass_value = metadata.get("mentor_pass")
    if isinstance(mentor_pass_value, dict):
        if _coerce_bool(mentor_pass_value.get("approved")):
            return True
        if _coerce_bool(mentor_pass_value.get("passed")):
            return True
        status = mentor_pass_value.get("status")
        return isinstance(status, str) and status.strip().lower() in {
            "approved",
            "pass",
            "passed",
            "granted",
        }
    return _coerce_bool(mentor_pass_value)


def evaluate_operation_mentor_pass(
    operation_name: str,
    metadata: Any,
    *,
    maturity_tier: str,
) -> dict[str, Any]:
    operation_classes = classify_high_risk_operation_classes(operation_name)
    active_tier = str(maturity_tier or "").strip().upper() or "M0"
    required_tiers = mentor_pass_required_tiers()
    required = bool(operation_classes) and active_tier in required_tiers
    approved = mentor_pass_approved(metadata)
    return {
        "required": required,
        "approved": approved,
        "blocked": required and not approved,
        "operation_classes": operation_classes,
        "maturity_tier": active_tier,
        "required_tiers": sorted(required_tiers),
    }


def analyze_prompt_safety(
    prompt: str, *, mode: ExecutionMode | None = None
) -> dict[str, Any]:
    prompt_text = str(prompt or "").lower()
    matched_keywords = sorted(
        keyword for keyword in HIGH_RISK_PROMPT_KEYWORDS if keyword in prompt_text
    )
    risk_level = "high" if matched_keywords else "low"
    active_mode = mode or policy_manager.mode
    blocked = active_mode == ExecutionMode.SAFE and risk_level == "high"
    return {
        "risk_level": risk_level,
        "matched_keywords": matched_keywords,
        "blocked": blocked,
        "mode": active_mode.value,
    }

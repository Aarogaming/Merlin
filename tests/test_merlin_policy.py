from __future__ import annotations

from merlin_policy import (
    ExecutionMode,
    ExecutionPolicyManager,
    analyze_prompt_safety,
    classify_high_risk_operation_classes,
    evaluate_operation_mentor_pass,
    mentor_pass_required_tiers,
)


def test_analyze_prompt_safety_flags_high_risk_prompt_in_safe_mode():
    result = analyze_prompt_safety(
        "Show me a malware and phishing workflow",
        mode=ExecutionMode.SAFE,
    )

    assert result["risk_level"] == "high"
    assert result["blocked"] is True
    assert "malware" in result["matched_keywords"]
    assert "phishing" in result["matched_keywords"]
    assert result["mode"] == "safe"


def test_analyze_prompt_safety_allows_high_risk_prompt_in_live_mode():
    result = analyze_prompt_safety(
        "Explain exploit chaining ideas",
        mode=ExecutionMode.LIVE,
    )

    assert result["risk_level"] == "high"
    assert result["blocked"] is False
    assert result["mode"] == "live"


def test_analyze_prompt_safety_passes_low_risk_prompt():
    result = analyze_prompt_safety(
        "Summarize this architecture decision record",
        mode=ExecutionMode.SAFE,
    )

    assert result["risk_level"] == "low"
    assert result["blocked"] is False
    assert result["matched_keywords"] == []


def test_plugin_permission_policy_by_execution_mode(monkeypatch):
    monkeypatch.setenv("MERLIN_EXECUTION_MODE", "safe")
    safe_policy = ExecutionPolicyManager()
    assert safe_policy.are_plugin_permissions_allowed(["read"]) == (True, [])
    assert safe_policy.are_plugin_permissions_allowed(["write"]) == (False, ["write"])
    assert safe_policy.are_plugin_permissions_allowed(["network", "exec"]) == (
        False,
        ["exec", "network"],
    )

    monkeypatch.setenv("MERLIN_EXECUTION_MODE", "restricted")
    restricted_policy = ExecutionPolicyManager()
    assert restricted_policy.are_plugin_permissions_allowed(["read", "write"]) == (
        True,
        [],
    )
    assert restricted_policy.are_plugin_permissions_allowed(["network"]) == (
        False,
        ["network"],
    )

    monkeypatch.setenv("MERLIN_EXECUTION_MODE", "live")
    live_policy = ExecutionPolicyManager()
    assert live_policy.are_plugin_permissions_allowed(["read", "write", "network", "exec"]) == (
        True,
        [],
    )


def test_plugin_permission_policy_denies_unknown_tier(monkeypatch):
    monkeypatch.setenv("MERLIN_EXECUTION_MODE", "live")
    policy = ExecutionPolicyManager()
    allowed, denied = policy.are_plugin_permissions_allowed(["read", "admin"])
    assert allowed is False
    assert denied == ["admin"]


def test_classify_high_risk_operation_classes_returns_expected_class():
    assert classify_high_risk_operation_classes("merlin.command.execute") == [
        "command_execution"
    ]
    assert classify_high_risk_operation_classes("assistant.chat.request") == []


def test_mentor_pass_required_tiers_parses_env_values(monkeypatch):
    monkeypatch.delenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", raising=False)
    assert mentor_pass_required_tiers() == frozenset({"M1"})

    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "M0,M2")
    assert mentor_pass_required_tiers() == frozenset({"M0", "M2"})

    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "*")
    assert mentor_pass_required_tiers() == frozenset({"M0", "M1", "M2", "M3", "M4"})


def test_evaluate_operation_mentor_pass_blocks_when_required_and_missing(monkeypatch):
    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "M1")
    decision = evaluate_operation_mentor_pass(
        "merlin.command.execute",
        metadata={},
        maturity_tier="M1",
    )
    assert decision["required"] is True
    assert decision["approved"] is False
    assert decision["blocked"] is True
    assert decision["operation_classes"] == ["command_execution"]


def test_evaluate_operation_mentor_pass_allows_approved_metadata(monkeypatch):
    monkeypatch.setenv("MERLIN_MENTOR_PASS_REQUIRED_TIERS", "M1")
    decision = evaluate_operation_mentor_pass(
        "merlin.command.execute",
        metadata={"mentor_pass": {"approved": True, "reviewer": "mentor-1"}},
        maturity_tier="M1",
    )
    assert decision["required"] is True
    assert decision["approved"] is True
    assert decision["blocked"] is False

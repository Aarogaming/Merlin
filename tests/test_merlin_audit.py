from merlin_audit import build_request_audit_metadata, log_read_only_rejection


def test_build_request_audit_metadata_contract_fields():
    metadata = build_request_audit_metadata(
        route="/merlin/operations",
        decision_version="operation-dispatch-v1",
        request_id="req-123",
        operation_name="assistant.chat.request",
    )

    assert metadata["request_id"] == "req-123"
    assert metadata["route"] == "/merlin/operations"
    assert metadata["decision_version"] == "operation-dispatch-v1"
    assert metadata["operation_name"] == "assistant.chat.request"


def test_log_read_only_rejection_emits_standardized_audit_event(monkeypatch):
    captured: dict = {}

    def _capture(action, details, user="system", request_id=None):
        captured.update(
            {
                "action": action,
                "details": details,
                "user": user,
                "request_id": request_id,
            }
        )

    monkeypatch.setattr("merlin_audit.log_audit_event", _capture)

    log_read_only_rejection(
        component="merlin_research_manager",
        operation="merlin.research.manager.session.create",
        details={"session_id": "abc123"},
        request_id="req-1",
    )

    assert captured["action"] == "read_only_rejection"
    assert captured["user"] == "merlin_research_manager"
    assert captured["request_id"] == "req-1"
    assert captured["details"]["component"] == "merlin_research_manager"
    assert captured["details"]["operation"] == "merlin.research.manager.session.create"
    assert captured["details"]["reason"] == "read_only_mode"
    assert captured["details"]["session_id"] == "abc123"

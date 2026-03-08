from merlin_self_healing import EndpointCircuitBreaker, RestartBudget


def test_endpoint_circuit_breaker_opens_and_recovers_after_timeout():
    now = [100.0]

    def _time() -> float:
        return now[0]

    breaker = EndpointCircuitBreaker(
        failure_threshold=2,
        recovery_timeout_seconds=5.0,
        time_fn=_time,
    )

    assert breaker.allow_request("voice") is True
    breaker.record_failure("voice", reason="VOICE_UNAVAILABLE")
    assert breaker.allow_request("voice") is True

    breaker.record_failure("voice", reason="VOICE_UNAVAILABLE")
    assert breaker.allow_request("voice") is False
    state = breaker.get_state("voice")
    assert state["state"] == "open"
    assert state["consecutive_failures"] == 2

    now[0] += 5.0
    assert breaker.allow_request("voice") is True
    half_open = breaker.get_state("voice")
    assert half_open["state"] == "half_open"

    breaker.record_success("voice")
    closed = breaker.get_state("voice")
    assert closed["state"] == "closed"
    assert closed["consecutive_failures"] == 0


def test_endpoint_circuit_breaker_half_open_failure_reopens():
    now = [50.0]

    def _time() -> float:
        return now[0]

    breaker = EndpointCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=2.0,
        time_fn=_time,
    )

    breaker.record_failure("plugins", reason="PLUGIN_EXECUTION_ERROR")
    assert breaker.allow_request("plugins") is False

    now[0] += 2.0
    assert breaker.allow_request("plugins") is True
    assert breaker.get_state("plugins")["state"] == "half_open"

    breaker.record_failure("plugins", reason="PLUGIN_EXECUTION_FAILED")
    assert breaker.allow_request("plugins") is False
    reopened = breaker.get_state("plugins")
    assert reopened["state"] == "open"
    assert reopened["last_failure_reason"] == "PLUGIN_EXECUTION_FAILED"


def test_endpoint_circuit_breaker_clear_resets_state():
    breaker = EndpointCircuitBreaker(failure_threshold=1, recovery_timeout_seconds=1.0)
    breaker.record_failure("aas", reason="AAS_TASK_CREATE_FAILED")
    assert breaker.allow_request("aas") is False

    breaker.clear("aas")
    assert breaker.allow_request("aas") is True
    assert breaker.get_state("aas")["state"] == "closed"


def test_restart_budget_caps_attempts_and_resets():
    budget = RestartBudget(max_attempts=2)

    assert budget.can_attempt("plugin_a") is True
    assert budget.record_attempt("plugin_a") == 1
    assert budget.can_attempt("plugin_a") is True
    assert budget.record_attempt("plugin_a") == 2
    assert budget.can_attempt("plugin_a") is False
    assert budget.attempts("plugin_a") == 2

    budget.reset("plugin_a")
    assert budget.attempts("plugin_a") == 0
    assert budget.can_attempt("plugin_a") is True

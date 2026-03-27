"""
Health protocol tests for Merlin manager classes.

Covers all 9 managers migrated to Wave 2 health protocol:
  ABTestingManager, CostOptimizationManager, MerlinIntelligenceManager,
  PluginManager, ExecutionPolicyManager, ResearchManager,
  MerlinTaskManager, MerlinToolManager, MerlinUserManager
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from manager_health_protocol import HealthCheckResult, HealthStatus, LifecycleState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_status_valid(result: dict, expected_service: str) -> None:
    assert isinstance(result, dict)
    assert result["service_name"] == expected_service
    assert result["lifecycle_state"] == LifecycleState.RUNNING.value
    assert result["health_status"] == HealthStatus.HEALTHY.value
    assert isinstance(result["metrics"], dict)


def _assert_health_valid(result: HealthCheckResult) -> None:
    assert isinstance(result, HealthCheckResult)
    assert result.is_healthy is True
    assert result.status == HealthStatus.HEALTHY
    assert isinstance(result.checks, dict)
    assert len(result.checks) > 0
    assert all(isinstance(v, bool) for v in result.checks.values())


def _assert_lifecycle_running(mgr) -> None:
    assert mgr.lifecycle_state == LifecycleState.RUNNING.value
    assert mgr.is_running() is True
    states = [ev["new_state"] for ev in mgr._lifecycle_events]
    assert LifecycleState.STARTING.value in states
    assert LifecycleState.RUNNING.value in states


# ===========================================================================
# ABTestingManager
# ===========================================================================

@pytest.fixture
def ab_testing_manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    from merlin_ab_testing import ABTestingManager
    return ABTestingManager()


class TestABTestingManagerGetStatus:
    def test_get_status_valid(self, ab_testing_manager):
        _assert_status_valid(ab_testing_manager.get_status(), "ABTestingManager")

    def test_metrics_active_tests(self, ab_testing_manager):
        assert "active_tests" in ab_testing_manager.get_status()["metrics"]

    def test_metrics_test_history_count(self, ab_testing_manager):
        assert "test_history_count" in ab_testing_manager.get_status()["metrics"]


class TestABTestingManagerHealthCheck:
    def test_health_check_valid(self, ab_testing_manager):
        _assert_health_valid(ab_testing_manager.health_check())

    def test_lifecycle_running_check(self, ab_testing_manager):
        assert ab_testing_manager.health_check().checks["lifecycle_running"] is True

    def test_active_tests_dict_ok(self, ab_testing_manager):
        assert ab_testing_manager.health_check().checks["active_tests_dict_ok"] is True


class TestABTestingManagerLifecycleState:
    def test_lifecycle_running_after_init(self, ab_testing_manager):
        _assert_lifecycle_running(ab_testing_manager)


# ===========================================================================
# CostOptimizationManager
# ===========================================================================

@pytest.fixture
def cost_manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    from merlin_cost_optimization import CostOptimizationManager
    return CostOptimizationManager()


class TestCostOptimizationManagerGetStatus:
    def test_get_status_valid(self, cost_manager):
        _assert_status_valid(cost_manager.get_status(), "CostOptimizationManager")

    def test_metrics_budget_limit(self, cost_manager):
        assert "budget_limit" in cost_manager.get_status()["metrics"]

    def test_metrics_models_tracked(self, cost_manager):
        assert "models_tracked" in cost_manager.get_status()["metrics"]


class TestCostOptimizationManagerHealthCheck:
    def test_health_check_valid(self, cost_manager):
        _assert_health_valid(cost_manager.health_check())

    def test_budget_configured(self, cost_manager):
        assert cost_manager.health_check().checks["budget_configured"] is True


class TestCostOptimizationManagerLifecycleState:
    def test_lifecycle_running_after_init(self, cost_manager):
        _assert_lifecycle_running(cost_manager)


# ===========================================================================
# MerlinIntelligenceManager
# ===========================================================================

@pytest.fixture
def intelligence_manager():
    from merlin_intelligence_integration import MerlinIntelligenceManager
    return MerlinIntelligenceManager(aas_hub_url="http://test:8000")


class TestMerlinIntelligenceManagerGetStatus:
    def test_get_status_valid(self, intelligence_manager):
        _assert_status_valid(intelligence_manager.get_status(), "MerlinIntelligenceManager")

    def test_metrics_hub_url(self, intelligence_manager):
        assert intelligence_manager.get_status()["metrics"]["aas_hub_url"] == "http://test:8000"

    def test_metrics_standalone_mode(self, intelligence_manager):
        assert "standalone_mode" in intelligence_manager.get_status()["metrics"]


class TestMerlinIntelligenceManagerHealthCheck:
    def test_health_check_valid(self, intelligence_manager):
        _assert_health_valid(intelligence_manager.health_check())

    def test_cache_initialised(self, intelligence_manager):
        assert intelligence_manager.health_check().checks["cache_initialised"] is True

    def test_hub_url_configured(self, intelligence_manager):
        assert intelligence_manager.health_check().checks["hub_url_configured"] is True


class TestMerlinIntelligenceManagerLifecycleState:
    def test_lifecycle_running_after_init(self, intelligence_manager):
        _assert_lifecycle_running(intelligence_manager)


# ===========================================================================
# PluginManager
# ===========================================================================

@pytest.fixture
def plugin_manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    from merlin_plugin_manager import PluginManager
    return PluginManager(plugin_dir=str(plugins_dir))


class TestPluginManagerGetStatus:
    def test_get_status_valid(self, plugin_manager):
        _assert_status_valid(plugin_manager.get_status(), "PluginManager")

    def test_metrics_plugins_loaded(self, plugin_manager):
        assert "plugins_loaded" in plugin_manager.get_status()["metrics"]

    def test_metrics_execution_mode(self, plugin_manager):
        assert "execution_mode" in plugin_manager.get_status()["metrics"]


class TestPluginManagerHealthCheck:
    def test_health_check_valid(self, plugin_manager):
        _assert_health_valid(plugin_manager.health_check())

    def test_plugin_directory_exists(self, plugin_manager):
        assert plugin_manager.health_check().checks["plugin_directory_exists"] is True


class TestPluginManagerLifecycleState:
    def test_lifecycle_running_after_init(self, plugin_manager):
        _assert_lifecycle_running(plugin_manager)


# ===========================================================================
# ExecutionPolicyManager
# ===========================================================================

@pytest.fixture
def policy_manager_fixture():
    from merlin_policy import ExecutionPolicyManager
    return ExecutionPolicyManager()


class TestExecutionPolicyManagerGetStatus:
    def test_get_status_valid(self, policy_manager_fixture):
        _assert_status_valid(policy_manager_fixture.get_status(), "ExecutionPolicyManager")

    def test_metrics_execution_mode(self, policy_manager_fixture):
        assert "execution_mode" in policy_manager_fixture.get_status()["metrics"]

    def test_metrics_blocked_commands_count(self, policy_manager_fixture):
        assert policy_manager_fixture.get_status()["metrics"]["blocked_commands_count"] == 3


class TestExecutionPolicyManagerHealthCheck:
    def test_health_check_valid(self, policy_manager_fixture):
        _assert_health_valid(policy_manager_fixture.health_check())

    def test_mode_configured(self, policy_manager_fixture):
        assert policy_manager_fixture.health_check().checks["mode_configured"] is True


class TestExecutionPolicyManagerLifecycleState:
    def test_lifecycle_running_after_init(self, policy_manager_fixture):
        _assert_lifecycle_running(policy_manager_fixture)


# ===========================================================================
# ResearchManager
# ===========================================================================

@pytest.fixture
def research_manager(tmp_path):
    from merlin_research_manager import ResearchManager
    return ResearchManager(storage_root=tmp_path / "research")


class TestResearchManagerGetStatus:
    def test_get_status_valid(self, research_manager):
        _assert_status_valid(research_manager.get_status(), "ResearchManager")

    def test_metrics_allow_writes(self, research_manager):
        assert "allow_writes" in research_manager.get_status()["metrics"]

    def test_metrics_session_ttl_days(self, research_manager):
        assert "session_ttl_days" in research_manager.get_status()["metrics"]

    def test_metrics_pending_briefs(self, research_manager):
        assert research_manager.get_status()["metrics"]["pending_briefs"] == 0


class TestResearchManagerHealthCheck:
    def test_health_check_valid(self, research_manager):
        _assert_health_valid(research_manager.health_check())

    def test_sessions_dir_exists(self, research_manager):
        assert research_manager.health_check().checks["sessions_dir_exists"] is True

    def test_archive_dir_exists(self, research_manager):
        assert research_manager.health_check().checks["archive_dir_exists"] is True


class TestResearchManagerLifecycleState:
    def test_lifecycle_running_after_init(self, research_manager):
        _assert_lifecycle_running(research_manager)


# ===========================================================================
# MerlinTaskManager
# ===========================================================================

@pytest.fixture
def task_manager_fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from merlin_tasks import MerlinTaskManager
    return MerlinTaskManager(tasks_file=str(tmp_path / "tasks.json"))


class TestMerlinTaskManagerGetStatus:
    def test_get_status_valid(self, task_manager_fixture):
        _assert_status_valid(task_manager_fixture.get_status(), "MerlinTaskManager")

    def test_metrics_task_count(self, task_manager_fixture):
        assert task_manager_fixture.get_status()["metrics"]["task_count"] == 0


class TestMerlinTaskManagerHealthCheck:
    def test_health_check_valid(self, task_manager_fixture):
        _assert_health_valid(task_manager_fixture.health_check())

    def test_tasks_list_ok(self, task_manager_fixture):
        assert task_manager_fixture.health_check().checks["tasks_list_ok"] is True


class TestMerlinTaskManagerLifecycleState:
    def test_lifecycle_running_after_init(self, task_manager_fixture):
        _assert_lifecycle_running(task_manager_fixture)


# ===========================================================================
# MerlinToolManager
# ===========================================================================

@pytest.fixture
def tool_manager_fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    from merlin_tools import MerlinToolManager
    return MerlinToolManager()


class TestMerlinToolManagerGetStatus:
    def test_get_status_valid(self, tool_manager_fixture):
        _assert_status_valid(tool_manager_fixture.get_status(), "MerlinToolManager")

    def test_metrics_plugins_available(self, tool_manager_fixture):
        assert "plugins_available" in tool_manager_fixture.get_status()["metrics"]


class TestMerlinToolManagerHealthCheck:
    def test_health_check_valid(self, tool_manager_fixture):
        _assert_health_valid(tool_manager_fixture.health_check())

    def test_plugin_manager_ready(self, tool_manager_fixture):
        assert tool_manager_fixture.health_check().checks["plugin_manager_ready"] is True


class TestMerlinToolManagerLifecycleState:
    def test_lifecycle_running_after_init(self, tool_manager_fixture):
        _assert_lifecycle_running(tool_manager_fixture)


# ===========================================================================
# MerlinUserManager
# ===========================================================================

@pytest.fixture
def user_manager_fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from merlin_user_manager import MerlinUserManager
    return MerlinUserManager(users_file=str(tmp_path / "users.json"))


class TestMerlinUserManagerGetStatus:
    def test_get_status_valid(self, user_manager_fixture):
        _assert_status_valid(user_manager_fixture.get_status(), "MerlinUserManager")

    def test_metrics_user_count(self, user_manager_fixture):
        assert user_manager_fixture.get_status()["metrics"]["user_count"] >= 1


class TestMerlinUserManagerHealthCheck:
    def test_health_check_valid(self, user_manager_fixture):
        _assert_health_valid(user_manager_fixture.health_check())

    def test_users_list_ok(self, user_manager_fixture):
        assert user_manager_fixture.health_check().checks["users_list_ok"] is True

    def test_has_users(self, user_manager_fixture):
        assert user_manager_fixture.health_check().checks["has_users"] is True


class TestMerlinUserManagerLifecycleState:
    def test_lifecycle_running_after_init(self, user_manager_fixture):
        _assert_lifecycle_running(user_manager_fixture)

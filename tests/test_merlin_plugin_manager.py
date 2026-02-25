from __future__ import annotations

import json
from pathlib import Path

import pytest

from merlin_plugin_manager import PluginManager
from merlin_tasks import MerlinTaskManager


def _write_plugin_module(path: Path, plugin_name: str):
    path.write_text(
        "\n".join(
            [
                "class _Plugin:",
                "    def execute(self, *args, **kwargs):",
                "        return {'ok': True, 'name': '" + plugin_name + "'}",
                "    def get_info(self):",
                "        return {'name': '"
                + plugin_name
                + "', 'description': 'd', 'category': 'general'}",
                "",
                "def get_plugin():",
                "    return _Plugin()",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_manifest(
    path: Path,
    name: str,
    entry: str = "plugin.py",
    permissions: list[str] | None = None,
    dependencies: list[dict[str, str]] | None = None,
    timeout_seconds: float | None = None,
):
    payload = {
        "schemaName": "PluginManifest",
        "schemaVersion": "1.0.0",
        "name": name,
        "version": "0.1.0",
        "description": f"{name} plugin",
        "entry": entry,
        "type": "plugin",
        "capabilities": [
            {
                "schemaName": "Capability",
                "schemaVersion": "1.0.0",
                "name": f"merlin.{name}.run",
                "version": "0.1.0",
            }
        ],
    }
    if permissions is not None:
        payload["permissions"] = permissions
    if dependencies is not None:
        payload["dependencies"] = dependencies
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_plugins_validates_manifest_before_loading_packaged_plugins(
    tmp_path: Path,
):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)

    legacy_plugin_path = plugin_root / "legacy_demo.py"
    _write_plugin_module(legacy_plugin_path, "legacy_demo")

    valid_pkg_dir = plugin_root / "valid_pkg"
    valid_pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(valid_pkg_dir / "plugin.py", "valid_pkg")
    _write_manifest(valid_pkg_dir / "manifest.json", name="valid_pkg")

    invalid_pkg_dir = plugin_root / "invalid_pkg"
    invalid_pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(invalid_pkg_dir / "plugin.py", "invalid_pkg")
    invalid_manifest = {
        "schemaName": "PluginManifest",
        "schemaVersion": "1.0.0",
        "name": "",
        "version": "0.1.0",
        "description": "broken",
        "entry": "plugin.py",
        "type": "plugin",
        "capabilities": [],
    }
    (invalid_pkg_dir / "manifest.json").write_text(
        json.dumps(invalid_manifest), encoding="utf-8"
    )

    manager = PluginManager(plugin_dir=plugin_root, strict_packaged_load=False)
    manager.load_plugins()

    assert "legacy_demo" in manager.plugins
    assert "valid_pkg" in manager.plugins
    assert "invalid_pkg" not in manager.plugins


def test_manifest_entry_path_traversal_is_rejected(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "danger_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(pkg_dir / "plugin.py", "danger_pkg")
    _write_manifest(pkg_dir / "manifest.json", name="danger_pkg", entry="../plugin.py")

    manager = PluginManager(plugin_dir=plugin_root)

    try:
        manager._read_and_validate_manifest(pkg_dir / "manifest.json")
    except ValueError as exc:
        assert "traverse parent directories" in str(exc)
    else:
        raise AssertionError("expected ValueError for traversal entry")


def test_list_plugin_info_uses_manifest_fallback_when_get_info_missing(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "manifest_only_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        return {'ok': True}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(pkg_dir / "manifest.json", name="manifest_only_pkg")

    manager = PluginManager(plugin_dir=plugin_root)
    manager.load_plugins()
    info = manager.list_plugin_info()

    assert "manifest_only_pkg" in info
    assert info["manifest_only_pkg"]["name"] == "manifest_only_pkg"
    assert info["manifest_only_pkg"]["category"] == "plugin"
    assert info["manifest_only_pkg"]["permissions"] == ["read"]


def test_manifest_permissions_validation_rejects_unknown_tier(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "bad_permissions_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(pkg_dir / "plugin.py", "bad_permissions_pkg")
    _write_manifest(
        pkg_dir / "manifest.json",
        name="bad_permissions_pkg",
        permissions=["admin"],
    )

    manager = PluginManager(plugin_dir=plugin_root)
    with pytest.raises(ValueError, match="permissions\\[0\\]"):
        manager._read_and_validate_manifest(pkg_dir / "manifest.json")


def test_execute_plugin_denies_disallowed_permission_tiers(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "exec_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(pkg_dir / "plugin.py", "exec_pkg")
    _write_manifest(
        pkg_dir / "manifest.json",
        name="exec_pkg",
        permissions=["exec"],
    )

    class RestrictivePolicy:
        def are_plugin_permissions_allowed(self, permissions):
            denied = sorted(
                permission for permission in permissions if permission == "exec"
            )
            return not denied, denied

    manager = PluginManager(
        plugin_dir=plugin_root, permission_policy=RestrictivePolicy()
    )
    manager.load_plugins()

    result = manager.execute_plugin("exec_pkg")
    assert result["code"] == "PLUGIN_PERMISSION_DENIED"
    assert result["denied_permissions"] == ["exec"]
    assert result["required_permissions"] == ["exec"]


def test_execute_plugin_returns_timeout_and_invokes_cancel_hook(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "timeout_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "import time",
                "",
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.cancelled = False",
                "    def execute(self, *args, **kwargs):",
                "        time.sleep(0.2)",
                "        return {'ok': True}",
                "    def cancel(self):",
                "        self.cancelled = True",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="timeout_pkg",
        permissions=["read"],
        timeout_seconds=0.01,
    )

    manager = PluginManager(plugin_dir=plugin_root, execution_mode="thread")
    manager.load_plugins()
    result = manager.execute_plugin("timeout_pkg")

    assert result["code"] == "PLUGIN_TIMEOUT"
    assert result["timeout_seconds"] == 0.01
    assert manager.plugins["timeout_pkg"].cancelled is True


def test_execute_plugin_timeout_updates_task_status_with_cancellation_hook(
    tmp_path: Path, monkeypatch
):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "timed_task_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "import time",
                "",
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.cancelled = False",
                "    def execute(self, *args, **kwargs):",
                "        time.sleep(0.2)",
                "        return {'ok': True}",
                "    def cancel(self):",
                "        self.cancelled = True",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="timed_task_pkg",
        permissions=["read"],
        timeout_seconds=0.01,
    )

    isolated_task_manager = MerlinTaskManager(tasks_file=str(tmp_path / "tasks.json"))
    task = isolated_task_manager.add_task(
        "plugin timeout",
        "validate timeout hook",
        "High",
    )
    monkeypatch.setattr("merlin_plugin_manager.task_manager", isolated_task_manager)

    manager = PluginManager(plugin_dir=plugin_root, execution_mode="thread")
    manager.load_plugins()
    result = manager.execute_plugin(
        "timed_task_pkg",
        __merlin_task_id=task["id"],
    )

    assert result["code"] == "PLUGIN_TIMEOUT"
    updated_task = isolated_task_manager.get_task(task["id"])
    assert updated_task is not None
    assert updated_task["status"] == "Timed Out"
    assert manager.plugins["timed_task_pkg"].cancelled is True


def test_execute_plugin_timeout_process_mode_returns_timeout(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "timeout_process_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "import time",
                "",
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        time.sleep(0.2)",
                "        return {'ok': True}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="timeout_process_pkg",
        permissions=["read"],
        timeout_seconds=0.01,
    )

    manager = PluginManager(plugin_dir=plugin_root, execution_mode="process")
    manager.load_plugins()
    result = manager.execute_plugin("timeout_process_pkg")

    assert result["code"] == "PLUGIN_TIMEOUT"
    assert result["timeout_seconds"] == 0.01
    assert "timeout_process_pkg" not in manager._process_executors


def test_process_pool_executor_reused_across_successful_calls(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "pool_reuse_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        return {'ok': True, 'arg': args[0] if args else None}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="pool_reuse_pkg",
        permissions=["read"],
    )

    manager = PluginManager(
        plugin_dir=plugin_root,
        execution_mode="process",
        process_pool_size=2,
    )
    manager.load_plugins()

    first = manager.execute_plugin("pool_reuse_pkg", "a")
    assert first == {"ok": True, "arg": "a"}
    first_executor = manager._process_executors.get("pool_reuse_pkg")
    assert first_executor is not None

    second = manager.execute_plugin("pool_reuse_pkg", "b")
    assert second == {"ok": True, "arg": "b"}
    assert manager._process_executors.get("pool_reuse_pkg") is first_executor


def test_process_pool_executor_recovers_after_timeout_reset(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "pool_reset_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "import time",
                "",
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        time.sleep(0.05)",
                "        return {'ok': True}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="pool_reset_pkg",
        permissions=["read"],
    )

    manager = PluginManager(
        plugin_dir=plugin_root,
        execution_mode="process",
        process_pool_size=1,
    )
    manager.load_plugins()

    timed_out = manager.execute_plugin(
        "pool_reset_pkg",
        __merlin_timeout_seconds=0.01,
    )
    assert timed_out["code"] == "PLUGIN_TIMEOUT"
    assert "pool_reset_pkg" not in manager._process_executors

    recovered = manager.execute_plugin(
        "pool_reset_pkg",
        __merlin_timeout_seconds=1.0,
    )
    assert recovered == {"ok": True}
    assert manager._process_executors.get("pool_reset_pkg") is not None


def test_process_pool_timeout_reset_isolated_to_single_plugin(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)

    fast_dir = plugin_root / "fast_pkg"
    fast_dir.mkdir(parents=True, exist_ok=True)
    (fast_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        return {'ok': True, 'name': 'fast_pkg'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(fast_dir / "manifest.json", name="fast_pkg", permissions=["read"])

    slow_dir = plugin_root / "slow_pkg"
    slow_dir.mkdir(parents=True, exist_ok=True)
    (slow_dir / "plugin.py").write_text(
        "\n".join(
            [
                "import time",
                "",
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        time.sleep(0.05)",
                "        return {'ok': True, 'name': 'slow_pkg'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(slow_dir / "manifest.json", name="slow_pkg", permissions=["read"])

    manager = PluginManager(
        plugin_dir=plugin_root,
        execution_mode="process",
        process_pool_size=1,
    )
    manager.load_plugins()

    fast_first = manager.execute_plugin("fast_pkg")
    assert fast_first == {"ok": True, "name": "fast_pkg"}
    fast_executor = manager._process_executors.get("fast_pkg")
    assert fast_executor is not None

    slow_timeout = manager.execute_plugin(
        "slow_pkg",
        __merlin_timeout_seconds=0.01,
    )
    assert slow_timeout["code"] == "PLUGIN_TIMEOUT"
    assert "slow_pkg" not in manager._process_executors
    assert manager._process_executors.get("fast_pkg") is fast_executor

    fast_second = manager.execute_plugin("fast_pkg")
    assert fast_second == {"ok": True, "name": "fast_pkg"}
    assert manager._process_executors.get("fast_pkg") is fast_executor


def test_execute_plugin_process_mode_reports_unpicklable_args(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "unpicklable_arg_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        return {'ok': True}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="unpicklable_arg_pkg",
        permissions=["read"],
    )

    manager = PluginManager(plugin_dir=plugin_root, execution_mode="process")
    manager.load_plugins()

    result = manager.execute_plugin("unpicklable_arg_pkg", lambda value: value)

    assert result["code"] == "PLUGIN_PROCESS_SERIALIZATION_ERROR"
    assert "pickle" in result["error"].lower()
    assert (
        manager.list_plugin_info()["unpicklable_arg_pkg"]["health_state"] == "healthy"
    )


def test_execute_plugin_process_mode_reports_unpicklable_results(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "unpicklable_result_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        def inner():",
                "            return 'ok'",
                "        return inner",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(
        pkg_dir / "manifest.json",
        name="unpicklable_result_pkg",
        permissions=["read"],
    )

    manager = PluginManager(plugin_dir=plugin_root, execution_mode="process")
    manager.load_plugins()

    result = manager.execute_plugin("unpicklable_result_pkg")

    assert result["code"] == "PLUGIN_PROCESS_SERIALIZATION_ERROR"
    assert "pickle" in result["error"].lower()
    assert (
        manager.list_plugin_info()["unpicklable_result_pkg"]["health_state"]
        == "healthy"
    )


def test_dependency_preflight_reports_missing_plugin_dependency(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "dependent_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(pkg_dir / "plugin.py", "dependent_pkg")
    _write_manifest(
        pkg_dir / "manifest.json",
        name="dependent_pkg",
        dependencies=[{"name": "missing_core", "version": "1.0.0"}],
    )

    manager = PluginManager(plugin_dir=plugin_root)
    issues = manager.check_packaged_plugin_dependency_compatibility()

    assert "dependent_pkg" in issues
    assert "missing dependency plugin: missing_core" in "; ".join(
        issues["dependent_pkg"]
    )


def test_load_plugins_skips_packaged_plugins_with_incompatible_dependencies(
    tmp_path: Path,
):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)

    core_dir = plugin_root / "core_pkg"
    core_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(core_dir / "plugin.py", "core_pkg")
    _write_manifest(core_dir / "manifest.json", name="core_pkg")

    dependent_dir = plugin_root / "dependent_pkg"
    dependent_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(dependent_dir / "plugin.py", "dependent_pkg")
    _write_manifest(
        dependent_dir / "manifest.json",
        name="dependent_pkg",
        dependencies=[{"name": "core_pkg", "version": ">=2.0.0"}],
    )

    manager = PluginManager(plugin_dir=plugin_root, strict_packaged_load=False)
    manager.load_plugins()

    assert "core_pkg" in manager.plugins
    assert "dependent_pkg" not in manager.plugins


def test_load_plugins_strict_packaged_mode_raises_on_packaged_skip(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)

    invalid_pkg_dir = plugin_root / "invalid_pkg"
    invalid_pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(invalid_pkg_dir / "plugin.py", "invalid_pkg")
    (invalid_pkg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schemaName": "PluginManifest",
                "schemaVersion": "1.0.0",
                "name": "",
                "version": "0.1.0",
                "description": "broken",
                "entry": "plugin.py",
                "type": "plugin",
                "capabilities": [],
            }
        ),
        encoding="utf-8",
    )

    manager = PluginManager(plugin_dir=plugin_root, strict_packaged_load=True)
    with pytest.raises(RuntimeError, match="strict packaged plugin load failed"):
        manager.load_plugins()
    assert manager.plugin_load_failures
    assert manager.plugin_load_failures[0]["source_type"] == "packaged"


def test_packaged_python_dependencies_are_preflighted(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)

    pkg_dir = plugin_root / "python_dep_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(pkg_dir / "plugin.py", "python_dep_pkg")
    _write_manifest(pkg_dir / "manifest.json", name="python_dep_pkg")

    manifest_path = pkg_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["python_dependencies"] = [
        {
            "module": "definitely_missing_python_module_xyz",
            "package": "definitely-missing-package-xyz",
            "extra": "plugins-all",
        }
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    manager = PluginManager(plugin_dir=plugin_root, strict_packaged_load=False)
    issues = manager.check_packaged_plugin_dependency_compatibility()

    assert "python_dep_pkg" in issues
    issue_text = "; ".join(issues["python_dep_pkg"])
    assert (
        "missing python dependency module 'definitely_missing_python_module_xyz'"
        in issue_text
    )


def test_legacy_optional_python_dependency_skip_records_load_failure(
    tmp_path: Path, monkeypatch
):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    _write_plugin_module(plugin_root / "legacy_opt_dep.py", "legacy_opt_dep")

    monkeypatch.setattr(
        "merlin_plugin_manager.LEGACY_PLUGIN_OPTIONAL_PYTHON_DEPENDENCIES",
        {
            "legacy_opt_dep": [
                {
                    "module": "definitely_missing_python_module_xyz",
                    "package": "definitely-missing-package-xyz",
                    "extra": "desktop",
                }
            ]
        },
    )

    manager = PluginManager(plugin_dir=plugin_root, strict_packaged_load=False)
    manager.load_plugins()

    assert "legacy_opt_dep" not in manager.plugins
    failures = manager.plugin_load_failures
    assert failures
    assert failures[0]["source_type"] == "legacy"
    assert "missing optional python dependency" in failures[0]["reason"]


def test_plugin_crash_isolation_with_capped_auto_restart(tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    pkg_dir = plugin_root / "crashy_pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "plugin.py").write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def __init__(self, manifest=None):",
                "        self.manifest = manifest or {}",
                "    def execute(self, *args, **kwargs):",
                "        raise RuntimeError('boom')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(pkg_dir / "manifest.json", name="crashy_pkg")

    manager = PluginManager(
        plugin_dir=plugin_root,
        max_restart_attempts=1,
        execution_mode="process",
    )
    manager.load_plugins()

    with pytest.raises(RuntimeError, match="boom"):
        manager.execute_plugin("crashy_pkg")

    isolated_result = manager.execute_plugin("crashy_pkg")
    assert isolated_result["code"] == "PLUGIN_CRASH_ISOLATED"
    assert "restart budget exhausted" in isolated_result["error"]

    info = manager.list_plugin_info()["crashy_pkg"]
    assert info["health_state"] == "isolated"
    assert info["restart_attempts"] == 1


def test_default_plugin_dir_missing_uses_packaged_plugin_directory(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    missing_default_plugins_dir = tmp_path / "plugins"
    assert not missing_default_plugins_dir.exists()

    manager = PluginManager(plugin_dir="plugins", strict_packaged_load=False)

    assert manager.plugin_dir.exists()
    assert manager.plugin_dir.resolve() != missing_default_plugins_dir.resolve()
    assert any(manager.plugin_dir.glob("*/manifest.json"))

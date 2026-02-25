import importlib.util
import json
import logging
import multiprocessing as mp
import os
import pickle
import re
import threading
from collections.abc import Callable
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
)
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

import merlin_settings as settings

try:
    from merlin_policy import PLUGIN_PERMISSION_TIERS, policy_manager
except ImportError:
    from merlin_policy import policy_manager

    PLUGIN_PERMISSION_TIERS = {"read", "write", "network", "exec"}
try:
    from merlin_self_healing import RestartBudget
except ImportError:

    class RestartBudget:
        def __init__(self, max_attempts: int = 2):
            self.max_attempts = max(0, int(max_attempts))
            self._attempts: dict[str, int] = {}

        def attempts(self, key: str) -> int:
            return int(self._attempts.get(key, 0))

        def can_attempt(self, key: str) -> bool:
            return int(self._attempts.get(key, 0)) < self.max_attempts

        def record_attempt(self, key: str) -> int:
            next_attempt = int(self._attempts.get(key, 0)) + 1
            self._attempts[key] = next_attempt
            return next_attempt

        def reset(self, key: str) -> None:
            self._attempts.pop(key, None)

        def clear(self) -> None:
            self._attempts.clear()


from merlin_tasks import task_manager

PLUGIN_MANIFEST_SCHEMA_NAME = "PluginManifest"
PLUGIN_MANIFEST_SCHEMA_VERSION = "1.0.0"
PLUGIN_MANIFEST_REQUIRED_FIELDS = {
    "schemaName": str,
    "schemaVersion": str,
    "name": str,
    "version": str,
    "description": str,
    "entry": str,
    "type": str,
    "capabilities": list,
}
PLUGIN_CAPABILITY_REQUIRED_FIELDS = {
    "schemaName": str,
    "schemaVersion": str,
    "name": str,
    "version": str,
}
PLUGIN_DEPENDENCY_REQUIRED_FIELDS = {
    "name": str,
    "version": str,
}
DEFAULT_PLUGIN_PERMISSIONS = ["read"]
DEFAULT_PLUGIN_TIMEOUT_SECONDS = 30.0
DEFAULT_PLUGIN_EXECUTION_MODE = "process"
DEFAULT_PLUGIN_PROCESS_POOL_SIZE = 2
VALID_PLUGIN_EXECUTION_MODES = frozenset({"thread", "process"})
LEGACY_PLUGIN_OPTIONAL_PYTHON_DEPENDENCIES: dict[str, list[dict[str, str]]] = {
    "telekinesis": [
        {"module": "pyautogui", "package": "pyautogui", "extra": "desktop"}
    ],
    "web_search": [{"module": "bs4", "package": "beautifulsoup4", "extra": "web"}],
}


class _PluginExecutionTimeout(Exception):
    def __init__(self, timeout_seconds: float):
        super().__init__(f"plugin execution timed out after {timeout_seconds}s")
        self.timeout_seconds = float(timeout_seconds)


class _PluginProcessSerializationError(Exception):
    pass


def _execute_plugin_in_worker(
    *,
    module_name: str,
    file_path: str,
    manifest: dict[str, Any] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    plugin = _load_plugin_instance_for_execution(
        module_name=module_name,
        file_path=Path(file_path),
        manifest=manifest,
    )
    if plugin is None or not hasattr(plugin, "execute"):
        raise RuntimeError(f"plugin module {file_path} missing executable entrypoint")
    return plugin.execute(*args, **kwargs)


def _load_plugin_instance_for_execution(
    *,
    module_name: str,
    file_path: Path,
    manifest: dict[str, Any] | None = None,
) -> Any | None:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "get_plugin"):
        return module.get_plugin()

    plugin_cls = getattr(module, "Plugin", None)
    if plugin_cls is None:
        return None

    try:
        return plugin_cls(manifest=manifest) if manifest is not None else plugin_cls()
    except TypeError:
        return plugin_cls()


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "enabled", "allow", "allowed"}


def _load_strict_packaged_default() -> bool:
    raw = os.getenv("MERLIN_PLUGIN_STRICT_PACKAGED")
    return _parse_bool(raw, default=True)


def _normalize_plugin_execution_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_PLUGIN_EXECUTION_MODES:
        return normalized
    return DEFAULT_PLUGIN_EXECUTION_MODE


def _load_plugin_execution_mode_default() -> str:
    configured = getattr(settings, "MERLIN_PLUGIN_EXECUTION_MODE", None)
    if configured is not None:
        return _normalize_plugin_execution_mode(configured)
    raw = os.getenv("MERLIN_PLUGIN_EXECUTION_MODE", DEFAULT_PLUGIN_EXECUTION_MODE)
    return _normalize_plugin_execution_mode(raw)


def _normalize_plugin_process_pool_size(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PLUGIN_PROCESS_POOL_SIZE
    if parsed <= 0:
        return DEFAULT_PLUGIN_PROCESS_POOL_SIZE
    return parsed


def _load_plugin_process_pool_size_default() -> int:
    configured = getattr(settings, "MERLIN_PLUGIN_PROCESS_POOL_SIZE", None)
    if configured is not None:
        return _normalize_plugin_process_pool_size(configured)
    raw = os.getenv(
        "MERLIN_PLUGIN_PROCESS_POOL_SIZE",
        str(DEFAULT_PLUGIN_PROCESS_POOL_SIZE),
    )
    return _normalize_plugin_process_pool_size(raw)


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"\d+\.\d+\.\d+", value.strip()) is None:
        return None
    major, minor, patch = value.strip().split(".")
    return int(major), int(minor), int(patch)


def _is_supported_dependency_version_spec(value: str) -> bool:
    spec = value.strip()
    if spec == "*":
        return True
    if spec.startswith(">=") or spec.startswith("=="):
        return _parse_semver(spec[2:]) is not None
    return _parse_semver(spec) is not None


def _is_dependency_version_compatible(
    required_version: str, actual_version: str
) -> bool:
    spec = required_version.strip()
    if spec == "*":
        return True
    parsed_actual = _parse_semver(actual_version)
    if parsed_actual is None:
        return False
    if spec.startswith(">="):
        parsed_required = _parse_semver(spec[2:])
        if parsed_required is None:
            return False
        return parsed_actual >= parsed_required
    if spec.startswith("=="):
        parsed_required = _parse_semver(spec[2:])
        if parsed_required is None:
            return False
        return parsed_actual == parsed_required
    parsed_required = _parse_semver(spec)
    if parsed_required is None:
        return False
    return parsed_actual == parsed_required


def _normalize_permissions(raw_permissions: Any) -> list[str]:
    if not isinstance(raw_permissions, (list, tuple, set)):
        return []
    normalized: list[str] = []
    for item in raw_permissions:
        if not isinstance(item, str):
            continue
        permission = item.strip().lower()
        if not permission:
            continue
        if permission in normalized:
            continue
        normalized.append(permission)
    return normalized


class MerlinPlugin:
    def __init__(
        self,
        name,
        description="",
        version="1.0.0",
        author="Unknown",
        category="general",
    ):
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.category = category

    def execute(self, *args, **kwargs):
        raise RuntimeError("Plugins must implement execute method")

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
        }


class PluginManager:
    def __init__(
        self,
        plugin_dir="plugins",
        permission_policy=None,
        max_restart_attempts: int | None = None,
        strict_packaged_load: bool | None = None,
        execution_mode: str | None = None,
        process_pool_size: int | None = None,
    ):
        requested_plugin_dir = Path(plugin_dir)
        self._plugin_directories = self._resolve_plugin_directories(
            requested_plugin_dir
        )
        self.plugin_dir = self._plugin_directories[0]
        self.plugins: dict[str, Any] = {}
        self._plugin_manifests: dict[str, dict[str, Any]] = {}
        self._plugin_sources: dict[str, dict[str, Any]] = {}
        self._plugin_crash_state: dict[str, dict[str, Any]] = {}
        self._plugin_load_failures: list[dict[str, str]] = []
        self.permission_policy = permission_policy or policy_manager
        self.strict_packaged_load = (
            bool(strict_packaged_load)
            if strict_packaged_load is not None
            else _load_strict_packaged_default()
        )
        self.execution_mode = _normalize_plugin_execution_mode(
            execution_mode
            if execution_mode is not None
            else _load_plugin_execution_mode_default()
        )
        self.process_pool_size = _normalize_plugin_process_pool_size(
            process_pool_size
            if process_pool_size is not None
            else _load_plugin_process_pool_size_default()
        )
        self._process_executors: dict[str, ProcessPoolExecutor] = {}
        self._process_executor_lock = threading.Lock()
        restart_limit = (
            max_restart_attempts
            if isinstance(max_restart_attempts, int)
            else int(getattr(settings, "MERLIN_PLUGIN_RESTART_MAX_ATTEMPTS", 2))
        )
        self._restart_budget = RestartBudget(max_attempts=restart_limit)

    @staticmethod
    def _is_default_plugins_dir(path: Path) -> bool:
        normalized = str(path).strip().replace("\\", "/")
        if path.is_absolute():
            return False
        return normalized in {"plugins", "./plugins"}

    @staticmethod
    def _discover_packaged_plugin_directories() -> list[Path]:
        candidates: list[Path] = []
        local_plugins_dir = Path(__file__).resolve().parent / "plugins"
        if local_plugins_dir.exists():
            candidates.append(local_plugins_dir)

        spec = importlib.util.find_spec("plugins")
        if spec is not None and spec.submodule_search_locations:
            for location in spec.submodule_search_locations:
                candidate = Path(location)
                if candidate.exists():
                    candidates.append(candidate)

        unique_candidates: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_candidates.append(candidate)
        return unique_candidates

    def _resolve_plugin_directories(self, requested: Path) -> list[Path]:
        if requested.exists():
            return [requested]

        if self._is_default_plugins_dir(requested):
            packaged_dirs = self._discover_packaged_plugin_directories()
            if packaged_dirs:
                logging.info(
                    "Plugin directory %s not found; using packaged plugin directories: %s",
                    requested,
                    ", ".join(str(path) for path in packaged_dirs),
                )
                return packaged_dirs

        requested.mkdir(parents=True, exist_ok=True)
        return [requested]

    def _iter_legacy_plugin_files(self):
        seen: set[Path] = set()
        for plugin_dir in self._plugin_directories:
            for file_path in sorted(plugin_dir.glob("*.py")):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield file_path

    def _iter_packaged_manifest_paths(self):
        seen: set[Path] = set()
        for plugin_dir in self._plugin_directories:
            for manifest_path in sorted(plugin_dir.glob("*/manifest.json")):
                resolved = manifest_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield manifest_path

    def load_plugins(self):
        if self.execution_mode == "process":
            self._reset_all_process_executors("plugin reload")
        self._plugin_load_failures = []
        self._load_packaged_plugins_from_manifest()
        self._load_legacy_python_plugins()

    def _reset_process_executor(self, plugin_name: str, reason: str = "") -> None:
        executor: ProcessPoolExecutor | None = None
        with self._process_executor_lock:
            executor = self._process_executors.pop(plugin_name, None)
        if executor is None:
            return
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            logging.warning(
                "Failed to shutdown plugin process pool for %s (%s): %s",
                plugin_name,
                reason,
                exc,
            )

    def _reset_all_process_executors(self, reason: str = "") -> None:
        executors: list[tuple[str, ProcessPoolExecutor]] = []
        with self._process_executor_lock:
            executors = list(self._process_executors.items())
            self._process_executors = {}
        for plugin_name, executor in executors:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:
                logging.warning(
                    "Failed to shutdown plugin process pool for %s (%s): %s",
                    plugin_name,
                    reason,
                    exc,
                )

    def _process_executor_for_run(self, plugin_name: str) -> ProcessPoolExecutor:
        with self._process_executor_lock:
            executor = self._process_executors.get(plugin_name)
            if executor is None:
                context = mp.get_context("spawn")
                executor = ProcessPoolExecutor(
                    max_workers=self.process_pool_size,
                    mp_context=context,
                )
                self._process_executors[plugin_name] = executor
            return executor

    @property
    def plugin_load_failures(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._plugin_load_failures]

    def _record_plugin_load_failure(
        self,
        *,
        plugin_name: str,
        source_type: str,
        file_path: Path | None,
        reason: str,
    ) -> None:
        self._plugin_load_failures.append(
            {
                "plugin_name": str(plugin_name or "").strip() or "unknown",
                "source_type": str(source_type or "").strip() or "unknown",
                "file_path": str(file_path) if isinstance(file_path, Path) else "",
                "reason": str(reason or "").strip() or "unknown failure",
            }
        )

    def _strict_packaged_load_guard(self) -> None:
        if not self.strict_packaged_load:
            return
        packaged_failures = [
            item
            for item in self._plugin_load_failures
            if item.get("source_type") == "packaged"
        ]
        if not packaged_failures:
            return

        detail_lines = [
            f"{item.get('plugin_name', 'unknown')}: {item.get('reason', 'unknown failure')}"
            for item in packaged_failures[:10]
        ]
        if len(packaged_failures) > 10:
            detail_lines.append(f"... and {len(packaged_failures) - 10} more")
        raise RuntimeError(
            "strict packaged plugin load failed; packaged plugins must load without skips. "
            + " | ".join(detail_lines)
        )

    def _missing_python_dependencies(
        self,
        dependencies: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        missing: list[dict[str, str]] = []
        for entry in dependencies:
            module_name = str(entry.get("module", "")).strip()
            if not module_name:
                continue
            if importlib.util.find_spec(module_name) is not None:
                continue
            missing.append(
                {
                    "module": module_name,
                    "package": str(entry.get("package") or module_name).strip(),
                    "extra": str(entry.get("extra") or "").strip(),
                }
            )
        return missing

    def _missing_python_dependency_text(
        self,
        dependencies: list[dict[str, str]],
    ) -> str:
        chunks: list[str] = []
        for dependency in dependencies:
            module_name = str(dependency.get("module", "")).strip()
            package_name = str(dependency.get("package") or module_name).strip()
            extra_name = str(dependency.get("extra") or "").strip()
            hint = f"pip install {package_name}"
            if extra_name:
                hint += f" or pip install .[{extra_name}]"
            chunks.append(f"{module_name} ({hint})")
        return "; ".join(chunks) if chunks else "unknown dependency"

    def _load_legacy_python_plugins(self):
        for file_path in self._iter_legacy_plugin_files():
            if file_path.name.startswith("__"):
                continue
            plugin_name = file_path.stem
            optional_deps = LEGACY_PLUGIN_OPTIONAL_PYTHON_DEPENDENCIES.get(
                plugin_name, []
            )
            if optional_deps:
                missing_optional_deps = self._missing_python_dependencies(optional_deps)
                if missing_optional_deps:
                    reason = (
                        "missing optional python dependency: "
                        + self._missing_python_dependency_text(missing_optional_deps)
                    )
                    self._record_plugin_load_failure(
                        plugin_name=plugin_name,
                        source_type="legacy",
                        file_path=file_path,
                        reason=reason,
                    )
                    logging.warning(
                        "Skipping plugin module %s due to %s",
                        file_path,
                        reason,
                    )
                    continue
            plugin = self._load_plugin_from_file(
                module_name=f"legacy_{plugin_name}",
                file_path=file_path,
            )
            if plugin is None:
                self._record_plugin_load_failure(
                    plugin_name=plugin_name,
                    source_type="legacy",
                    file_path=file_path,
                    reason="import/get_plugin/plugin init failure",
                )
                continue
            self._register_loaded_plugin(
                name=plugin_name,
                plugin=plugin,
                module_name=f"legacy_{plugin_name}",
                file_path=file_path,
                manifest=None,
            )
            logging.info("Loaded legacy plugin: %s", plugin_name)

    def _load_packaged_plugins_from_manifest(self):
        packaged_manifests: dict[str, tuple[dict[str, Any], Path]] = {}
        for manifest_path in self._iter_packaged_manifest_paths():
            try:
                manifest = self._read_and_validate_manifest(manifest_path)
            except ValueError as exc:
                self._record_plugin_load_failure(
                    plugin_name=manifest_path.parent.name,
                    source_type="packaged",
                    file_path=manifest_path,
                    reason=f"manifest validation error: {exc}",
                )
                logging.warning(
                    "Skipping packaged plugin %s due to manifest validation error: %s",
                    manifest_path.parent.name,
                    exc,
                )
                continue

            plugin_name = manifest["name"]
            if plugin_name in packaged_manifests:
                self._record_plugin_load_failure(
                    plugin_name=plugin_name,
                    source_type="packaged",
                    file_path=manifest_path,
                    reason=f"duplicate manifest name: {plugin_name}",
                )
                logging.warning(
                    "Skipping packaged plugin %s due to duplicate manifest name: %s",
                    manifest_path.parent.name,
                    plugin_name,
                )
                continue
            packaged_manifests[plugin_name] = (manifest, manifest_path)

        dependency_issues = self.check_packaged_plugin_dependency_compatibility(
            manifests={
                plugin_name: manifest
                for plugin_name, (manifest, _) in packaged_manifests.items()
            }
        )

        for plugin_name, (manifest, manifest_path) in sorted(
            packaged_manifests.items()
        ):
            issues = dependency_issues.get(plugin_name, [])
            if issues:
                self._record_plugin_load_failure(
                    plugin_name=plugin_name,
                    source_type="packaged",
                    file_path=manifest_path,
                    reason="dependency preflight error: " + "; ".join(issues),
                )
                logging.warning(
                    "Skipping packaged plugin %s due to dependency preflight error: %s",
                    plugin_name,
                    "; ".join(issues),
                )
                continue

            entry_path = manifest_path.parent / manifest["entry"]
            plugin = self._load_plugin_from_file(
                module_name=f"packaged_{plugin_name}",
                file_path=entry_path,
                manifest=manifest,
            )
            if plugin is None:
                self._record_plugin_load_failure(
                    plugin_name=plugin_name,
                    source_type="packaged",
                    file_path=entry_path,
                    reason="import/get_plugin/plugin init failure",
                )
                continue

            self._register_loaded_plugin(
                name=plugin_name,
                plugin=plugin,
                module_name=f"packaged_{plugin_name}",
                file_path=entry_path,
                manifest=manifest,
            )
            logging.info("Loaded packaged plugin: %s", plugin_name)

        self._strict_packaged_load_guard()

    def _register_loaded_plugin(
        self,
        *,
        name: str,
        plugin: Any,
        module_name: str,
        file_path: Path,
        manifest: dict[str, Any] | None,
    ) -> None:
        self.plugins[name] = plugin
        if manifest is not None:
            self._plugin_manifests[name] = manifest
        self._plugin_sources[name] = {
            "module_name": module_name,
            "file_path": file_path,
            "manifest": manifest,
        }
        state = self._plugin_crash_state.setdefault(
            name,
            {
                "consecutive_crashes": 0,
                "isolated": False,
                "last_error": None,
            },
        )
        state["isolated"] = False

    def _legacy_plugin_names(self) -> set[str]:
        names: set[str] = set()
        for file_path in self._iter_legacy_plugin_files():
            if file_path.name.startswith("__"):
                continue
            names.add(file_path.stem)
        return names

    def check_packaged_plugin_dependency_compatibility(
        self, manifests: dict[str, dict[str, Any]] | None = None
    ) -> dict[str, list[str]]:
        manifests_by_name = manifests or {}
        if manifests is None:
            for manifest_path in self._iter_packaged_manifest_paths():
                try:
                    manifest = self._read_and_validate_manifest(manifest_path)
                except ValueError:
                    continue
                manifests_by_name[manifest["name"]] = manifest

        issues_by_plugin: dict[str, list[str]] = {}
        legacy_plugins = self._legacy_plugin_names()

        for plugin_name, manifest in manifests_by_name.items():
            raw_dependencies = manifest.get("dependencies", [])
            if not isinstance(raw_dependencies, list):
                issues_by_plugin.setdefault(plugin_name, []).append(
                    "dependencies must be an array"
                )
                continue

            for dependency in raw_dependencies:
                if not isinstance(dependency, dict):
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        "dependency entry must be an object"
                    )
                    continue

                dependency_name = str(dependency.get("name", "")).strip()
                dependency_version = str(dependency.get("version", "")).strip()
                if not dependency_name or not dependency_version:
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        "dependency entries require non-empty name/version"
                    )
                    continue

                if dependency_name == plugin_name:
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        f"self dependency is not allowed ({dependency_name})"
                    )
                    continue

                dependency_manifest = manifests_by_name.get(dependency_name)
                if dependency_manifest is None:
                    if dependency_name in legacy_plugins:
                        if dependency_version != "*":
                            issues_by_plugin.setdefault(plugin_name, []).append(
                                (
                                    f"legacy dependency {dependency_name} only supports "
                                    "version='*' (no manifest version metadata)"
                                )
                            )
                        continue
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        f"missing dependency plugin: {dependency_name}"
                    )
                    continue

                actual_version = str(dependency_manifest.get("version", "")).strip()
                if not _is_dependency_version_compatible(
                    dependency_version,
                    actual_version,
                ):
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        (
                            f"incompatible dependency {dependency_name}: "
                            f"required {dependency_version}, found {actual_version}"
                        )
                    )

            raw_python_dependencies = manifest.get("python_dependencies", [])
            if not isinstance(raw_python_dependencies, list):
                issues_by_plugin.setdefault(plugin_name, []).append(
                    "python_dependencies must be an array"
                )
                continue
            normalized_python_dependencies: list[dict[str, str]] = []
            for dependency in raw_python_dependencies:
                if not isinstance(dependency, dict):
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        "python dependency entry must be an object"
                    )
                    continue
                module_name = str(dependency.get("module", "")).strip()
                if not module_name:
                    issues_by_plugin.setdefault(plugin_name, []).append(
                        "python dependency entries require non-empty module"
                    )
                    continue
                normalized_python_dependencies.append(
                    {
                        "module": module_name,
                        "package": str(
                            dependency.get("package") or module_name
                        ).strip(),
                        "extra": str(dependency.get("extra") or "").strip(),
                    }
                )
            missing_python = self._missing_python_dependencies(
                normalized_python_dependencies
            )
            for dependency in missing_python:
                module_name = dependency.get("module", "unknown")
                package_name = dependency.get("package", module_name)
                extra_name = dependency.get("extra", "")
                hint = f"pip install {package_name}"
                if extra_name:
                    hint += f" or pip install .[{extra_name}]"
                issues_by_plugin.setdefault(plugin_name, []).append(
                    f"missing python dependency module '{module_name}' ({hint})"
                )

        return issues_by_plugin

    def _read_and_validate_manifest(self, manifest_path: Path) -> dict[str, Any]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")

        for field_name, field_type in PLUGIN_MANIFEST_REQUIRED_FIELDS.items():
            value = manifest.get(field_name)
            if not isinstance(value, field_type):
                raise ValueError(
                    f"manifest field {field_name!r} must be {field_type.__name__}"
                )
            if field_type is str and not value.strip():
                raise ValueError(f"manifest field {field_name!r} must be non-empty")

        if manifest["schemaName"] != PLUGIN_MANIFEST_SCHEMA_NAME:
            raise ValueError(
                f"schemaName must be {PLUGIN_MANIFEST_SCHEMA_NAME!r}, got {manifest['schemaName']!r}"
            )
        if manifest["schemaVersion"] != PLUGIN_MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                "unsupported schemaVersion "
                f"{manifest['schemaVersion']!r}; expected {PLUGIN_MANIFEST_SCHEMA_VERSION!r}"
            )
        if manifest["type"] != "plugin":
            raise ValueError("manifest type must be 'plugin'")

        entry = manifest["entry"].strip()
        if Path(entry).is_absolute():
            raise ValueError("entry must be relative")
        entry_parts = Path(entry).parts
        if ".." in entry_parts:
            raise ValueError("entry cannot traverse parent directories")
        if not entry.endswith(".py"):
            raise ValueError("entry must target a .py module")

        entry_path = (manifest_path.parent / entry).resolve()
        plugin_root = manifest_path.parent.resolve()
        if plugin_root not in entry_path.parents and entry_path != plugin_root:
            raise ValueError("entry must resolve within plugin directory")
        if not entry_path.exists():
            raise ValueError(f"entry module not found: {entry}")

        capabilities = manifest.get("capabilities", [])
        for index, capability in enumerate(capabilities):
            if not isinstance(capability, dict):
                raise ValueError(f"capabilities[{index}] must be an object")
            for field_name, field_type in PLUGIN_CAPABILITY_REQUIRED_FIELDS.items():
                value = capability.get(field_name)
                if not isinstance(value, field_type):
                    raise ValueError(
                        f"capabilities[{index}].{field_name} must be {field_type.__name__}"
                    )
                if field_type is str and not value.strip():
                    raise ValueError(
                        f"capabilities[{index}].{field_name} must be non-empty"
                    )

        raw_dependencies = manifest.get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            raise ValueError(
                "manifest field 'dependencies' must be an array when provided"
            )
        normalized_dependencies: list[dict[str, str]] = []
        for index, dependency in enumerate(raw_dependencies):
            if not isinstance(dependency, dict):
                raise ValueError(f"dependencies[{index}] must be an object")
            for field_name, field_type in PLUGIN_DEPENDENCY_REQUIRED_FIELDS.items():
                value = dependency.get(field_name)
                if not isinstance(value, field_type) or not value.strip():
                    raise ValueError(
                        f"dependencies[{index}].{field_name} must be non-empty {field_type.__name__}"
                    )
            dependency_name = dependency["name"].strip()
            dependency_version = dependency["version"].strip()
            if not _is_supported_dependency_version_spec(dependency_version):
                raise ValueError(
                    (
                        f"dependencies[{index}].version must be semver, ==semver, "
                        ">=semver, or '*'"
                    )
                )
            normalized_dependencies.append(
                {"name": dependency_name, "version": dependency_version}
            )
        manifest["dependencies"] = normalized_dependencies

        raw_python_dependencies = manifest.get("python_dependencies", [])
        if not isinstance(raw_python_dependencies, list):
            raise ValueError(
                "manifest field 'python_dependencies' must be an array when provided"
            )
        normalized_python_dependencies: list[dict[str, str]] = []
        for index, dependency in enumerate(raw_python_dependencies):
            if not isinstance(dependency, dict):
                raise ValueError(f"python_dependencies[{index}] must be an object")
            module_name = str(dependency.get("module", "")).strip()
            if not module_name:
                raise ValueError(
                    f"python_dependencies[{index}].module must be a non-empty string"
                )
            package_name = str(dependency.get("package") or module_name).strip()
            if not package_name:
                package_name = module_name
            extra_name = str(dependency.get("extra") or "").strip()
            normalized_python_dependencies.append(
                {
                    "module": module_name,
                    "package": package_name,
                    "extra": extra_name,
                }
            )
        manifest["python_dependencies"] = normalized_python_dependencies

        raw_permissions = manifest.get("permissions", list(DEFAULT_PLUGIN_PERMISSIONS))
        if not isinstance(raw_permissions, list):
            raise ValueError(
                "manifest field 'permissions' must be an array when provided"
            )
        normalized_permissions: list[str] = []
        for index, permission in enumerate(raw_permissions):
            if not isinstance(permission, str) or not permission.strip():
                raise ValueError(f"permissions[{index}] must be a non-empty string")
            normalized = permission.strip().lower()
            if normalized not in PLUGIN_PERMISSION_TIERS:
                raise ValueError(
                    "permissions["
                    f"{index}] must be one of: {', '.join(sorted(PLUGIN_PERMISSION_TIERS))}"
                )
            if normalized not in normalized_permissions:
                normalized_permissions.append(normalized)
        if not normalized_permissions:
            normalized_permissions = list(DEFAULT_PLUGIN_PERMISSIONS)
        manifest["permissions"] = normalized_permissions

        raw_timeout_seconds = manifest.get("timeout_seconds", None)
        if raw_timeout_seconds is None:
            manifest["timeout_seconds"] = None
        elif isinstance(raw_timeout_seconds, bool) or not isinstance(
            raw_timeout_seconds, (int, float)
        ):
            raise ValueError(
                "manifest field 'timeout_seconds' must be a number when provided"
            )
        elif float(raw_timeout_seconds) <= 0:
            raise ValueError(
                "manifest field 'timeout_seconds' must be greater than zero"
            )
        else:
            manifest["timeout_seconds"] = float(raw_timeout_seconds)

        return manifest

    def _load_plugin_from_file(
        self,
        module_name: str,
        file_path: Path,
        manifest: dict[str, Any] | None = None,
    ):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            logging.warning(
                "Skipping plugin module %s: unable to create import spec", file_path
            )
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            logging.warning(
                "Skipping plugin module %s due to import error: %s", file_path, exc
            )
            return None

        if hasattr(module, "get_plugin"):
            try:
                return module.get_plugin()
            except Exception as exc:
                logging.warning(
                    "Skipping plugin module %s due to get_plugin failure: %s",
                    file_path,
                    exc,
                )
                return None

        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None:
            logging.warning(
                "Skipping plugin module %s: missing get_plugin/Plugin", file_path
            )
            return None

        try:
            return (
                plugin_cls(manifest=manifest) if manifest is not None else plugin_cls()
            )
        except TypeError:
            try:
                return plugin_cls()
            except Exception as exc:
                logging.warning(
                    "Skipping plugin module %s due to Plugin init failure: %s",
                    file_path,
                    exc,
                )
                return None
        except Exception as exc:
            logging.warning(
                "Skipping plugin module %s due to Plugin init failure: %s",
                file_path,
                exc,
            )
            return None

    def _plugin_permissions(self, name: str, plugin: Any | None = None) -> list[str]:
        manifest = self._plugin_manifests.get(name, {})
        if isinstance(manifest, dict):
            manifest_permissions = _normalize_permissions(manifest.get("permissions"))
            if manifest_permissions:
                return manifest_permissions
        plugin_instance = plugin if plugin is not None else self.plugins.get(name)
        plugin_permissions = _normalize_permissions(
            getattr(plugin_instance, "permissions", None)
        )
        if plugin_permissions:
            return plugin_permissions
        return list(DEFAULT_PLUGIN_PERMISSIONS)

    def _plugin_capabilities(self, name: str, plugin: Any | None = None) -> list[str]:
        manifest = self._plugin_manifests.get(name, {})
        if isinstance(manifest, dict):
            raw_capabilities = manifest.get("capabilities", [])
            if isinstance(raw_capabilities, list):
                manifest_capabilities = [
                    str(item.get("name", "")).strip()
                    for item in raw_capabilities
                    if isinstance(item, dict)
                ]
                capabilities = [item for item in manifest_capabilities if item]
                if capabilities:
                    return capabilities

        plugin_instance = plugin if plugin is not None else self.plugins.get(name)
        raw_plugin_capabilities = getattr(plugin_instance, "capabilities", None)
        if isinstance(raw_plugin_capabilities, (list, tuple, set)):
            capabilities = [
                str(item).strip()
                for item in raw_plugin_capabilities
                if str(item).strip()
            ]
            if capabilities:
                return capabilities
        return []

    def _permissions_allowed(self, permissions: list[str]) -> tuple[bool, list[str]]:
        checker = getattr(
            self.permission_policy, "are_plugin_permissions_allowed", None
        )
        if callable(checker):
            allowed, denied = checker(permissions)
            return bool(allowed), list(denied)
        return True, []

    def _plugin_timeout_seconds(
        self, name: str, plugin: Any, override: Any = None
    ) -> float:
        if isinstance(override, (int, float)) and not isinstance(override, bool):
            if float(override) > 0:
                return float(override)

        manifest = self._plugin_manifests.get(name, {})
        manifest_timeout = (
            manifest.get("timeout_seconds") if isinstance(manifest, dict) else None
        )
        if isinstance(manifest_timeout, (int, float)) and not isinstance(
            manifest_timeout, bool
        ):
            if float(manifest_timeout) > 0:
                return float(manifest_timeout)

        plugin_timeout = getattr(plugin, "timeout_seconds", None)
        if isinstance(plugin_timeout, (int, float)) and not isinstance(
            plugin_timeout, bool
        ):
            if float(plugin_timeout) > 0:
                return float(plugin_timeout)
        return DEFAULT_PLUGIN_TIMEOUT_SECONDS

    def _plugin_crash_state_for(self, name: str) -> dict[str, Any]:
        return self._plugin_crash_state.setdefault(
            name,
            {
                "consecutive_crashes": 0,
                "isolated": False,
                "last_error": None,
            },
        )

    def _is_plugin_isolated(self, name: str) -> bool:
        state = self._plugin_crash_state_for(name)
        return bool(state.get("isolated", False))

    def _mark_plugin_execution_success(self, name: str) -> None:
        state = self._plugin_crash_state_for(name)
        state["consecutive_crashes"] = 0
        state["isolated"] = False
        state["last_error"] = None
        self._restart_budget.reset(name)

    def _record_plugin_crash(self, name: str, error: Exception) -> None:
        state = self._plugin_crash_state_for(name)
        state["consecutive_crashes"] = int(state.get("consecutive_crashes", 0)) + 1
        state["last_error"] = str(error)
        if not self._restart_budget.can_attempt(name):
            state["isolated"] = True

    def _attempt_plugin_restart(self, name: str) -> bool:
        source = self._plugin_sources.get(name)
        if not isinstance(source, dict):
            return False

        state = self._plugin_crash_state_for(name)
        if not self._restart_budget.can_attempt(name):
            state["isolated"] = True
            return False

        attempt = self._restart_budget.record_attempt(name)
        module_name = f"{source['module_name']}_restart_{attempt}"
        plugin = self._load_plugin_from_file(
            module_name=module_name,
            file_path=source["file_path"],
            manifest=source.get("manifest"),
        )
        if plugin is None:
            if not self._restart_budget.can_attempt(name):
                state["isolated"] = True
            return False

        self.plugins[name] = plugin
        state["consecutive_crashes"] = 0
        state["isolated"] = False
        state["last_error"] = None
        return True

    def _plugin_health_snapshot(self, name: str) -> dict[str, Any]:
        state = self._plugin_crash_state_for(name)
        restart_attempts = self._restart_budget.attempts(name)
        isolated = bool(state.get("isolated", False))
        if isolated:
            health_state = "isolated"
        elif int(state.get("consecutive_crashes", 0)) > 0:
            health_state = "degraded"
        else:
            health_state = "healthy"
        return {
            "health_state": health_state,
            "consecutive_crashes": int(state.get("consecutive_crashes", 0)),
            "restart_attempts": restart_attempts,
            "restart_attempts_remaining": max(
                0, int(self._restart_budget.max_attempts) - int(restart_attempts)
            ),
            "isolated": isolated,
            "last_error": state.get("last_error"),
        }

    @staticmethod
    def _is_pickle_related_error_text(text: str) -> bool:
        lowered = str(text or "").lower()
        if "pickle" in lowered:
            return True
        return "serializ" in lowered

    @staticmethod
    def _is_process_serialization_error(
        error: Exception | None = None,
        *,
        error_type: str = "",
        error_text: str = "",
    ) -> bool:
        if isinstance(error, (pickle.PicklingError, AttributeError)):
            return True
        if isinstance(error, TypeError) and PluginManager._is_pickle_related_error_text(
            str(error)
        ):
            return True

        normalized_type = str(error_type or "").strip().lower()
        if normalized_type in {"picklingerror", "pickleerror"}:
            return True
        if normalized_type in {
            "typeerror",
            "attributeerror",
        } and PluginManager._is_pickle_related_error_text(error_text):
            return True
        return PluginManager._is_pickle_related_error_text(error_text)

    def _execute_plugin_thread_mode(
        self,
        *,
        name: str,
        plugin: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        timeout_seconds: float,
        timeout_cancel_hook: Callable[[], None] | None = None,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(plugin.execute, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            if callable(timeout_cancel_hook):
                try:
                    timeout_cancel_hook()
                except Exception as cancel_error:
                    logging.warning(
                        "Plugin %s cancel hook failed after timeout: %s",
                        name,
                        cancel_error,
                    )
            raise _PluginExecutionTimeout(timeout_seconds) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _execute_plugin_process_mode(
        self,
        *,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        timeout_seconds: float,
    ) -> Any:
        source = self._plugin_sources.get(name)
        if not isinstance(source, dict):
            raise RuntimeError(
                f"Plugin {name} source metadata unavailable for process execution"
            )

        raw_path = source.get("file_path")
        file_path = raw_path if isinstance(raw_path, Path) else Path(str(raw_path))
        module_name = f"{source.get('module_name', f'plugin_{name}')}_exec"
        manifest = source.get("manifest")
        future = None
        for attempt in (1, 2):
            executor = self._process_executor_for_run(name)
            try:
                future = executor.submit(
                    _execute_plugin_in_worker,
                    module_name=module_name,
                    file_path=str(file_path),
                    manifest=manifest if isinstance(manifest, dict) else None,
                    args=args,
                    kwargs=kwargs,
                )
                break
            except Exception as exc:
                if self._is_process_serialization_error(exc, error_text=str(exc)):
                    raise _PluginProcessSerializationError(str(exc)) from exc
                if isinstance(exc, BrokenProcessPool) and attempt == 1:
                    self._reset_process_executor(name, "broken process pool on submit")
                    continue
                raise
        if future is None:
            raise RuntimeError(f"Plugin {name} execution submission failed")
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            self._reset_process_executor(name, "plugin timeout")
            raise _PluginExecutionTimeout(timeout_seconds) from exc
        except Exception as exc:
            if self._is_process_serialization_error(exc, error_text=str(exc)):
                raise _PluginProcessSerializationError(str(exc)) from exc
            if isinstance(exc, BrokenProcessPool):
                self._reset_process_executor(name, "broken process pool")
            raise

    def execute_plugin(self, name, *args, **kwargs):
        if name in self.plugins:
            plugin = self.plugins[name]
            if self._is_plugin_isolated(name):
                health = self._plugin_health_snapshot(name)
                return {
                    "error": (
                        f"Plugin {name} is isolated after repeated crashes "
                        "(restart budget exhausted)"
                    ),
                    "code": "PLUGIN_CRASH_ISOLATED",
                    "health": health,
                }
            permissions = self._plugin_permissions(name, plugin)
            allowed, denied_permissions = self._permissions_allowed(permissions)
            if not allowed:
                denied_sorted = sorted({item for item in denied_permissions if item})
                denied_text = ", ".join(denied_sorted) or "unknown"
                return {
                    "error": (
                        f"Plugin {name} denied by policy for permission tiers: "
                        f"{denied_text}"
                    ),
                    "code": "PLUGIN_PERMISSION_DENIED",
                    "required_permissions": permissions,
                    "denied_permissions": denied_sorted,
                }
            if hasattr(plugin, "execute"):
                timeout_override = kwargs.pop("__merlin_timeout_seconds", None)
                raw_task_id = kwargs.pop("__merlin_task_id", None)
                task_id = (
                    raw_task_id
                    if isinstance(raw_task_id, int) and raw_task_id > 0
                    else None
                )

                cancel_hook = getattr(plugin, "cancel", None)
                timeout_seconds = self._plugin_timeout_seconds(
                    name,
                    plugin,
                    override=timeout_override,
                )
                registered_cancel_hook: Callable[[], None] | None = None
                register_cancellation_hook = getattr(
                    task_manager,
                    "register_cancellation_hook",
                    None,
                )
                clear_cancellation_hook = getattr(
                    task_manager,
                    "clear_cancellation_hook",
                    None,
                )

                if self.execution_mode == "process":
                    registered_cancel_hook = lambda: self._reset_process_executor(
                        name,
                        "task cancellation",
                    )
                elif callable(cancel_hook):
                    registered_cancel_hook = cancel_hook

                if (
                    task_id is not None
                    and registered_cancel_hook is not None
                    and callable(register_cancellation_hook)
                ):
                    register_cancellation_hook(
                        task_id, registered_cancel_hook
                    )
                try:
                    if self.execution_mode == "process":
                        result = self._execute_plugin_process_mode(
                            name=name,
                            args=args,
                            kwargs=kwargs,
                            timeout_seconds=timeout_seconds,
                        )
                    else:
                        result = self._execute_plugin_thread_mode(
                            name=name,
                            plugin=plugin,
                            args=args,
                            kwargs=kwargs,
                            timeout_seconds=timeout_seconds,
                            timeout_cancel_hook=(
                                cancel_hook if callable(cancel_hook) else None
                            ),
                        )
                    self._mark_plugin_execution_success(name)
                    return result
                except _PluginExecutionTimeout as timeout_error:
                    if task_id is not None:
                        task_manager.update_task_status(task_id, "Timed Out")
                    return {
                        "error": (
                            f"Plugin {name} timed out after {round(timeout_error.timeout_seconds, 3)}s"
                        ),
                        "code": "PLUGIN_TIMEOUT",
                        "timeout_seconds": round(timeout_error.timeout_seconds, 3),
                    }
                except _PluginProcessSerializationError as serialization_error:
                    if task_id is not None:
                        task_manager.update_task_status(task_id, "Failed")
                    return {
                        "error": (
                            "Plugin "
                            + name
                            + " process serialization failed: "
                            + str(serialization_error)
                        ),
                        "code": "PLUGIN_PROCESS_SERIALIZATION_ERROR",
                        "execution_mode": self.execution_mode,
                    }
                except Exception as exc:
                    self._record_plugin_crash(name, exc)
                    restarted = self._attempt_plugin_restart(name)
                    if not restarted and self._is_plugin_isolated(name):
                        return {
                            "error": (
                                f"Plugin {name} is isolated after repeated crashes "
                                "(restart budget exhausted)"
                            ),
                            "code": "PLUGIN_CRASH_ISOLATED",
                            "health": self._plugin_health_snapshot(name),
                        }
                    raise
                finally:
                    if task_id is not None and callable(clear_cancellation_hook):
                        clear_cancellation_hook(task_id)
            return {"error": f"Plugin {name} does not expose execute"}
        return {"error": f"Plugin {name} not found"}

    def list_plugin_info(self):
        info: dict[str, dict[str, Any]] = {}
        for name, plugin in self.plugins.items():
            if hasattr(plugin, "get_info"):
                plugin_info = plugin.get_info()
                if not isinstance(plugin_info, dict):
                    plugin_info = {"name": name}
                plugin_info = dict(plugin_info)
                plugin_info["permissions"] = self._plugin_permissions(name, plugin)
                plugin_info["capabilities"] = self._plugin_capabilities(name, plugin)
                plugin_info["timeout_seconds"] = self._plugin_timeout_seconds(
                    name,
                    plugin,
                )
                manifest = self._plugin_manifests.get(name, {})
                plugin_info["dependencies"] = (
                    list(manifest.get("dependencies", []))
                    if isinstance(manifest, dict)
                    else []
                )
                plugin_info["python_dependencies"] = (
                    list(manifest.get("python_dependencies", []))
                    if isinstance(manifest, dict)
                    else []
                )
                plugin_info.update(self._plugin_health_snapshot(name))
                info[name] = plugin_info
                continue

            manifest = self._plugin_manifests.get(name, {})
            info[name] = {
                "name": manifest.get("name", name),
                "description": manifest.get("description", ""),
                "version": manifest.get("version", ""),
                "author": manifest.get("author", "Unknown"),
                "category": manifest.get("type", "plugin"),
                "permissions": self._plugin_permissions(name, plugin),
                "capabilities": self._plugin_capabilities(name, plugin),
                "timeout_seconds": self._plugin_timeout_seconds(name, plugin),
                "dependencies": list(manifest.get("dependencies", [])),
                "python_dependencies": list(manifest.get("python_dependencies", [])),
            }
            info[name].update(self._plugin_health_snapshot(name))
        return info

    def close(self) -> None:
        self._reset_all_process_executors("manager close")

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pm = PluginManager()
    pm.load_plugins()
    print(f"Loaded plugins: {list(pm.plugins.keys())}")

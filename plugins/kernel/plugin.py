from __future__ import annotations

from typing import Any, Dict, List

from core.plugin_manifest import get_hive_metadata
from loguru import logger


from pathlib import Path
import json
import time


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()
        self.name = f"{self.hive}.kernel"
        self.root = Path(__file__).resolve().parents[2]

    def commands(self) -> Dict[str, Any]:
        return {
            f"{self.hive}.hive.status": self.hive_status,
            f"{self.hive}.hive.plugins": self.hive_plugins,
            f"{self.hive}.round.table": self.round_table,
            f"{self.hive}.planning.audit": self.planning_audit,
            f"{self.hive}.ops.evaluate": self.evaluate_maturity,
            f"{self.hive}.ops.discover": self.deep_discovery,
        }

    def deep_discovery(self) -> Dict[str, Any]:
        """Trigger a deep discovery evaluation."""
        import subprocess
        import sys
        script = self.root / "scripts" / "discovery.py"
        try:
            subprocess.run([sys.executable, str(script)], check=True)
            return {"ok": True, "message": "Merlin deep discovery complete."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def evaluate_maturity(self) -> Dict[str, Any]:
        """Trigger a maturity and benchmark evaluation."""
        import subprocess
        import sys
        script = self.root / "scripts" / "evaluate.py"
        try:
            subprocess.run([sys.executable, str(script)], check=True)
            return {"ok": True, "message": "Merlin strategic evaluation complete."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def round_table(self) -> Dict[str, Any]:
        """Summary of current Merlin intelligence and planning activity."""
        history_dir = self.root / "merlin_chat_history"
        bench_dir = self.root / "artifacts" / "benchmarks"
        
        # Count active sessions
        sessions = len(list(history_dir.glob("*.json"))) if history_dir.exists() else 0
        
        # Check model usage
        usage_path = self.root / "artifacts" / "model_usage.json"
        usage = {}
        if usage_path.exists():
            try:
                usage = json.loads(usage_path.read_text(encoding="utf-8"))
            except: pass

        return {
            "ok": True,
            "status": "Unified Strategy",
            "intelligence": {
                "active_sessions": sessions,
                "model_usage_summary": usage,
                "last_planning_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "benchmarks_available": len(list(bench_dir.glob("*.json"))) if bench_dir.exists() else 0
            }
        }

    def planning_audit(self) -> Dict[str, Any]:
        """Audit the integrity of Merlin's planning and memory systems."""
        checks = {
            "vector_memory": self.root / "merlin_vector_memory.py",
            "planning_tasks": self.root / "merlin_tasks.py",
            "intelligence_integration": self.root / "merlin_intelligence_integration.py"
        }
        
        results = {}
        for name, path in checks.items():
            results[name] = "✅ OK" if path.exists() else "❌ MISSING"

        return {
            "ok": True,
            "phase": "Intelligence Audit",
            "results": results,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    def hive_status(self) -> Dict[str, Any]:
        plugins = self._collect_plugins()
        return {
            "ok": True,
            "hive": self.hive,
            "plugin_count": len(plugins),
            "plugins": plugins,
        }

    def hive_plugins(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "hive": self.hive,
            "plugins": self._collect_plugins(),
        }

    def _collect_plugins(self) -> List[str]:
        if not self.hub or not hasattr(self.hub, "hives"):
            return []
        grouped = self.hub.hives
        metas = grouped.get(self.hive, [])
        return sorted([meta.name for meta in metas])

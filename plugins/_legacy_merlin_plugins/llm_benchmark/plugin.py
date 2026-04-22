from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from core.plugin_manifest import get_hive_metadata
from loguru import logger

MERLIN_ROOT = Path(__file__).resolve().parents[2]
if str(MERLIN_ROOT) not in sys.path:
    sys.path.insert(0, str(MERLIN_ROOT))

try:
    import requests
    import merlin_settings as settings
except Exception as exc:  # pragma: no cover - import guard
    requests = None
    settings = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class Plugin:
    def __init__(self, hub: Any = None, manifest: Dict[str, Any] | None = None):
        self.hub = hub
        self.manifest = manifest or {}
        hive_meta = get_hive_metadata(self.manifest)
        self.hive = str(hive_meta.get("hive") or "merlin").lower()

    def commands(self) -> Dict[str, Any]:
        return {"merlin.llm.benchmark": self.benchmark_llm}

    def benchmark_llm(
        self,
        prompt: str = "Explain the importance of modular software architecture.",
        iterations: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 200,
        model: str = "",
        timeout_sec: int = 30,
    ) -> Dict[str, Any]:
        if requests is None or settings is None:
            return {
                "ok": False,
                "error": f"merlin_benchmark import failed: {_IMPORT_ERROR}",
            }

        raw_url = getattr(settings, "LM_STUDIO_URL", "")
        if not raw_url:
            return {"ok": False, "error": "LM_STUDIO_URL not configured."}

        base_url = self._base_url(raw_url)
        target_url = self._resolve_endpoint(raw_url)
        model_name = model or getattr(settings, "OPENAI_MODEL", "")
        if not model_name:
            return {"ok": False, "error": "OPENAI_MODEL not configured."}

        available_models = self._fetch_models(base_url, timeout_sec)
        model_selected, used_fallback = self._select_model(
            model_name, available_models
        )
        if used_fallback:
            logger.warning(
                f"Requested model '{model_name}' not available; using '{model_selected}'"
            )
        model_name = model_selected

        latencies: List[float] = []
        tokens_per_sec: List[float] = []
        errors: List[str] = []
        responses: List[str] = []

        for i in range(max(1, int(iterations))):
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            }
            start_time = time.time()
            try:
                response = requests.post(target_url, json=payload, timeout=timeout_sec)
                end_time = time.time()
                data = None
                try:
                    data = response.json()
                except Exception:
                    data = None

                if response.status_code >= 400:
                    errors.append(self._format_error(data, response.text))
                    continue

                if isinstance(data, dict) and data.get("error"):
                    errors.append(self._format_error(data, ""))
                    continue

                content = self._extract_content(data)
                if not content:
                    errors.append("Response missing content.")
                    continue

                duration = end_time - start_time
                latencies.append(duration)
                responses.append(content)
                token_count = max(1.0, len(content) / 4.0)
                tokens_per_sec.append(token_count / duration)
            except Exception as exc:
                errors.append(str(exc))

        if not latencies:
            return {
                "ok": False,
                "error": "Benchmark failed to collect data.",
                "errors": errors,
                "target_url": target_url,
                "model": model_name,
                "available_models": available_models,
            }

        summary = {
            "avg_latency_s": statistics.mean(latencies),
            "min_latency_s": min(latencies),
            "max_latency_s": max(latencies),
            "avg_tokens_per_sec": (
                statistics.mean(tokens_per_sec) if tokens_per_sec else None
            ),
        }

        if errors:
            logger.warning(f"Merlin benchmark encountered {len(errors)} errors")

        return {
            "ok": True,
            "target_url": target_url,
            "model": model_name,
            "iterations": len(latencies),
            "summary": summary,
            "errors": errors,
            "sample_response": responses[-1] if responses else "",
            "available_models": available_models,
            "model_fallback": used_fallback,
        }

    @staticmethod
    def _resolve_endpoint(raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if not parsed.scheme:
            return raw_url
        path = parsed.path or ""
        if path in {"", "/"}:
            return urljoin(raw_url, "/v1/chat/completions")
        if path.endswith("/v1"):
            return raw_url.rstrip("/") + "/chat/completions"
        if path.endswith("/v1/"):
            return raw_url.rstrip("/") + "chat/completions"
        if path.endswith("/v1/chat/completions") or path.endswith("/v1/completions"):
            return raw_url
        if "/v1/" not in path:
            return urljoin(raw_url.rstrip("/") + "/", "v1/chat/completions")
        return raw_url

    @staticmethod
    def _base_url(raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if not parsed.scheme:
            return raw_url
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base

    @staticmethod
    def _fetch_models(base_url: str, timeout_sec: int) -> List[str]:
        if requests is None:
            return []
        try:
            resp = requests.get(f"{base_url}/v1/models", timeout=timeout_sec)
            if not resp.ok:
                return []
            payload = resp.json()
            return [
                item.get("id")
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception:
            return []

    @staticmethod
    def _select_model(model_name: str, available_models: List[str]) -> tuple[str, bool]:
        if not available_models:
            return model_name, False
        if model_name in available_models:
            return model_name, False
        for candidate in available_models:
            if "embed" in candidate.lower():
                continue
            return candidate, True
        return available_models[0], True

    @staticmethod
    def _extract_content(payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict) and message.get("content"):
                    return str(message.get("content"))
                if choice.get("text"):
                    return str(choice.get("text"))
        return None

    @staticmethod
    def _format_error(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                message = err.get("message") or err.get("type") or err.get("code")
                if message:
                    return str(message)
            if err:
                return str(err)
        return fallback.strip() or "Request failed."

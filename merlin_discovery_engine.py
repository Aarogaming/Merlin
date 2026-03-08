from __future__ import annotations

import hashlib
import json
import os
import errno
import re
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

DISCOVERY_SCHEMA_VERSION = "1.0.0"
DEFAULT_TOP_K = 3
DEFAULT_MIN_SCORE = 0.35
DEFAULT_MAX_RETRIES = 2
DEFAULT_LEASE_TTL_SECONDS = 300
DEFAULT_MAX_BUNDLE_SIZE = 4
DEFAULT_WORKER_ID = "discovery-engine-v1"
DEFAULT_QUEUE_LOCK_TIMEOUT_SECONDS = 10.0
DEFAULT_QUEUE_LOCK_STALE_SECONDS = 30.0
DEFAULT_QUEUE_LOCK_RETRY_SECONDS = 0.02
DEFAULT_QUEUE_LOCK_HEARTBEAT_SECONDS = 5.0
DEFAULT_RSS_TIMEOUT_SECONDS = 8.0
DEFAULT_RSS_MAX_BYTES = 1_000_000
DEFAULT_GITHUB_TIMEOUT_SECONDS = 8.0
DEFAULT_GIT_COMMAND_TIMEOUT_SECONDS = 10.0

PUBLIC_PROFILE = "public"
EXPERIMENTAL_PROFILE = "experimental"
VALID_PROFILES = {PUBLIC_PROFILE, EXPERIMENTAL_PROFILE}

POLICY_ALLOWED = "allowed"
POLICY_BLOCKED = "blocked"
POLICY_STUBBED = "stubbed"

WORK_STATE_NEW = "NEW"
WORK_STATE_CLAIMED = "CLAIMED"
WORK_STATE_DONE = "DONE"
WORK_STATE_FAILED = "FAILED"
WORK_STATE_BLOCKED = "BLOCKED"

PLAN_CREATE = "CREATE"
PLAN_OVERWRITE = "OVERWRITE"
PLAN_SKIP = "SKIP"

DEFAULT_REQUIRED_SECTIONS = (
    "# Summary",
    "# Why This Matters To AAS",
    "# Technical Notes",
    "# Integration Ideas (AAS)",
    "# Risks / Policy Notes",
    "# Action Items",
)

NETWORK_COLLECTORS = {
    "rss",
    "github_trending",
    "github_search",
    "google_trends",
}

OFFLINE_COLLECTORS = {
    "local_fixture",
    "local_cache",
}

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dotnet": ("dotnet", ".net", "c#", "asp.net"),
    "policy": ("policy", "governance", "compliance", "risk"),
    "ocr": ("ocr", "document", "pdf", "vision"),
    "ci": ("ci", "pipeline", "build", "test", "github actions"),
    "ux": ("ux", "ui", "frontend", "design", "accessibility"),
    "llm": ("llm", "model", "inference", "prompt"),
    "security": ("security", "auth", "cve", "vulnerability"),
    "python": ("python", "pypi", "fastapi", "pytest"),
}

SOURCE_TRUST_DEFAULT = {
    "local_fixture": 0.55,
    "local_cache": 0.65,
    "rss": 0.75,
    "github_trending": 0.7,
    "github_search": 0.75,
    "google_trends": 0.7,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _lease_expiry_iso(*, now: datetime, lease_ttl_seconds: int) -> str:
    """Serialize lease expiry with microsecond precision to preserve TTL accuracy."""
    expiry = now + timedelta(seconds=max(1, int(lease_ttl_seconds)))
    return expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _coerce_profile(value: str | None) -> str:
    profile = str(value or PUBLIC_PROFILE).strip().lower()
    if profile not in VALID_PROFILES:
        raise ValueError(
            f"unsupported profile '{value}' (expected one of: {sorted(VALID_PROFILES)})"
        )
    return profile


def _slugify(value: str, *, max_length: int = 80) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        return "untitled"
    return normalized[:max_length].strip("-") or "untitled"


def _hash_text(value: str, *, length: int = 16) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:length]


def canonical_key_for_url(url: str) -> str:
    normalized = str(url or "").strip().lower()
    return f"ck_{_hash_text(normalized, length=24)}"


def _make_seed_id(topic: str, source: str, created_at: str) -> str:
    return f"seed_{_hash_text(f'{topic}|{source}|{created_at}', length=16)}"


def _make_item_id(seed_id: str, canonical_url: str) -> str:
    return f"item_{_hash_text(f'{seed_id}|{canonical_url}', length=16)}"


def _make_topic_id(run_id: str, canonical_key: str) -> str:
    return f"topic_{_hash_text(f'{run_id}|{canonical_key}', length=16)}"


def _make_artifact_id(topic_id: str, artifact_path: str) -> str:
    return f"artifact_{_hash_text(f'{topic_id}|{artifact_path}', length=16)}"


def _make_work_id(seed_id: str) -> str:
    return f"work_{_hash_text(seed_id, length=16)}"


def _make_run_id() -> str:
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: Path, content: str) -> None:
    _ensure_parent(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    _ensure_parent(path)
    lines = [json.dumps(row, sort_keys=True) for row in rows]
    content = "\n".join(lines)
    if content:
        content += "\n"
    _atomic_write_text(path, content)


def _atomic_append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    rows = _read_jsonl(path)
    rows.append(payload)
    _write_jsonl(path, rows)


def _normalize_source_name(source: str) -> str:
    normalized = re.sub(
        r"[^a-zA-Z0-9_\-]+", "_", str(source or "unknown").strip().lower()
    )
    return normalized.strip("_") or "unknown"


def _safe_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0.0
    if parsed > 1:
        return 1.0
    return parsed


def _safe_int(value: Any, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_url_hostname(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    return parsed.netloc.strip().lower() or "rss"


def _markdown_escape(value: str) -> str:
    return str(value or "").replace('"', '\\"')


def _render_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key in (
        "title",
        "date",
        "source",
        "canonical_url",
        "tags",
        "confidence",
        "run_id",
    ):
        value = frontmatter.get(key)
        if isinstance(value, list):
            items = ", ".join(f'"{_markdown_escape(str(item))}"' for item in value)
            lines.append(f"{key}: [{items}]")
        elif isinstance(value, float):
            lines.append(f"{key}: {round(value, 4)}")
        else:
            lines.append(f'{key}: "{_markdown_escape(str(value))}"')
    lines.append("---")
    return "\n".join(lines)


def _extract_required_section_content(markdown: str, heading: str) -> str:
    marker = heading.strip()
    if marker not in markdown:
        return ""
    start = markdown.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    tail = markdown[start:]
    next_match = re.search(r"\n# ", tail)
    if next_match is None:
        return tail.strip()
    return tail[: next_match.start()].strip()


def validate_artifact_markdown(markdown: str) -> dict[str, Any]:
    errors: list[str] = []
    stripped = markdown.strip()
    if not stripped.startswith("---"):
        errors.append("missing frontmatter start marker")

    if stripped.startswith("---"):
        second_marker = stripped.find("\n---", 3)
        if second_marker < 0:
            errors.append("missing frontmatter end marker")

    for section in DEFAULT_REQUIRED_SECTIONS:
        if section not in markdown:
            errors.append(f"missing required section: {section}")
            continue
        content = _extract_required_section_content(markdown, section)
        if not content:
            errors.append(f"section is empty: {section}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _load_seed_payloads(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"seed file not found: {path}")

    if path.suffix.lower() == ".jsonl":
        return _read_jsonl(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("seed file must contain a JSON object, array, or JSONL objects")


def _load_fixture_items(path: Path) -> list[dict[str, Any]]:
    items = _read_jsonl(path)
    if items:
        return items

    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


@dataclass(frozen=True)
class CapabilityDecision:
    decision: str
    reason: str


@dataclass
class DiscoveryPolicy:
    profile: str
    allow_live_automation: bool

    def __post_init__(self) -> None:
        self.profile = _coerce_profile(self.profile)
        self.allow_live_automation = bool(self.allow_live_automation)

    def collector_decision(self, collector_name: str) -> CapabilityDecision:
        normalized = _normalize_source_name(collector_name)
        if normalized in OFFLINE_COLLECTORS:
            return CapabilityDecision(POLICY_ALLOWED, "offline collector enabled")

        if normalized in NETWORK_COLLECTORS:
            if self.profile == PUBLIC_PROFILE:
                return CapabilityDecision(
                    POLICY_BLOCKED,
                    "network collectors are disabled in public profile",
                )
            if not self.allow_live_automation:
                return CapabilityDecision(
                    POLICY_STUBBED,
                    "ALLOW_LIVE_AUTOMATION override set to false",
                )
            return CapabilityDecision(
                POLICY_ALLOWED, "experimental live collector enabled"
            )

        return CapabilityDecision(POLICY_STUBBED, "collector not implemented")

    def publisher_decision(self, publisher_mode: str) -> CapabilityDecision:
        normalized = _normalize_source_name(publisher_mode)
        if normalized in {"stage_only", "stage-only", "staging", "none"}:
            return CapabilityDecision(
                POLICY_ALLOWED, "stage-only publisher is always available"
            )

        if normalized in {"pr", "git", "push"}:
            if self.profile == PUBLIC_PROFILE:
                return CapabilityDecision(
                    POLICY_BLOCKED,
                    "live publisher is disabled in public profile",
                )
            if not self.allow_live_automation:
                return CapabilityDecision(
                    POLICY_STUBBED,
                    "ALLOW_LIVE_AUTOMATION override set to false",
                )
            return CapabilityDecision(
                POLICY_ALLOWED, "experimental live publisher allowed"
            )

        return CapabilityDecision(POLICY_STUBBED, "publisher mode not implemented")


class IMerlinScorer(Protocol):
    def score(
        self, item: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]: ...


class IMerlinSummarizer(Protocol):
    def summarize(
        self,
        topic_bundle: dict[str, Any],
        template: str,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class IMerlinClassifier(Protocol):
    def classify(self, item: dict[str, Any]) -> list[str]: ...


class LocalMerlinAdapter(IMerlinScorer, IMerlinSummarizer, IMerlinClassifier):
    mode = "local"

    def classify(self, item: dict[str, Any]) -> list[str]:
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        tags: list[str] = []
        for tag, keywords in DOMAIN_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                tags.append(tag)
        if not tags:
            tags.append("general")
        return sorted(set(tags))

    def score(self, item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        tags = self.classify(item)
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        source_name = _normalize_source_name(item.get("collector", "local_fixture"))
        source_trust = context.get("source_trust", SOURCE_TRUST_DEFAULT)
        trust_weight = _safe_float(source_trust.get(source_name), default=0.55)

        lexicon = context.get("aas_lexicon", [])
        lexicon_hits = 0
        if isinstance(lexicon, list):
            lexicon_hits = sum(1 for token in lexicon if str(token).lower() in text)

        novelty = min(1.0, 0.2 + 0.1 * len(tags))
        relevance = min(1.0, 0.25 + 0.08 * lexicon_hits + 0.07 * len(tags))
        raw_score = min(1.0, 0.5 * trust_weight + 0.35 * relevance + 0.15 * novelty)
        confidence = min(1.0, 0.45 + 0.2 * trust_weight + 0.05 * len(tags))

        reason = (
            f"source_trust={round(trust_weight, 3)}, "
            f"tags={','.join(tags)}, "
            f"lexicon_hits={lexicon_hits}"
        )

        return {
            "schema_name": "AAS.Discovery.ScoreResult",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "item_id": item.get("item_id"),
            "score": round(raw_score, 4),
            "confidence": round(confidence, 4),
            "model_mode": self.mode,
            "reason": reason,
            "tags": tags,
            "scored_at": _utc_now_iso(),
            "explainability": {
                "source_trust": round(trust_weight, 4),
                "relevance": round(relevance, 4),
                "novelty": round(novelty, 4),
            },
        }

    def summarize(
        self,
        topic_bundle: dict[str, Any],
        template: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        title = (
            str(topic_bundle.get("title", "Untitled Topic")).strip() or "Untitled Topic"
        )
        canonical_url = str(topic_bundle.get("canonical_url", "")).strip()
        tags = topic_bundle.get("tags")
        if not isinstance(tags, list):
            tags = ["general"]

        supporting = topic_bundle.get("supporting_items")
        if not isinstance(supporting, list):
            supporting = []

        snippets: list[str] = []
        for item in supporting[:2]:
            snippet = str(item.get("snippet", "")).strip()
            if snippet:
                snippets.append(snippet)

        summary_text = (
            snippets[0]
            if snippets
            else "Signal collected and normalized by DiscoveryEngine."
        )
        technical_notes = (
            snippets[1]
            if len(snippets) > 1
            else "No secondary technical snippet available."
        )

        actions = [
            "Create a follow-up implementation task in AAS task manager.",
            "Attach this artifact to the next integration planning cycle.",
            "Validate policy posture before enabling live collectors.",
        ]

        markdown = "\n".join(
            [
                "# Summary",
                summary_text,
                "",
                "# Why This Matters To AAS",
                (
                    "This topic intersects with orchestration, policy gating, and durable "
                    "knowledge capture for AAS discovery workflows."
                ),
                "",
                "# Technical Notes",
                technical_notes,
                f"Canonical URL: {canonical_url}",
                "",
                "# Integration Ideas (AAS)",
                "- Route this signal through DiscoveryEngine queue leasing for deterministic retries.",
                "- Use Merlin scoring confidence as a threshold for artifact generation gates.",
                "- Keep indexing in Library-owned JSON index for repo-local portability.",
                "",
                "# Risks / Policy Notes",
                (
                    "Avoid proprietary feed scraping. Respect profile/capability gating and "
                    "explicit ALLOW_LIVE_AUTOMATION approval before live collection or PR publishing."
                ),
                "",
                "# Action Items",
                "- [ ] " + actions[0],
                "- [ ] " + actions[1],
                "- [ ] " + actions[2],
            ]
        )

        return {
            "schema_name": "AAS.Discovery.ArtifactDraft",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "title": title,
            "tags": sorted(set(tags)),
            "confidence": round(
                _safe_float(topic_bundle.get("confidence", 0.5), default=0.5), 4
            ),
            "markdown": markdown,
            "actions": actions,
            "template": template,
        }


class NullMerlinAdapter(IMerlinScorer, IMerlinSummarizer, IMerlinClassifier):
    mode = "null"

    def classify(self, item: dict[str, Any]) -> list[str]:
        _ = item
        return ["general"]

    def score(self, item: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        _ = context
        return {
            "schema_name": "AAS.Discovery.ScoreResult",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "item_id": item.get("item_id"),
            "score": 0.4,
            "confidence": 0.3,
            "model_mode": self.mode,
            "reason": "NullMerlin adapter used (no model available)",
            "tags": ["general"],
            "scored_at": _utc_now_iso(),
            "explainability": {
                "source_trust": 0.0,
                "relevance": 0.0,
                "novelty": 0.0,
            },
        }

    def summarize(
        self,
        topic_bundle: dict[str, Any],
        template: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        _ = template
        _ = context
        title = (
            str(topic_bundle.get("title", "Untitled Topic")).strip() or "Untitled Topic"
        )
        markdown = "\n".join(
            [
                "# Summary",
                "NullMerlin produced a deterministic placeholder summary.",
                "",
                "# Why This Matters To AAS",
                "Keeps pipeline functional in strict offline/no-model environments.",
                "",
                "# Technical Notes",
                "No advanced synthesis performed.",
                "",
                "# Integration Ideas (AAS)",
                "- Swap to LocalMerlin when offline model runtime is available.",
                "",
                "# Risks / Policy Notes",
                "Low-confidence output requires curator review before publishing.",
                "",
                "# Action Items",
                "- [ ] Re-run with LocalMerlin adapter for higher confidence output.",
            ]
        )

        return {
            "schema_name": "AAS.Discovery.ArtifactDraft",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "title": title,
            "tags": ["general"],
            "confidence": 0.3,
            "markdown": markdown,
            "actions": ["Re-run with LocalMerlin adapter"],
            "template": "builtin-null",
        }


class DiscoveryEventBus:
    def __init__(self, events_path: Path, *, no_write: bool = False):
        self.events_path = events_path
        self.no_write = no_write

    def emit(
        self,
        *,
        event_type: str,
        run_id: str,
        payload: dict[str, Any],
        stage: str,
        status: str = "ok",
    ) -> dict[str, Any]:
        envelope = {
            "schema_name": "AAS.Discovery.EventEnvelope",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "event_id": f"evt_{uuid.uuid4().hex}",
            "event_type": event_type,
            "run_id": run_id,
            "timestamp_utc": _utc_now_iso(),
            "stage": stage,
            "status": status,
            "payload": payload,
        }
        if not self.no_write:
            _atomic_append_jsonl(self.events_path, envelope)
        return envelope


class DiscoveryQueue:
    def __init__(self, queue_root: Path, *, no_write: bool = False):
        self.queue_root = queue_root
        self.no_write = no_write
        self.seeds_path = queue_root / "seeds.jsonl"
        self.work_path = queue_root / "work.jsonl"
        self.deadletter_path = queue_root / "deadletter.jsonl"
        self.pause_flag_path = queue_root / ".paused"
        self.lock_path = queue_root / ".queue.lock"

    def _read_lock_payload(self) -> dict[str, Any]:
        try:
            raw = self.lock_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    @staticmethod
    def _pid_is_active(pid_value: Any) -> bool:
        try:
            pid = int(pid_value)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False

        current_pid = os.getpid()
        if pid == current_pid:
            return True

        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = [
                    wintypes.DWORD,
                    wintypes.BOOL,
                    wintypes.DWORD,
                ]
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL

                handle = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    pid,
                )
                if not handle:
                    return False
                kernel32.CloseHandle(handle)
                return True
            except Exception:
                return False

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError as exc:
            err = getattr(exc, "errno", None)
            if err == errno.ESRCH:
                return False
            if err == errno.EPERM:
                return True
            return False
        return True

    def _lock_age_seconds(self) -> float:
        try:
            stat_age_seconds = max(0.0, time.time() - self.lock_path.stat().st_mtime)
        except OSError:
            return 0.0

        lock_payload = self._read_lock_payload()
        heartbeat_at = str(lock_payload.get("heartbeat_at", "")).strip()
        if heartbeat_at:
            heartbeat_dt = _parse_datetime(heartbeat_at)
            if heartbeat_dt is not None:
                heartbeat_age = max(0.0, (_utc_now() - heartbeat_dt).total_seconds())
                return min(stat_age_seconds, heartbeat_age)
        return stat_age_seconds

    def _start_lock_heartbeat(
        self,
        *,
        lock_id: str,
    ) -> tuple[threading.Event, threading.Thread]:
        stop_event = threading.Event()

        def _heartbeat_loop() -> None:
            while not stop_event.wait(DEFAULT_QUEUE_LOCK_HEARTBEAT_SECONDS):
                try:
                    lock_payload = self._read_lock_payload()
                    if str(lock_payload.get("lock_id", "")).strip() != lock_id:
                        return
                    lock_payload["heartbeat_at"] = _utc_now_iso()
                    _atomic_write_text(
                        self.lock_path,
                        json.dumps(lock_payload, sort_keys=True) + "\n",
                    )
                except Exception:
                    return

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name="merlin-discovery-queue-lock-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        return stop_event, heartbeat_thread

    def _lock_is_stale(self) -> bool:
        if not self.lock_path.exists():
            return False
        age_seconds = self._lock_age_seconds()
        if age_seconds < DEFAULT_QUEUE_LOCK_STALE_SECONDS:
            return False
        lock_payload = self._read_lock_payload()
        if self._pid_is_active(lock_payload.get("pid")):
            return False
        return True

    @contextmanager
    def _mutation_lock(self):
        if self.no_write:
            yield
            return

        self.queue_root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + DEFAULT_QUEUE_LOCK_TIMEOUT_SECONDS

        while True:
            try:
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if self._lock_is_stale():
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"queue lock acquisition timed out: {self.lock_path}"
                    )
                time.sleep(DEFAULT_QUEUE_LOCK_RETRY_SECONDS)
                continue

            lock_payload = {
                "schema_name": "AAS.Discovery.QueueLock",
                "lock_id": f"lock_{uuid.uuid4().hex[:12]}",
                "pid": os.getpid(),
                "acquired_at": _utc_now_iso(),
                "heartbeat_at": _utc_now_iso(),
            }
            lock_id = str(lock_payload["lock_id"])
            with os.fdopen(fd, "w", encoding="utf-8") as lock_handle:
                lock_handle.write(json.dumps(lock_payload, sort_keys=True) + "\n")

            heartbeat_stop, heartbeat_thread = self._start_lock_heartbeat(
                lock_id=lock_id,
            )
            try:
                yield
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(
                    timeout=max(
                        0.1,
                        float(DEFAULT_QUEUE_LOCK_HEARTBEAT_SECONDS) + 0.1,
                    )
                )
                try:
                    current_lock = self._read_lock_payload()
                    if str(current_lock.get("lock_id", "")).strip() == lock_id:
                        self.lock_path.unlink()
                except FileNotFoundError:
                    pass
            return

    def append_seed(self, seed: dict[str, Any]) -> None:
        if self.no_write:
            return
        with self._mutation_lock():
            _atomic_append_jsonl(self.seeds_path, seed)

    def list_seeds(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.seeds_path)

    def list_work(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.work_path)

    def list_deadletter(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.deadletter_path)

    def _write_work(self, work_items: list[dict[str, Any]]) -> None:
        if self.no_write:
            return
        _write_jsonl(self.work_path, work_items)

    def promote_seeds_to_work(self, *, run_id: str) -> int:
        with self._mutation_lock():
            seeds = self.list_seeds()
            work_items = self.list_work()
            known_work_ids = {str(item.get("work_id", "")) for item in work_items}

            appended = 0
            for seed in seeds:
                seed_id = str(seed.get("seed_id", "")).strip()
                if not seed_id:
                    continue
                work_id = _make_work_id(seed_id)
                if work_id in known_work_ids:
                    continue

                work_items.append(
                    {
                        "schema_name": "AAS.Discovery.WorkItem",
                        "schema_version": DISCOVERY_SCHEMA_VERSION,
                        "work_id": work_id,
                        "seed_id": seed_id,
                        "seed": seed,
                        "state": WORK_STATE_NEW,
                        "attempt": 0,
                        "lease": None,
                        "last_error": None,
                        "created_at": _utc_now_iso(),
                        "updated_at": _utc_now_iso(),
                        "run_id": run_id,
                    }
                )
                known_work_ids.add(work_id)
                appended += 1

            if appended > 0:
                self._write_work(work_items)
            return appended

    def claim(
        self,
        *,
        worker_id: str,
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
        claim_write_delay_seconds: float = 0.0,
    ) -> dict[str, Any] | None:
        with self._mutation_lock():
            work_items = self.list_work()
            now = _utc_now()

            target_index: int | None = None
            for index, item in enumerate(work_items):
                state = item.get("state")
                if state == WORK_STATE_NEW:
                    target_index = index
                    break

                if state != WORK_STATE_CLAIMED:
                    continue

                lease = item.get("lease")
                if not isinstance(lease, dict):
                    target_index = index
                    break

                lease_expires_at = str(lease.get("lease_expires_at", "")).strip()
                if not lease_expires_at:
                    target_index = index
                    break

                expires_dt = _parse_datetime(lease_expires_at)
                if expires_dt is None:
                    target_index = index
                    break

                if expires_dt <= now:
                    target_index = index
                    break

            if target_index is None:
                return None

            target = dict(work_items[target_index])
            target["state"] = WORK_STATE_CLAIMED
            target["attempt"] = int(target.get("attempt", 0)) + 1
            target["lease"] = {
                "lease_id": f"lease_{uuid.uuid4().hex[:10]}",
                "worker_id": worker_id,
                "leased_at": _utc_now_iso(),
                "lease_expires_at": _lease_expiry_iso(
                    now=now, lease_ttl_seconds=lease_ttl_seconds
                ),
            }
            target["updated_at"] = _utc_now_iso()

            try:
                delay_seconds = max(0.0, float(claim_write_delay_seconds))
            except (TypeError, ValueError):
                delay_seconds = 0.0
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            work_items[target_index] = target
            self._write_work(work_items)
            return target

    def renew_lease(
        self,
        *,
        work_id: str,
        worker_id: str,
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    ) -> bool:
        with self._mutation_lock():
            work_items = self.list_work()
            now = _utc_now()

            renewed = False
            for index, item in enumerate(work_items):
                if str(item.get("work_id", "")) != work_id:
                    continue
                lease = item.get("lease")
                if not isinstance(lease, dict):
                    return False
                if str(lease.get("worker_id", "")) != worker_id:
                    return False

                lease["lease_expires_at"] = _lease_expiry_iso(
                    now=now, lease_ttl_seconds=lease_ttl_seconds
                )
                item["lease"] = lease
                item["updated_at"] = _utc_now_iso()
                work_items[index] = item
                renewed = True
                break

            if renewed:
                self._write_work(work_items)
            return renewed

    def release(
        self,
        *,
        work_id: str,
        status: str,
        error: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> dict[str, Any] | None:
        with self._mutation_lock():
            work_items = self.list_work()
            updated_item: dict[str, Any] | None = None
            retained_work: list[dict[str, Any]] = []

            for item in work_items:
                if str(item.get("work_id", "")) != work_id:
                    retained_work.append(item)
                    continue

                updated_item = dict(item)
                updated_item["updated_at"] = _utc_now_iso()
                updated_item["lease"] = None
                updated_item["last_error"] = error

                if status == WORK_STATE_DONE:
                    updated_item["state"] = WORK_STATE_DONE
                    retained_work.append(updated_item)
                elif status == WORK_STATE_BLOCKED:
                    updated_item["state"] = WORK_STATE_BLOCKED
                    retained_work.append(updated_item)
                elif status == WORK_STATE_FAILED:
                    attempt = int(updated_item.get("attempt", 0))
                    if attempt <= max_retries:
                        updated_item["state"] = WORK_STATE_NEW
                        retained_work.append(updated_item)
                    else:
                        updated_item["state"] = WORK_STATE_FAILED
                        if not self.no_write:
                            _atomic_append_jsonl(self.deadletter_path, updated_item)
                else:
                    updated_item["state"] = status
                    retained_work.append(updated_item)

            if updated_item is not None:
                self._write_work(retained_work)
            return updated_item

    def purge_deadletter(self) -> int:
        with self._mutation_lock():
            deadletter_items = self.list_deadletter()
            if not self.no_write:
                _write_jsonl(self.deadletter_path, [])
            return len(deadletter_items)

    def pause(self) -> None:
        if self.no_write:
            return
        with self._mutation_lock():
            self.queue_root.mkdir(parents=True, exist_ok=True)
            self.pause_flag_path.write_text(_utc_now_iso() + "\n", encoding="utf-8")

    def resume(self) -> None:
        if self.no_write:
            return
        with self._mutation_lock():
            if self.pause_flag_path.exists():
                self.pause_flag_path.unlink()

    def is_paused(self) -> bool:
        return self.pause_flag_path.exists()

    def queue_status(self) -> dict[str, Any]:
        with self._mutation_lock():
            seeds = self.list_seeds()
            work_items = self.list_work()
            deadletter_items = self.list_deadletter()
            paused = self.is_paused()

        counts = {
            "new": 0,
            "claimed": 0,
            "done": 0,
            "failed": 0,
            "blocked": 0,
        }

        for item in work_items:
            state = str(item.get("state", "")).upper()
            if state == WORK_STATE_NEW:
                counts["new"] += 1
            elif state == WORK_STATE_CLAIMED:
                counts["claimed"] += 1
            elif state == WORK_STATE_DONE:
                counts["done"] += 1
            elif state == WORK_STATE_FAILED:
                counts["failed"] += 1
            elif state == WORK_STATE_BLOCKED:
                counts["blocked"] += 1

        return {
            "schema_name": "AAS.Discovery.QueueStatus",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "queue_root": str(self.queue_root),
            "seeds": len(seeds),
            "work": len(work_items),
            "deadletter": len(deadletter_items),
            "paused": paused,
            "counts": counts,
        }


@dataclass
class DiscoveryEngine:
    workspace_root: Path
    merlin_mode: str = "local"

    def __post_init__(self) -> None:
        normalized_mode = str(self.merlin_mode or "local").strip().lower()
        if normalized_mode not in {"local", "null"}:
            normalized_mode = "local"
        self.merlin_mode = normalized_mode

        if self.merlin_mode == "null":
            adapter: Any = NullMerlinAdapter()
        else:
            adapter = LocalMerlinAdapter()

        self.scorer: IMerlinScorer = adapter
        self.summarizer: IMerlinSummarizer = adapter
        self.classifier: IMerlinClassifier = adapter

    def _paths(self, out_root: Path) -> dict[str, Path]:
        return {
            "root": out_root,
            "knowledge": out_root / "knowledge",
            "feeds": out_root / "knowledge" / "feeds",
            "research": out_root / "knowledge" / "research",
            "index": out_root / "knowledge" / "index.json",
            "tags": out_root / "knowledge" / "tags.json",
            "templates": out_root / "knowledge" / "templates",
            "queue": out_root / "queue",
            "runs": out_root / "runs",
        }

    def _normalize_seed(
        self, payload: dict[str, Any], *, source_hint: str = "local"
    ) -> dict[str, Any]:
        topic = str(
            payload.get("topic") or payload.get("query") or "Untitled seed"
        ).strip()
        source = str(payload.get("source") or source_hint).strip() or source_hint
        created_at = str(payload.get("created_at") or _utc_now_iso()).strip()
        seed_id = str(
            payload.get("seed_id") or _make_seed_id(topic, source, created_at)
        ).strip()
        metadata = (
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        )

        collector = payload.get("collector")
        if collector and isinstance(collector, str):
            metadata = {**metadata, "collector": collector}

        return {
            "schema_name": "AAS.Discovery.Seed",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "seed_id": seed_id,
            "topic": topic,
            "source": source,
            "created_at": created_at,
            "profile": str(payload.get("profile") or PUBLIC_PROFILE).strip().lower(),
            "metadata": metadata,
        }

    def _matches_topic(self, item: dict[str, Any], topic: str) -> bool:
        topic_tokens = [
            token for token in re.split(r"[^a-zA-Z0-9]+", topic.lower()) if token
        ]
        if not topic_tokens:
            return True
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        return any(token in haystack for token in topic_tokens)

    def _collect_from_fixture(
        self,
        *,
        seed: dict[str, Any],
        collector_name: str,
        fixture_feed: Path,
        max_items: int,
    ) -> list[dict[str, Any]]:
        rows = _load_fixture_items(fixture_feed)
        if not rows:
            return []

        topic = str(seed.get("topic", "")).strip()
        matching = [row for row in rows if self._matches_topic(row, topic)]
        if not matching:
            matching = rows

        selected_rows = matching[: max(1, max_items)]
        collected: list[dict[str, Any]] = []
        for row in selected_rows:
            title = str(row.get("title") or topic or "Untitled item").strip()
            url = str(row.get("url") or row.get("canonical_url") or "").strip()
            snippet = str(row.get("snippet") or row.get("summary") or "").strip()
            source_name = str(row.get("source") or collector_name).strip()
            published_at = str(
                row.get("published_at") or row.get("date") or _utc_now_iso()
            ).strip()
            canonical_url = url or f"https://local.discovery/{_slugify(title)}"
            canonical_key = canonical_key_for_url(canonical_url)
            seed_id = str(seed.get("seed_id", "")).strip()

            collected.append(
                {
                    "schema_name": "AAS.Discovery.CollectedItem",
                    "schema_version": DISCOVERY_SCHEMA_VERSION,
                    "item_id": _make_item_id(seed_id, canonical_url),
                    "seed_id": seed_id,
                    "title": title,
                    "url": canonical_url,
                    "canonical_url": canonical_url,
                    "canonical_key": canonical_key,
                    "snippet": snippet,
                    "source": source_name,
                    "collector": collector_name,
                    "published_at": published_at,
                    "collected_at": _utc_now_iso(),
                }
            )

        return collected

    def _collect_from_cache(
        self,
        *,
        seed: dict[str, Any],
        feeds_root: Path,
        max_items: int,
    ) -> list[dict[str, Any]]:
        if not feeds_root.exists():
            return []

        candidates: list[dict[str, Any]] = []
        for feed_path in sorted(feeds_root.glob("*/*.jsonl"), reverse=True):
            for row in _read_jsonl(feed_path):
                if self._matches_topic(row, str(seed.get("topic", ""))):
                    candidates.append(row)
                    if len(candidates) >= max_items:
                        return candidates

        return candidates[:max_items]

    def _rss_feed_urls(
        self,
        *,
        seed: dict[str, Any],
        metadata: dict[str, Any],
    ) -> list[str]:
        candidates: list[str] = []
        for key in ("feed_url", "rss_url", "url"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        raw_urls = metadata.get("feed_urls")
        if isinstance(raw_urls, list):
            for value in raw_urls:
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
        seed_url = seed.get("url")
        if isinstance(seed_url, str) and seed_url.strip():
            candidates.append(seed_url.strip())

        normalized: list[str] = []
        for value in candidates:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"}:
                continue
            if value in normalized:
                continue
            normalized.append(value)
        return normalized[:5]

    def _parse_rss_items(
        self,
        *,
        seed: dict[str, Any],
        collector_name: str,
        topic: str,
        feed_url: str,
        xml_bytes: bytes,
        max_items: int,
    ) -> list[dict[str, Any]]:
        if b"<!DOCTYPE" in xml_bytes.upper():
            return []
        try:
            root = ElementTree.fromstring(xml_bytes)
        except ElementTree.ParseError:
            return []

        rss_items = root.findall(".//item")
        atom_items = root.findall(".//{*}entry")
        nodes = rss_items if rss_items else atom_items

        seed_id = str(seed.get("seed_id", "")).strip()
        source_name = _parse_url_hostname(feed_url)
        collected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for node in nodes:
            if len(collected) >= max_items:
                break

            title = str(
                node.findtext("title")
                or node.findtext("{*}title")
                or topic
                or "Untitled item"
            ).strip()
            if not title:
                title = "Untitled item"

            canonical_url = ""
            for path in ("link", "{*}link"):
                direct_link = node.findtext(path)
                if isinstance(direct_link, str) and direct_link.strip():
                    canonical_url = direct_link.strip()
                    break
            if not canonical_url:
                for link_node in node.findall("{*}link") + node.findall("link"):
                    if not isinstance(link_node, ElementTree.Element):
                        continue
                    href = str(link_node.attrib.get("href") or "").strip()
                    rel = (
                        str(link_node.attrib.get("rel") or "alternate").strip().lower()
                    )
                    if href and rel in {"", "alternate"}:
                        canonical_url = href
                        break
            if not canonical_url:
                canonical_url = "https://rss.local/" + _hash_text(
                    f"{feed_url}|{title}", length=24
                )

            parsed_url = urlparse(canonical_url)
            if parsed_url.scheme not in {"http", "https"}:
                continue
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)

            snippet = str(
                node.findtext("description")
                or node.findtext("{*}summary")
                or node.findtext("summary")
                or node.findtext("{*}content")
                or ""
            ).strip()
            if len(snippet) > 8000:
                snippet = snippet[:8000]

            raw_published_at = str(
                node.findtext("pubDate")
                or node.findtext("{*}published")
                or node.findtext("published")
                or node.findtext("{*}updated")
                or node.findtext("updated")
                or ""
            ).strip()
            published_dt = _parse_datetime(raw_published_at)
            published_at = _to_iso(published_dt) if published_dt else _utc_now_iso()

            collected.append(
                {
                    "schema_name": "AAS.Discovery.CollectedItem",
                    "schema_version": DISCOVERY_SCHEMA_VERSION,
                    "item_id": _make_item_id(seed_id, canonical_url),
                    "seed_id": seed_id,
                    "title": title,
                    "url": canonical_url,
                    "canonical_url": canonical_url,
                    "canonical_key": canonical_key_for_url(canonical_url),
                    "snippet": snippet,
                    "source": source_name,
                    "collector": collector_name,
                    "published_at": published_at,
                    "collected_at": _utc_now_iso(),
                }
            )

        return collected

    def _collect_from_rss(
        self,
        *,
        seed: dict[str, Any],
        collector_name: str,
        metadata: dict[str, Any],
        max_items: int,
    ) -> list[dict[str, Any]]:
        feed_urls = self._rss_feed_urls(seed=seed, metadata=metadata)
        if not feed_urls:
            return []

        timeout_seconds = float(
            _safe_int(
                metadata.get("timeout_seconds"),
                default=int(DEFAULT_RSS_TIMEOUT_SECONDS),
                minimum=1,
            )
        )
        max_feed_bytes = _safe_int(
            metadata.get("max_feed_bytes"),
            default=DEFAULT_RSS_MAX_BYTES,
            minimum=1024,
        )
        topic = str(seed.get("topic", "")).strip()
        headers = {"User-Agent": "MerlinDiscovery/1.0 (+https://aas.local)"}

        collected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for feed_url in feed_urls:
            if len(collected) >= max_items:
                break
            try:
                response = requests.get(
                    feed_url,
                    timeout=timeout_seconds,
                    headers=headers,
                )
            except requests.RequestException:
                continue
            if response.status_code >= 400:
                continue

            xml_bytes = bytes(response.content[:max_feed_bytes])
            parsed_items = self._parse_rss_items(
                seed=seed,
                collector_name=collector_name,
                topic=topic,
                feed_url=feed_url,
                xml_bytes=xml_bytes,
                max_items=max_items,
            )
            for item in parsed_items:
                canonical_url = str(item.get("canonical_url", "")).strip()
                if not canonical_url or canonical_url in seen_urls:
                    continue
                collected.append(item)
                seen_urls.add(canonical_url)
                if len(collected) >= max_items:
                    break

        return collected[:max_items]

    def _collect_from_github_search(
        self,
        *,
        seed: dict[str, Any],
        collector_name: str,
        metadata: dict[str, Any],
        max_items: int,
    ) -> list[dict[str, Any]]:
        topic = str(seed.get("topic", "")).strip()
        query = str(metadata.get("query") or topic).strip()
        if not query:
            return []

        timeout_seconds = float(
            _safe_int(
                metadata.get("timeout_seconds"),
                default=int(DEFAULT_GITHUB_TIMEOUT_SECONDS),
                minimum=1,
            )
        )

        api_url = str(
            metadata.get("api_url") or "https://api.github.com/search/repositories"
        ).strip()
        parsed_api = urlparse(api_url)
        if parsed_api.scheme not in {"http", "https"}:
            return []

        per_page = max(1, min(100, max_items))
        params = {
            "q": query,
            "sort": str(metadata.get("sort") or "updated").strip() or "updated",
            "order": str(metadata.get("order") or "desc").strip() or "desc",
            "per_page": str(per_page),
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "MerlinDiscovery/1.0 (+https://aas.local)",
        }
        token = str(os.getenv("GITHUB_TOKEN", "")).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = requests.get(
                api_url,
                params=params,
                timeout=timeout_seconds,
                headers=headers,
            )
        except requests.RequestException:
            return []
        if response.status_code >= 400:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []
        raw_items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(raw_items, list):
            return []

        seed_id = str(seed.get("seed_id", "")).strip()
        collected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for row in raw_items:
            if len(collected) >= max_items:
                break
            if not isinstance(row, dict):
                continue

            canonical_url = str(row.get("html_url") or "").strip()
            parsed_url = urlparse(canonical_url)
            if parsed_url.scheme not in {"http", "https"}:
                continue
            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)

            full_name = str(row.get("full_name") or row.get("name") or "").strip()
            title = full_name or topic or "Untitled repository"

            description = str(row.get("description") or "").strip()
            if len(description) > 8000:
                description = description[:8000]

            stars = row.get("stargazers_count")
            language = str(row.get("language") or "").strip()
            snippet_parts: list[str] = []
            if description:
                snippet_parts.append(description)
            if isinstance(stars, int):
                snippet_parts.append(f"stars: {stars}")
            if language:
                snippet_parts.append(f"language: {language}")
            snippet = " | ".join(snippet_parts)
            if len(snippet) > 8000:
                snippet = snippet[:8000]

            raw_published_at = str(
                row.get("updated_at")
                or row.get("pushed_at")
                or row.get("created_at")
                or ""
            ).strip()
            published_dt = _parse_datetime(raw_published_at)
            published_at = _to_iso(published_dt) if published_dt else _utc_now_iso()

            collected.append(
                {
                    "schema_name": "AAS.Discovery.CollectedItem",
                    "schema_version": DISCOVERY_SCHEMA_VERSION,
                    "item_id": _make_item_id(seed_id, canonical_url),
                    "seed_id": seed_id,
                    "title": title,
                    "url": canonical_url,
                    "canonical_url": canonical_url,
                    "canonical_key": canonical_key_for_url(canonical_url),
                    "snippet": snippet,
                    "source": "github.com",
                    "collector": collector_name,
                    "published_at": published_at,
                    "collected_at": _utc_now_iso(),
                }
            )

        return collected[:max_items]

    def _collect(
        self,
        *,
        seed: dict[str, Any],
        policy: DiscoveryPolicy,
        fixture_feed: Path,
        feeds_root: Path,
        max_items: int,
    ) -> dict[str, Any]:
        metadata = (
            seed.get("metadata") if isinstance(seed.get("metadata"), dict) else {}
        )
        collector_name = _normalize_source_name(
            str(metadata.get("collector") or seed.get("source") or "local_fixture")
        )

        decision = policy.collector_decision(collector_name)
        if decision.decision == POLICY_BLOCKED:
            return {
                "status": "blocked",
                "collector": collector_name,
                "decision": decision.decision,
                "reason": decision.reason,
                "items": [],
            }

        if decision.decision == POLICY_STUBBED and collector_name in NETWORK_COLLECTORS:
            return {
                "status": "stubbed",
                "collector": collector_name,
                "decision": decision.decision,
                "reason": decision.reason,
                "items": [],
            }

        if collector_name == "local_cache":
            items = self._collect_from_cache(
                seed=seed, feeds_root=feeds_root, max_items=max_items
            )
        elif collector_name == "rss":
            items = self._collect_from_rss(
                seed=seed,
                collector_name=collector_name,
                metadata=metadata,
                max_items=max_items,
            )
            if not items:
                return {
                    "status": "ok",
                    "collector": collector_name,
                    "decision": decision.decision,
                    "reason": "rss collector returned no items",
                    "items": [],
                }
        elif collector_name == "github_search":
            items = self._collect_from_github_search(
                seed=seed,
                collector_name=collector_name,
                metadata=metadata,
                max_items=max_items,
            )
            if not items:
                return {
                    "status": "ok",
                    "collector": collector_name,
                    "decision": decision.decision,
                    "reason": "github search collector returned no items",
                    "items": [],
                }
        elif collector_name in NETWORK_COLLECTORS:
            return {
                "status": "stubbed",
                "collector": collector_name,
                "decision": POLICY_STUBBED,
                "reason": "collector implementation deferred",
                "items": [],
            }
        else:
            items = self._collect_from_fixture(
                seed=seed,
                collector_name="local_fixture",
                fixture_feed=fixture_feed,
                max_items=max_items,
            )
            collector_name = "local_fixture"

        return {
            "status": "ok",
            "collector": collector_name,
            "decision": decision.decision,
            "reason": decision.reason,
            "items": items,
        }

    def _artifact_path(
        self,
        *,
        research_root: Path,
        date_value: str,
        title: str,
    ) -> Path:
        date_bits = date_value.split("-")
        if len(date_bits) != 3:
            date_bits = _utc_now().strftime("%Y-%m-%d").split("-")
        year, month, day = date_bits
        slug = _slugify(title)
        return research_root / year / month / day / f"{slug}.md"

    def _load_template(self, templates_root: Path) -> str:
        template_path = templates_root / "research_note.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return "\n".join(DEFAULT_REQUIRED_SECTIONS)

    def _upsert_index(
        self,
        *,
        index_path: Path,
        tags_path: Path,
        artifacts: list[dict[str, Any]],
        no_write: bool,
    ) -> dict[str, Any]:
        index_payload = _read_json(
            index_path,
            default={
                "schema_name": "AAS.Knowledge.Index",
                "schema_version": "1.0.0",
                "updated_at": _utc_now_iso(),
                "by_canonical_key": {},
            },
        )
        if not isinstance(index_payload, dict):
            index_payload = {
                "schema_name": "AAS.Knowledge.Index",
                "schema_version": "1.0.0",
                "updated_at": _utc_now_iso(),
                "by_canonical_key": {},
            }

        by_key = index_payload.get("by_canonical_key")
        if not isinstance(by_key, dict):
            by_key = {}

        tags_payload = _read_json(
            tags_path,
            default={
                "schema_name": "AAS.Knowledge.Tags",
                "schema_version": "1.0.0",
                "updated_at": _utc_now_iso(),
                "tags": {},
            },
        )
        if not isinstance(tags_payload, dict):
            tags_payload = {
                "schema_name": "AAS.Knowledge.Tags",
                "schema_version": "1.0.0",
                "updated_at": _utc_now_iso(),
                "tags": {},
            }

        tags_map = tags_payload.get("tags")
        if not isinstance(tags_map, dict):
            tags_map = {}

        upserted = 0
        for artifact in artifacts:
            if artifact.get("plan_action") == PLAN_SKIP:
                continue
            if not artifact.get("validation", {}).get("ok"):
                continue
            canonical_key = str(artifact.get("canonical_key", "")).strip()
            if not canonical_key:
                continue
            by_key[canonical_key] = {
                "title": artifact.get("title"),
                "path": artifact.get("path"),
                "canonical_url": artifact.get("canonical_url"),
                "tags": artifact.get("tags", []),
                "run_id": artifact.get("run_id"),
                "updated_at": _utc_now_iso(),
            }
            upserted += 1

            for tag in artifact.get("tags", []):
                tag_name = str(tag).strip().lower()
                if not tag_name:
                    continue
                entries = tags_map.setdefault(tag_name, [])
                if artifact.get("path") not in entries:
                    entries.append(artifact.get("path"))

        index_payload["by_canonical_key"] = by_key
        index_payload["updated_at"] = _utc_now_iso()

        tags_payload["tags"] = tags_map
        tags_payload["updated_at"] = _utc_now_iso()

        if not no_write:
            _atomic_write_json(index_path, index_payload)
            _atomic_write_json(tags_path, tags_payload)

        return {
            "upserted": upserted,
            "index_path": str(index_path),
            "tags_path": str(tags_path),
        }

    def _git_repo_root(self, *, start_path: Path) -> Path | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(start_path), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_GIT_COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        root_text = result.stdout.strip()
        if not root_text:
            return None
        return Path(root_text).resolve()

    def _publish_git(
        self,
        *,
        run_id: str,
        out_root: Path,
        planned_paths: list[str],
    ) -> dict[str, Any]:
        if not planned_paths:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "skipped",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": "no artifact paths available for git publish",
                "created_paths": [],
            }

        repo_root = self._git_repo_root(start_path=out_root)
        if repo_root is None:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "blocked",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": (
                    "git publisher requires a local git repository; run from a git worktree "
                    "or use publisher_mode=stage_only"
                ),
                "created_paths": [],
            }

        repo_relative_paths: list[str] = []
        repo_to_out_relpath: dict[str, str] = {}
        for out_relpath in planned_paths:
            artifact_abs = (out_root / out_relpath).resolve()
            if not artifact_abs.exists():
                continue
            try:
                repo_relpath = artifact_abs.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if repo_relpath in repo_to_out_relpath:
                continue
            repo_to_out_relpath[repo_relpath] = out_relpath
            repo_relative_paths.append(repo_relpath)

        if not repo_relative_paths:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "blocked",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": (
                    "artifact paths are outside the current git repository; choose an output root "
                    "within the worktree or use publisher_mode=stage_only"
                ),
                "created_paths": [],
            }

        try:
            add_result = subprocess.run(
                ["git", "-C", str(repo_root), "add", "--", *repo_relative_paths],
                capture_output=True,
                text=True,
                timeout=DEFAULT_GIT_COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "blocked",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": f"git add failed: {exc}",
                "created_paths": [],
            }

        if add_result.returncode != 0:
            stderr_text = add_result.stderr.strip() or add_result.stdout.strip()
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "blocked",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": "git add failed: " + (stderr_text or "unknown git error"),
                "created_paths": [],
            }

        staged_result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--cached",
                "--name-only",
                "--",
                *repo_relative_paths,
            ],
            capture_output=True,
            text=True,
            timeout=DEFAULT_GIT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        staged_repo_paths = [
            line.strip() for line in staged_result.stdout.splitlines() if line.strip()
        ]
        staged_out_paths = [
            repo_to_out_relpath[path]
            for path in staged_repo_paths
            if path in repo_to_out_relpath
        ]

        if not staged_out_paths:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": "git",
                "status": "skipped",
                "blocked_by_policy": False,
                "decision": POLICY_ALLOWED,
                "message": "git publish completed with no staged changes",
                "created_paths": [],
            }

        return {
            "schema_name": "AAS.Discovery.PublishResult",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "run_id": run_id,
            "publisher_mode": "git",
            "status": "published",
            "blocked_by_policy": False,
            "decision": POLICY_ALLOWED,
            "message": (
                f"staged {len(staged_out_paths)} artifact path(s) in local git index"
            ),
            "created_paths": staged_out_paths,
        }

    def _publish(
        self,
        *,
        policy: DiscoveryPolicy,
        run_id: str,
        out_root: Path,
        publisher_mode: str,
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decision = policy.publisher_decision(publisher_mode)
        mode = _normalize_source_name(publisher_mode).replace("-", "_")
        planned_paths = [
            artifact["path"]
            for artifact in artifacts
            if artifact.get("plan_action") != PLAN_SKIP
        ]

        if decision.decision == POLICY_BLOCKED:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": mode,
                "status": "blocked",
                "blocked_by_policy": True,
                "decision": decision.decision,
                "message": decision.reason,
                "created_paths": [],
            }

        if decision.decision == POLICY_STUBBED and mode in {"pr", "git", "push"}:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": mode,
                "status": "blocked",
                "blocked_by_policy": True,
                "decision": decision.decision,
                "message": decision.reason,
                "created_paths": [],
            }

        if mode == "git":
            return self._publish_git(
                run_id=run_id,
                out_root=out_root,
                planned_paths=planned_paths,
            )

        if mode in {"pr", "push"}:
            return {
                "schema_name": "AAS.Discovery.PublishResult",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "run_id": run_id,
                "publisher_mode": mode,
                "status": "blocked",
                "blocked_by_policy": True,
                "decision": POLICY_STUBBED,
                "message": (
                    "publisher implementation deferred; use publisher_mode=git for local "
                    "index staging or stage_only for no-op publish"
                ),
                "created_paths": [],
            }

        status = "staged" if planned_paths else "skipped"
        return {
            "schema_name": "AAS.Discovery.PublishResult",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "run_id": run_id,
            "publisher_mode": "stage_only",
            "status": status,
            "blocked_by_policy": False,
            "decision": POLICY_ALLOWED,
            "message": "artifacts staged in working tree",
            "created_paths": planned_paths,
        }

    def run(
        self,
        *,
        profile: str = PUBLIC_PROFILE,
        out: str | Path | None = None,
        allow_live_automation: bool | None = None,
        seeds_file: str | Path | None = None,
        fixture_feed: str | Path | None = None,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        max_bundle_size: int = DEFAULT_MAX_BUNDLE_SIZE,
        max_items_per_seed: int = 10,
        dry_run: bool = False,
        no_write: bool = False,
        overwrite: bool = False,
        publisher_mode: str = "stage_only",
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        worker_id: str = DEFAULT_WORKER_ID,
    ) -> dict[str, Any]:
        started_at = _utc_now_iso()
        normalized_profile = _coerce_profile(profile)

        if allow_live_automation is None:
            allow_live_automation = _parse_bool(
                os.getenv("ALLOW_LIVE_AUTOMATION"),
                default=True,
            )

        policy = DiscoveryPolicy(
            profile=normalized_profile,
            allow_live_automation=bool(allow_live_automation),
        )

        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        paths = self._paths(out_root)
        run_id = _make_run_id()
        run_dir = paths["runs"] / run_id

        effective_no_write = bool(no_write)
        if not effective_no_write:
            run_dir.mkdir(parents=True, exist_ok=True)

        event_bus = DiscoveryEventBus(
            run_dir / "events.jsonl", no_write=effective_no_write
        )
        queue = DiscoveryQueue(paths["queue"], no_write=effective_no_write)

        policy_snapshot = {
            "profile": policy.profile,
            "allow_live_automation": policy.allow_live_automation,
            "collector_decisions": {
                name: policy.collector_decision(name).__dict__
                for name in sorted(OFFLINE_COLLECTORS | NETWORK_COLLECTORS)
            },
            "publisher_decisions": {
                mode: policy.publisher_decision(mode).__dict__
                for mode in ("stage_only", "pr", "git")
            },
            "dry_run": bool(dry_run),
            "no_write": bool(no_write),
        }

        counts = {
            "seeds_added": 0,
            "work_promoted": 0,
            "work_claimed": 0,
            "items_collected": 0,
            "items_scored": 0,
            "topics_selected": 0,
            "artifacts_generated": 0,
            "artifacts_written": 0,
            "artifacts_skipped": 0,
            "blocked_by_policy": 0,
            "failed": 0,
        }

        event_bus.emit(
            event_type="discovery.seed.created",
            run_id=run_id,
            payload={"message": "run started", "policy": policy_snapshot},
            stage="seed",
        )

        if seeds_file:
            seed_rows = _load_seed_payloads(Path(seeds_file))
            for row in seed_rows:
                seed = self._normalize_seed(row, source_hint="seed_file")
                queue.append_seed(seed)
                counts["seeds_added"] += 1
                event_bus.emit(
                    event_type="discovery.seed.created",
                    run_id=run_id,
                    payload=seed,
                    stage="seed",
                )

        promoted = queue.promote_seeds_to_work(run_id=run_id)
        counts["work_promoted"] = promoted

        fixture_path = (
            Path(fixture_feed)
            if fixture_feed
            else self.workspace_root
            / "knowledge"
            / "feeds"
            / "_fixtures"
            / "local_fixture.jsonl"
        )

        template_text = self._load_template(paths["templates"])

        existing_index = _read_json(paths["index"], default={})
        by_key = (
            existing_index.get("by_canonical_key")
            if isinstance(existing_index, dict)
            else {}
        )
        indexed_keys = set(by_key.keys()) if isinstance(by_key, dict) else set()

        scored_candidates: dict[str, dict[str, Any]] = {}

        while True:
            if queue.is_paused():
                event_bus.emit(
                    event_type="discovery.run.completed",
                    run_id=run_id,
                    payload={"status": "paused", "reason": "queue pause flag set"},
                    stage="run",
                    status="paused",
                )
                break

            work_item = queue.claim(
                worker_id=worker_id, lease_ttl_seconds=lease_ttl_seconds
            )
            if work_item is None:
                break

            counts["work_claimed"] += 1
            seed = (
                work_item.get("seed") if isinstance(work_item.get("seed"), dict) else {}
            )

            event_bus.emit(
                event_type="discovery.item.collected",
                run_id=run_id,
                payload={
                    "work_id": work_item.get("work_id"),
                    "seed_id": seed.get("seed_id"),
                    "state": WORK_STATE_CLAIMED,
                },
                stage="collect",
            )

            collected = self._collect(
                seed=seed,
                policy=policy,
                fixture_feed=fixture_path,
                feeds_root=paths["feeds"],
                max_items=max(1, int(max_items_per_seed)),
            )

            collect_status = collected.get("status")
            collector_name = str(collected.get("collector", "local_fixture"))
            work_id = str(work_item.get("work_id", ""))

            if collect_status in {"blocked", "stubbed"}:
                counts["blocked_by_policy"] += 1
                queue.release(
                    work_id=work_id,
                    status=WORK_STATE_BLOCKED,
                    error=str(collected.get("reason", "collector blocked")),
                    max_retries=max_retries,
                )
                event_bus.emit(
                    event_type="discovery.item.collected",
                    run_id=run_id,
                    payload={
                        "work_id": work_id,
                        "seed_id": seed.get("seed_id"),
                        "status": collect_status,
                        "collector": collector_name,
                        "reason": collected.get("reason"),
                    },
                    stage="collect",
                    status=collect_status,
                )
                continue

            items = (
                collected.get("items")
                if isinstance(collected.get("items"), list)
                else []
            )
            counts["items_collected"] += len(items)

            feed_date = _utc_now().strftime("%Y-%m-%d")
            feed_path = paths["feeds"] / collector_name / f"{feed_date}.jsonl"
            if not effective_no_write:
                existing_rows = _read_jsonl(feed_path)
                existing_ids = {str(row.get("item_id", "")) for row in existing_rows}
                merged = list(existing_rows)
                for item in items:
                    if item.get("item_id") in existing_ids:
                        continue
                    merged.append(item)
                    existing_ids.add(str(item.get("item_id", "")))
                _write_jsonl(feed_path, merged)

            try:
                for item in items:
                    canonical_key = str(item.get("canonical_key", "")).strip()
                    if not canonical_key or canonical_key in indexed_keys:
                        continue

                    tags = self.classifier.classify(item)
                    context = {
                        "source_trust": SOURCE_TRUST_DEFAULT,
                        "aas_lexicon": sorted(
                            {
                                "orchestrator",
                                "policy",
                                "plugin",
                                "discovery",
                                "queue",
                                "index",
                                *DOMAIN_KEYWORDS.keys(),
                            }
                        ),
                    }
                    score_result = self.scorer.score(item, context)
                    score_result["tags"] = sorted(
                        set(tags + list(score_result.get("tags", [])))
                    )

                    counts["items_scored"] += 1
                    event_bus.emit(
                        event_type="discovery.item.scored",
                        run_id=run_id,
                        payload=score_result,
                        stage="rank",
                    )

                    score_value = _safe_float(score_result.get("score"), default=0.0)
                    if score_value < min_score:
                        continue

                    previous = scored_candidates.get(canonical_key)
                    if (
                        previous
                        and _safe_float(previous.get("score"), default=0.0)
                        >= score_value
                    ):
                        continue

                    scored_candidates[canonical_key] = {
                        "item": item,
                        "score": score_value,
                        "confidence": _safe_float(
                            score_result.get("confidence"), default=0.5
                        ),
                        "tags": score_result.get("tags", []),
                        "reason": score_result.get("reason"),
                    }

                queue.release(
                    work_id=work_id, status=WORK_STATE_DONE, max_retries=max_retries
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                counts["failed"] += 1
                queue.release(
                    work_id=work_id,
                    status=WORK_STATE_FAILED,
                    error=str(exc),
                    max_retries=max_retries,
                )
                event_bus.emit(
                    event_type="discovery.item.collected",
                    run_id=run_id,
                    payload={"work_id": work_id, "error": str(exc)},
                    stage="collect",
                    status="failed",
                )

        ranked = sorted(
            scored_candidates.values(),
            key=lambda row: (
                _safe_float(row.get("score"), default=0.0),
                _safe_float(row.get("confidence"), default=0.0),
            ),
            reverse=True,
        )

        selections: list[dict[str, Any]] = []
        for candidate in ranked[: max(1, int(top_k))]:
            item = candidate["item"]
            topic_id = _make_topic_id(run_id, str(item.get("canonical_key", "")))
            selection = {
                "schema_name": "AAS.Discovery.TopicSelection",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "topic_id": topic_id,
                "run_id": run_id,
                "title": item.get("title"),
                "canonical_url": item.get("canonical_url"),
                "canonical_key": item.get("canonical_key"),
                "item_ids": [item.get("item_id")],
                "selection_score": round(
                    _safe_float(candidate.get("score"), default=0.0), 4
                ),
                "confidence": round(
                    _safe_float(candidate.get("confidence"), default=0.5), 4
                ),
                "tags": candidate.get("tags", []),
                "reason": candidate.get("reason", ""),
                "selected_at": _utc_now_iso(),
            }
            selections.append(selection)
            event_bus.emit(
                event_type="discovery.topic.selected",
                run_id=run_id,
                payload=selection,
                stage="select",
            )

        counts["topics_selected"] = len(selections)

        artifacts: list[dict[str, Any]] = []
        for selection in selections:
            topic_bundle = {
                "topic_id": selection["topic_id"],
                "title": selection["title"],
                "canonical_url": selection["canonical_url"],
                "canonical_key": selection["canonical_key"],
                "supporting_items": [
                    row["item"]
                    for row in ranked
                    if row.get("item", {}).get("canonical_key")
                    == selection["canonical_key"]
                ][: max(1, int(max_bundle_size))],
                "score": selection.get("selection_score"),
                "confidence": selection.get("confidence"),
                "tags": selection.get("tags", []),
            }

            synthesized = self.summarizer.summarize(
                topic_bundle,
                template=template_text,
                context={"run_id": run_id, "profile": normalized_profile},
            )

            date_value = _utc_now().strftime("%Y-%m-%d")
            artifact_path = self._artifact_path(
                research_root=paths["research"],
                date_value=date_value,
                title=str(selection.get("title", "Untitled")),
            )

            plan_action = PLAN_CREATE
            if artifact_path.exists() and not overwrite:
                plan_action = PLAN_SKIP
            elif artifact_path.exists() and overwrite:
                plan_action = PLAN_OVERWRITE

            frontmatter = {
                "title": str(selection.get("title", "Untitled Topic")),
                "date": date_value,
                "source": [
                    str(item.get("source", "unknown"))
                    for item in topic_bundle["supporting_items"]
                ],
                "canonical_url": str(selection.get("canonical_url", "")),
                "tags": sorted(
                    set(str(tag) for tag in synthesized.get("tags", ["general"]))
                ),
                "confidence": _safe_float(selection.get("confidence"), default=0.5),
                "run_id": run_id,
            }

            body = str(synthesized.get("markdown", "")).strip()
            artifact_markdown = _render_frontmatter(frontmatter) + "\n\n" + body + "\n"
            validation = validate_artifact_markdown(artifact_markdown)

            artifact_relpath = str(artifact_path.relative_to(out_root))
            artifact_payload = {
                "schema_name": "AAS.Discovery.Artifact",
                "schema_version": DISCOVERY_SCHEMA_VERSION,
                "artifact_id": _make_artifact_id(
                    selection["topic_id"], artifact_relpath
                ),
                "topic_id": selection["topic_id"],
                "run_id": run_id,
                "title": frontmatter["title"],
                "path": artifact_relpath,
                "canonical_url": frontmatter["canonical_url"],
                "canonical_key": selection.get("canonical_key"),
                "tags": frontmatter["tags"],
                "confidence": frontmatter["confidence"],
                "created_at": _utc_now_iso(),
                "plan_action": plan_action,
                "validation": validation,
            }

            artifacts.append(artifact_payload)
            counts["artifacts_generated"] += 1

            event_bus.emit(
                event_type="discovery.artifact.generated",
                run_id=run_id,
                payload={
                    "artifact_id": artifact_payload["artifact_id"],
                    "topic_id": selection["topic_id"],
                    "path": artifact_relpath,
                    "plan_action": plan_action,
                },
                stage="synthesize",
            )

            event_bus.emit(
                event_type="discovery.artifact.validated",
                run_id=run_id,
                payload={
                    "artifact_id": artifact_payload["artifact_id"],
                    "ok": validation.get("ok"),
                    "errors": validation.get("errors", []),
                },
                stage="validate",
                status="ok" if validation.get("ok") else "failed",
            )

            if plan_action == PLAN_SKIP:
                counts["artifacts_skipped"] += 1
                continue

            if not validation.get("ok"):
                counts["failed"] += 1
                continue

            if not effective_no_write:
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(artifact_markdown, encoding="utf-8")
            counts["artifacts_written"] += 1
            event_bus.emit(
                event_type="discovery.topic.researched",
                run_id=run_id,
                payload={
                    "topic_id": selection["topic_id"],
                    "artifact_id": artifact_payload["artifact_id"],
                },
                stage="research",
            )

        index_update = self._upsert_index(
            index_path=paths["index"],
            tags_path=paths["tags"],
            artifacts=artifacts,
            no_write=effective_no_write,
        )

        event_bus.emit(
            event_type="discovery.index.updated",
            run_id=run_id,
            payload=index_update,
            stage="index",
        )

        publish_result = self._publish(
            policy=policy,
            run_id=run_id,
            out_root=out_root,
            publisher_mode=publisher_mode,
            artifacts=artifacts,
        )
        if publish_result.get("blocked_by_policy"):
            counts["blocked_by_policy"] += 1

        event_bus.emit(
            event_type="discovery.artifact.published",
            run_id=run_id,
            payload=publish_result,
            stage="publish",
            status=publish_result.get("status", "ok"),
        )

        completed_at = _utc_now_iso()
        report = {
            "schema_name": "AAS.Discovery.RunReport",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "run_id": run_id,
            "profile": normalized_profile,
            "allow_live_automation": bool(allow_live_automation),
            "merlin_mode": self.merlin_mode,
            "started_at": started_at,
            "completed_at": completed_at,
            "status": "ok" if counts["failed"] == 0 else "partial_failure",
            "counts": counts,
            "policy": policy_snapshot,
            "publish_result": publish_result,
            "plan": [
                {
                    "artifact_id": artifact["artifact_id"],
                    "path": artifact["path"],
                    "action": artifact["plan_action"],
                    "valid": artifact["validation"].get("ok", False),
                }
                for artifact in artifacts
            ],
            "paths": {
                "output_root": str(out_root),
                "knowledge_root": str(paths["knowledge"]),
                "queue_root": str(paths["queue"]),
                "run_dir": str(run_dir),
            },
        }

        event_bus.emit(
            event_type="discovery.run.completed",
            run_id=run_id,
            payload={
                "status": report["status"],
                "counts": counts,
            },
            stage="run",
            status=report["status"],
        )

        if not effective_no_write:
            _atomic_write_json(run_dir / "report.json", report)
            summary_lines = [
                f"# Discovery Run Summary ({run_id})",
                "",
                f"- profile: `{normalized_profile}`",
                f"- allow_live_automation: `{str(bool(allow_live_automation)).lower()}`",
                f"- status: `{report['status']}`",
                f"- items_collected: `{counts['items_collected']}`",
                f"- items_scored: `{counts['items_scored']}`",
                f"- topics_selected: `{counts['topics_selected']}`",
                f"- artifacts_written: `{counts['artifacts_written']}`",
                f"- blocked_by_policy: `{counts['blocked_by_policy']}`",
                "",
                "## Plan",
            ]
            for plan_item in report["plan"]:
                summary_lines.append(
                    (
                        f"- {plan_item['action']}: `{plan_item['path']}` "
                        f"(valid={str(plan_item['valid']).lower()})"
                    )
                )
            (run_dir / "SUMMARY.md").write_text(
                "\n".join(summary_lines) + "\n", encoding="utf-8"
            )
            (run_dir / "logs.txt").write_text(
                json.dumps({"run_id": run_id, "completed_at": completed_at}, indent=2)
                + "\n",
                encoding="utf-8",
            )

        return report

    def queue_status(self, *, out: str | Path | None = None) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        queue = DiscoveryQueue(out_root / "queue")
        return queue.queue_status()

    def queue_drain(
        self, *, out: str | Path | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        queue = DiscoveryQueue(out_root / "queue")
        promoted = queue.promote_seeds_to_work(run_id=run_id or _make_run_id())
        status = queue.queue_status()
        return {
            "schema_name": "AAS.Discovery.QueueDrain",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "promoted": promoted,
            "status": status,
        }

    def queue_purge_deadletter(
        self, *, out: str | Path | None = None
    ) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        queue = DiscoveryQueue(out_root / "queue")
        purged = queue.purge_deadletter()
        status = queue.queue_status()
        return {
            "schema_name": "AAS.Discovery.QueuePurgeDeadletter",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "purged": purged,
            "status": status,
        }

    def queue_pause(self, *, out: str | Path | None = None) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        queue = DiscoveryQueue(out_root / "queue")
        queue.pause()
        status = queue.queue_status()
        return {
            "schema_name": "AAS.Discovery.QueuePause",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "status": status,
        }

    def queue_resume(self, *, out: str | Path | None = None) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        queue = DiscoveryQueue(out_root / "queue")
        queue.resume()
        status = queue.queue_status()
        return {
            "schema_name": "AAS.Discovery.QueueResume",
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "status": status,
        }

    def knowledge_search(
        self,
        *,
        query: str,
        out: str | Path | None = None,
        limit: int = 20,
        tag: str | None = None,
    ) -> dict[str, Any]:
        out_root = Path(out).resolve() if out else self.workspace_root.resolve()
        paths = self._paths(out_root)
        payload = _read_json(paths["index"], default={})
        by_key = payload.get("by_canonical_key") if isinstance(payload, dict) else {}
        if not isinstance(by_key, dict):
            by_key = {}

        needle = str(query or "").strip().lower()
        normalized_tag = str(tag or "").strip().lower()
        results: list[dict[str, Any]] = []

        for canonical_key, entry in by_key.items():
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", ""))
            canonical_url = str(entry.get("canonical_url", ""))
            entry_tags = (
                entry.get("tags") if isinstance(entry.get("tags"), list) else []
            )
            haystack = f"{title} {canonical_url} {' '.join(str(item) for item in entry_tags)}".lower()

            if needle and needle not in haystack:
                continue
            if normalized_tag and normalized_tag not in {
                str(item).strip().lower() for item in entry_tags
            }:
                continue

            result_entry = {
                "canonical_key": canonical_key,
                "title": title,
                "path": entry.get("path"),
                "canonical_url": canonical_url,
                "tags": entry_tags,
                "run_id": entry.get("run_id"),
                "updated_at": entry.get("updated_at"),
            }
            results.append(result_entry)

        results = sorted(
            results,
            key=lambda row: str(row.get("updated_at", "")),
            reverse=True,
        )[: max(1, int(limit))]

        return {
            "schema_name": "AAS.Knowledge.SearchResult",
            "schema_version": "1.0.0",
            "query": query,
            "tag": tag,
            "count": len(results),
            "results": results,
            "index_path": str(paths["index"]),
        }


def build_engine(
    *, workspace_root: str | Path, merlin_mode: str = "local"
) -> DiscoveryEngine:
    return DiscoveryEngine(workspace_root=Path(workspace_root), merlin_mode=merlin_mode)

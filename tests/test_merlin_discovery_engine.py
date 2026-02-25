from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from merlin_discovery_engine import (
    DiscoveryQueue,
    build_engine,
    validate_artifact_markdown,
)

ROOT_DIR = Path(__file__).resolve().parents[1]


def _write_fixture_feed(root: Path) -> Path:
    fixture_path = root / "knowledge" / "feeds" / "_fixtures" / "local_fixture.jsonl"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "title": "Offline-first discovery orchestration for plugin ecosystems",
                        "url": "https://example.org/aas/offline-discovery",
                        "snippet": "Queue leasing and policy-gated collectors.",
                        "source": "fixture:aas_notes",
                        "published_at": "2026-02-23T18:00:00Z",
                    }
                ),
                json.dumps(
                    {
                        "title": "Policy boundaries for automation modes",
                        "url": "https://example.org/aas/policy-boundaries",
                        "snippet": "Public profile blocks network collectors by default.",
                        "source": "fixture:policy_lab",
                        "published_at": "2026-02-23T19:15:00Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture_path


def _write_seed_file(root: Path, payload: list[dict]) -> Path:
    seed_path = root / "seeds.json"
    seed_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return seed_path


def _rss_xml_fixture() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>AAS Feed</title>
    <link>https://example.org/feed</link>
    <description>Discovery fixture feed</description>
    <item>
      <title>Policy-gated discovery pipeline walkthrough</title>
      <link>https://example.org/articles/discovery-policy</link>
      <description>Queue locking and policy matrix guidance.</description>
      <pubDate>Tue, 24 Feb 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Contract-driven operations for discovery</title>
      <link>https://example.org/articles/discovery-contracts</link>
      <description>Operation envelope integration details.</description>
      <pubDate>Tue, 24 Feb 2026 12:10:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _github_search_json_fixture() -> dict:
    return {
        "total_count": 2,
        "incomplete_results": False,
        "items": [
            {
                "full_name": "AaroneousAutomationSuite/Merlin",
                "html_url": "https://github.com/AaroneousAutomationSuite/Merlin",
                "description": "Policy-gated, contract-driven discovery operations for Merlin.",
                "language": "Python",
                "stargazers_count": 42,
                "updated_at": "2026-02-24T12:00:00Z",
            },
            {
                "full_name": "AaroneousAutomationSuite/Hub",
                "html_url": "https://github.com/AaroneousAutomationSuite/Hub",
                "description": "Hub orchestration for Merlin operations envelope workflows.",
                "language": "Python",
                "stargazers_count": 31,
                "updated_at": "2026-02-24T12:10:00Z",
            },
        ],
    }


@contextmanager
def _serve_rss_feed(feed_xml: str):
    feed_bytes = feed_xml.encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # type: ignore[override]
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(feed_bytes)))
            self.end_headers()
            self.wfile.write(feed_bytes)

        def log_message(self, fmt, *args):  # type: ignore[override]
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/feed.xml"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def _serve_json_payload(payload: dict):
    payload_bytes = json.dumps(payload).encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # type: ignore[override]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload_bytes)))
            self.end_headers()
            self.wfile.write(payload_bytes)

        def log_message(self, fmt, *args):  # type: ignore[override]
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/search/repositories"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_discovery_engine_public_offline_run_generates_artifacts(tmp_path: Path):
    fixture_path = _write_fixture_feed(tmp_path)
    seed_file = _write_seed_file(
        tmp_path,
        [
            {
                "topic": "offline discovery orchestration",
                "source": "local_seed_file",
                "metadata": {"collector": "local_fixture"},
            },
            {
                "topic": "policy boundaries",
                "source": "local_seed_file",
                "metadata": {"collector": "local_fixture"},
            },
        ],
    )

    engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
    report = engine.run(
        profile="public",
        out=tmp_path,
        seeds_file=seed_file,
        fixture_feed=fixture_path,
        top_k=2,
        min_score=0.01,
    )

    assert report["schema_name"] == "AAS.Discovery.RunReport"
    assert report["profile"] == "public"
    assert report["allow_live_automation"] is True
    assert report["counts"]["items_collected"] >= 1
    assert report["counts"]["topics_selected"] >= 1
    assert report["counts"]["artifacts_written"] >= 1
    assert report["publish_result"]["status"] == "staged"

    run_dir = Path(report["paths"]["run_dir"])
    assert (run_dir / "report.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "SUMMARY.md").exists()

    research_files = list((tmp_path / "knowledge" / "research").glob("**/*.md"))
    assert research_files, "expected at least one generated research artifact"

    artifact_text = research_files[0].read_text(encoding="utf-8")
    validation = validate_artifact_markdown(artifact_text)
    assert validation["ok"] is True

    index_payload = json.loads(
        (tmp_path / "knowledge" / "index.json").read_text(encoding="utf-8")
    )
    assert index_payload.get("by_canonical_key")


def test_discovery_engine_blocks_network_collectors_in_public(tmp_path: Path):
    fixture_path = _write_fixture_feed(tmp_path)
    seed_file = _write_seed_file(
        tmp_path,
        [
            {
                "topic": "latest technology news",
                "source": "user_seed",
                "metadata": {"collector": "rss"},
            }
        ],
    )

    engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
    report = engine.run(
        profile="public",
        out=tmp_path,
        seeds_file=seed_file,
        fixture_feed=fixture_path,
    )

    assert report["counts"]["blocked_by_policy"] >= 1
    assert report["counts"]["items_collected"] == 0

    queue_payload = [
        row
        for row in DiscoveryQueue(tmp_path / "queue").list_work()
        if row.get("state") == "BLOCKED"
    ]
    assert queue_payload


def test_discovery_engine_experimental_rss_is_stubbed_when_live_automation_disabled(
    tmp_path: Path,
):
    fixture_path = _write_fixture_feed(tmp_path)
    out_root = tmp_path / "experimental_no_live"
    with _serve_rss_feed(_rss_xml_fixture()) as feed_url:
        seed_file = _write_seed_file(
            tmp_path,
            [
                {
                    "topic": "discovery contract governance",
                    "source": "user_seed",
                    "metadata": {
                        "collector": "rss",
                        "feed_url": feed_url,
                    },
                }
            ],
        )

        engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
        report = engine.run(
            profile="experimental",
            allow_live_automation=False,
            out=out_root,
            seeds_file=seed_file,
            fixture_feed=fixture_path,
        )

    assert report["profile"] == "experimental"
    assert report["allow_live_automation"] is False
    assert report["counts"]["blocked_by_policy"] >= 1
    assert report["counts"]["items_collected"] == 0
    assert report["policy"]["collector_decisions"]["rss"]["decision"] == "stubbed"


def test_discovery_engine_experimental_rss_collects_when_live_automation_enabled(
    tmp_path: Path,
):
    fixture_path = _write_fixture_feed(tmp_path)
    out_root = tmp_path / "experimental_live"
    with _serve_rss_feed(_rss_xml_fixture()) as feed_url:
        seed_file = _write_seed_file(
            tmp_path,
            [
                {
                    "topic": "discovery contract governance",
                    "source": "user_seed",
                    "metadata": {
                        "collector": "rss",
                        "feed_url": feed_url,
                    },
                }
            ],
        )

        engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
        report = engine.run(
            profile="experimental",
            allow_live_automation=True,
            out=out_root,
            seeds_file=seed_file,
            fixture_feed=fixture_path,
            top_k=1,
            min_score=0.01,
        )

    assert report["profile"] == "experimental"
    assert report["allow_live_automation"] is True
    assert report["counts"]["blocked_by_policy"] == 0
    assert report["counts"]["items_collected"] >= 1
    assert report["policy"]["collector_decisions"]["rss"]["decision"] == "allowed"

    rss_feeds = list((out_root / "knowledge" / "feeds" / "rss").glob("*.jsonl"))
    assert rss_feeds
    rows = [
        json.loads(line)
        for line in rss_feeds[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert rows[0]["collector"] == "rss"


def test_discovery_engine_github_search_policy_matrix(tmp_path: Path):
    fixture_path = _write_fixture_feed(tmp_path)
    with _serve_json_payload(_github_search_json_fixture()) as api_url:
        seed_file = _write_seed_file(
            tmp_path,
            [
                {
                    "topic": "discovery policy governance",
                    "source": "user_seed",
                    "metadata": {
                        "collector": "github_search",
                        "api_url": api_url,
                        "query": "merlin discovery policy",
                    },
                }
            ],
        )

        engine = build_engine(workspace_root=tmp_path, merlin_mode="local")

        public_report = engine.run(
            profile="public",
            allow_live_automation=True,
            out=tmp_path / "github_public",
            seeds_file=seed_file,
            fixture_feed=fixture_path,
            top_k=1,
            min_score=0.01,
        )
        assert public_report["counts"]["items_collected"] == 0
        assert public_report["counts"]["blocked_by_policy"] >= 1
        assert (
            public_report["policy"]["collector_decisions"]["github_search"]["decision"]
            == "blocked"
        )

        stubbed_report = engine.run(
            profile="experimental",
            allow_live_automation=False,
            out=tmp_path / "github_stubbed",
            seeds_file=seed_file,
            fixture_feed=fixture_path,
            top_k=1,
            min_score=0.01,
        )
        assert stubbed_report["counts"]["items_collected"] == 0
        assert stubbed_report["counts"]["blocked_by_policy"] >= 1
        assert (
            stubbed_report["policy"]["collector_decisions"]["github_search"]["decision"]
            == "stubbed"
        )

        allowed_out = tmp_path / "github_allowed"
        allowed_report = engine.run(
            profile="experimental",
            allow_live_automation=True,
            out=allowed_out,
            seeds_file=seed_file,
            fixture_feed=fixture_path,
            top_k=1,
            min_score=0.01,
        )
        assert allowed_report["counts"]["items_collected"] >= 1
        assert allowed_report["counts"]["blocked_by_policy"] == 0
        assert (
            allowed_report["policy"]["collector_decisions"]["github_search"]["decision"]
            == "allowed"
        )

        github_feeds = list(
            (allowed_out / "knowledge" / "feeds" / "github_search").glob("*.jsonl")
        )
        assert github_feeds
        rows = [
            json.loads(line)
            for line in github_feeds[0].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows
        assert rows[0]["collector"] == "github_search"


def test_discovery_engine_git_publisher_stages_artifacts_in_local_repo(tmp_path: Path):
    if shutil.which("git") is None:
        pytest.skip("git is required for git publisher test")

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", str(repo_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    fixture_path = _write_fixture_feed(tmp_path)
    seed_file = _write_seed_file(
        tmp_path,
        [
            {
                "topic": "offline discovery orchestration",
                "source": "local_seed_file",
                "metadata": {"collector": "local_fixture"},
            }
        ],
    )

    engine = build_engine(workspace_root=repo_root, merlin_mode="local")
    report = engine.run(
        profile="experimental",
        allow_live_automation=True,
        out=repo_root,
        seeds_file=seed_file,
        fixture_feed=fixture_path,
        top_k=1,
        min_score=0.01,
        publisher_mode="git",
    )

    assert report["publish_result"]["publisher_mode"] == "git"
    assert report["publish_result"]["status"] == "published"
    assert report["publish_result"]["decision"] == "allowed"
    assert report["publish_result"]["blocked_by_policy"] is False
    assert report["publish_result"]["created_paths"]

    staged = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    staged_paths = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
    assert staged_paths
    assert any(path.startswith("knowledge/research/") for path in staged_paths)


def test_discovery_queue_leasing_recovers_expired_claim(tmp_path: Path):
    queue = DiscoveryQueue(tmp_path / "queue")
    seed = {
        "schema_name": "AAS.Discovery.Seed",
        "schema_version": "1.0.0",
        "seed_id": "seed_deadbeef12345678",
        "topic": "queue leasing",
        "source": "local",
        "created_at": "2026-02-24T05:00:00Z",
        "profile": "public",
        "metadata": {"collector": "local_fixture"},
    }
    queue.append_seed(seed)
    queue.promote_seeds_to_work(run_id="run_20260224T050500Z_abcd1234")

    first_claim = queue.claim(worker_id="worker_a", lease_ttl_seconds=1)
    assert first_claim is not None

    second_claim = queue.claim(worker_id="worker_b", lease_ttl_seconds=1)
    assert second_claim is None

    time.sleep(1.1)
    reclaimed = queue.claim(worker_id="worker_b", lease_ttl_seconds=1)
    assert reclaimed is not None
    assert reclaimed["work_id"] == first_claim["work_id"]


def test_discovery_queue_claim_lock_prevents_duplicate_claim_under_race(tmp_path: Path):
    queue_root = tmp_path / "queue"
    queue = DiscoveryQueue(queue_root)
    queue.append_seed(
        {
            "schema_name": "AAS.Discovery.Seed",
            "schema_version": "1.0.0",
            "seed_id": "seed_race_1234567890ab",
            "topic": "queue race lock test",
            "source": "local",
            "created_at": "2026-02-24T05:12:00Z",
            "profile": "public",
            "metadata": {"collector": "local_fixture"},
        }
    )
    queue.promote_seeds_to_work(run_id="run_20260224T051200Z_locktest")

    result_a = tmp_path / "worker_a.json"
    result_b = tmp_path / "worker_b.json"

    script_template = """
import json
from pathlib import Path
from merlin_discovery_engine import DiscoveryQueue

queue = DiscoveryQueue(Path({queue_root!r}))
claim = queue.claim(
    worker_id={worker_id!r},
    lease_ttl_seconds=120,
    claim_write_delay_seconds=0.2,
)
payload = {{
    \"worker_id\": {worker_id!r},
    \"work_id\": claim.get(\"work_id\") if isinstance(claim, dict) else None,
}}
Path({result_path!r}).write_text(json.dumps(payload), encoding=\"utf-8\")
"""
    process_a = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script_template.format(
                queue_root=str(queue_root),
                worker_id="worker_a",
                result_path=str(result_a),
            ),
        ],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    process_b = subprocess.Popen(
        [
            sys.executable,
            "-c",
            script_template.format(
                queue_root=str(queue_root),
                worker_id="worker_b",
                result_path=str(result_b),
            ),
        ],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_a, stderr_a = process_a.communicate(timeout=20)
    stdout_b, stderr_b = process_b.communicate(timeout=20)

    assert process_a.returncode == 0, f"worker_a failed: {stderr_a}\n{stdout_a}"
    assert process_b.returncode == 0, f"worker_b failed: {stderr_b}\n{stdout_b}"
    assert result_a.exists()
    assert result_b.exists()

    claims = [
        json.loads(result_a.read_text(encoding="utf-8")),
        json.loads(result_b.read_text(encoding="utf-8")),
    ]
    claimed_work_ids = [
        str(item["work_id"])
        for item in claims
        if isinstance(item.get("work_id"), str) and item["work_id"]
    ]
    assert len(claimed_work_ids) == 1

    work_items = queue.list_work()
    claimed_rows = [row for row in work_items if row.get("state") == "CLAIMED"]
    assert len(claimed_rows) == 1


def test_discovery_queue_stale_lock_not_reclaimed_when_owner_pid_is_alive(
    tmp_path: Path, monkeypatch
):
    queue = DiscoveryQueue(tmp_path / "queue")
    queue.queue_root.mkdir(parents=True, exist_ok=True)
    queue.lock_path.write_text(
        json.dumps(
            {
                "schema_name": "AAS.Discovery.QueueLock",
                "lock_id": "lock_live_owner",
                "pid": os.getpid(),
                "acquired_at": "2026-02-24T05:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stale_time = time.time() - 120.0
    os.utime(queue.lock_path, (stale_time, stale_time))

    monkeypatch.setattr(
        "merlin_discovery_engine.DEFAULT_QUEUE_LOCK_TIMEOUT_SECONDS", 0.05
    )
    monkeypatch.setattr(
        "merlin_discovery_engine.DEFAULT_QUEUE_LOCK_RETRY_SECONDS", 0.005
    )

    with pytest.raises(TimeoutError):
        with queue._mutation_lock():
            pass
    assert queue.lock_path.exists()


def test_discovery_queue_lock_heartbeat_updates_lock_payload(
    tmp_path: Path, monkeypatch
):
    queue = DiscoveryQueue(tmp_path / "queue")
    queue.queue_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "merlin_discovery_engine.DEFAULT_QUEUE_LOCK_HEARTBEAT_SECONDS", 0.01
    )

    with queue._mutation_lock():
        first_payload = queue._read_lock_payload()
        first_heartbeat = str(first_payload.get("heartbeat_at", "")).strip()
        assert first_heartbeat
        time.sleep(0.08)
        second_payload = queue._read_lock_payload()
        second_heartbeat = str(second_payload.get("heartbeat_at", "")).strip()

    assert second_heartbeat
    assert second_heartbeat >= first_heartbeat


def test_discovery_queue_stale_lock_release_is_lock_id_safe(tmp_path: Path):
    queue = DiscoveryQueue(tmp_path / "queue")
    queue.queue_root.mkdir(parents=True, exist_ok=True)

    with queue._mutation_lock():
        queue.lock_path.write_text(
            json.dumps(
                {
                    "schema_name": "AAS.Discovery.QueueLock",
                    "lock_id": "lock_foreign_owner",
                    "pid": os.getpid(),
                    "acquired_at": "2026-02-24T05:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    assert queue.lock_path.exists()
    payload = json.loads(queue.lock_path.read_text(encoding="utf-8"))
    assert payload.get("lock_id") == "lock_foreign_owner"


def test_discovery_queue_failed_work_moves_to_deadletter_after_retry_budget(
    tmp_path: Path,
):
    queue = DiscoveryQueue(tmp_path / "queue")
    seed = {
        "schema_name": "AAS.Discovery.Seed",
        "schema_version": "1.0.0",
        "seed_id": "seed_abcdef0123456789",
        "topic": "deadletter test",
        "source": "local",
        "created_at": "2026-02-24T05:10:00Z",
        "profile": "public",
        "metadata": {"collector": "local_fixture"},
    }
    queue.append_seed(seed)
    queue.promote_seeds_to_work(run_id="run_20260224T051000Z_dcba4321")

    claim = queue.claim(worker_id="worker", lease_ttl_seconds=30)
    assert claim is not None
    queue.release(
        work_id=claim["work_id"],
        status="FAILED",
        error="synthetic failure",
        max_retries=0,
    )

    deadletter = queue.list_deadletter()
    assert len(deadletter) == 1
    assert deadletter[0]["work_id"] == claim["work_id"]
    assert queue.list_work() == []


def test_discovery_queue_pause_resume_and_status(tmp_path: Path):
    queue = DiscoveryQueue(tmp_path / "queue")
    assert queue.queue_status()["paused"] is False

    queue.pause()
    assert queue.queue_status()["paused"] is True

    queue.resume()
    assert queue.queue_status()["paused"] is False


def test_discovery_engine_knowledge_search_returns_index_hits(tmp_path: Path):
    fixture_path = _write_fixture_feed(tmp_path)
    seed_file = _write_seed_file(
        tmp_path,
        [
            {
                "topic": "policy boundaries",
                "source": "local_seed_file",
                "metadata": {"collector": "local_fixture"},
            }
        ],
    )

    engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
    engine.run(
        profile="public",
        out=tmp_path,
        seeds_file=seed_file,
        fixture_feed=fixture_path,
        top_k=1,
        min_score=0.01,
    )

    result = engine.knowledge_search(query="policy", out=tmp_path, limit=5)
    assert result["schema_name"] == "AAS.Knowledge.SearchResult"
    assert result["count"] >= 1


def test_discovery_engine_allow_live_automation_can_be_explicitly_disabled(
    tmp_path: Path,
):
    fixture_path = _write_fixture_feed(tmp_path)
    seed_file = _write_seed_file(
        tmp_path,
        [
            {
                "topic": "policy boundaries",
                "source": "local_seed_file",
                "metadata": {"collector": "local_fixture"},
            }
        ],
    )

    engine = build_engine(workspace_root=tmp_path, merlin_mode="local")
    report = engine.run(
        profile="public",
        out=tmp_path,
        seeds_file=seed_file,
        fixture_feed=fixture_path,
        allow_live_automation=False,
    )

    assert report["allow_live_automation"] is False

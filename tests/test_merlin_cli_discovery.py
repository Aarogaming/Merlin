from __future__ import annotations

import json
import sys
from pathlib import Path

import merlin_cli


def _set_argv(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["merlin_cli.py", *args])


def _write_fixture_feed(root: Path) -> Path:
    fixture_path = root / "fixtures" / "local_fixture.jsonl"
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
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture_path


def _write_seed_file(root: Path) -> Path:
    seed_path = root / "seeds.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "topic": "offline discovery orchestration",
                    "source": "local_seed_file",
                    "metadata": {"collector": "local_fixture"},
                }
            ]
        ),
        encoding="utf-8",
    )
    return seed_path


def test_discovery_cli_run_and_queue_status(monkeypatch, tmp_path: Path, capsys):
    fixture_path = _write_fixture_feed(tmp_path)
    seed_path = _write_seed_file(tmp_path)
    out_root = tmp_path / "out"

    _set_argv(
        monkeypatch,
        "discovery",
        "run",
        "--profile",
        "public",
        "--out",
        str(out_root),
        "--seeds-file",
        str(seed_path),
        "--fixture-feed",
        str(fixture_path),
        "--top-k",
        "1",
        "--min-score",
        "0.01",
    )
    merlin_cli.main()
    run_payload = json.loads(capsys.readouterr().out)

    assert run_payload["schema_name"] == "AAS.Discovery.RunReport"
    assert run_payload["profile"] == "public"
    assert run_payload["allow_live_automation"] is True
    assert run_payload["counts"]["artifacts_written"] >= 1

    _set_argv(monkeypatch, "discovery", "queue", "status", "--out", str(out_root))
    merlin_cli.main()
    status_payload = json.loads(capsys.readouterr().out)

    assert status_payload["schema_name"] == "AAS.Discovery.QueueStatus"
    assert status_payload["work"] >= 1

    _set_argv(monkeypatch, "discovery", "queue", "pause", "--out", str(out_root))
    merlin_cli.main()
    paused_payload = json.loads(capsys.readouterr().out)
    assert paused_payload["schema_name"] == "AAS.Discovery.QueuePause"
    assert paused_payload["status"]["paused"] is True

    _set_argv(monkeypatch, "discovery", "queue", "resume", "--out", str(out_root))
    merlin_cli.main()
    resumed_payload = json.loads(capsys.readouterr().out)
    assert resumed_payload["schema_name"] == "AAS.Discovery.QueueResume"
    assert resumed_payload["status"]["paused"] is False

    _set_argv(
        monkeypatch,
        "knowledge",
        "search",
        "offline",
        "--out",
        str(out_root),
        "--limit",
        "5",
    )
    merlin_cli.main()
    search_payload = json.loads(capsys.readouterr().out)
    assert search_payload["schema_name"] == "AAS.Knowledge.SearchResult"
    assert search_payload["count"] >= 1

    _set_argv(
        monkeypatch,
        "discovery",
        "run",
        "--profile",
        "public",
        "--out",
        str(out_root),
        "--seeds-file",
        str(seed_path),
        "--fixture-feed",
        str(fixture_path),
        "--no-live-automation",
    )
    merlin_cli.main()
    no_live_payload = json.loads(capsys.readouterr().out)
    assert no_live_payload["allow_live_automation"] is False

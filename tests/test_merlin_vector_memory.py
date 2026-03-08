from __future__ import annotations

from pathlib import Path

from merlin_vector_memory import MerlinVectorMemory


def test_add_memories_filters_invalid_items_and_persists(tmp_path: Path):
    collection = str(tmp_path / "memory_store")
    memory = MerlinVectorMemory(collection_name=collection)

    memory.add_memories(
        [
            {"text": "alpha document", "metadata": {"path": "a.txt"}},
            {"text": "", "metadata": {"path": "empty.txt"}},
            {"metadata": {"path": "missing.txt"}},
            {"text": "beta document"},
        ]
    )

    assert len(memory.memories) == 2
    assert memory.memories[0]["metadata"]["path"] == "a.txt"
    assert memory.memories[1]["metadata"] == {}
    assert memory.memories[0]["timestamp"] > 0
    assert memory.memories[1]["timestamp"] > 0

    reloaded = MerlinVectorMemory(collection_name=collection)
    assert len(reloaded.memories) == 2
    assert reloaded.query("alpha")[0]["text"] == "alpha document"


def test_add_memory_and_query_limit(tmp_path: Path):
    collection = str(tmp_path / "limit_store")
    memory = MerlinVectorMemory(collection_name=collection)

    memory.add_memory("first hit")
    memory.add_memory("second hit")
    memory.add_memory("third hit")

    results = memory.query("hit", limit=2)
    assert len(results) == 2
    assert results[0]["text"] == "first hit"
    assert results[1]["text"] == "second hit"


def test_compact_memories_deduplicates_and_trims(tmp_path: Path):
    collection = str(tmp_path / "compact_store")
    memory = MerlinVectorMemory(collection_name=collection)
    memory.memories = [
        {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 10.0},
        {"text": "beta", "metadata": {"path": "b"}, "timestamp": 20.0},
        {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 30.0},
        {"text": "gamma", "metadata": {"path": "c"}, "timestamp": 40.0},
    ]

    summary = memory.compact_memories(max_entries=2, deduplicate=True)

    assert summary["before"] == 4
    assert summary["deduplicated"] == 1
    assert summary["trimmed"] == 1
    assert summary["after"] == 2
    assert [item["text"] for item in memory.memories] == ["alpha", "gamma"]


def test_cleanup_stale_vectors_removes_old_entries(tmp_path: Path):
    collection = str(tmp_path / "stale_store")
    memory = MerlinVectorMemory(collection_name=collection)
    memory.memories = [
        {"text": "old", "metadata": {}, "timestamp": 10.0},
        {"text": "recent", "metadata": {}, "timestamp": 95.0},
        {"text": "new", "metadata": {}, "timestamp": 100.0},
    ]

    summary = memory.cleanup_stale_vectors(max_age_seconds=20.0, now=110.0)

    assert summary["before"] == 3
    assert summary["removed_stale"] == 1
    assert summary["after"] == 2
    assert [item["text"] for item in memory.memories] == ["recent", "new"]


def test_integrity_report_flags_invalid_and_duplicate_entries(tmp_path: Path):
    collection = str(tmp_path / "integrity_store")
    memory = MerlinVectorMemory(collection_name=collection)
    memory.memories = [
        {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 10.0},
        {"text": "alpha", "metadata": {"path": "a"}, "timestamp": 11.0},
        {"text": "", "metadata": {"path": "bad"}, "timestamp": 12.0},
        {"text": "beta", "metadata": "bad", "timestamp": 13.0},
    ]

    report = memory.integrity_report()

    assert report["total_entries"] == 4
    assert report["duplicate_entries"] == 1
    assert report["invalid_entries"] == 2
    assert report["invalid_indices"] == [2, 3]
    assert report["oldest_timestamp"] == 10.0
    assert report["newest_timestamp"] == 11.0

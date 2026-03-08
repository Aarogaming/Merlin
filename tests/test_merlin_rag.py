from __future__ import annotations

import json
from pathlib import Path

import merlin_rag as rag_module


class _StubVectorMemory:
    def __init__(self):
        self.added_batches = []
        self.queries = []

    def add_memories(self, memories):
        self.added_batches.append(memories)

    def query(self, query_text, limit=5):
        self.queries.append((query_text, limit))
        return [{"text": f"match:{query_text}", "metadata": {"limit": limit}}]


def _write_index(path: Path):
    payload = {
        "docs": [
            {"path": "docs/a.md", "summary": "alpha"},
            {"path": "docs/b.md"},
            {"summary": "missing-path"},
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_indexing_disabled_by_default_under_pytest(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MERLIN_RAG_INDEX_ON_LOAD", raising=False)
    stub = _StubVectorMemory()
    monkeypatch.setattr(rag_module, "vector_memory", stub)

    index_path = tmp_path / "index.json"
    _write_index(index_path)

    rag = rag_module.MerlinRAG(index_path=str(index_path))
    assert rag.index_on_load is False
    assert rag.documents[0]["path"] == "docs/a.md"
    assert stub.added_batches == []


def test_indexing_on_load_can_be_enabled_and_is_idempotent(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MERLIN_RAG_INDEX_ON_LOAD", "true")
    stub = _StubVectorMemory()
    monkeypatch.setattr(rag_module, "vector_memory", stub)

    index_path = tmp_path / "index.json"
    _write_index(index_path)

    rag = rag_module.MerlinRAG(index_path=str(index_path))
    assert rag.index_on_load is True
    assert rag._indexed_on_load is True
    assert len(stub.added_batches) == 1
    assert len(stub.added_batches[0]) == 2
    assert "Document: docs/a.md." in stub.added_batches[0][0]["text"]

    rag.load_index()
    assert len(stub.added_batches) == 1


def test_search_delegates_to_vector_memory(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MERLIN_RAG_INDEX_ON_LOAD", raising=False)
    stub = _StubVectorMemory()
    monkeypatch.setattr(rag_module, "vector_memory", stub)

    rag = rag_module.MerlinRAG(index_path=str(tmp_path / "missing.json"))
    result = rag.search("policy", limit=3)

    assert stub.queries == [("policy", 3)]
    assert result[0]["text"] == "match:policy"
    diagnostics = rag.get_last_retrieval_diagnostics()
    assert diagnostics["k"] == 3
    assert diagnostics["hit_count"] == 1
    assert diagnostics["top_k_hit_rate"] == 0.3333
    assert diagnostics["source_diversity"] == 0.0


def test_search_updates_relevance_diagnostics_with_source_diversity(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("MERLIN_RAG_INDEX_ON_LOAD", raising=False)
    stub = _StubVectorMemory()
    stub.query = lambda query_text, limit=5: [
        {"text": "a", "metadata": {"path": "docs/a.md"}},
        {"text": "b", "metadata": {"path": "docs/b.md"}},
        {"text": "b2", "metadata": {"path": "docs/b.md"}},
    ]
    monkeypatch.setattr(rag_module, "vector_memory", stub)

    rag = rag_module.MerlinRAG(index_path=str(tmp_path / "missing.json"))
    _ = rag.search("policy", limit=3)
    diagnostics = rag.get_last_retrieval_diagnostics()

    assert diagnostics["k"] == 3
    assert diagnostics["hit_count"] == 3
    assert diagnostics["top_k_hit_rate"] == 1.0
    assert diagnostics["source_diversity"] == 0.6667

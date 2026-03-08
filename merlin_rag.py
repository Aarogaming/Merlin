import os
import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from merlin_logger import merlin_logger
from merlin_vector_memory import vector_memory


class MerlinRAG:
    def __init__(self, index_path="merlin_resource_index.json"):
        self.index_path = Path(index_path)
        self.documents = []
        self.index_on_load = self._should_index_on_load()
        self._indexed_on_load = False
        self.last_retrieval_diagnostics = {
            "top_k_hit_rate": 0.0,
            "source_diversity": 0.0,
            "hit_count": 0,
            "k": 0,
        }
        self.load_index()

    def _should_index_on_load(self) -> bool:
        override = os.getenv("MERLIN_RAG_INDEX_ON_LOAD")
        if override is not None:
            return override.strip().lower() in {"1", "true", "yes", "on"}
        if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
            return False
        return True

    def load_index(self):
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Focus on docs for RAG
                    self.documents = data.get("docs", [])
                    merlin_logger.info(
                        f"RAG loaded {len(self.documents)} documents from index."
                    )

                    if self.index_on_load and not self._indexed_on_load:
                        memories = []
                        for doc in self.documents:
                            doc_path = doc.get("path")
                            if not doc_path:
                                continue
                            memories.append(
                                {
                                    "text": f"Document: {doc_path}. Content summary: {doc.get('summary', 'No summary available')}",
                                    "metadata": {"path": doc_path, "type": "doc"},
                                }
                            )
                        vector_memory.add_memories(memories)
                        self._indexed_on_load = True
            except Exception as e:
                merlin_logger.error(f"RAG failed to load index: {e}")

    def _compute_retrieval_diagnostics(
        self, matches: List[Dict[str, Any]], limit: int
    ) -> Dict[str, Any]:
        requested_k = max(1, int(limit))
        hit_count = len(matches)
        top_k_hit_rate = round(min(hit_count, requested_k) / requested_k, 4)

        unique_sources = set()
        for match in matches:
            if not isinstance(match, dict):
                continue
            metadata = match.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            source_candidate = metadata.get("path") or metadata.get("source_id")
            if isinstance(source_candidate, str) and source_candidate.strip():
                unique_sources.add(source_candidate.strip())

        source_diversity = (
            round(len(unique_sources) / hit_count, 4) if hit_count > 0 else 0.0
        )
        return {
            "top_k_hit_rate": top_k_hit_rate,
            "source_diversity": source_diversity,
            "hit_count": hit_count,
            "k": requested_k,
        }

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        merlin_logger.info(f"RAG searching for: {query}")
        # Use vector memory for semantic search.
        matches = vector_memory.query(query, limit=limit)
        normalized_matches = matches if isinstance(matches, list) else []
        self.last_retrieval_diagnostics = self._compute_retrieval_diagnostics(
            normalized_matches,
            limit=limit,
        )
        return normalized_matches

    def get_last_retrieval_diagnostics(self) -> Dict[str, Any]:
        return dict(self.last_retrieval_diagnostics)


merlin_rag = MerlinRAG()

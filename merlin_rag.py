import os
import json
from pathlib import Path
from typing import List, Dict, Any
from merlin_logger import merlin_logger
from merlin_vector_memory import vector_memory


class MerlinRAG:
    def __init__(self, index_path="merlin_resource_index.json"):
        self.index_path = Path(index_path)
        self.documents = []
        self.load_index()

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

                    # Index documents into vector memory (simulated)
                    for doc in self.documents:
                        vector_memory.add_memory(
                            text=f"Document: {doc['path']}. Content summary: {doc.get('summary', 'No summary available')}",
                            metadata={"path": doc["path"], "type": "doc"},
                        )
            except Exception as e:
                merlin_logger.error(f"RAG failed to load index: {e}")

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        merlin_logger.info(f"RAG searching for: {query}")
        # Use vector memory for semantic search (simulated)
        return vector_memory.query(query, limit=limit)


merlin_rag = MerlinRAG()

import json
import os
from typing import List, Dict, Any
from merlin_logger import merlin_logger

class MerlinVectorMemory:
    def __init__(self, collection_name="merlin_memory"):
        self.collection_name = collection_name
        self.storage_file = f"{collection_name}.json"
        self.memories = self._load_memories()

    def _load_memories(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                merlin_logger.error(f"Failed to load vector memory: {e}")
        return []

    def _save_memories(self):
        try:
            with open(self.storage_file, "w") as f:
                json.dump(self.memories, f, indent=2)
        except Exception as e:
            merlin_logger.error(f"Failed to save vector memory: {e}")

    def add_memory(self, text: str, metadata: Dict[str, Any] = None):
        # In a real Vector DB, this would generate embeddings
        memory = {
            "text": text,
            "metadata": metadata or {},
            "timestamp": os.path.getmtime(self.storage_file) if os.path.exists(self.storage_file) else 0
        }
        self.memories.append(memory)
        self._save_memories()
        merlin_logger.info(f"Added memory to {self.collection_name}")

    def query(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Simple keyword-based similarity for this prototype
        results = []
        query_text = query_text.lower()
        for memory in self.memories:
            if query_text in memory["text"].lower():
                results.append(memory)
            if len(results) >= limit:
                break
        return results

vector_memory = MerlinVectorMemory()

if __name__ == "__main__":
    vector_memory.add_memory("Merlin was updated with self-healing capabilities on Jan 12, 2026.")
    print(vector_memory.query("self-healing"))

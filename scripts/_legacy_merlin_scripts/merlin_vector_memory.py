import json
import os
import time
from typing import Any, Dict, List, Optional
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

    def _build_memory(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # In a real Vector DB, this would generate embeddings.
        memory = {
            "text": text,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        return memory

    def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        memory = self._build_memory(text=text, metadata=metadata)
        self.memories.append(memory)
        self._save_memories()
        merlin_logger.info(f"Added memory to {self.collection_name}")

    def add_memories(self, memories: List[Dict[str, Any]]):
        if not memories:
            return

        added = 0
        for item in memories:
            text = item.get("text")
            if not text:
                continue
            memory = self._build_memory(text=text, metadata=item.get("metadata"))
            self.memories.append(memory)
            added += 1

        if added == 0:
            return

        self._save_memories()
        merlin_logger.info(f"Added {added} memories to {self.collection_name}")

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

    def _memory_identity_key(self, memory: Dict[str, Any]) -> str:
        text = str(memory.get("text", "")).strip()
        metadata = memory.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        try:
            metadata_key = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        except TypeError:
            metadata_key = str(metadata)
        return f"{text}\n{metadata_key}"

    def _memory_timestamp(self, memory: Dict[str, Any]) -> float:
        raw_timestamp = memory.get("timestamp")
        if isinstance(raw_timestamp, (int, float)):
            return float(raw_timestamp)
        return 0.0

    def compact_memories(
        self,
        max_entries: Optional[int] = None,
        *,
        deduplicate: bool = True,
    ) -> Dict[str, Any]:
        """
        Compact vector memory by deduplicating and optionally trimming history size.
        Keeps newest entries when trimming.
        """
        before_count = len(self.memories)
        working = list(self.memories)

        deduplicated_count = 0
        if deduplicate:
            seen_keys: set[str] = set()
            deduped: List[Dict[str, Any]] = []
            for memory in sorted(working, key=self._memory_timestamp, reverse=True):
                identity = self._memory_identity_key(memory)
                if identity in seen_keys:
                    deduplicated_count += 1
                    continue
                seen_keys.add(identity)
                deduped.append(memory)
            working = list(reversed(deduped))

        trimmed_count = 0
        if isinstance(max_entries, int) and max_entries > 0 and len(working) > max_entries:
            trimmed_count = len(working) - max_entries
            working = working[-max_entries:]

        self.memories = working
        if deduplicated_count > 0 or trimmed_count > 0:
            self._save_memories()

        return {
            "before": before_count,
            "after": len(self.memories),
            "deduplicated": deduplicated_count,
            "trimmed": trimmed_count,
            "removed": deduplicated_count + trimmed_count,
        }

    def cleanup_stale_vectors(
        self,
        *,
        max_age_seconds: float,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Remove stale vector memories older than max_age_seconds.
        """
        if not isinstance(max_age_seconds, (int, float)) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be a positive number")

        reference_time = float(now) if isinstance(now, (int, float)) else time.time()
        cutoff = reference_time - float(max_age_seconds)

        before_count = len(self.memories)
        kept: List[Dict[str, Any]] = []
        removed_stale = 0
        for memory in self.memories:
            timestamp = self._memory_timestamp(memory)
            if timestamp < cutoff:
                removed_stale += 1
                continue
            kept.append(memory)

        self.memories = kept
        if removed_stale > 0:
            self._save_memories()

        return {
            "before": before_count,
            "after": len(self.memories),
            "removed_stale": removed_stale,
        }

    def integrity_report(self) -> Dict[str, Any]:
        invalid_indices: List[int] = []
        duplicate_entries = 0
        seen_keys: set[str] = set()
        timestamps: List[float] = []

        for index, memory in enumerate(self.memories):
            is_valid = True
            if not isinstance(memory, dict):
                is_valid = False
            else:
                text = memory.get("text")
                metadata = memory.get("metadata")
                timestamp = memory.get("timestamp")
                if not isinstance(text, str) or not text.strip():
                    is_valid = False
                if not isinstance(metadata, dict):
                    is_valid = False
                if not isinstance(timestamp, (int, float)) or float(timestamp) <= 0:
                    is_valid = False

            if not is_valid:
                invalid_indices.append(index)
                continue

            timestamp_value = float(memory["timestamp"])
            timestamps.append(timestamp_value)
            identity = self._memory_identity_key(memory)
            if identity in seen_keys:
                duplicate_entries += 1
            else:
                seen_keys.add(identity)

        return {
            "collection_name": self.collection_name,
            "storage_file": self.storage_file,
            "total_entries": len(self.memories),
            "invalid_entries": len(invalid_indices),
            "invalid_indices": invalid_indices,
            "duplicate_entries": duplicate_entries,
            "oldest_timestamp": min(timestamps) if timestamps else None,
            "newest_timestamp": max(timestamps) if timestamps else None,
        }


vector_memory = MerlinVectorMemory()

if __name__ == "__main__":
    vector_memory.add_memory(
        "Merlin was updated with self-healing capabilities on Jan 12, 2026."
    )
    print(vector_memory.query("self-healing"))

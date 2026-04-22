import json
import sqlite3
from pathlib import Path
from datetime import datetime

try:
    import litellm
    import sqlite_vec
    HAS_VECTOR = True
except ImportError:
    HAS_VECTOR = False

from aas_kernel import ReflexPlugin

class Knowledge(ReflexPlugin):
    """
    Domain: Library (Knowledge)
    Manages Omni Constellation relations and Vector Embeddings.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_path = Path(__file__).resolve().parents[1] / "artifacts" / "knowledge.sqlite"
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        
        if HAS_VECTOR:
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                domain TEXT,
                content TEXT
            )
        """)
        if HAS_VECTOR:
            try:
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge USING vec0(embedding float[1536])")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    @property
    def capabilities(self) -> list[str]:
        return [
            "aaroneousautomationsuite_store_memory",
            "aaroneousautomationsuite_query_memory",
            "aaroneousautomationsuite_library_map_omni_node",
            "aaroneousautomationsuite_library_query_omni_constellation",
            "aaroneousautomationsuite_library_record_sop"
        ]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        import time
        start_time = time.time()
        cursor = self.conn.cursor()

        if capability_id == "aaroneousautomationsuite_store_memory":
            content = payload.get("content", "")
            cursor.execute(
                "INSERT INTO knowledge_nodes (timestamp, domain, content) VALUES (?, ?, ?)",
                (datetime.utcnow().isoformat(), "epigenetic", content)
            )
            self.conn.commit()
            return self._format_success(capability_id, f"Stored at index {cursor.lastrowid}", start_time)

        elif capability_id == "aaroneousautomationsuite_query_memory":
            query = payload.get("query", "")
            
            # --- Dynamic Spectrum Implementation ---
            # Deeply analytical agents pull more memory context
            depth = self.cognitive_biases.get("analytical_depth", 50.0)
            # Base limit is 5. High analytical depth pushes limit higher (50 -> 5, 100 -> 15).
            depth_scalar = depth / 50.0
            query_limit = int(max(1, 5 * (depth_scalar * 3)))
            
            cursor.execute("SELECT content FROM knowledge_nodes WHERE content LIKE ? LIMIT ?", (f"%{query}%", query_limit))
            results = [row[0] for row in cursor.fetchall()]
            
            return self._format_success(capability_id, {"results": results, "analytical_depth_applied": depth, "limit": query_limit}, start_time)

        elif capability_id == "aaroneousautomationsuite_library_map_omni_node":
            return self._format_success(capability_id, f"Mapped Omni Node: {payload.get('node_name')}", start_time)
            
        elif capability_id == "aaroneousautomationsuite_library_query_omni_constellation":
            return self._format_success(capability_id, f"Constellation data for {payload.get('target_node')}", start_time)
            
        elif capability_id == "aaroneousautomationsuite_library_record_sop":
            return self._format_success(capability_id, "SOP Crystallized", start_time)

        return self._format_error(capability_id, "Unknown knowledge capability.")

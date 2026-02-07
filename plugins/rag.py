# Merlin Plugin: RAG Search
from merlin_rag import merlin_rag


class MerlinRagPlugin:
    def __init__(self):
        self.name = "rag"
        self.description = "RAG search over Merlin's indexed documents."
        self.version = "1.0.0"
        self.author = "AAS"

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
        }

    def execute(self, query: str, limit: int = 5):
        if not query:
            return {"error": "query_required"}
        try:
            results = merlin_rag.search(query, limit=limit)
        except Exception as exc:
            return {"error": "rag_search_failed", "detail": str(exc)}
        return {"query": query, "limit": limit, "results": results}


def get_plugin():
    return MerlinRagPlugin()

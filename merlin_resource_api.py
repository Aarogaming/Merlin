from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import json
import os
import logging

app = FastAPI()


# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "merlin_resource_config.json")
DEFAULT_INDEX_PATH = os.path.join(os.path.dirname(__file__), "merlin_resource_index.json")
DEFAULT_LOG_LEVEL = "INFO"

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
RESOURCE_INDEX_PATH = os.path.join(os.path.dirname(__file__), config.get("resource_index_path", "merlin_resource_index.json"))
log_level = config.get("log_level", DEFAULT_LOG_LEVEL).upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s %(levelname)s %(message)s')


# Load resource index at startup
def load_resource_index():
    if os.path.exists(RESOURCE_INDEX_PATH):
        with open(RESOURCE_INDEX_PATH, "r", encoding="utf-8") as f:
            logging.info(f"Loaded resource index from {RESOURCE_INDEX_PATH}")
            return json.load(f)
    logging.warning(f"Resource index not found at {RESOURCE_INDEX_PATH}")
    return {}

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/resources/refresh")
def refresh_resources():
    # In a real implementation, this would trigger merlin_resource_indexer.py
    # For now, we just reload the index from disk
    index = load_resource_index()
    counts = {k: len(v) for k, v in index.items()}
    return {"status": "refreshed", "counts": counts}

@app.get("/resources")
def get_resources(type: str = Query(None, description="Resource type: audio, scripts, executables, docs")):
    index = load_resource_index()
    if type:
        return JSONResponse(content=index.get(type, []))
    return JSONResponse(content=index)

@app.get("/resources/search")
def search_resources(q: str = Query(..., description="Search string"), type: str = Query(None, description="Resource type")):
    index = load_resource_index()
    results = []
    types = [type] if type else index.keys()
    for t in types:
        for item in index.get(t, []):
            if q.lower() in item["path"].lower():
                results.append(item)
    return JSONResponse(content=results)

# Example: Run with `uvicorn merlin_resource_api:app --reload`

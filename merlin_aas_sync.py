import requests
import os
import json
import logging
from merlin_logger import merlin_logger

AAS_DOCS_URL = os.environ.get(
    "AAS_DOCS_URL",
    "https://raw.githubusercontent.com/aaroneous/aas/main/docs/context.json",
)
SYNC_INTERVAL_HOURS = int(os.environ.get("MERLIN_SYNC_INTERVAL", "24"))


def sync_aas_context():
    merlin_logger.info("Starting AAS context sync...")
    try:
        response = requests.get(AAS_DOCS_URL, timeout=30)
        response.raise_for_status()
        context_data = response.json()

        # Save context locally
        with open("aas_context.json", "w", encoding="utf-8") as f:
            json.dump(context_data, f, indent=2)

        merlin_logger.info("AAS context synced successfully.")
        return True
    except Exception as e:
        merlin_logger.error(f"Failed to sync AAS context: {e}")
        return False


def get_aas_context():
    if os.path.exists("aas_context.json"):
        with open("aas_context.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    sync_aas_context()

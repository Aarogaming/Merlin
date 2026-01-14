import json
import os
from pathlib import Path
from merlin_emotion_chat import load_chat
from merlin_logger import merlin_logger

def export_user_data_json(user_id):
    history = load_chat(user_id)
    export_data = {
        "user_id": user_id,
        "history": history,
        "settings_snapshot": {
            "LM_STUDIO_URL": os.environ.get("LM_STUDIO_URL"),
            "OPENAI_MODEL": os.environ.get("OPENAI_MODEL")
        }
    }
    
    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)
    
    file_path = export_dir / f"export_{user_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
        merlin_logger.info(f"Data exported for user {user_id} to {file_path}")
        return str(file_path)
    except Exception as e:
        merlin_logger.error(f"Export failed for user {user_id}: {e}")
        return None

if __name__ == "__main__":
    print(export_user_data_json("default"))

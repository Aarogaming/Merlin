import os
import shutil
import pathlib

ALLOWED_ROOT = os.path.abspath(".")

def is_path_allowed(path):
    abs_path = os.path.abspath(path)
    return abs_path.startswith(ALLOWED_ROOT)

def list_files(path="."):
    if not is_path_allowed(path):
        return {"error": "Access denied: Path outside allowed root."}
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            is_dir = os.path.isdir(full_path)
            result.append({
                "name": item,
                "is_dir": is_dir,
                "size": os.path.getsize(full_path) if not is_dir else 0,
                "path": os.path.abspath(full_path)
            })
        return result
    except Exception as e:
        return {"error": str(e)}

def delete_file(path):
    if not is_path_allowed(path):
        return {"error": "Access denied: Path outside allowed root."}
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

def move_file(src, dst):
    if not is_path_allowed(src) or not is_path_allowed(dst):
        return {"error": "Access denied: Path outside allowed root."}
    try:
        shutil.move(src, dst)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

def open_file(path):
    if not is_path_allowed(path):
        return {"error": "Access denied: Path outside allowed root."}
    try:
        os.startfile(path)
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import json
    print(json.dumps(list_files(), indent=2))

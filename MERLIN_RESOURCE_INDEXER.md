# Merlin Resource Indexer Module

## Purpose

Automatically scan, catalog, and document available local resources (scripts, sounds, docs, programs) for Merlin’s use. Enables dynamic inventory refresh and safe access.

---

## Features

- **Scan workspace for:**
  - Audio files (mp3, wav, ogg, flac)
  - Scripts (py, ps1, bat, sh, js, ts, etc.)
  - Executables/programs (exe, msi, app, jar)
  - Documentation (md, txt, pdf, docx)

- **Catalog results:**
  - Store resource lists in a structured format (JSON, YAML, or DB)
  - Include metadata: path, type, last modified, size

- **Dynamic refresh:**
  - Scheduled or on-demand re-scan

- **Security controls:**
  - Permission checks before access/execute
  - Logging of resource usage

- **Integration hooks:**
  - API for Merlin to query resources
  - UI module for browsing resources

---

## Implementation Plan

1. **Prototype Python script:**
   - Use `os`, `glob`, and `pathlib` to scan directories
   - Output to JSON file

2. **Integrate with Merlin backend:**
   - Add API endpoint for resource queries
   - Add permission and logging hooks

3. **UI integration:**
   - Resource browser in Merlin’s frontend

4. **Documentation:**
   - Document module usage and update checklist

---

## Configuration

Edit `merlin_resource_config.json` to control:

- `scan_root`: root directory to scan (relative to this file)
- `exclude_dirs`: directories to skip (e.g., `.git`, `node_modules`)
- `exclude_globs`: filename patterns to ignore
- `max_file_size_mb`: skip files above this size
- `relative_paths`: store relative paths for portability

---

## Usage

Build the index:

```bash
python merlin_resource_indexer.py
```

Query the index from CLI:

```bash
python merlin_resource_cli.py --search ".md" --limit 10
```

---

## Example Output

```json
{
  "audio": [
    {"path": ".../assets/audio/01-42.mp3", "type": "mp3", "size": 123456, "modified": "2026-01-10T12:34:56"},
    ...
  ],
  "scripts": [
    {"path": ".../scripts/aas_tray.py", "type": "py", "size": 2345, "modified": "2026-01-09T09:00:00"},
    ...
  ],
  ...
}
```

---

*This module will make Merlin smarter, safer, and more resourceful!*

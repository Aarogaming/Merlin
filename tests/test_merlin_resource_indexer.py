from pathlib import Path

import merlin_resource_indexer as indexer


def test_scan_resources_respects_excludes(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "song.mp3").write_bytes(b"data")
    (root / "notes.txt").write_text("hello", encoding="utf-8")

    node_modules = root / "node_modules"
    node_modules.mkdir()
    (node_modules / "skip.js").write_text("ignore", encoding="utf-8")

    log_file = root / "debug.log"
    log_file.write_text("ignore", encoding="utf-8")

    config_path = tmp_path / "merlin_resource_config.json"
    config_path.write_text(
        "{\n"
        '  "resource_index_path": "merlin_resource_index.json",\n'
        '  "log_level": "INFO",\n'
        '  "scan_root": ".",\n'
        '  "exclude_dirs": ["node_modules"],\n'
        '  "exclude_globs": ["*.log"],\n'
        '  "max_file_size_mb": 1,\n'
        '  "follow_symlinks": false,\n'
        '  "include_hidden": false,\n'
        '  "relative_paths": true\n'
        "}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(indexer, "CONFIG_PATH", config_path)

    resources = indexer.scan_resources(str(root))

    audio_paths = {item["path"] for item in resources["audio"]}
    doc_paths = {item["path"] for item in resources["docs"]}
    script_paths = {item["path"] for item in resources["scripts"]}

    assert "song.mp3" in audio_paths
    assert "notes.txt" in doc_paths
    assert not any("node_modules" in path for path in script_paths)
    assert not any(
        path.endswith(".log") for path in audio_paths | doc_paths | script_paths
    )

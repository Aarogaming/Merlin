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


def test_scan_resources_reuses_hash_cache_for_unchanged_files(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    config_path = tmp_path / "merlin_resource_config.json"
    config_path.write_text(
        "{\n"
        '  "resource_index_path": "merlin_resource_index.json",\n'
        '  "resource_hash_cache_path": "merlin_resource_hash_cache.json",\n'
        '  "scan_root": ".",\n'
        '  "exclude_dirs": [],\n'
        '  "exclude_globs": [],\n'
        '  "max_file_size_mb": 5\n'
        "}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(indexer, "CONFIG_PATH", config_path)
    hash_calls: list[str] = []
    real_hash = indexer._hash_file_sha256

    def _tracking_hash(file_path, chunk_size=1024 * 1024):
        hash_calls.append(str(file_path))
        return real_hash(file_path, chunk_size=chunk_size)

    monkeypatch.setattr(indexer, "_hash_file_sha256", _tracking_hash)

    first = indexer.scan_resources(str(root))
    assert len(hash_calls) == 1
    first_hash = first["docs"][0]["sha256"]
    assert isinstance(first_hash, str) and first_hash

    hash_calls.clear()
    second = indexer.scan_resources(str(root))
    assert len(hash_calls) == 0
    assert second["docs"][0]["sha256"] == first_hash

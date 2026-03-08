from __future__ import annotations

import json
from pathlib import Path

from merlin_voice_benchmark import _build_dataset_metadata, _load_source_catalog


def test_load_source_catalog_missing_file_returns_default(tmp_path: Path):
    missing_path = tmp_path / "missing_sources.json"
    catalog = _load_source_catalog(missing_path)

    assert catalog["schema_name"] == "AAS.VoiceSourceCatalog"
    assert catalog["dataset_version"] == "unknown"
    assert catalog["sources"] == []
    assert catalog["provenance"]["status"] == "missing"


def test_build_dataset_metadata_filters_selected_sources(tmp_path: Path):
    catalog_path = tmp_path / "sources.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_name": "AAS.VoiceSourceCatalog",
                "schema_version": "1.0.0",
                "dataset_version": "2026.02",
                "provenance": {"maintainer": "merlin"},
                "sources": [
                    {"id": "ljspeech", "label": "LJSpeech"},
                    {"id": "vctk", "label": "VCTK"},
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = _load_source_catalog(catalog_path)

    metadata = _build_dataset_metadata(
        catalog=catalog,
        source_catalog_path=catalog_path,
        selected_source_ids=["vctk"],
        override_dataset_version=None,
    )

    assert metadata["dataset_version"] == "2026.02"
    assert metadata["selected_source_ids"] == ["vctk"]
    assert len(metadata["selected_sources"]) == 1
    assert metadata["selected_sources"][0]["id"] == "vctk"


def test_build_dataset_metadata_supports_dataset_version_override(tmp_path: Path):
    catalog = {
        "schema_name": "AAS.VoiceSourceCatalog",
        "schema_version": "1.0.0",
        "dataset_version": "2026.01",
        "provenance": {"maintainer": "merlin"},
        "sources": [],
    }
    metadata = _build_dataset_metadata(
        catalog=catalog,
        source_catalog_path=tmp_path / "sources.json",
        selected_source_ids=[],
        override_dataset_version="2026.03-hotfix",
    )

    assert metadata["dataset_version"] == "2026.03-hotfix"

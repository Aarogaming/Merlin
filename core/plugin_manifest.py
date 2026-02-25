from __future__ import annotations

from typing import Any


def get_hive_metadata(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return normalized hive metadata from plugin manifest extensions.

    This shim keeps packaged plugins compatible in standalone Merlin runtime,
    where the legacy `core.plugin_manifest` import path may be unavailable.
    """

    if not isinstance(manifest, dict):
        return {}

    extensions = manifest.get("extensions")
    if isinstance(extensions, dict):
        aas_metadata = extensions.get("aas")
        if isinstance(aas_metadata, dict):
            return dict(aas_metadata)

    legacy = manifest.get("aas")
    if isinstance(legacy, dict):
        return dict(legacy)
    return {}

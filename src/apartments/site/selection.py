"""The app's model selection (config/main-analysis.json), for the build and the pages."""

from __future__ import annotations

import json
from pathlib import Path

SELECTION = Path(__file__).resolve().parents[3] / "config" / "main-analysis.json"
SELECTION_FIELDS = ("run", "model", "selected_by", "selection_reason", "uncertainty")


def selection_note(selection: Path, bundle_sha256: str | None) -> dict | None:
    """Why the published bundle is served: the selection's own words, when the
    selection names this bundle (None for a bundle published by hand)."""
    try:
        record = json.loads(selection.read_text())
    except (OSError, ValueError):
        return None
    if not bundle_sha256 or record.get("summary_manifest_sha256") != bundle_sha256:
        return None
    return {k: record[k] for k in SELECTION_FIELDS if k in record}

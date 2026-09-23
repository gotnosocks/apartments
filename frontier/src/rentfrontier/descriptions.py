"""Advertisement description text, joined by audit_id (own advertisement only).

Source: the existing description evidence bundle (read-only). Each row there
is the text of that listing's own advertisement, matched by audit_id and
source listing id, so text never travels between listings of a unit.

The extracted (audit_id, description) table is cached under
OUTPUT_ROOT/features/ with a provenance record: source path, source
SHA-256 and the code commit that built it.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from . import data

SOURCE = Path(
    os.environ.get(
        "FRONTIER_DESCRIPTIONS",
        "/home/ben/code/apartments/data/model/chelsea-refreshed-bayesian-descriptions-20260918/evidence.jsonl",
    )
)


def _commit() -> str:
    commit = os.environ.get("FRONTIER_COMMIT")
    if commit:
        return commit
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load(source: Path = SOURCE) -> pd.DataFrame:
    digest = data.sha256(source)
    out_dir = data.OUTPUT_ROOT / "features"
    cache = out_dir / f"descriptions-{digest[:16]}.parquet"
    if not cache.exists():
        rows = []
        with open(source) as fh:
            for line in fh:
                r = json.loads(line)
                rows.append(
                    (
                        r["audit_id"],
                        r.get("source_listing_id"),
                        r.get("description") or "",
                        r.get("description_source"),
                    )
                )
        table = pd.DataFrame(
            rows,
            columns=[
                "audit_id",
                "desc_listing_id",
                "description",
                "description_source",
            ],
        )
        table = table.drop_duplicates("audit_id")
        out_dir.mkdir(parents=True, exist_ok=True)
        table.to_parquet(cache.with_suffix(".tmp"))
        cache.with_suffix(".tmp").rename(cache)
        cache.with_suffix(".json").write_text(
            json.dumps(
                {
                    "source": str(source),
                    "source_sha256": digest,
                    "commit": _commit(),
                    "rows": len(table),
                },
                indent=2,
            )
        )
    table = pd.read_parquet(cache)
    table.attrs["source_sha256"] = digest
    return table


def attach(frame: pd.DataFrame) -> pd.Series:
    """Lower-cased description per frame row ('' when unavailable)."""
    table = load()
    merged = frame[["audit_id", "source_listing_id"]].merge(
        table, on="audit_id", how="left"
    )
    mismatch = merged.desc_listing_id.notna() & (
        merged.desc_listing_id != merged.source_listing_id
    )
    if mismatch.any():
        raise ValueError(
            f"{int(mismatch.sum())} descriptions belong to a different listing id"
        )
    return merged.description.fillna("").str.lower().set_axis(frame.index)

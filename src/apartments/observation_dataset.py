"""Streaming raw-plus-corrected observations for the next model preparation stage.

This does not join the latest attributes onto historical price events. A capture's
price_history is source evidence, not an assertion that its attributes were valid
throughout every episode in that history.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

import duckdb

from .corrections import CorrectionError, Overlay, canonical, instant

VERSION = "observation-overlay-v1"


def iter_observations(
    db,
    overlay: Overlay,
    *,
    collected_as_of=None,
    interpreted_as_of=None,
    effective_at=None,
    version_id=None,
    known_as_of=None,
):
    """Read versions without guessing attribute validity from collection dates.

    Use known_as_of for a strict historical reconstruction. Other cutoffs are
    intentionally independent; API callers construct Overlay(as_of=...) explicitly.
    """
    if known_as_of is not None:
        if collected_as_of is not None or interpreted_as_of is not None:
            raise CorrectionError(
                "known_as_of cannot be combined with separate collection/interpretation cutoffs"
            )
        if overlay.enabled and overlay.as_of > instant(known_as_of):
            raise CorrectionError(
                "Overlay contains later knowledge; set corrections_as_of to known_as_of or earlier"
            )
        collected_as_of = interpreted_as_of = known_as_of
    filters, args = [], []
    for column, value in [
        ("collected_at", collected_as_of),
        ("recorded_at", interpreted_as_of),
    ]:
        if value is not None:
            filters.append(f"{column} <= ?")
            args.append(instant(value))
    if version_id is not None:
        filters.append("version_id = ?")
        args.append(version_id)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    cursor = db.execute(
        """SELECT version_id,capture_id,source,source_listing_id,
        episode_id,building_slug,unit,
        strftime(collected_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') AS collected_at,
        collection_time_basis,
        strftime(recorded_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') AS recorded_at,
        parser_version,
        strftime(source_created_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') AS source_created_at,
        strftime(source_updated_at AT TIME ZONE 'UTC','%Y-%m-%dT%H:%M:%S.%fZ') AS source_updated_at,
        source_on_market_date,
        structured_json,provenance_json FROM attribute_versions"""
        + where
        + " ORDER BY version_id",
        args,
    )
    columns = [c[0] for c in cursor.description]
    while batch := cursor.fetchmany(32):
        for row in batch:
            values = dict(zip(columns, row))
            raw = json.loads(values.pop("structured_json"))
            provenance = json.loads(values.pop("provenance_json"))
            context = {
                k: values[k]
                for k in (
                    "version_id",
                    "capture_id",
                    "source",
                    "source_listing_id",
                    "episode_id",
                    "building_slug",
                    "unit",
                )
            }
            corrected, edits = overlay.apply(raw, context, effective_at=effective_at)
            # The envelope is original evidence: edits cannot change selectors or clocks.
            clocks = {
                k: v.isoformat() if hasattr(v, "isoformat") else v
                for k, v in values.items()
            }
            yield {
                "observation": clocks,
                "provenance": provenance,
                "raw": raw,
                "corrected": corrected,
                "corrections": edits,
                "effective_at": instant(effective_at).isoformat()
                if effective_at
                else None,
                "attribute_time_basis": "capture_observation; historical validity requires separate episode evidence",
            }


def export_observations(db_path, output, overlay, **selection):
    """Publish a new derived bundle, with its completeness manifest written last."""
    output = Path(output)
    db = duckdb.connect(
        str(db_path), read_only=True, config={"memory_limit": "512MB", "threads": "2"}
    )
    count = corrected = 0
    applied = set()
    input_hash, output_hash = hashlib.sha256(), hashlib.sha256()
    try:
        # Refuse overwrites, including previously interrupted exports.
        output.mkdir(parents=True, exist_ok=False)
        partial = output / "observations.jsonl.partial"
        with partial.open("x", encoding="utf-8") as stream:
            for row in iter_observations(db, overlay, **selection):
                input_hash.update(
                    (
                        canonical(
                            {k: row[k] for k in ("observation", "raw", "provenance")}
                        )
                        + "\n"
                    ).encode()
                )
                line = canonical(row) + "\n"
                stream.write(line)
                output_hash.update(line.encode())
                count += 1
                corrected += bool(row["corrections"])
                applied.update(e["id"] for e in row["corrections"])
        partial.rename(output / "observations.jsonl")
        # Freeze the visible ledger prefix, including withdrawn/superseded edits.
        (output / "corrections.jsonl").write_text(
            "".join(canonical(r) + "\n" for r in overlay.records), encoding="utf-8"
        )
        manifest = {
            "dataset_version": VERSION,
            "observations": count,
            "corrected_observations": corrected,
            "applied_correction_ids": sorted(applied),
            "overlay": overlay.manifest,
            "selection": {
                k: v.isoformat() if isinstance(v, datetime) else v
                for k, v in selection.items()
            },
            "source_observations_sha256": input_hash.hexdigest(),
            "observations_sha256": output_hash.hexdigest(),
            "limitations": [
                "Observation export, not a fitted model or a verified physical-unit/episode training table.",
                "Source and corrected documents are separate; collection time is not attribute effective time.",
                "Legacy building_overrides.json is not applied to this observation layer.",
            ],
        }
        (output / "metadata.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return manifest
    finally:
        db.close()

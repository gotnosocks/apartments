"""Validate and publish a completed local or cloud granular transform.

The completion marker is written last. Failed validation leaves the run
incomplete, so it can be inspected or resumed without advertising partial data.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import pyarrow.parquet as pq

from . import inventory_links
from .canonical_units import SCHEMAS as UNIT_SCHEMAS, build_canonical_units
from .granular_export import SCHEMAS, implementation_hash, shard_files_valid, write_json
from .granular_quality import audit_dataset
from .granular_report import render_report
from .unit_canonical import ASSOCIATION_RULE


METADATA_TABLES = frozenset(
    {"snapshots", "fetch_observations", "frontier", "url_aliases"}
)
SHARD_TABLES = frozenset(SCHEMAS) - METADATA_TABLES


def _require_files(root: Path, table: str, expected: set[str]) -> None:
    """Reject extra files even when they contain zero rows."""
    directory = root / table
    actual = {str(path.relative_to(directory)) for path in directory.rglob("*.parquet")}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"Output files mismatch for {table}: missing={missing}, unexpected={unexpected}"
        )


def _validate_source_outputs(
    root: Path, plan: dict
) -> tuple[list[dict], dict[str, int]]:
    metadata_counts = plan["metadata_counts"]
    if set(metadata_counts) != METADATA_TABLES:
        raise ValueError("Metadata table set does not match the transform schema")

    for table, count in metadata_counts.items():
        _require_files(root, table, {"metadata.parquet"})
        if pq.read_metadata(root / table / "metadata.parquet").num_rows != count:
            raise ValueError(f"Metadata count mismatch: {table}")

    checkpoints = []
    counts = Counter(metadata_counts)
    source_hash = implementation_hash()
    for part in range(plan["shards"]):
        checkpoint = root / "checkpoints" / f"{part:05d}.json"
        if not checkpoint.is_file():
            raise ValueError(
                f"Missing shard checkpoint {part}; resume before finalizing"
            )
        result = json.loads(checkpoint.read_text())
        if result.get("part") != part:
            raise ValueError(
                f"Checkpoint part mismatch: expected {part}, got {result.get('part')}"
            )
        if result.get("implementation_sha256") != source_hash:
            raise ValueError("Mixed parser versions; choose a new run ID")
        if set(result["counts"]) != SHARD_TABLES:
            raise ValueError(
                f"Shard {part} table set does not match the transform schema"
            )
        if not shard_files_valid(root, result):
            raise ValueError(
                f"Missing or damaged shard output {part}; resume before finalizing"
            )
        counts.update(result["counts"])
        checkpoints.append(result)

    expected_parts = {f"part-{part:05d}.parquet" for part in range(plan["shards"])}
    for table in SHARD_TABLES:
        _require_files(root, table, expected_parts)
    return checkpoints, dict(counts)


def _inventory_interpretation(root: Path) -> dict:
    marker = root / "inventory-links.json"
    if not marker.exists():
        result = inventory_links.build_inventory_links(root)
        write_json(marker, result)
    else:
        result = json.loads(marker.read_text())
        source_hash = hashlib.sha256(
            Path(inventory_links.__file__).read_bytes()
        ).hexdigest()
        if result["implementation_sha256"] != source_hash:
            raise ValueError(
                "Inventory link parser changed; choose a new derived interpretation"
            )
    _require_files(root, "inventory_row_links", {"derived.parquet"})
    if (
        pq.read_metadata(root / "inventory_row_links" / "derived.parquet").num_rows
        != result["rows"]
    ):
        raise ValueError("Inventory link output changed")
    return result


def _validate_audit(audit: dict, expected_counts: dict[str, int]) -> None:
    actual_counts = audit["tables"]["counts"]
    for table, expected in expected_counts.items():
        if actual_counts.get(table, 0) != expected:
            raise ValueError(f"Audited count mismatch: {table}")
    if any(row["expected_unobserved"] for row in audit.get("coverage", {}).values()):
        raise ValueError("Snapshot coverage reconciliation failed")
    if any(audit["referential_checks"].values()):
        raise ValueError("Broken snapshot links")
    occurrences = audit["event_mentions"]["occurrence_uniqueness"]
    if occurrences["rows"] != occurrences["distinct_occurrences"]:
        raise ValueError("Duplicate occurrence primary keys")
    links = audit["inventory_row_links"]
    if (
        links["missing_source_rows"]
        or links["unlinked_source_rows"]
        or links["rows"] != links["distinct_occurrences"]
    ):
        raise ValueError("Inventory link reconciliation failed")


def finish(root: str | Path) -> dict:
    """Finalize only when every planned output and derived association reconciles."""
    root = Path(root)
    if (root / "complete.json").exists():
        raise ValueError("Dataset is complete; choose a new output ID")
    plan = json.loads((root / "plan.json").read_text())
    checkpoints, expected_counts = _validate_source_outputs(root, plan)
    links = _inventory_interpretation(root)
    units = build_canonical_units(root)
    for table in UNIT_SCHEMAS:
        _require_files(root, table, {"derived.parquet"})
    expected_counts.update(units["counts"], inventory_row_links=links["rows"])

    audit = audit_dataset(root)
    _validate_audit(audit, expected_counts)
    audit.update(
        canonical_unit_association=units,
        inventory_link_interpretation=links,
        implementation_sha256=implementation_hash(),
        provenance=plan,
        finished_at=time.time(),
        export_errors={
            "count": sum(len(checkpoint["errors"]) for checkpoint in checkpoints),
            "examples": [
                error for checkpoint in checkpoints for error in checkpoint["errors"]
            ][:30],
        },
    )
    schemas = {**SCHEMAS, "inventory_row_links": inventory_links.SCHEMA, **UNIT_SCHEMAS}
    write_json(
        root / "schemas.json",
        {
            name: {field.name: str(field.type) for field in schema}
            for name, schema in schemas.items()
        },
    )
    write_json(root / "quality-report.json", audit)
    (root / "quality-report.md").write_text(render_report(audit))
    write_json(
        root / "complete.json",
        {
            "finished_at": time.time(),
            "version": plan["version"],
            "shards": len(checkpoints),
            "counts": audit["tables"]["counts"],
            "quality_report": "quality-report.json",
            "unit_association_rule": ASSOCIATION_RULE,
        },
    )
    return audit

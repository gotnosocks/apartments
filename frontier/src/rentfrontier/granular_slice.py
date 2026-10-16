"""Building slices of a granular transform too large to build in one pass.

The history builder (`apartments.historical_dataset`) and `rentfrontier.cohort`
hold a whole transform in memory. The four-region API backfill of 2026-10-15
(`api-granular-20261015-canonical-url-v1`) has 1.69 million ads, about 16 times
Midtown West's, so I cut it into slices of whole buildings and build each slice
as its own transform:

1. `plan` reads each ad's region from the collector's archive
   (`graphql_search_members`) and its building from `listing_observations`,
   then deals each region's buildings, in slug order, into slices of at most
   `max_ads` ads.
2. `write` copies every slice's rows of four tables into its own directory:
   - `listing_observations` and `building_observations` by building slug;
   - `rental_unit_memberships` by listing id;
   - `event_mentions` by snapshot id, from the slice's own captures.
3. Each slice gets a `complete.json` with the source's `finished_at` and
   unit association rule, its own row counts and the source's hash, so the
   history builder takes it as it takes a whole transform.

A unit's listings all sit in one building, so no unit spans two slices, and the
builder's unit-month layout check sees every row it compares. `write` checks
this and refuses a plan that splits a unit.

    python -m rentfrontier.granular_slice <granular dir> <archive.sqlite3> <output dir> [max ads]
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BY_BUILDING = ("listing_observations", "building_observations")
VERSION = "granular-building-slice-v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shards(granular: Path, table: str) -> list[Path]:
    return sorted((granular / table).glob("*.parquet"))


def plan(granular: Path, archive: Path, max_ads: int) -> pd.DataFrame:
    """building_slug -> region and slice name ("<region>-NN")."""
    with sqlite3.connect(f"file:{archive}?mode=ro", uri=True) as db:
        members = pd.read_sql(
            "SELECT DISTINCT listing_id, region FROM graphql_search_members", db
        )
    members["listing_id"] = members.listing_id.astype(str)
    ads = pd.concat(
        pq.read_table(p, columns=["listing_id", "building_slug", "listing_type"])
        .to_pandas()
        .query("listing_type == 'rental'")
        for p in _shards(granular, "listing_observations")
    ).drop_duplicates(["listing_id", "building_slug"])
    ads = ads.merge(members, on="listing_id", how="left")
    if ads.region.isna().any():
        raise SystemExit(f"{ads.region.isna().sum()} ads have no region")
    regions = ads.groupby("building_slug").region.agg(set)
    if (split := regions[regions.map(len) > 1]).size:
        raise SystemExit(f"{split.size} buildings have ads in two regions")
    count = ads.groupby(["region", "building_slug"]).size()
    out = []
    for region, sizes in count.groupby(level=0):
        index, total = 1, 0
        for (_, slug), n in sizes.sort_index().items():
            if total and total + n > max_ads:
                index, total = index + 1, 0
            total += n
            out.append((slug, region, f"{region}-{index:02d}"))
    return pd.DataFrame(out, columns=["building_slug", "region", "slice"])


def _route(shards, column, key_to_slice, writers, output, table, schema):
    """Append each shard's rows to the writer of the slice its key maps to."""
    counts = {}
    for path in shards:
        frame = pq.read_table(path).to_pandas()
        names = frame[column].map(key_to_slice)
        for name, part in frame[names.notna()].groupby(names[names.notna()]):
            key = (name, table)
            if key not in writers:
                (output / name / table).mkdir(parents=True, exist_ok=True)
                writers[key] = pq.ParquetWriter(
                    output / name / table / "part-00000.parquet", schema
                )
            writers[key].write_table(
                pa.Table.from_pandas(part, schema=schema, preserve_index=False)
            )
            counts[name] = counts.get(name, 0) + len(part)
    return counts


def write(granular: Path, slices: pd.DataFrame, output: Path) -> dict:
    """Write every slice's tables and complete.json under `output`."""
    source = json.loads((granular / "complete.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    by_slug = slices.set_index("building_slug").slice
    names = sorted(slices.slice.unique())
    counts = {name: {} for name in names}
    writers = {}
    listing_slice, snapshot_slice = {}, {}
    try:
        for table in BY_BUILDING:
            shards = _shards(granular, table)
            schema = pq.read_schema(shards[0])
            for name, n in _route(
                shards, "building_slug", by_slug, writers, output, table, schema
            ).items():
                counts[name][table] = n
        for (name, table), writer in list(writers.items()):
            writer.close()
            if table == "listing_observations":
                done = pq.read_table(
                    output / name / table,
                    columns=["listing_id", "snapshot_id", "listing_type"],
                ).to_pandas()
                for listing in done.listing_id.astype(str):
                    if listing_slice.setdefault(listing, name) != name:
                        raise SystemExit(f"listing {listing} is in two slices")
                snapshot_slice.update(dict.fromkeys(done.snapshot_id, name))
        writers.clear()
        for table, column, mapping in (
            ("rental_unit_memberships", "listing_id", listing_slice),
            ("event_mentions", "snapshot_id", snapshot_slice),
        ):
            shards = _shards(granular, table)
            schema = pq.read_schema(shards[0])
            for name, n in _route(
                shards, column, pd.Series(mapping), writers, output, table, schema
            ).items():
                counts[name][table] = n
    finally:
        for writer in writers.values():
            writer.close()
    units = pd.concat(
        pq.read_table(output / name / "rental_unit_memberships", columns=["unit_id"])
        .to_pandas()
        .assign(slice=name)
        for name in names
        if (output / name / "rental_unit_memberships").exists()
    ).drop_duplicates()
    if (shared := units.unit_id.duplicated()).any():
        raise SystemExit(f"{shared.sum()} units have listings in two slices")
    report = {}
    for name in names:
        complete = {
            "version": VERSION,
            "unit_association_rule": source["unit_association_rule"],
            "finished_at": source["finished_at"],
            "counts": {
                t: counts[name].get(t, 0)
                for t in (*BY_BUILDING, "rental_unit_memberships", "event_mentions")
            },
            "source": {
                "path": str(granular),
                "complete_sha256": _sha(granular / "complete.json"),
            },
            "slice": name,
            "buildings": int((slices.slice == name).sum()),
        }
        (output / name / "complete.json").write_text(
            json.dumps(complete, indent=2) + "\n"
        )
        report[name] = complete["counts"]
    slices.to_csv(output / "slices.csv", index=False)
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    granular, archive, output = map(Path, argv[:3])
    max_ads = int(argv[3]) if len(argv) > 3 else 120_000
    slices = plan(granular, archive, max_ads)
    print(json.dumps(write(granular, slices, output), indent=2))


if __name__ == "__main__":
    main()

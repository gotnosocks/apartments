"""Advertisement description text, joined by audit_id (own advertisement only).

Source: the existing description evidence bundle (read-only). Each row there
is the text of that listing's own advertisement, matched by audit_id and
source listing id, so text never travels between listings of a unit.

The extracted (audit_id, description) table is cached under
OUTPUT_ROOT/features/ with a provenance record: source path, source
SHA-256 and the code commit that built it.

West Village has its own evidence file, built from a granular crawl's
listing records (each listing's own ad, as last captured):

    python -m rentfrontier.descriptions --granular <granular dir> \\
        --dataset <cohort dir> --name west-village
    python -m rentfrontier.descriptions --records --dataset <cohort dir> --name <name>

writes OUTPUT_ROOT/descriptions/<name>-<date>-<commit>/evidence.jsonl and
provenance.json. Refuses a dirty tree. With `--records`, I read the API records
of the newest clean build in the data pipeline's catalog in place of a granular
crawl, after checking the file's SHA-256 (`rentfrontier.api_records`). I keep
only the cohort's listings, so one run covers every region, and provenance.json
names the file under `records`. From the records file I take each listing's
ACTIVE record fetched last, or its record fetched last when it has no ACTIVE
record (`record_descriptions`). Each evidence line names the record it came
from under `description_record`: `last_active` or `latest`, and every line from
a granular crawl reads `latest`. Feature sets read an evidence file only where
`SOURCES` lists it, so every other feature set keeps its text.
"""

from __future__ import annotations

import argparse
import contextvars
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import api_records, data

SOURCE = Path(
    os.environ.get(
        "FRONTIER_DESCRIPTIONS",
        "/home/ben/code/apartments/data/model/chelsea-refreshed-bayesian-descriptions-20260918/evidence.jsonl",
    )
)
# West Village: each row's own ad from the granular crawl of 2026-09-30
# (cohort west-village-analysis-20261001-6b3ad1a; 34,087 of 34,118 rows).
WV_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/west-village-20261002-62172be/evidence.jsonl"
)
# Greenwich Village: each row's own ad from the granular crawl of 2026-10-05
# (cohort greenwich-village-analysis-20261005-81bcf4a; 18,416 of 18,425 rows).
GV_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/greenwich-village-20261005-2d5b3b6/evidence.jsonl"
)
# Flatiron + Gramercy Park: each row's own ad from the granular crawl of 2026-10-07
# (cohort flatiron-gramercy-park-analysis-20261007-34b958d; 30,468 of 30,515 rows).
FGP_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/flatiron-gramercy-park-20261008-bda2959/evidence.jsonl"
)
# Stuyvesant Town/PCV: each row's own ad from the granular crawl of 2026-10-08
# (cohort stuyvesant-town-pcv-analysis-20261008-966f0a0; 3,605 of 3,628 rows).
STUY_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/stuyvesant-town-pcv-20261008-d405de4/evidence.jsonl"
)
# NoMad: each row's own ad from the granular crawl of 2026-10-08
# (cohort nomad-analysis-20261009-d3b4050; 9,258 of 9,286 rows).
NOMAD_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/nomad-20261009-d3b4050/evidence.jsonl"
)
# East Village: each row's own ad from the building-first crawl of 2026-10-08
# (cohort east-village-analysis-20261010-3ebfea04; 66,340 evidence lines).
EV_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/east-village-20261010-3ebfea0/evidence.jsonl"
)
# Midtown West: each row's own ad from the building-first crawl of 2026-10-13
# (cohort midtown-west-analysis-20261014-ca9dbf6e; 81,674 evidence lines).
MW_SOURCE = Path(
    "/data1/apartments/frontier/descriptions/midtown-west-20261014-ca9dbf6/evidence.jsonl"
)
# The evidence files `attach` reads while a feature set is built
# (`features.build`); Chelsea's alone unless the feature set lists more.
SOURCES: contextvars.ContextVar[tuple[Path, ...]] = contextvars.ContextVar(
    "description_sources", default=(SOURCE,)
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


_DIGESTS: dict[tuple[str, int, int], str] = {}


def _digest(source: Path) -> str:
    """The evidence file's SHA-256, worked out once per path, size and
    modification time, since a feature set calls `attach` many times."""
    stat = os.stat(source)
    key = (str(source), stat.st_size, stat.st_mtime_ns)
    if key not in _DIGESTS:
        _DIGESTS[key] = data.sha256(source)
    return _DIGESTS[key]


def _cache(source: Path) -> tuple[Path, str]:
    """The extracted table's parquet for `source` and the source's SHA-256,
    after writing the parquet when it is missing."""
    digest = _digest(source)
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
    return cache, digest


def load(source: Path = SOURCE) -> pd.DataFrame:
    cache, digest = _cache(source)
    table = pd.read_parquet(cache)
    table.attrs["source_sha256"] = digest
    return table


def attach(frame: pd.DataFrame) -> pd.Series:
    """Lower-cased description per frame row ('' when unavailable), from the
    evidence files in `SOURCES`."""
    caches = [_cache(path)[0] for path in SOURCES.get()]
    ids = pa.chunked_array(
        [pq.read_table(c, columns=["audit_id"]).column(0) for c in caches]
    )
    if pc.count_distinct(ids, mode="all").as_py() != len(ids):
        raise ValueError("Description sources overlap")
    # Only the frame's rows come out of each source, so memory follows the
    # frame's size.
    wanted = pa.array(frame.audit_id.dropna().unique(), type=ids.type)
    parts = []
    for c in caches:
        part = pd.read_parquet(
            c,
            columns=["audit_id", "desc_listing_id", "description"],
            filters=pc.field("audit_id").isin(wanted),
        )
        # Each source is lower-cased as it is read, so only that source's text
        # is ever held twice. On the 1.75M all-scraped rows the text comes to
        # 1.29 billion characters and about 2.9 GB once it is in Python strings.
        part["description"] = part.description.str.lower()
        parts.append(part)
    table = pd.concat(parts, ignore_index=True)
    del parts
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
    return merged.description.fillna("").set_axis(frame.index)


def granular_descriptions(granular: Path) -> pd.Series:
    """Each listing id's own ad text in a granular crawl: the description of
    its last captured listing record (None when the record has none)."""
    table = pd.read_parquet(
        granular / "listing_observations",
        columns=["listing_id", "collected_at", "snapshot_id", "raw_listing_json"],
    ).sort_values(["collected_at", "snapshot_id"])
    last = table.drop_duplicates("listing_id", keep="last")
    text = last.raw_listing_json.map(
        lambda raw: (json.loads(raw) or {}).get("description") if raw else None
    )
    return pd.Series(text.to_numpy(), index=last.listing_id.astype(str).to_numpy())


def record_descriptions(records: dict, wanted: set[str]) -> pd.DataFrame:
    """Each wanted listing id's own ad text in the pipeline's records file `records`.

    I take the description of the listing's ACTIVE record fetched last. Once an ad
    is rented or delisted, StreetEasy can cut or strip its description, and the
    fit's target is the ask the ad carried while ACTIVE. A listing with no ACTIVE
    record takes the description of its record fetched last. The frame's index is
    the listing id, `description` holds the text (None when that record has
    none), and `record` holds `last_active` or `latest` for the record I read."""
    latest, active = {}, {}
    columns = ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"]
    for r in api_records.captures(records, columns):
        listing = r["listing_id"]
        if listing not in wanted:
            continue
        key = (r["collected_at"], r["snapshot_id"])
        raw = r["raw_listing_json"]
        ad = (json.loads(raw) or {}) if raw else {}
        entry = (key, ad.get("description"))
        if listing not in latest or key >= latest[listing][0]:
            latest[listing] = entry
        if ad.get("status") == "ACTIVE" and (
            listing not in active or key >= active[listing][0]
        ):
            active[listing] = entry
    rows = {
        listing: (active[listing][1], "last_active")
        if listing in active
        else (text, "latest")
        for listing, (_, text) in latest.items()
    }
    return pd.DataFrame.from_dict(
        rows, orient="index", columns=["description", "record"], dtype=object
    )


def build(
    granular: Path | None,
    dataset: Path,
    name: str,
    commit: str,
    skip: Path | None = None,
    records: dict | None = None,
) -> Path:
    """Write the evidence file for every row of a cohort from its granular
    crawl, or from the checked records file `records`, in the shape `load`
    reads, with a provenance record. With `skip`, I leave out the rows of that
    dataset, so an extended cohort's added rows get a file beside its base's
    evidence."""
    with open(dataset / "observations.jsonl") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if skip is not None:
        with open(skip / "observations.jsonl") as f:
            known = {json.loads(line)["audit_id"] for line in f if line.strip()}
        rows = [r for r in rows if r["audit_id"] not in known]
    if records is None:
        text = granular_descriptions(granular)
        chosen = pd.Series("latest", index=text.index, dtype=object)
    else:
        table = record_descriptions(
            records, {str(r["source_listing_id"]) for r in rows}
        )
        text, chosen = table.description, table.record
    stamp = dt.datetime.now(dt.UTC)
    out = data.OUTPUT_ROOT / "descriptions" / f"{name}-{stamp:%Y%m%d}-{commit[:7]}"
    out.mkdir(parents=True, exist_ok=False)
    found = 0
    by_record = {}
    with open(out / "evidence.jsonl", "w") as f:
        for row in rows:
            listing = str(row["source_listing_id"])
            description = text.get(listing)
            if not isinstance(description, str):
                continue
            found += 1
            by_record[chosen[listing]] = by_record.get(chosen[listing], 0) + 1
            record = {
                "audit_id": row["audit_id"],
                "source_listing_id": listing,
                "description": description,
                "description_record": chosen[listing],
                "description_source": "granular_listing_record",
                "source_path": "/description",
            }
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    provenance = {
        "granular": str(granular) if records is None else None,
        "granular_complete_sha256": data.sha256(granular / "complete.json")
        if records is None
        else None,
        "records": records,
        "dataset": str(dataset),
        "observations_sha256": data.sha256(dataset / "observations.jsonl"),
        "rule": "the listing's own ad: the description of its last captured record"
        if records is None
        else "the listing's own ad: the description of its ACTIVE record fetched last,"
        " or of its record fetched last when it has no ACTIVE record",
        "skipped_dataset": str(skip) if skip else None,
        "rows": len(rows),
        "rows_with_description": found,
        "rows_by_description_record": by_record,
        "evidence_sha256": data.sha256(out / "evidence.jsonl"),
        "commit": commit,
        "built_at": stamp.isoformat(),
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--granular", type=Path)
    source.add_argument(
        "--records",
        action="store_true",
        help="read the pipeline's records file in place of a granular crawl",
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--skip", type=Path, help="dataset whose rows to leave out")
    args = parser.parse_args(argv)
    from .run import git

    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    records = api_records.records_file() if args.records else None
    out = build(
        args.granular,
        args.dataset,
        args.name,
        git("rev-parse", "HEAD"),
        args.skip,
        records,
    )
    print(out)


if __name__ == "__main__":
    main()

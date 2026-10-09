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

writes OUTPUT_ROOT/descriptions/<name>-<date>-<commit>/evidence.jsonl and
provenance.json. Refuses a dirty tree. Feature sets read it only where
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

from . import data

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
    """Lower-cased description per frame row ('' when unavailable), from the
    evidence files in `SOURCES`."""
    table = pd.concat([load(path) for path in SOURCES.get()], ignore_index=True)
    if table.audit_id.duplicated().any():
        raise ValueError("Description sources overlap")
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


def build(granular: Path, dataset: Path, name: str, commit: str) -> Path:
    """Write the evidence file for every row of a cohort from its granular
    crawl, in the shape `load` reads, with a provenance record."""
    text = granular_descriptions(granular)
    with open(dataset / "observations.jsonl") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    stamp = dt.datetime.now(dt.UTC)
    out = data.OUTPUT_ROOT / "descriptions" / f"{name}-{stamp:%Y%m%d}-{commit[:7]}"
    out.mkdir(parents=True, exist_ok=False)
    found = 0
    with open(out / "evidence.jsonl", "w") as f:
        for row in rows:
            listing = str(row["source_listing_id"])
            description = text.get(listing)
            if not isinstance(description, str):
                continue
            found += 1
            record = {
                "audit_id": row["audit_id"],
                "source_listing_id": listing,
                "description": description,
                "description_source": "granular_listing_record",
                "source_path": "/description",
            }
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    provenance = {
        "granular": str(granular),
        "granular_complete_sha256": data.sha256(granular / "complete.json"),
        "dataset": str(dataset),
        "observations_sha256": data.sha256(dataset / "observations.jsonl"),
        "rule": "the listing's own ad: the description of its last captured record",
        "rows": len(rows),
        "rows_with_description": found,
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
    parser.add_argument("--granular", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    from .run import git

    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    out = build(args.granular, args.dataset, args.name, git("rev-parse", "HEAD"))
    print(out)


if __name__ == "__main__":
    main()

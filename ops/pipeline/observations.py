"""Write a dataset folder for the frontier fits from the pipeline's fit-ready rows.

    python ops/pipeline/observations.py OUT [--catalog DIR] [--rows FILE [--ads FILE]]
        [--neighbourhoods NAME,...] [--rename OLD=NEW ...] [--served DATASET]
        [--audit-ids DATASET]
    python ops/pipeline/observations.py OUT --check-against DATASET [--latest-ask RULE]
        [--api-reference DATASET] [--export DIR] [--chain-run N] [--report FILE]

`rentfrontier.data.load` reads the folder's `observations.jsonl` as it reads the chain's
analysis datasets, so a fit takes it with `FRONTIER_DATASET=OUT`. The script works in these
steps:

1. It picks a build from DIR's `catalog.ndjson`, /data1/apartments/pipeline/datasets unless
   given: the newest line with its line break from a clean checkout, as the website does. With
   `--rows FILE`, it picks the line whose rows file has FILE's SHA-256 instead, and a rows file
   no line lists needs its ads file as `--ads FILE`. It checks each file's SHA-256 against the
   line and stops on a mismatch.
2. It takes the neighbourhoods from `--neighbourhoods`, or else the distinct `neighbourhood`
   values of the served dataset, `rentfrontier.data.DATASET` unless `--served` names another.
3. It reads the ad, audit ID and price basis of each row of the chain's dataset of all scraped
   areas, `rentfrontier.data.DATASET_ALL` unless `--audit-ids` names another, and keeps the rows
   priced at the ad's first ask. The chain's other rows price an ad's current page, under IDs
   starting `capture:refresh:`. The script stops if an ad has two first-ask rows there. It reads
   the served dataset the same way and lists each ad both datasets hold under different audit
   IDs.
4. It writes a line to `observations.jsonl` for each row of the rows file in those
   neighbourhoods, in the rows file's order, by `listing_id`. The line gives the chain's field
   names and JSON types, keys sorted as the chain sorts them:
     - `source_listing_id` from `listing_id`, `canonical_unit_url` from `page`,
       `reported_full_bathrooms` and `reported_half_bathrooms` from `full_baths` and
       `half_baths`, and `floor_label_provenance` as `status` and `building_floor_count` from
       `floor_status` and `building_floor_count`. The other fields keep their names.
     - `asking_rent` from the row's `latest_ask`: the ledger's ask where the ledger sets one,
       and otherwise the latest ask `analysis.latest_ask` chooses. The rows file's
       `asking_rent` holds the first ask, which only the check reads. The script stops on a
       rows file without `latest_ask`, as written by builds before the column, and on a row
       without a latest ask.
     - `unit_id` from the row's `split_unit`: its piece of the unit `analysis.label_units`
       joins its unit into, as the chain's `unit-labels-v17` joins it and `unit-splits-v4`
       cuts it. The script stops on a rows file without `split_unit`, as written by builds
       before the column.
     - `neighbourhood` as the rows file gives it, or as NEW for each `--rename OLD=NEW`. The
       neighbourhoods of step 2 name the rows file's neighbourhoods, before the renames, and
       the script adds each OLD to them. It stops if a rename moves no rows.
     - `audit_id` from the chain's row for the ad in step 3, or `api:<listing_id>` for an ad
       the chain lacks. The script stops if two rows get one ID.
     - `analysis_price_basis` as `historical_initial_own_advertisement_ask` and
       `description_interpreted_at` as null on every row.
5. It writes `manifest.json`, with the build's files and their SHA-256, the catalog line's
   build time, code, ledger files and stale days, the written neighbourhoods with their row
   counts, the renames with the rows each moved, the audit ID sources with their SHA-256, the
   counts of each kind of audit ID, the audit IDs the served dataset gives otherwise, and the
   SHA-256 of `observations.jsonl`.

It writes both files into a hidden folder beside OUT and renames the folder to OUT at the end. It
refuses an OUT already there.

With `--check-against DATASET`, the script writes nothing to OUT. It loads OUT and DATASET with
`rentfrontier.data.load`, its cache in a temporary folder, matches their rows by ad and counts
the differences field by field. Before comparing, it gives DATASET's rows the asks of the
chain's latest ask rule, `latest-ask-v9` unless `--latest-ask` names another, the fills of the
rules `elevator-from-ad-v1` and `pets-from-ad-v2`, and the units of `building-joins-v1`,
`west-coast-wings-v1`, `unit-labels-v17`, `unit-reviews-v5` and `unit-splits-v4`, in the fit's
order. The served fit applies `unit-reviews-v2`, and the unit ledger holds the lines of v5, its
latest version. It compares the rows file's first asks with DATASET's own asks. It then puts each difference down to the first
of these causes to fit, checked in this order:
  - the ad has a live ledger set of the field,
  - the API chain's dataset given as `--api-reference` holds the ad with OUT's value,
  - the ads file's `from_text` lists the field, so the pipeline filled OUT's value from the
    ad's descriptions, and DATASET leaves it `unknown` after the rules' fills. The pipeline
    reads every ad's descriptions in the export, and the rules' files hold the NB9 rows alone,
    read from page crawls,
  - for an ask, the ad's latest API record came after export run N, the last run the chain's
    latest asks read, its price differs from the last price up to run N, and OUT's ask equals
    it. Run N is run 5 of the export in /data1/apartments/archive/crawls/api/export, unless
    `--chain-run` and `--export` give others,
  - for an ask, DATASET also prices the ad's current page in a row of its own, and its
    first-ask row ends at that row's price,
  - DATASET's ask matches under the rule before `latest-ask-v9` only,
  - `has_description` follows from the null `description_interpreted_at`.
A difference fitting none of them counts as unexplained. The script sorts the rows of one side
alone by their ad's fate or label fate in the build's ads file. `--report FILE` saves the counts and up to 50
unexplained differences of each field as JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = Path("/data1/apartments/pipeline/datasets")
FIRST_ASK = "historical_initial_own_advertisement_ask"
VERSION = "pipeline-observations-v1"
MEMORY = os.environ.get("PIPELINE_MEMORY", "2GB")
EXPORT = Path("/data1/apartments/archive/crawls/api/export")
CHAIN_RUN = 5
# The served fit's rules filling an unknown elevator or pet policy from the row's own ad.
AD_FILLS = ("elevator-from-ad-v1", "pets-from-ad-v2")
# The chain's rules moving ads to other units, in the fit's order. The rows carry their changes:
# the unit ledger's moves, the label units and the history splits.
UNIT_RULES = (
    "building-joins-v1",
    "west-coast-wings-v1",
    "unit-labels-v17",
    "unit-reviews-v5",
    "unit-splits-v4",
)
# The fields the rules fill, with their names in the ads file's `from_text`.
TEXT_FIELDS = {"elevator": "elevator", "pets": "pet_policy"}


def frontier_data():
    """The chain's `rentfrontier.data`, from this checkout."""
    src = str(REPO / "frontier" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from rentfrontier import data

    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        config={"TimeZone": "UTC", "memory_limit": MEMORY, "threads": 4}
    )


def pick_build(catalog: Path, rows: Path | None, ads: Path | None) -> dict:
    """The build's rows and ads files, checked against its catalog line, and the line."""
    path = catalog / "catalog.ndjson"
    # A last line without its line break is still being written.
    text = path.read_text().split("\n")[:-1] if path.is_file() else []
    lines = [json.loads(line) for line in text if line.strip()]
    if rows is None:
        lines = [e for e in lines if e.get("code", {}).get("clean") is True]
        if not lines:
            raise SystemExit(f"{path} lists no build from a clean checkout")
        line = lines[-1]
    else:
        digest = sha256(rows)
        found = [e for e in lines if e.get("rows", {}).get("sha256") == digest]
        line = found[-1] if found else None
        if line is None:
            if ads is None:
                raise SystemExit(f"no line of {path} lists {rows}; give its ads file")
            return {
                "rows": {"path": str(rows.resolve()), "sha256": digest},
                "ads": {"path": str(ads.resolve()), "sha256": sha256(ads)},
                "catalog": None,
            }
    files = {}
    for key, name in (("rows", "rows"), ("ads", "ads_file")):
        file = catalog / line[name]["path"]
        if sha256(file) != line[name]["sha256"]:
            raise SystemExit(f"{file} differs from {path}")
        files[key] = {"path": str(file.resolve()), "sha256": line[name]["sha256"]}
    files["catalog"] = {
        "path": str(path.resolve()),
        "built": line.get("built"),
        "code": line.get("code"),
        "ledger": line.get("ledger", {}).get("files"),
        "stale_days": line.get("stale_days"),
    }
    return files


def first_ask_ids(db, dataset: Path) -> dict:
    """source_listing_id -> audit_id over the dataset's rows priced at the ad's first ask."""
    rows = db.execute(
        """SELECT source_listing_id, audit_id, analysis_price_basis
        FROM read_json(?, format = 'newline_delimited', columns = {
            'source_listing_id': 'VARCHAR', 'audit_id': 'VARCHAR',
            'analysis_price_basis': 'VARCHAR'})""",
        [str(dataset / "observations.jsonl")],
    ).fetchall()
    ids = {}
    for listing, audit, basis in rows:
        if basis != FIRST_ASK:
            continue
        if listing in ids:
            raise SystemExit(f"ad {listing} has two first-ask rows in {dataset}")
        ids[listing] = audit
    return ids


RECORD = """
SELECT r.listing_id, r.split_unit, r.page, r.building,
    strftime(timezone('UTC', r.price_at), '%Y-%m-%dT%H:%M:%S+00:00') AS price_at,
    strftime(r.period, '%Y-%m-%d') AS period, r.latest_ask, r.bedrooms, r.bathrooms,
    r.full_baths, r.half_baths, r.square_feet, r.listed_floor, r.label_derived_floor,
    r.floor_status, r.building_floor_count, r.advertised_floor, r.physical_floor,
    r.floors_above_ground, r.elevator, r.laundry_type, r.doorman_type, r.hvac_type,
    r.pet_policy, r.view_exposures::VARCHAR, r.window_exposures::VARCHAR, r.neighbourhood
FROM read_parquet($rows) r
WHERE list_contains($hoods, r.neighbourhood)
ORDER BY r.listing_id
"""


def record(row: tuple, audit_id: str) -> dict:
    """The chain's observation for a row of RECORD."""
    (
        listing_id,
        unit_id,
        page,
        building,
        price_at,
        period,
        latest_ask,
        bedrooms,
        bathrooms,
        full_baths,
        half_baths,
        square_feet,
        listed_floor,
        label_derived_floor,
        floor_status,
        building_floor_count,
        advertised_floor,
        physical_floor,
        floors_above_ground,
        elevator,
        laundry_type,
        doorman_type,
        hvac_type,
        pet_policy,
        views,
        windows,
        neighbourhood,
    ) = row
    if latest_ask is None:
        raise SystemExit(f"ad {listing_id} has no latest_ask in the rows file")
    # The chain writes a floor read from the unit label as an int.
    if floor_status == "label_proxy" and listed_floor is not None:
        listed_floor = int(listed_floor)
    return {
        "advertised_floor": advertised_floor,
        "analysis_price_basis": FIRST_ASK,
        "asking_rent": float(latest_ask),
        "audit_id": audit_id,
        "bathrooms": bathrooms,
        "bedrooms": bedrooms,
        "building": building,
        "canonical_unit_url": page,
        "description_interpreted_at": None,
        "doorman_type": doorman_type,
        "elevator": elevator,
        "floor_label_provenance": {
            "building_floor_count": building_floor_count,
            "status": floor_status,
        },
        "floors_above_ground": floors_above_ground,
        "hvac_type": hvac_type,
        "label_derived_floor": label_derived_floor,
        "laundry_type": laundry_type,
        "listed_floor": listed_floor,
        "neighbourhood": neighbourhood,
        "period": period,
        "pet_policy": pet_policy,
        "physical_floor": physical_floor,
        "price_at": price_at,
        "reported_full_bathrooms": full_baths,
        "reported_half_bathrooms": half_baths,
        "source_listing_id": listing_id,
        "square_feet": square_feet,
        "unit_id": unit_id,
        # An API record without views or windows leaves the column null, and
        # `rentfrontier.data.load` reads a null as it reads an object of nulls.
        "view_exposures": None if views is None else json.loads(views),
        "window_exposures": None if windows is None else json.loads(windows),
    }


def code() -> dict:
    """The checkout's commit, and whether this script differs from it."""

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, text=True
        ).stdout.strip()

    changes = git("status", "--porcelain", "--", "ops/pipeline/observations.py")
    return {"commit": git("rev-parse", "HEAD") or None, "clean": not changes}


def write(
    out: Path,
    build: dict,
    hoods: list[str] | None,
    served: Path,
    audit_source: Path,
    renames: dict[str, str] | None = None,
) -> dict:
    """Write OUT's two files from the build and return the manifest."""
    renames = renames or {}
    if out.exists():
        raise SystemExit(f"{out} exists")
    db = connect()
    if hoods is None:
        hoods = [
            h
            for (h,) in db.execute(
                """SELECT DISTINCT neighbourhood FROM read_json(?,
                format = 'newline_delimited', columns = {'neighbourhood': 'VARCHAR'})
                ORDER BY 1""",
                [str(served / "observations.jsonl")],
            ).fetchall()
        ]
    hoods = sorted(set(hoods) | set(renames))
    chain = first_ask_ids(db, audit_source)
    shown = first_ask_ids(db, served)
    differ = [
        {"source_listing_id": k, "served": v, "audit_ids": chain[k]}
        for k, v in sorted(shown.items())
        if k in chain and chain[k] != v
    ]

    columns = db.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [build["rows"]["path"]]
    ).fetchall()
    if "latest_ask" not in {c[0] for c in columns}:
        raise SystemExit(
            f"{build['rows']['path']} has no latest_ask column. Its asking_rent holds the "
            "first ask, and the fits take the latest ask, so build the rows file again "
            "with a checkout writing latest_ask."
        )
    if "split_unit" not in {c[0] for c in columns}:
        raise SystemExit(
            f"{build['rows']['path']} has no split_unit column. The fits take each row's "
            "piece of its label unit in place of unit-labels-v17 and unit-splits-v4, so "
            "build the rows file again with a checkout writing split_unit."
        )

    tmp = out.with_name(f".{out.name}.tmp-{os.getpid()}")
    tmp.mkdir(parents=True)
    try:
        counts, moved, kinds, seen = {}, {}, {"chain": 0, "api": 0}, set()
        cursor = db.execute(
            RECORD,
            {
                "rows": build["rows"]["path"],
                "hoods": hoods,
            },
        )
        with open(tmp / "observations.jsonl", "w") as f:
            while batch := cursor.fetchmany(20_000):
                for row in batch:
                    listing = row[0]
                    audit_id = chain.get(listing)
                    kinds["api" if audit_id is None else "chain"] += 1
                    audit_id = audit_id or f"api:{listing}"
                    if audit_id in seen:
                        raise SystemExit(f"audit ID {audit_id} repeats")
                    seen.add(audit_id)
                    if row[26] in renames:
                        moved[row[26]] = moved.get(row[26], 0) + 1
                        row = (*row[:26], renames[row[26]])
                    counts[row[26]] = counts.get(row[26], 0) + 1
                    line = json.dumps(
                        record(row, audit_id), sort_keys=True, allow_nan=False
                    )
                    f.write(line + "\n")
        idle = sorted(old for old in renames if not moved.get(old))
        if idle:
            raise SystemExit(
                f"--rename moved no rows of {', '.join(idle)}: the rows file has no "
                "rows there"
            )
        manifest = {
            "version": VERSION,
            "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "code": code(),
            "rows_file": build["rows"],
            "ads_file": build["ads"],
            "catalog": build["catalog"],
            "neighbourhoods": {
                h: counts.get(h, 0) for h in sorted({renames.get(h, h) for h in hoods})
            },
            "renamed": {
                old: {"to": new, "rows": moved.get(old, 0)}
                for old, new in sorted(renames.items())
            },
            "served": {
                "path": str(served),
                "observations_sha256": sha256(served / "observations.jsonl"),
                "first_ask_ads": len(shown),
                "audit_id_differs": differ,
            },
            "audit_ids": {
                "path": str(audit_source),
                "observations_sha256": sha256(audit_source / "observations.jsonl"),
                "first_ask_ads": len(chain),
                "from_chain": kinds["chain"],
                "api": kinds["api"],
            },
            "rows": sum(counts.values()),
            "files": {"observations.jsonl": sha256(tmp / "observations.jsonl")},
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        if out.exists():
            raise SystemExit(f"{out} exists")
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return manifest


NUMBERS = (
    "asking_rent",
    "first_ask",
    "bedrooms",
    "bathrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "listed_floor",
    "label_derived_floor",
    "advertised_floor",
    "physical_floor",
    "floors_above_ground",
    "building_floor_count",
)
# The raw fields `_flatten` leaves out, read from both files beside it.
RAW = """
SELECT source_listing_id, analysis_price_basis,
    floor_label_provenance->>'status' AS floor_status,
    coalesce(floor_label_provenance->>'building_floor_count',
        floor_label_provenance->>'building_floor_count_limit')::DOUBLE AS building_floor_count,
    advertised_floor, physical_floor, floors_above_ground
FROM read_json($path, format = 'newline_delimited', columns = {
    'source_listing_id': 'VARCHAR', 'analysis_price_basis': 'VARCHAR',
    'floor_label_provenance': 'JSON', 'advertised_floor': 'DOUBLE',
    'physical_floor': 'DOUBLE', 'floors_above_ground': 'DOUBLE'})
WHERE analysis_price_basis = $basis
"""


def ledger_sets(build: dict) -> dict:
    """Live ledger entry ID -> the fields its set gives, over the build's ledger files.

    An entry's ID is the first 16 hex digits of the SHA-256 of its line. The build's catalog
    line gives its files by name, or by absolute path for builds before #1116, and a name
    points into this checkout's ledger. The files of this checkout's ledger join the build's,
    in case a build's file has moved since. A build's file missing here, or differing from its
    SHA-256 in the catalog line, gets a warning, as a lane's ledger can hold files this
    checkout lacks."""
    folder = REPO / "pipeline" / "ledger"
    files = set(folder.glob("*.ndjson"))
    listed = (build.get("catalog") or {}).get("ledger") or {}
    for name, digest in listed.items():
        path = folder / name
        if not path.is_file() or sha256(path) != digest:
            print(
                f"warning: {path} differs from the build's ledger file", file=sys.stderr
            )
        files.add(path)
    fields = {}
    for path in sorted(files):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            key = hashlib.sha256(line.encode()).hexdigest()[:16]
            fields[key] = (entry["change"], sorted(entry.get("set") or {}))
    return fields


def same(a, b, numeric: bool):
    """Element-wise equality, with two missing values equal."""
    import pandas as pd

    if numeric:
        a = pd.to_numeric(a, errors="coerce").astype(float)
        b = pd.to_numeric(b, errors="coerce").astype(float)
    missing = a.isna().to_numpy() & b.isna().to_numpy()
    equal = (a.to_numpy() == b.to_numpy()) if numeric else (a == b).to_numpy()
    return missing | (equal & ~a.isna().to_numpy() & ~b.isna().to_numpy())


def side(data, db, path: Path, cache: Path):
    """The dataset's first-ask rows as `rentfrontier.data.load` gives them, with the raw
    fields beside them, and the ad and price of each of its rows priced at a page."""
    frame = data.load(path, cache_root=cache).drop(columns="log_rent")
    paged = frame[frame.price_basis != FIRST_ASK]
    pages = set(zip(paged.source_listing_id, paged.asking_rent.astype(float)))
    frame = frame[frame.price_basis == FIRST_ASK]
    raw = db.execute(
        RAW, {"path": str(path / "observations.jsonl"), "basis": FIRST_ASK}
    )
    raw = raw.df().drop(columns="analysis_price_basis")
    return frame.merge(raw, on="source_listing_id", how="left"), pages


def check(
    out: Path,
    dataset: Path,
    rule: str,
    api: Path | None,
    report: Path | None,
    export: Path = EXPORT,
    chain_run: int = CHAIN_RUN,
) -> dict:
    """Compare OUT with DATASET field by field and sort the differences by cause."""
    import numpy as np
    import pandas as pd

    data = frontier_data()
    manifest = json.loads((out / "manifest.json").read_text())
    build = {
        "rows": manifest["rows_file"],
        "ads": manifest["ads_file"],
        "catalog": manifest["catalog"],
    }
    db = connect()
    tmp = Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
    with tempfile.TemporaryDirectory(dir=tmp, prefix="observations-check-") as cache:
        ours, _ = side(data, db, out, Path(cache))
        theirs, pages = side(data, db, dataset, Path(cache))
        ref = side(data, db, api, Path(cache))[0] if api else None
    theirs["first_ask"] = theirs.asking_rent
    theirs = data.DATA_RULES[rule](theirs).drop(columns="log_rent")
    for fill in AD_FILLS + UNIT_RULES:
        theirs = data.DATA_RULES[fill](theirs)
    previous = {"latest-ask-v9": "latest-ask-v8", "latest-ask-v8": "latest-ask-v7"}.get(
        rule
    )
    if previous:
        theirs[previous] = data.DATA_RULES[previous](theirs).asking_rent.to_numpy()
    first = db.execute(
        "SELECT listing_id AS source_listing_id, asking_rent AS first_ask "
        "FROM read_parquet(?)",
        [build["rows"]["path"]],
    ).df()
    ours = ours.merge(first, on="source_listing_id", how="left")
    # The chain's latest asks come from records fetched up to the end of export run
    # `chain_run`. `after_chain` marks an ad whose latest record came later and gives a price
    # other than the last price up to that run, and `price_after` holds that later price.
    # Ads files written before analysis.label_months carry no `label_fate`.
    columns = {
        name
        for (name,) in db.execute(
            "SELECT name FROM parquet_schema(?)", [build["ads"]["path"]]
        ).fetchall()
    }
    label_fate = (
        "a.label_fate" if "label_fate" in columns else "NULL::VARCHAR AS label_fate"
    )
    ads = db.execute(
        f"""WITH priced AS (
            SELECT listing_id::VARCHAR AS listing_id, fetched, run,
                try_cast(json_extract_string(record, '$.pricing.price') AS DOUBLE) AS price
            FROM read_parquet($export) WHERE record IS NOT NULL),
        upto AS (
            SELECT listing_id, arg_max(price, fetched) AS price_then FROM priced
            WHERE run <= $run AND price IS NOT NULL GROUP BY 1),
        latest AS (
            SELECT listing_id, arg_max(price, fetched) AS price_after FROM priced
            WHERE price IS NOT NULL GROUP BY 1)
        SELECT a.listing_id AS source_listing_id, a.neighbourhood AS ads_neighbourhood,
            a.fetched::VARCHAR AS fetched,
            coalesce(a.fetched > (SELECT max(fetched) FROM priced WHERE run = $run)
                AND l.price_after IS DISTINCT FROM u.price_then, false) AS after_chain,
            l.price_after,
            a.fate, {label_fate}, a.in_rows, a.identity_reasons, a.exclusion_reasons,
            a.ledger_entries, a.from_text
        FROM read_parquet($ads) a
        LEFT JOIN upto u ON u.listing_id = a.listing_id::VARCHAR
        LEFT JOIN latest l ON l.listing_id = a.listing_id::VARCHAR""",
        {
            "export": str(export / "ads" / "*" / "*.parquet"),
            "run": chain_run,
            "ads": build["ads"]["path"],
        },
    ).df()
    entries = ledger_sets(build)
    hoods = set(manifest["neighbourhoods"]) | set(manifest.get("renamed", {}))

    joined = ours.merge(
        theirs,
        on="source_listing_id",
        how="outer",
        suffixes=("", "_chain"),
        indicator=True,
    )
    joined = joined.merge(ads, on="source_listing_id", how="left")
    both = joined[joined["_merge"] == "both"].reset_index(drop=True)
    if ref is not None:
        # The API chain's audit IDs and asks differ by design: it keys its own rows and
        # gives the first ask, which `first_ask_api` holds.
        ref = ref.assign(first_ask=ref.asking_rent)
        ref = ref.drop(columns=["audit_id", "asking_rent", "price_basis"]).add_suffix(
            "_api"
        )
        ref = ref.rename(columns={"source_listing_id_api": "source_listing_id"})
        both = both.merge(ref, on="source_listing_id", how="left")
        present = both.unit_id_api.notna().to_numpy()

    def sets(keys) -> set:
        found = set()
        for key in [] if keys is None else keys:
            change, fields = entries.get(key, (None, []))
            if change == "set":
                found.update(fields)
        return found

    live = both.ledger_entries.map(sets)
    fields = [
        c
        for c in ours.columns
        if c in theirs.columns and c not in ("source_listing_id", "price_basis")
    ]
    table, unexplained = [], {}
    for field in fields:
        numeric = field in NUMBERS
        differs = ~same(both[field], both[f"{field}_chain"], numeric)
        cause = np.full(len(both), "unexplained", dtype=object)
        if field == "has_description":
            cause[:] = "description_interpreted_at null"
        if field == "asking_rent" and previous:
            cause[same(both[field], both[previous], True)] = f"{rule} only"
        if field == "asking_rent":
            paged = [
                (listing, float(ask)) in pages
                for listing, ask in zip(both.source_listing_id, both.asking_rent_chain)
            ]
            cause[np.array(paged, dtype=bool)] = "chain page row"
            after = both.after_chain.astype("boolean").fillna(False).to_numpy(
                dtype=bool
            ) & same(both.asking_rent, both.price_after, True)
            cause[after] = f"API record after run {chain_run}"
        if field in TEXT_FIELDS:
            filled = [
                TEXT_FIELDS[field] in (names if names is not None else ())
                for names in both.from_text
            ]
            text = np.array(filled, dtype=bool) & (
                both[f"{field}_chain"] == "unknown"
            ).to_numpy(dtype=bool)
            cause[text] = "ad text fill"
        if f"{field}_api" in both:
            api_value = both[f"{field}_api"]
            cause[present & same(both[field], api_value, numeric)] = "API record agrees"
        cause[np.array([field in s for s in live], dtype=bool)] = "ledger set"
        counts = pd.Series(cause[differs]).value_counts().to_dict()
        table.append({"field": field, "differ": int(differs.sum()), **counts})
        left = both[differs & (cause == "unexplained")]
        if len(left):
            columns = [
                c
                for c in (
                    "source_listing_id",
                    field,
                    f"{field}_chain",
                    f"{field}_api",
                    "fetched",
                )
                if c in left
            ]
            items = left[columns].head(50).astype(object)
            unexplained[field] = {
                "count": len(left),
                "examples": items.where(items.notna(), None)
                .astype(str)
                .to_dict("records"),
            }

    def alone(row) -> str:
        if row["_merge"] == "left_only":
            if row.audit_id.startswith("api:"):
                return "ours: no chain row"
            return "ours: chain row outside the dataset"
        if pd.isna(row.fate) and pd.isna(row.in_rows):
            return "chain: no API record"
        if row.in_rows:
            if row.ads_neighbourhood not in hoods:
                return f"chain: neighbourhood {row.ads_neighbourhood}"
            return "chain: in the rows file"
        if isinstance(row.label_fate, str):
            return f"chain: {row.label_fate}"
        if row.fate == "kept":
            return "chain: ledger exclude"
        if isinstance(row.fate, str):
            return f"chain: {row.fate}"
        reasons = list(row.identity_reasons if row.identity_reasons is not None else [])
        if reasons:
            return f"chain: identity {reasons[0]}"
        reasons = list(
            row.exclusion_reasons if row.exclusion_reasons is not None else []
        )
        return f"chain: exclusion {reasons[0]}" if reasons else "chain: other"

    one = joined[joined["_merge"] != "both"]
    sides = one.apply(alone, axis=1).value_counts().to_dict() if len(one) else {}
    sides["chain: priced at the current page"] = len({listing for listing, _ in pages})
    result = {
        "ours": str(out),
        "chain": str(dataset),
        "api": None if api is None else str(api),
        "rule": rule,
        "rows": {"ours": len(ours), "chain": len(theirs), "both": len(both)},
        "fields": table,
        "alone": {k: int(v) for k, v in sorted(sides.items(), key=lambda kv: -kv[1])},
        "unexplained": unexplained,
    }
    if report is not None:
        report.write_text(json.dumps(result, indent=1, default=str) + "\n")
    return result


def show(result: dict) -> None:
    rows = result["rows"]
    print(
        f"rows: ours {rows['ours']:,}, chain {rows['chain']:,}, both {rows['both']:,}"
    )
    print("field differences on ads both have:")
    for item in result["fields"]:
        causes = ", ".join(
            f"{k} {v:,}" for k, v in item.items() if k not in ("field", "differ")
        )
        print(f"  {item['field']:22} {item['differ']:>8,}  {causes}")
    print("rows of one side alone:")
    for cause, n in result["alone"].items():
        print(f"  {cause:60} {n:>8,}")
    for field, item in result["unexplained"].items():
        print(f"unexplained {field}: {item['count']:,}, e.g.")
        for example in item["examples"][:5]:
            print(f"  {example}")


def main(argv: list[str] | None = None) -> None:
    import resource
    import time

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--ads", type=Path)
    parser.add_argument("--neighbourhoods")
    parser.add_argument("--rename", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--served", type=Path)
    parser.add_argument("--audit-ids", type=Path)
    parser.add_argument("--check-against", type=Path)
    parser.add_argument("--latest-ask", default="latest-ask-v9")
    parser.add_argument("--api-reference", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--export", type=Path, default=EXPORT)
    parser.add_argument("--chain-run", type=int, default=CHAIN_RUN)
    args = parser.parse_args(argv)
    start = time.monotonic()
    if args.check_against is not None:
        show(
            check(
                args.out,
                args.check_against,
                args.latest_ask,
                args.api_reference,
                args.report,
                args.export,
                args.chain_run,
            )
        )
    else:
        data = frontier_data()
        build = pick_build(args.catalog, args.rows, args.ads)
        hoods = args.neighbourhoods.split(",") if args.neighbourhoods else None
        if any("=" not in pair for pair in args.rename):
            parser.error("--rename takes OLD=NEW")
        renames = dict(pair.split("=", 1) for pair in args.rename)
        manifest = write(
            args.out,
            build,
            hoods,
            args.served or data.DATASET,
            args.audit_ids or data.DATASET_ALL,
            renames,
        )
        print(f"{args.out}: {manifest['rows']:,} rows")
        print(f"observations.jsonl {manifest['files']['observations.jsonl']}")
        print(
            f"audit IDs: {manifest['audit_ids']['from_chain']:,} from the chain, "
            f"{manifest['audit_ids']['api']:,} api:"
        )
        print(
            f"served dataset gives another audit ID for "
            f"{len(manifest['served']['audit_id_differs']):,} ads"
        )
    peak = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    print(f"{time.monotonic() - start:.0f} s, peak {peak:,} MiB")


if __name__ == "__main__":
    main()

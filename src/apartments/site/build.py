"""Build the listings site's database from a summary bundle.

    uv run python -m apartments.site build [--summary <bundle>] [--root <site root>]

Without --summary it publishes the app's selected model: the summary that
config/main-analysis.json selects (checked against the selection's sha256).

Inputs, each checked against the bundle's provenance (complete.json):
- the summary bundle of `rentfrontier.summary`: per-listing estimates, the
  market index, building effects, feature coefficients (file sha256s);
- the analytical dataset it was made from (observations.jsonl sha256): the
  listing attributes, prices, dates and StreetEasy links;
- the building registry and MapPLUTO extracts the run used, when recorded
  (sha256): addresses, coordinates and building facts;
- the bundle's copies of the run's row-dropping data rules (quarantine-v1):
  a dataset row missing from the bundle must be one of their rows. Those
  listings are kept in their own table, with the review's reason and no
  estimate, so the site can say which listings are quarantined and why.

Writes <root>/builds/<stamp>/site.sqlite and build.json, then points
<root>/current at the new build with an atomic symlink swap and keeps the
newest KEEP builds, or only the new one when its database passes
LARGE_BYTES. The site opens current/site.sqlite read-only for each request,
so publishing needs no restart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import sqlite3
import statistics
import tempfile
from collections import Counter
from pathlib import Path

import duckdb

from . import (
    ad_dates,
    boroughs,
    captures,
    detail,
    estimate_build,
    exposure,
    story,
    wings,
)
from .selection import SELECTION, selection_note

VERSION = "listings-site-v1"
SCHEMA_VERSION = 4
DEFAULT_ROOT = Path(os.environ.get("SITE_ROOT", "/data1/apartments/site"))
SELECTION_VERSION = "main-analysis-selection-v2"
KEEP = 3
# A build whose database is larger than this keeps only itself. A build of
# every borough makes a database of about 8 GB, and three of those would fill
# /data1.
LARGE_BYTES = 4 << 30
# Rent maps of runs (`rentfrontier.rentmap`): <run>-<7-hex commit>/map.json.
MAPS = Path(os.environ.get("FRONTIER_MAPS", "/data1/apartments/frontier/maps"))
# Where the ask falls in its leave-own-row-out predictive distribution.
PRICE_BANDS = (0.10, 0.90)
# Building tax classes the rent map can pick out (playtest round 7, landlord).
KINDS = {"C": "walkup", "D": "elevator"}
HISTORICAL_BASIS = "historical_initial_own_advertisement_ask"

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE terms(position INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE market(period TEXT PRIMARY KEY, rent REAL, deseasoned REAL,
  deseasoned_lower REAL, deseasoned_upper REAL);
CREATE TABLE coefficients(feature TEXT PRIMARY KEY, feature_group TEXT NOT NULL,
  pct REAL, pct_lower REAL, pct_upper REAL, probability_positive REAL);
CREATE TABLE buildings(
  id TEXT PRIMARY KEY, name TEXT, address TEXT NOT NULL, sort_key TEXT NOT NULL,
  search TEXT NOT NULL, latitude REAL, longitude REAL, bbl TEXT,
  year_built INTEGER, floors INTEGER, residential_units INTEGER,
  building_class TEXT, landmark TEXT, historic_district TEXT,
  level_pct REAL, level_pct_lower REAL, level_pct_upper REAL,
  trend_pct REAL, trend_pct_lower REAL, trend_pct_upper REAL,
  fit_rows INTEGER, listings INTEGER NOT NULL, units INTEGER NOT NULL,
  neighbourhood TEXT,
  current_listings INTEGER NOT NULL, first_period TEXT, last_period TEXT,
  median_residual_pct REAL);
CREATE TABLE units(
  id TEXT PRIMARY KEY, building_id TEXT NOT NULL REFERENCES buildings(id),
  label TEXT, url TEXT, bedrooms REAL, bathrooms REAL, square_feet REAL,
  floor INTEGER, listings INTEGER NOT NULL, first_period TEXT, last_period TEXT,
  last_ask REAL, last_estimate REAL, last_residual_pct REAL);
CREATE TABLE listings(
  id INTEGER PRIMARY KEY, audit_id TEXT NOT NULL UNIQUE,
  neighbourhood TEXT NOT NULL,
  unit_id TEXT NOT NULL REFERENCES units(id),
  building_id TEXT NOT NULL REFERENCES buildings(id),
  unit_label TEXT, unit_url TEXT, listing_id TEXT, listing_url TEXT,
  period TEXT NOT NULL, price_at TEXT, is_current INTEGER NOT NULL,
  price_basis TEXT, ask REAL NOT NULL, bedrooms REAL, bathrooms REAL,
  full_baths INTEGER, half_baths INTEGER, square_feet REAL, floor INTEGER,
  elevator TEXT, doorman TEXT, laundry TEXT, hvac TEXT, pets TEXT,
  views TEXT, windows TEXT, concession TEXT, collected_at TEXT,
  in_fit INTEGER NOT NULL, unit_fit_rows INTEGER NOT NULL, method TEXT NOT NULL,
  estimate REAL NOT NULL, estimate_lower REAL NOT NULL, estimate_upper REAL NOT NULL,
  estimate_median REAL NOT NULL, residual_usd REAL NOT NULL,
  residual_pct REAL NOT NULL, pit REAL NOT NULL, price_band TEXT NOT NULL,
  pareto_k REAL, reliable INTEGER NOT NULL,
  fitted REAL, fitted_lower REAL, fitted_upper REAL,
  pred_lower_95 REAL, pred_upper_95 REAL, pred_lower_80 REAL, pred_upper_80 REAL,
  contributions TEXT, inputs TEXT NOT NULL);
-- Every sort key has an index ending in id, in the same direction as the key,
-- so ORDER BY <key> <dir>, id <dir> scans it either way (no temp sort).
CREATE TABLE quarantined(
  audit_id TEXT PRIMARY KEY, building_id TEXT NOT NULL, building TEXT NOT NULL,
  unit_id TEXT, unit_label TEXT, unit_url TEXT, listing_url TEXT,
  period TEXT NOT NULL, is_current INTEGER NOT NULL, ask REAL NOT NULL,
  bedrooms REAL, bathrooms REAL, square_feet REAL,
  rule TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
  evidence TEXT, external_evidence TEXT);
CREATE INDEX quarantined_building ON quarantined(building_id, period);
CREATE INDEX quarantined_unit ON quarantined(unit_id, period);
CREATE INDEX quarantined_period ON quarantined(period, audit_id);
CREATE INDEX listings_period ON listings(period, id);
CREATE INDEX listings_ask ON listings(ask, id);
CREATE INDEX listings_estimate ON listings(estimate, id);
CREATE INDEX listings_residual_usd ON listings(residual_usd, id);
CREATE INDEX listings_residual_pct ON listings(residual_pct, id);
CREATE INDEX listings_building ON listings(building_id, period, id);
CREATE INDEX listings_unit ON listings(unit_id, period);
CREATE INDEX listings_current ON listings(is_current, period, id);
CREATE INDEX listings_bedrooms ON listings(bedrooms);
CREATE INDEX listings_neighbourhood ON listings(neighbourhood, period, id);
CREATE INDEX units_building ON units(building_id);
"""


class BuildError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_summary(selection: Path = SELECTION) -> Path:
    """The summary bundle the app's model selection names, verified."""
    try:
        record = json.loads(selection.read_text())
    except (OSError, ValueError) as error:
        raise BuildError(f"cannot read the selection {selection}: {error}") from None
    if (
        record.get("version") != SELECTION_VERSION
        or record.get("model_family") != "frontier_summary"
    ):
        raise BuildError(
            f"{selection} does not select a summary bundle; pass --summary"
        )
    if not {"summary", "summary_manifest_sha256"} <= record.keys():
        raise BuildError(f"{selection} names no summary bundle and sha256")
    summary = Path(record["summary"])
    complete = summary / "complete.json"
    if not complete.is_file() or sha256(complete) != record["summary_manifest_sha256"]:
        raise BuildError("the selected summary differs from the selection's record")
    return summary


def load_bundle(summary: Path) -> dict:
    """The bundle's provenance, with every listed file verified."""
    complete = summary / "complete.json"
    if not complete.is_file():
        raise BuildError(f"{summary} is not a complete summary bundle")
    record = json.loads(complete.read_text())
    if record.get("version") != "frontier-summary-v1":
        raise BuildError(f"unsupported summary version {record.get('version')!r}")
    for name, expected in record["files"].items():
        if sha256(summary / name) != expected:
            raise BuildError(f"{name} differs from the bundle's record")
    record["_sha256"] = sha256(complete)
    return record


def parquet_rows(path: Path) -> list[dict]:
    connection = duckdb.connect()
    try:
        result = connection.execute("SELECT * FROM read_parquet(?)", [str(path)])
        columns = [d[0] for d in result.description]
        return [
            {c: _plain(v) for c, v in zip(columns, row)} for row in result.fetchall()
        ]
    finally:
        connection.close()


def _plain(value):
    """Dates as ISO text (a parquet writer may store `period` as a date)."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


class Observations:
    """The dataset's rows by audit id, parsed from observations.jsonl when
    asked for. The first pass checks the file's sha256 and notes the offset of
    each row, so a build of every borough holds 1.6M offsets in memory and
    parses each row when a step reads it."""

    def __init__(self, dataset: Path, expected_sha256: str):
        source = dataset / "observations.jsonl"
        digest = hashlib.sha256()
        self._offsets: dict[str, int] = {}
        offset = 0
        with open(source, "rb") as f:
            for line in f:
                digest.update(line)
                if line.strip():
                    self._offsets[json.loads(line)["audit_id"]] = offset
                offset += len(line)
        if digest.hexdigest() != expected_sha256:
            raise BuildError(
                "the dataset differs from the one the summary was made from"
            )
        self._file = open(source, "rb")

    def close(self) -> None:
        self._file.close()

    def __len__(self) -> int:
        return len(self._offsets)

    def __contains__(self, audit_id) -> bool:
        return audit_id in self._offsets

    def __getitem__(self, audit_id: str) -> dict:
        self._file.seek(self._offsets[audit_id])
        return json.loads(self._file.readline())

    def get(self, audit_id: str, default=None):
        return self[audit_id] if audit_id in self._offsets else default

    def keys(self):
        return self._offsets.keys()

    def items(self):
        """Every row in the file's order, one parsed at a time."""
        with open(self._file.name, "rb") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    yield row["audit_id"], row


# Rows per chunk of the streamed build: about 0.6 GB of parsed rows and
# listings at a time.
CHUNK_ROWS = 40_000


def bundle_chunks(bundle: Path, size: int | None = None):
    """The bundle's rows (rows.parquet) in chunks of whole buildings, about
    `size` rows each (CHUNK_ROWS by default). Buildings that share a unit go in
    the same chunk, so each chunk holds every listing of its units and
    buildings. Each row carries its place in the bundle as `_row`."""
    size = size or CHUNK_ROWS
    path = str(bundle / "rows.parquet")
    connection = duckdb.connect()
    try:
        connection.execute("SET memory_limit = '1GB'")
        # One thread spills the sort of a wide bundle (2 GB of rows at 1.75M
        # rows) within the limit; with more threads DuckDB fails to pin blocks.
        connection.execute("SET threads = 1")
        connection.execute("SET preserve_insertion_order = false")
        connection.execute("SET temp_directory = ?", [tempfile.gettempdir()])
        pairs = connection.execute(
            "SELECT building, unit_id, COUNT(*) FROM read_parquet(?) "
            "GROUP BY building, unit_id ORDER BY building, unit_id",
            [path],
        ).fetchall()
        parent: dict[str, str] = {}

        def root(b):
            while parent[b] != b:
                parent[b] = parent[parent[b]]
                b = parent[b]
            return b

        home: dict[str, str] = {}
        count: Counter = Counter()
        for building, unit, n in pairs:
            parent.setdefault(building, building)
            count[building] += n
            if unit in home:
                a, b = root(home[unit]), root(building)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                home[unit] = building
        groups: dict[str, list[str]] = {}
        for building in sorted(parent):
            groups.setdefault(root(building), []).append(building)
        chunk_of, chunk, filled = {}, 0, 0
        for members in groups.values():
            rows = sum(count[b] for b in members)
            if filled and filled + rows > size:
                chunk, filled = chunk + 1, 0
            filled += rows
            chunk_of.update((b, chunk) for b in members)
        del pairs, parent, home, groups
        connection.execute(
            "CREATE TEMP TABLE chunk_of AS SELECT unnest(?) AS building, "
            "unnest(?) AS chunk",
            [list(chunk_of), list(chunk_of.values())],
        )
        result = connection.execute(
            # each chunk keeps the bundle's row order, which breaks ties in time
            # for a unit's latest listing and a building's newest one
            "SELECT r.* EXCLUDE (file_row_number), r.file_row_number AS _row, "
            "c.chunk AS _chunk "
            "FROM read_parquet(?, file_row_number = true) r "
            "JOIN chunk_of c ON r.building = c.building "
            "ORDER BY c.chunk, r.file_row_number",
            [path],
        )
        columns = [d[0] for d in result.description]
        current, rows = None, []
        while batch := result.fetchmany(5000):
            for values in batch:
                row = {c: _plain(v) for c, v in zip(columns, values)}
                chunk = row.pop("_chunk")
                if chunk != current and rows:
                    yield rows
                    rows = []
                current = chunk
                rows.append(row)
        if rows:
            yield rows
    finally:
        connection.close()


def external(record: dict, key: str) -> list[dict]:
    """A recorded external extract (registry, pluto), verified; [] if absent."""
    source = record.get("feature_sources", {}).get(key)
    if not source:
        return []
    path = Path(source["path"])
    if sha256(path) != source["sha256"]:
        raise BuildError(f"{key} extract differs from the run's record")
    return parquet_rows(path)


def latest_asks(record: dict) -> dict[str, float]:
    """The asks the latest-ask rules gave the run's rows (`rentfrontier.data.latest_ask_v3`),
    by audit id, from the rules' recorded tables, verified; {} if the run has no such rule.
    The model's target is each listing's latest ask, so the bundle carries these asks
    in place of the dataset's. The rules apply in order, and a row a table lacks keeps
    the ask before it."""
    asks = {}
    for rule in record.get("data_rules", ()):
        if not rule.startswith("latest-ask-"):
            continue
        source = record.get("data_rule_sources", {}).get(rule)
        if not source:
            raise BuildError(f"{rule} has no recorded table")
        path = Path(source["path"])
        if sha256(path) != source["sha256"]:
            raise BuildError(f"{rule} table differs from the run's record")
        query = f"SELECT audit_id, latest_ask FROM read_parquet('{path}')"
        table = duckdb.sql(query).fetchall()
        asks.update((a, float(v)) for a, v in table if v is not None)
    return asks


STREET_TYPES = {"STREET", "AVENUE", "PLACE", "ST", "AVE"}


def ordinal(number: str) -> str:
    n = int(number)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{number}{suffix}"


def title_address(label: str | None) -> str | None:
    """'134 WEST 23 STREET, New York, NY, USA' -> '134 West 23rd Street'."""
    if not label:
        return None
    words = label.split(",")[0].split()
    out = []
    for i, w in enumerate(words):
        following = words[i + 1].upper() if i + 1 < len(words) else ""
        if i > 0 and w.isdigit() and following in STREET_TYPES:
            out.append(ordinal(w))
        else:
            out.append(w if w[0].isdigit() else w.capitalize())
    return " ".join(out)


def building_names(slug: str, address: str | None) -> tuple[str | None, str]:
    """(name, address) for display. The name is the slug's words before the
    address's house number ("the-grove-250-west-19th-street" -> "The Grove");
    None when the slug is just the address."""
    words = slug.removesuffix("-new_york").split("-")
    titled = " ".join(w if w[0].isdigit() else w.capitalize() for w in words if w)
    if not address:
        return None, titled
    number = address.split()[0].lower()
    if number in words:
        cut = words.index(number)
        name = " ".join(w.capitalize() for w in words[:cut] if w)
        return (name or None), address
    return titled, address


def unit_label(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1].upper()


def natural_key(text: str) -> str:
    """Sort key that orders embedded numbers numerically ('9' before '10')."""
    return re.sub(r"\d+", lambda m: m.group().zfill(6), text.lower())


def price_band(pit: float) -> str:
    low, high = PRICE_BANDS
    return "below" if pit < low else "above" if pit > high else "typical"


def _floor(obs: dict) -> int | None:
    for key in ("listed_floor", "label_derived_floor"):
        value = obs.get(key)
        if value is not None:
            return int(value)
    return None


def _true_keys(mapping) -> str | None:
    keys = [k for k, v in (mapping or {}).items() if v]
    return json.dumps(keys) if keys else None


def _concession(value) -> str | None:
    if value in (None, "", [], {}):
        return None
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def listing_rows(
    rows, observations, names, k_threshold, scope="Chelsea", asks=None
) -> list[dict]:
    """Site rows of the listings. Each carries its neighbourhood: the summary's
    (combined cohorts), else the dataset's, else the build's scope. Each ask
    matches the dataset's, or the latest ask in `asks` (`latest_asks`). With
    `names` None the rows carry no dollar parts (detail.py)."""
    asks = asks or {}
    out = []
    for r in rows:
        obs = observations.get(r["audit_id"])
        if obs is None:
            raise BuildError(f"{r['audit_id']} is not in the dataset")
        expected = asks.get(r["audit_id"], float(obs["asking_rent"]))
        if abs(expected - r["asking_rent"]) > 1e-6:
            raise BuildError(f"{r['audit_id']}: ask differs from the dataset")
        median = r["estimate_median"]
        contributions = (
            json.dumps(detail.parts(r, names), separators=(",", ":"))
            if names is not None
            else None
        )
        k = r["pareto_k"]
        k = None if k is None or math.isnan(k) else float(k)
        listing_id = str(obs["source_listing_id"])
        out.append(
            {
                # the bundle's row order, which later steps read as a tie-break
                **({"id": r["_row"] + 1} if "_row" in r else {}),
                "audit_id": r["audit_id"],
                "neighbourhood": r.get("neighbourhood")
                or obs.get("neighbourhood")
                or scope,
                "unit_id": r["unit_id"],
                "building_id": r["building"],
                "unit_label": unit_label(obs.get("canonical_unit_url")),
                "unit_url": obs.get("canonical_unit_url"),
                "listing_id": listing_id,
                "listing_url": (
                    f"https://streeteasy.com/rental/{listing_id}"
                    if listing_id.isdigit()
                    else None
                ),
                "period": r["period"],
                "price_at": obs.get("price_at"),
                "is_current": int(obs["analysis_price_basis"] != HISTORICAL_BASIS),
                "price_basis": obs["analysis_price_basis"],
                "ask": r["asking_rent"],
                "bedrooms": obs.get("bedrooms"),
                "bathrooms": obs.get("bathrooms"),
                "full_baths": obs.get("reported_full_bathrooms"),
                "half_baths": obs.get("reported_half_bathrooms"),
                "square_feet": obs.get("square_feet"),
                "floor": _floor(obs),
                "elevator": {True: "yes", False: "no"}.get(obs.get("elevator")),
                "doorman": obs.get("doorman_type"),
                "laundry": obs.get("laundry_type"),
                "hvac": obs.get("hvac_type"),
                "pets": obs.get("pet_policy"),
                "views": _true_keys(obs.get("view_exposures")),
                "windows": _true_keys(obs.get("window_exposures")),
                "concession": _concession(obs.get("concession")),
                "collected_at": obs.get("collected_at"),
                "in_fit": int(r["in_fit"]),
                "unit_fit_rows": int(r["unit_fit_rows"]),
                "method": r["estimate_method"],
                "estimate": median,
                "estimate_lower": r["estimate_lower_95"],
                "estimate_upper": r["estimate_upper_95"],
                "estimate_median": r["estimate_median"],
                "residual_usd": r["asking_rent"] - median,
                "residual_pct": r["asking_rent"] / median - 1,
                "pit": r["pit"],
                "price_band": price_band(r["pit"]),
                "pareto_k": k,
                "reliable": int(k is None or k <= k_threshold),
                "fitted": r["fitted_rent"],
                "fitted_lower": r["fitted_rent_lower_95"],
                "fitted_upper": r["fitted_rent_upper_95"],
                # Where the ask itself is likely to fall (the predictive
                # interval, noise included); bundles before it have none.
                **{
                    f"pred_{side}_{level}": _real(
                        r.get(f"estimate_pred_{side}_{level}")
                    )
                    for level in (95, 80)
                    for side in ("lower", "upper")
                },
                "contributions": contributions,
                "inputs": r["inputs"],
            }
        )
    return out


def unit_heading(rows) -> str | None:
    """The label a unit goes by: a clean form first (no leading zero, no
    UNIT/APT prefix), then the one its listings use most often, then the
    shorter ignoring hyphens, then the hyphenated, then the most recent. So a
    joined unit is headed "4U", not by whichever variant came last ("004U"),
    and "460-11D" keeps its hyphen."""
    counts = Counter(r["unit_label"] for r in rows if r["unit_label"])
    if not counts:
        return None
    order = {r["unit_label"]: i for i, r in enumerate(rows)}  # last index wins

    def rank(label):
        clean = not re.match(r"(0\d|UNIT|APT)", label)
        return (
            clean,
            counts[label],
            -len(label.replace("-", "")),
            # A hyphen that separates parts (460-11D), not floor and letter (1-B).
            "-" in label and not re.fullmatch(r"\d+-[A-Z]", label),
            order[label],
        )

    return max(counts, key=rank)


def unit_rows(listings) -> list[dict]:
    by_unit: dict[str, list[dict]] = {}
    for row in listings:
        by_unit.setdefault(row["unit_id"], []).append(row)
    out = []
    for unit_id, rows in by_unit.items():
        rows.sort(key=lambda r: (r["period"], r["price_at"] or ""))
        last = rows[-1]

        def latest(key, rows=rows):
            values = [r[key] for r in rows if r[key] is not None]
            return values[-1] if values else None

        out.append(
            {
                "id": unit_id,
                "building_id": last["building_id"],
                "label": unit_heading(rows),
                "url": last["unit_url"],
                "bedrooms": latest("bedrooms"),
                "bathrooms": latest("bathrooms"),
                "square_feet": latest("square_feet"),
                "floor": latest("floor"),
                "listings": len(rows),
                "first_period": rows[0]["period"],
                "last_period": last["period"],
                "last_ask": last["ask"],
                "last_estimate": last["estimate"],
                "last_residual_pct": last["residual_pct"],
            }
        )
    return out


def building_rows(
    effects, listings, units, registry, pluto, wing_names=None
) -> list[dict]:
    located = {r["building"]: r for r in registry}
    lots = {str(r["bbl"]): r for r in pluto}
    by_building: dict[str, list[dict]] = {}
    for row in listings:
        by_building.setdefault(row["building_id"], []).append(row)
    unit_count: dict[str, int] = {}
    for unit in units:
        unit_count[unit["building_id"]] = unit_count.get(unit["building_id"], 0) + 1
    effect = {e["building"]: e for e in effects}
    if wing_names is None:
        wing_names = wings.names(by_building)
    out = []
    for slug, rows in by_building.items():
        reg = located.get(slug, {})
        lot = lots.get(str(reg.get("bbl")), {}) if reg.get("bbl") else {}
        name, address = building_names(slug, title_address(reg.get("label")))
        name = wing_names.get(slug, name)
        e = effect.get(slug, {})
        periods = sorted(r["period"] for r in rows)
        display = name or address
        out.append(
            {
                "id": slug,
                "neighbourhood": Counter(r["neighbourhood"] for r in rows).most_common(
                    1
                )[0][0],
                "name": name,
                "address": address,
                "sort_key": natural_key(display),
                "search": " ".join(
                    x.lower() for x in (name, address, slug.replace("-", " ")) if x
                ),
                "latitude": reg.get("latitude"),
                "longitude": reg.get("longitude"),
                "bbl": reg.get("bbl"),
                "year_built": _int(lot.get("yearbuilt")),
                "floors": _int(lot.get("numfloors")),
                "residential_units": _int(lot.get("unitsres")),
                "building_class": lot.get("bldgclass"),
                "landmark": lot.get("landmark"),
                "historic_district": lot.get("histdist"),
                "level_pct": e.get("level_pct"),
                "level_pct_lower": e.get("level_pct_lower_95"),
                "level_pct_upper": e.get("level_pct_upper_95"),
                "trend_pct": e.get("trend_pct_per_year"),
                "trend_pct_lower": e.get("trend_pct_per_year_lower_95"),
                "trend_pct_upper": e.get("trend_pct_per_year_upper_95"),
                "fit_rows": e.get("fit_rows"),
                "listings": len(rows),
                "units": unit_count.get(slug, 0),
                "current_listings": sum(r["is_current"] for r in rows),
                "first_period": periods[0],
                "last_period": periods[-1],
                "median_residual_pct": statistics.median(
                    r["residual_pct"] for r in rows
                ),
            }
        )
    return out


def calibration(listings) -> dict:
    """Share of asks inside the leave-own-row-out predictive 95% and 80% ranges
    (from each ask's PIT) and the median |ask / estimate - 1|, by how the
    estimate was made: held out of the fit, from the unit's other listings, or
    for a unit listed once (building and features only)."""
    groups = {"heldout": [], "multi": [], "single": []}
    for r in listings:
        if r["method"] == "heldout":
            groups["heldout"].append(r)
        else:
            groups["multi" if r["unit_fit_rows"] > 1 else "single"].append(r)
    out = {}
    for key, rows in groups.items():
        if not rows:
            continue
        n = len(rows)
        out[key] = {
            "n": n,
            "cover95": sum(0.025 < r["pit"] < 0.975 for r in rows) / n,
            "cover80": sum(0.1 < r["pit"] < 0.9 for r in rows) / n,
            "median_abs_pct": statistics.median(abs(r["residual_pct"]) for r in rows),
        }
    return out


def calibration_by_year(listings) -> list[dict]:
    """The same coverage by listing year, with the mean log(ask / estimate):
    whether the estimates are centred each year, and whether the ranges are as
    wide as the asks' scatter that year."""
    years: dict[str, list] = {}
    for r in listings:
        years.setdefault(r["period"][:4], []).append(r)
    out = []
    for year, rows in sorted(years.items()):
        n = len(rows)
        out.append(
            {
                "year": int(year),
                "n": n,
                "cover95": sum(0.025 < r["pit"] < 0.975 for r in rows) / n,
                "cover80": sum(0.1 < r["pit"] < 0.9 for r in rows) / n,
                "mean_log_residual": sum(math.log1p(r["residual_pct"]) for r in rows)
                / n,
            }
        )
    return out


def _int(value):
    """A whole number from a MapPLUTO field, which the snapshots store as text
    ("20.0000000"); None when absent or not a number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else int(number)


def _real(value) -> float | None:
    """A float, or None for a missing or NaN value."""
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


def _insert(db, table, rows, verb="INSERT"):
    if not rows:
        return
    columns = list(rows[0])
    db.executemany(
        f"{verb} INTO {table}({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})",
        [tuple(r[c] for c in columns) for r in rows],
    )


def rule_decisions(record: dict, bundle: Path) -> dict[str, dict]:
    """audit_id -> the review decision of every row a row-dropping data rule
    of the run leaves out (from the bundle's verified copies)."""
    out = {}
    for rule, name in record.get("data_rule_files", {}).items():
        if name not in record.get("files", {}):
            raise BuildError(f"the bundle's {rule} file is not in its hashed files")
        with open(bundle / name) as f:
            for line in f:
                if line.strip():
                    decision = json.loads(line)
                    out[decision["audit_id"]] = {**decision, "rule": rule}
    return out


def _listing_url(obs: dict) -> str | None:
    listing_id = str(obs["source_listing_id"])
    return (
        f"https://streeteasy.com/rental/{listing_id}" if listing_id.isdigit() else None
    )


def quarantined_rows(missing, observations, decisions, registry) -> list[dict]:
    located = {r["building"]: r for r in registry}
    out = []
    for audit_id in sorted(missing, key=lambda a: (observations[a]["period"], a)):
        obs, d = observations[audit_id], decisions[audit_id]
        reg = located.get(obs["building"], {})
        name, address = building_names(obs["building"], title_address(reg.get("label")))
        listing_url = _listing_url(obs)
        out.append(
            {
                "audit_id": audit_id,
                "building_id": obs["building"],
                "building": name or address,
                "unit_id": d.get("unit_id"),
                "unit_label": unit_label(obs.get("canonical_unit_url")),
                "unit_url": obs.get("canonical_unit_url"),
                "listing_url": listing_url,
                "period": obs["period"],
                "is_current": int(obs["analysis_price_basis"] != HISTORICAL_BASIS),
                "ask": float(obs["asking_rent"]),
                "bedrooms": obs.get("bedrooms"),
                "bathrooms": obs.get("bathrooms"),
                "square_feet": obs.get("square_feet"),
                "rule": d["rule"],
                "action": d["action"],
                "reason": d["reason"],
                "evidence": d.get("evidence") or None,
                "external_evidence": d.get("external_evidence"),
            }
        )
    return out


def _whole_buildings(db, buildings: set[str]) -> list[dict]:
    """Every listing of `buildings`, widened to the buildings their units
    also have listings in, so the unit and building rows come out whole."""
    buildings = set(buildings)
    while True:
        marks = ",".join("?" * len(buildings))
        wider = {
            b
            for (b,) in db.execute(
                f"SELECT DISTINCT building_id FROM listings WHERE unit_id IN "
                f"(SELECT unit_id FROM listings WHERE building_id IN ({marks}))",
                tuple(buildings),
            )
        }
        if wider <= buildings:
            break
        buildings |= wider
    marks = ",".join("?" * len(buildings))
    cursor = db.execute(
        f"SELECT * FROM listings WHERE building_id IN ({marks}) ORDER BY id",
        tuple(buildings),
    )
    columns = [d[0] for d in cursor.description]
    return [
        {c: v for c, v in zip(columns, row) if c != "id"} for row in cursor.fetchall()
    ]


class StoredListings:
    """The fitted listings already in the build's database, read afresh on
    each pass, for the kit's checks over every listing."""

    def __init__(self, db):
        self._db = db

    def __iter__(self):
        cursor = self._db.cursor()
        cursor.row_factory = sqlite3.Row
        yield from cursor.execute(
            "SELECT * FROM listings WHERE method != ? ORDER BY id", (captures.METHOD,)
        )


def write_database(
    path: Path,
    record: dict,
    bundle: Path,
    scope: str | None,
    selection: dict | None = None,
    kits: Path | None = None,
    pipeline: Path | None = None,
    exposure_file: Path | None = None,
    on_request: bool | None = None,
) -> dict:
    """Write the site database at `path`. With `on_request` (by default
    SITE_DETAIL_ON_REQUEST=1) the fitted listings' dollar parts go to
    detail.parquet beside it instead of the `listings` table. A bundle with
    range atoms gets ranges.parquet and noise.json beside it (detail.py)."""
    if on_request is None:
        on_request = os.environ.get("SITE_DETAIL_ON_REQUEST") == "1"
    observations = Observations(
        Path(record["dataset"]), record["dataset_observations_sha256"]
    )
    db = sqlite3.connect(path)
    try:
        return _write(
            db,
            observations,
            record,
            bundle,
            scope,
            selection,
            kits,
            pipeline,
            exposure_file,
            path.parent / detail.FILE if on_request else None,
            path.parent / detail.RANGES_FILE,
        )
    finally:
        db.close()
        observations.close()


def _write(
    db,
    observations,
    record,
    bundle,
    scope,
    selection,
    kits,
    pipeline,
    exposure_file,
    detail_file,
    ranges_file,
) -> dict:
    terms = json.loads((bundle / "terms.json").read_text())
    names = [t["name"] for t in terms]
    if names != record["terms"]:
        raise BuildError("terms.json differs from the bundle's record")
    decisions = rule_decisions(record, bundle)
    k_threshold = record["estimate_pareto_k"]["threshold"]
    asks = latest_asks(record)
    registry = external(record, "registry")
    pluto = external(record, "pluto")
    effects = parquet_rows(bundle / "buildings.parquet")
    slugs = [
        b
        for (b,) in duckdb.sql(
            f"SELECT DISTINCT building FROM read_parquet('{bundle / 'rows.parquet'}')"
        ).fetchall()
    ]
    wing_names = wings.names(slugs)
    del slugs

    def buildings_of(listings, units):
        return building_rows(effects, listings, units, registry, pluto, wing_names)

    # A listing is on the market now when it was seen active within
    # captures.CURRENT_DAYS of this build (a week, Ben 2026-10-10, plus two
    # days for the weekly top-up): the dataset's current rows age out too.
    at = captures.now()
    db.executescript(SCHEMA)
    # The bundle's rows go in a chunk of whole buildings at a time: a build
    # of every borough has 1.6M of them.
    fit_ids: set[str] = set()
    neighbourhoods: set[str] = set()
    for rows in bundle_chunks(bundle):
        listings = listing_rows(
            rows,
            observations,
            None if detail_file else names,
            k_threshold,
            scope or "Chelsea",
            asks,
        )
        del rows
        for r in listings:
            if r["is_current"] and not captures.fresh(r, at):
                r["is_current"] = 0
        units = unit_rows(listings)
        _insert(db, "buildings", buildings_of(listings, units))
        _insert(db, "units", units)
        _insert(db, "listings", listings)
        fit_ids.update(r["audit_id"] for r in listings)
        neighbourhoods.update(r["neighbourhood"] for r in listings)
        del listings, units
    missing = observations.keys() - fit_ids
    unexplained = missing - decisions.keys()
    if unexplained:
        raise BuildError(
            f"{len(unexplained)} dataset rows are missing from the bundle and no "
            "data rule drops them"
        )
    # The rule's rows are exactly the missing ones: none left in the bundle,
    # none absent from the dataset.
    if decisions.keys() - missing:
        raise BuildError(
            f"{len(decisions.keys() - missing)} rows a data rule drops are in the "
            "bundle or not in the dataset"
        )
    if not scope:
        scope = scope_of([{"neighbourhood": n} for n in neighbourhoods])
    reader = db.cursor()
    reader.row_factory = sqlite3.Row
    fitted = reader.execute(
        "SELECT method, unit_fit_rows, pit, residual_pct, period FROM listings"
    ).fetchall()
    stats = {
        "calibration": calibration(fitted),
        "calibration_by_year": calibration_by_year(fitted),
    }
    del fitted
    if detail_file:
        stats["detail"] = detail.write(bundle, names, detail_file)
    # The kit's checks compare its ranges with these where the table has none.
    likely = None
    if detail.has_atoms(bundle):
        stats["ranges"] = detail.write_ranges(bundle, ranges_file)
        likely = detail.Ranges(ranges_file).likely_ask

    kit_dir = estimate_build.find_kit(
        record["run"], record["_sha256"], kits or estimate_build.KITS
    )

    def local(ad_units: set[str], ad_buildings: set[str]):
        """The listings and building rows the ads' pricing reads: every
        listing of their buildings and units."""
        marks = ",".join("?" * len(ad_units))
        widen = {
            b
            for (b,) in db.execute(
                f"SELECT DISTINCT building_id FROM listings WHERE unit_id IN ({marks})",
                tuple(ad_units),
            )
        }
        listings = (
            _whole_buildings(db, ad_buildings | widen) if ad_buildings | widen else []
        )
        ids = {r["building_id"] for r in listings}
        marks = ",".join("?" * len(ids))
        cursor = db.execute(
            f"SELECT * FROM buildings WHERE id IN ({marks})", tuple(ids)
        )
        columns = [d[0] for d in cursor.description]
        return listings, [dict(zip(columns, row)) for row in cursor.fetchall()]

    # The ads on the market in the pipeline's newest build, priced with the
    # kit (captures.py); every other row is the bundle's.
    files = captures.pipeline_files(pipeline or captures.PIPELINE)
    # units in the bundle's order, each one's listings in time order, as
    # captures.relisting_centre visits them
    cursor = db.execute(
        "SELECT l.unit_id, l.price_at, l.period, l.collected_at, l.inputs "
        "FROM listings l JOIN (SELECT unit_id, MIN(id) AS first FROM listings "
        "WHERE method != ? GROUP BY unit_id) u ON l.unit_id = u.unit_id "
        "WHERE l.method != ? "
        "ORDER BY u.first, COALESCE(NULLIF(l.price_at, ''), l.period), l.id",
        (captures.METHOD, captures.METHOD),
    )
    cursor.row_factory = sqlite3.Row
    centre = captures.centre_of(
        [dict(r) for r in rows]
        for _, rows in itertools.groupby(cursor, key=lambda r: r["unit_id"])
    )
    cursor.close()
    captured, captured_status = captures.price(
        kit_dir,
        StoredListings(db),
        [],
        files,
        names,
        observations,
        at,
        local=local,
        fit_ids=fit_ids,
        centre=centre,
        likely=likely,
    )
    stats["estimate_form"] = estimate_build.install(
        db, kit_dir, StoredListings(db), observations, likely
    )
    if captured:
        # a unit the pipeline read since the dataset last saw it is current there
        newer = sorted({r["unit_id"] for r in captured})
        marks = ",".join("?" * len(newer))
        touched = {r["building_id"] for r in captured} | {
            b
            for (b,) in db.execute(
                f"SELECT DISTINCT building_id FROM listings WHERE unit_id IN ({marks})",
                newer,
            )
        }
        db.execute(
            f"UPDATE listings SET is_current = 0 WHERE is_current = 1 "
            f"AND unit_id IN ({marks})",
            newer,
        )
        # A new unit's row goes in before its listings.
        whole = _whole_buildings(db, touched)
        units = unit_rows(whole + captured)
        _insert(db, "units", units, "INSERT OR REPLACE")
        _insert(db, "listings", captured)
        _insert(
            db, "buildings", buildings_of(whole + captured, units), "INSERT OR REPLACE"
        )
        del whole, units
    quarantined = quarantined_rows(missing, observations, decisions, registry)
    for r in quarantined:
        if r["is_current"] and not captures.fresh(observations[r["audit_id"]], at):
            r["is_current"] = 0
    market = [
        {
            "period": m["period"],
            "rent": m["reference_rent"],
            "deseasoned": m["reference_rent_deseasoned"],
            "deseasoned_lower": m["reference_rent_deseasoned_lower_95"],
            "deseasoned_upper": m["reference_rent_deseasoned_upper_95"],
        }
        for m in parquet_rows(bundle / "market.parquet")
    ]
    coefficients = [
        {
            "feature": c["feature"],
            "feature_group": c["group"],
            "pct": c["pct"],
            "pct_lower": c["pct_lower_95"],
            "pct_upper": c["pct_upper_95"],
            "probability_positive": c["probability_positive"],
        }
        for c in parquet_rows(bundle / "coefficients.parquet")
    ]
    (count, current, first, last, unreliable) = db.execute(
        "SELECT COUNT(*), SUM(is_current), MIN(period), MAX(period), "
        "SUM(1 - reliable) FROM listings"
    ).fetchone()
    stats |= {
        "listings": count,
        "current_listings": current,
        "neighbourhoods": dict(
            db.execute(
                "SELECT neighbourhood, COUNT(*) FROM listings "
                "GROUP BY neighbourhood ORDER BY neighbourhood"
            ).fetchall()
        ),
        "units": db.execute("SELECT COUNT(*) FROM units").fetchone()[0],
        "buildings": db.execute("SELECT COUNT(*) FROM buildings").fetchone()[0],
        "first_period": first,
        "last_period": last,
        "unreliable_estimates": unreliable,
        "current_ads": captured_status,
        "quarantined_listings": len(quarantined),
        "quarantined_current": sum(r["is_current"] for r in quarantined),
    }
    _insert(db, "quarantined", quarantined)
    _insert(db, "market", market)
    _insert(db, "coefficients", coefficients)
    current_rows = [
        {"audit_id": a, "listing_id": i, "is_current": 1}
        for a, i in db.execute(
            "SELECT audit_id, listing_id FROM listings WHERE is_current = 1"
        )
    ]
    stats["ad_dates"] = ad_dates.install(
        db, ad_dates.collect(files, current_rows), current_rows
    )
    # Which way each unit faces, when Data improvements' labels exist; a
    # build without them shows none.
    labels = exposure_file or exposure.FILE
    stats["exposure"] = (
        exposure.install(
            db,
            labels,
            parquet_rows(labels),
            {u for (u,) in db.execute("SELECT id FROM units")},
        )
        if labels.is_file()
        else {"installed": False, "reason": f"no labels at {labels}"}
    )
    db.executemany(
        "INSERT INTO terms VALUES (?,?,?,?)",
        [(i, t["name"], t["label"], t["description"]) for i, t in enumerate(terms)],
    )
    provenance = {
        k: v for k, v in record.items() if not k.startswith("_") and k != "files"
    }
    meta = {
        "version": VERSION,
        "scope": scope,
        "summary": str(bundle),
        "summary_sha256": record["_sha256"],
        "provenance": provenance,
        "stats": stats,
        "price_bands": PRICE_BANDS,
        "selection": selection,
        "story_checks": story_checks(db),
    }
    db.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [(k, json.dumps(v)) for k, v in meta.items()],
    )
    db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    db.commit()
    db.execute("ANALYZE")
    db.commit()
    problems = db.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise BuildError(f"foreign key violations: {problems[:5]}")
    return stats


def story_checks(db) -> list:
    """The research story's held-out accuracy, rent jumps, unit examples and
    border medians. Each scans every listing or building, so the build works
    them out once and the server reads them from meta."""
    factory = db.row_factory
    db.row_factory = sqlite3.Row
    try:
        return [
            story.accuracy(db),
            story.rent_jumps(db),
            story.unit_examples(db),
            story.borders(db),
        ]
    finally:
        db.row_factory = factory


def bundle_map(source: Path, target: Path, database: Path) -> None:
    """The run's rent map for the build, each building tagged with its
    neighbourhood from the build's database (the map's neighbourhood choice
    lists a neighbourhood's buildings by it) and, from its tax class, whether
    it is a walk-up (C) or an elevator building (D), for the map's building
    choice."""
    data = json.loads(source.read_text())
    db = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        columns = {r[1] for r in db.execute("PRAGMA table_info(buildings)")}
        names = (
            dict(db.execute("SELECT id, neighbourhood FROM buildings"))
            if "neighbourhood" in columns
            else {}
        )
        kinds = (
            {
                id_: KINDS[cls[:1]]
                for id_, cls in db.execute("SELECT id, building_class FROM buildings")
                if cls and cls[:1] in KINDS
            }
            if "building_class" in columns
            else {}
        )
    finally:
        db.close()
    for b in data.get("buildings", []):
        # rentmap's own tag (the neighbourhood its medians used) wins.
        if not b.get("neighbourhood") and names.get(b.get("id")):
            b["neighbourhood"] = names[b["id"]]
        if kinds.get(b.get("id")):
            b["kind"] = kinds[b["id"]]
    target.write_text(json.dumps(data, separators=(",", ":")))


def rent_map(run: str, maps: Path | None = None) -> Path | None:
    """The newest rent map of `run`, if one has been made; a bundle that names
    another run is refused."""
    maps = MAPS if maps is None else maps
    found = sorted(
        maps.glob(f"{glob.escape(run)}-{'[0-9a-f]' * 7}/map.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not found:
        return None
    try:
        named = json.loads(found[-1].read_text()).get("run")
    except (OSError, ValueError) as error:
        raise BuildError(f"cannot read the rent map {found[-1]}: {error}") from None
    if named != run:
        raise BuildError(f"the rent map {found[-1]} is of {named}, not {run}")
    return found[-1]


def publish(build_dir: Path, root: Path, keep: int = KEEP) -> None:
    """Point root/current at build_dir atomically; prune old builds."""
    link = root / "current"
    tmp = root / f".current-{os.getpid()}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(build_dir.relative_to(root))
    os.replace(tmp, link)
    builds = sorted(
        p
        for p in (root / "builds").iterdir()
        if p.is_dir() and not p.name.endswith(".tmp")
    )
    live = build_dir.resolve()
    database = build_dir / "site.sqlite"
    if database.exists() and database.stat().st_size > LARGE_BYTES:
        keep = 1
    for old in builds[:-keep]:
        if old.resolve() != live:
            shutil.rmtree(old)


def override_of(note: dict | None) -> dict | None:
    """The selection's recorded decision to serve a run that fails the gate,
    when it says who decided, when and why."""
    override = (note or {}).get("gate_override")
    if isinstance(override, dict) and all(
        override.get(k) for k in ("by", "at", "reason")
    ):
        return override
    return None


def scope_of(listings: list[dict]) -> str:
    """The neighbourhoods the listings cover, in words ("Chelsea and West
    Village", or by count and borough past twelve): the site's name for the
    area when the publish does not give one."""
    return boroughs.scope_words(sorted({row["neighbourhood"] for row in listings}))


def build(
    summary: Path,
    root: Path = DEFAULT_ROOT,
    scope: str | None = None,
    selection: Path = SELECTION,
) -> Path:
    summary = summary.resolve()
    record = load_bundle(summary)
    note = selection_note(selection, record["_sha256"])
    if not record["gate"]["passes"] and not override_of(note):
        raise BuildError(
            "the summary's run fails the convergence gate, and the selection "
            "records no decision to serve it anyway"
        )
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    build_dir = root / "builds" / f"{stamp}-{record['_sha256'][:8]}"
    staging = build_dir.with_name(build_dir.name + ".tmp")
    staging.mkdir(parents=True)
    try:
        stats = write_database(
            staging / "site.sqlite",
            record,
            summary,
            scope,
            note,
        )
        source_map = rent_map(record["run"])
        if source_map is not None:
            bundle_map(source_map, staging / "map.json", staging / "site.sqlite")
        info = {
            "version": VERSION,
            "rent_map": str(source_map) if source_map else None,
            "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "summary": str(summary),
            "summary_sha256": record["_sha256"],
            "run": record["run"],
            "stats": stats,
            "site_sqlite_sha256": sha256(staging / "site.sqlite"),
        }
        (staging / "build.json").write_text(json.dumps(info, indent=2))
        staging.rename(build_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    publish(build_dir, root)
    return build_dir


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m apartments.site build",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--summary", type=Path, help="bundle to publish (default: the selected model's)"
    )
    parser.add_argument("--selection", type=Path, default=SELECTION)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--scope",
        default=None,
        help="neighbourhoods covered, in words (default: the listings' own)",
    )
    args = parser.parse_args(argv)
    try:
        summary = args.summary or selected_summary(args.selection)
        path = build(summary, args.root, args.scope, args.selection)
    except BuildError as error:
        raise SystemExit(f"build failed: {error}") from None
    print(f"published {path}")

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
  (sha256): addresses, coordinates and building facts.

Writes <root>/builds/<stamp>/site.sqlite and build.json, then points
<root>/current at the new build with an atomic symlink swap and keeps the
newest KEEP builds. The site opens current/site.sqlite read-only for each
request, so publishing needs no restart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import statistics
from pathlib import Path

import duckdb

VERSION = "listings-site-v1"
SCHEMA_VERSION = 1
DEFAULT_ROOT = Path(os.environ.get("SITE_ROOT", "/data1/apartments/site"))
SELECTION = Path(__file__).resolve().parents[3] / "config" / "main-analysis.json"
SELECTION_VERSION = "main-analysis-selection-v2"
KEEP = 3
# Where the ask falls in its leave-own-row-out predictive distribution.
PRICE_BANDS = (0.10, 0.90)
HISTORICAL_BASIS = "historical_initial_own_advertisement_ask"

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE terms(position INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE market(period TEXT PRIMARY KEY, rent REAL, rent_lower REAL,
  rent_upper REAL, deseasoned REAL, deseasoned_lower REAL, deseasoned_upper REAL);
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
  current_listings INTEGER NOT NULL, first_period TEXT, last_period TEXT,
  median_residual_pct REAL);
CREATE TABLE units(
  id TEXT PRIMARY KEY, building_id TEXT NOT NULL REFERENCES buildings(id),
  label TEXT, url TEXT, bedrooms REAL, bathrooms REAL, square_feet REAL,
  floor INTEGER, listings INTEGER NOT NULL, first_period TEXT, last_period TEXT,
  last_ask REAL, last_estimate REAL, last_residual_pct REAL);
CREATE TABLE listings(
  id INTEGER PRIMARY KEY, audit_id TEXT NOT NULL UNIQUE,
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
  contributions TEXT NOT NULL, inputs TEXT NOT NULL);
CREATE INDEX listings_period ON listings(period DESC, id);
CREATE INDEX listings_ask ON listings(ask);
CREATE INDEX listings_residual_pct ON listings(residual_pct);
CREATE INDEX listings_building ON listings(building_id, period DESC);
CREATE INDEX listings_unit ON listings(unit_id, period);
CREATE INDEX listings_current ON listings(is_current, period DESC);
CREATE INDEX listings_bedrooms ON listings(bedrooms);
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
    record = json.loads(selection.read_text())
    if (
        record.get("version") != SELECTION_VERSION
        or record.get("model_family") != "frontier_summary"
    ):
        raise BuildError(
            f"{selection} does not select a summary bundle; pass --summary"
        )
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


def load_observations(dataset: Path, expected_sha256: str) -> dict[str, dict]:
    source = dataset / "observations.jsonl"
    if sha256(source) != expected_sha256:
        raise BuildError("the dataset differs from the one the summary was made from")
    rows = {}
    with open(source) as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows[row["audit_id"]] = row
    return rows


def external(record: dict, key: str) -> list[dict]:
    """A recorded external extract (registry, pluto), verified; [] if absent."""
    source = record.get("feature_sources", {}).get(key)
    if not source:
        return []
    path = Path(source["path"])
    if sha256(path) != source["sha256"]:
        raise BuildError(f"{key} extract differs from the run's record")
    return parquet_rows(path)


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


def listing_rows(rows, observations, names, k_threshold) -> list[dict]:
    out = []
    for r in rows:
        obs = observations.get(r["audit_id"])
        if obs is None:
            raise BuildError(f"{r['audit_id']} is not in the dataset")
        if abs(float(obs["asking_rent"]) - r["asking_rent"]) > 1e-6:
            raise BuildError(f"{r['audit_id']}: ask differs from the dataset")
        contributions = [
            {
                "term": name,
                "usd": round(r[f"{name}_usd"], 2),
                "lower": round(r[f"{name}_usd_lower_95"], 2),
                "upper": round(r[f"{name}_usd_upper_95"], 2),
            }
            for name in names
        ]
        k = r["pareto_k"]
        k = None if k is None or math.isnan(k) else float(k)
        listing_id = str(obs["source_listing_id"])
        out.append(
            {
                "audit_id": r["audit_id"],
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
                "estimate": r["estimate"],
                "estimate_lower": r["estimate_lower_95"],
                "estimate_upper": r["estimate_upper_95"],
                "estimate_median": r["estimate_median"],
                "residual_usd": r["residual_usd"],
                "residual_pct": r["residual_pct"],
                "pit": r["pit"],
                "price_band": price_band(r["pit"]),
                "pareto_k": k,
                "reliable": int(k is None or k <= k_threshold),
                "fitted": r["fitted_rent"],
                "fitted_lower": r["fitted_rent_lower_95"],
                "fitted_upper": r["fitted_rent_upper_95"],
                "contributions": json.dumps(contributions, separators=(",", ":")),
                "inputs": r["inputs"],
            }
        )
    return out


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
                "label": last["unit_label"],
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


def building_rows(effects, listings, units, registry, pluto) -> list[dict]:
    located = {r["building"]: r for r in registry}
    lots = {str(r["bbl"]): r for r in pluto}
    by_building: dict[str, list[dict]] = {}
    for row in listings:
        by_building.setdefault(row["building_id"], []).append(row)
    unit_count: dict[str, int] = {}
    for unit in units:
        unit_count[unit["building_id"]] = unit_count.get(unit["building_id"], 0) + 1
    effect = {e["building"]: e for e in effects}
    out = []
    for slug, rows in by_building.items():
        reg = located.get(slug, {})
        lot = lots.get(str(reg.get("bbl")), {}) if reg.get("bbl") else {}
        name, address = building_names(slug, title_address(reg.get("label")))
        e = effect.get(slug, {})
        periods = sorted(r["period"] for r in rows)
        display = name or address
        out.append(
            {
                "id": slug,
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


def _int(value):
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _insert(db, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    db.executemany(
        f"INSERT INTO {table}({','.join(columns)}) "
        f"VALUES ({','.join('?' * len(columns))})",
        [tuple(r[c] for c in columns) for r in rows],
    )


def write_database(path: Path, record: dict, bundle: Path, scope: str) -> dict:
    observations = load_observations(
        Path(record["dataset"]), record["dataset_observations_sha256"]
    )
    rows = parquet_rows(bundle / "rows.parquet")
    if len(rows) != len(observations):
        raise BuildError(
            f"the bundle has {len(rows)} rows, the dataset {len(observations)}"
        )
    terms = json.loads((bundle / "terms.json").read_text())
    names = [t["name"] for t in terms]
    if names != record["terms"]:
        raise BuildError("terms.json differs from the bundle's record")
    k_threshold = record["estimate_pareto_k"]["threshold"]
    listings = listing_rows(rows, observations, names, k_threshold)
    units = unit_rows(listings)
    buildings = building_rows(
        parquet_rows(bundle / "buildings.parquet"),
        listings,
        units,
        external(record, "registry"),
        external(record, "pluto"),
    )
    market = [
        {
            "period": m["period"],
            "rent": m["reference_rent"],
            "rent_lower": m["reference_rent_lower_95"],
            "rent_upper": m["reference_rent_upper_95"],
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
    periods = sorted(r["period"] for r in listings)
    stats = {
        "calibration": calibration(listings),
        "listings": len(listings),
        "current_listings": sum(r["is_current"] for r in listings),
        "units": len(units),
        "buildings": len(buildings),
        "first_period": periods[0],
        "last_period": periods[-1],
        "unreliable_estimates": sum(1 - r["reliable"] for r in listings),
    }
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        _insert(db, "buildings", buildings)
        _insert(db, "units", units)
        _insert(db, "listings", listings)
        _insert(db, "market", market)
        _insert(db, "coefficients", coefficients)
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
    finally:
        db.close()
    return stats


def publish(build_dir: Path, root: Path, keep: int = KEEP) -> None:
    """Point root/current at build_dir atomically; prune old builds."""
    link = root / "current"
    tmp = root / f".current-{os.getpid()}"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(build_dir.relative_to(root))
    os.replace(tmp, link)
    builds = sorted(p for p in (root / "builds").iterdir() if p.is_dir())
    live = build_dir.resolve()
    for old in builds[:-keep]:
        if old.resolve() != live:
            shutil.rmtree(old)


def build(summary: Path, root: Path = DEFAULT_ROOT, scope: str = "Chelsea") -> Path:
    summary = summary.resolve()
    record = load_bundle(summary)
    if not record["gate"]["passes"]:
        raise BuildError("the summary's run fails the convergence gate")
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    build_dir = root / "builds" / f"{stamp}-{record['_sha256'][:8]}"
    staging = build_dir.with_name(build_dir.name + ".tmp")
    staging.mkdir(parents=True)
    try:
        stats = write_database(staging / "site.sqlite", record, summary, scope)
        info = {
            "version": VERSION,
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
    parser.add_argument("--scope", default="Chelsea", help="neighborhoods covered")
    args = parser.parse_args(argv)
    try:
        summary = args.summary or selected_summary(args.selection)
        path = build(summary, args.root, args.scope)
    except BuildError as error:
        raise SystemExit(f"build failed: {error}") from None
    print(f"published {path}")

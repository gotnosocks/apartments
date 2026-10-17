"""Install the served run's prediction kit into a site build, after checking it.

The kit (`rentfrontier.kit`) is found by run and must name the build's summary
bundle by sha256. Before the estimate form uses it, the build checks it two
ways, and a kit that fails either gets no form (the build itself goes ahead):

1. Scoring: the bundle's own rows of the last month whose apartment has only
   that row in the fit are rescored from their inputs, as new apartments. The
   kit uses the full posterior and the bundle leaves each row out (PSIS), so
   single rows differ by a few percent; the median of kit / bundle - 1 must be
   within SCORE_TOLERANCE for the median estimate and both 80% bounds. A
   missing term, a wrong season or a wrong building would move every row.
2. Encoding: the form's encoder, run on a listing's own recorded fields,
   must give the inputs the model gave that listing, column group by column
   group, on at least ENCODE_AGREEMENT of the listings (data rules correct a
   few fields after the dataset, so not all). Only apartments listed once
   count: the model takes some fields from all of an apartment's listings
   (its median size, its usual bedroom count), and for an apartment listed
   once those are the listing's own, as they are for the form's apartment.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import itertools
import json
import os
import re
import sqlite3
import statistics
from array import array
from collections import Counter
from pathlib import Path

import duckdb

from . import estimate

KITS = Path(os.environ.get("FRONTIER_KITS", "/data1/apartments/frontier/kits"))
VERSION = "frontier-kit-v1"
SCORE_ROWS = 150
SCORE_MIN_ROWS = 20
SCORE_SAMPLES = 40
SCORE_TOLERANCE = 0.02
ENCODE_AGREEMENT = 0.95
# Column groups the encoding check compares, with the recorded fields they need.
ENCODE_GROUPS = (
    "bedrooms",
    "bathrooms",
    "size",
    "floor",
    "laundry",
    "views",
    "windows",
    "unit label",
)

SCHEMA = """
CREATE TABLE kit(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE kit_buildings(building_id TEXT PRIMARY KEY, level TEXT NOT NULL,
  bedroom_slope TEXT NOT NULL, fslope TEXT NOT NULL);
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_kit(run: str, summary_sha256: str, kits: Path = KITS) -> Path | None:
    """The newest complete kit of `run` made for this summary bundle."""
    found = []
    for path in glob.glob(str(kits / glob.escape(run)) + "-*/complete.json"):
        try:
            record = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if (
            record.get("version") == VERSION
            and record.get("run") == run
            and record.get("summary_sha256") == summary_sha256
        ):
            found.append((record.get("created_at", ""), Path(path).parent))
    return max(found)[1] if found else None


KIT_BATCH_ROWS = 2048


class Draws:
    """A building's feature slopes over the kit's draws, a row per draw, held
    in a flat float array."""

    def __init__(self, rows: list[list[float]]):
        self._rows = len(rows)
        self._width = len(rows[0]) if rows else 0
        self._data = array("d", itertools.chain.from_iterable(rows))

    def __len__(self) -> int:
        return self._rows

    def __getitem__(self, s: int) -> array:
        if not -self._rows <= s < self._rows:
            raise IndexError(s)
        s %= self._rows
        return self._data[s * self._width : (s + 1) * self._width]

    def tolist(self) -> list[list[float]]:
        return [self[s].tolist() for s in range(self._rows)]


def load_kit(kit_dir: Path) -> tuple[dict, list[dict]]:
    complete = json.loads((kit_dir / "complete.json").read_text())
    for name, expected in complete["files"].items():
        if _sha256(kit_dir / name) != expected:
            raise estimate.KitError(f"{name} differs from the kit's record")
    record = json.loads((kit_dir / "kit.json").read_text())
    connection = duckdb.connect()
    try:
        result = connection.execute(
            "SELECT building, level, bedroom_slope, fslope FROM read_parquet(?)",
            [str(kit_dir / "buildings.parquet")],
        )
        # Each building's draws go into flat float arrays a batch at a time:
        # as Python lists the 67,735 buildings of an all-scraped kit took
        # several GB.
        buildings = []
        while batch := result.fetchmany(KIT_BATCH_ROWS):
            buildings.extend(
                {
                    "building": b,
                    "level": array("d", lv),
                    "bedroom_slope": array("d", bs),
                    "fslope": Draws(fs),
                }
                for b, lv, bs, fs in batch
            )
    finally:
        connection.close()
    return record, buildings


def load_units(kit_dir: Path, only=None) -> dict[str, list[float]]:
    """The fit's level of each unit it has seen, over the kit's draws
    (`units.parquet`, hashed in complete.json), or of the units in `only`;
    empty for a kit built before the file (#380)."""
    path = kit_dir / "units.parquet"
    if not path.exists():
        return {}
    complete = json.loads((kit_dir / "complete.json").read_text())
    if _sha256(path) != complete["files"].get("units.parquet"):
        raise estimate.KitError("units.parquet differs from the kit's record")
    connection = duckdb.connect()
    try:
        if only is None:
            result = connection.execute(
                "SELECT unit, level FROM read_parquet(?)", [str(path)]
            )
        else:
            result = connection.execute(
                "SELECT unit, level FROM read_parquet(?) WHERE unit IN "
                "(SELECT unnest(?))",
                [str(path), sorted(only)],
            )
        return {u: [float(v) for v in lv] for u, lv in result.fetchall()}
    finally:
        connection.close()


def _date(text: str | None, period: str) -> dt.date:
    if text:
        try:
            return dt.datetime.fromisoformat(text).astimezone(dt.UTC).date()
        except ValueError:
            pass
    return dt.date.fromisoformat(period[:10]).replace(day=15)


def check_scoring(
    kit: estimate.Kit, buildings: dict, listings: list[dict], likely=None
) -> dict:
    """Score SCORE_ROWS of the fit's own rows with the kit and compare with the
    bundle's median and 80% range. `likely(audit_id)` gives the range of a row
    whose bundle has range atoms in its place (detail.Ranges.likely_ask)."""

    def checked(r):
        if r["pred_lower_80"] is not None or likely is None:
            return r
        found = likely(r["audit_id"])
        return None if found is None else {**r, **found}

    candidates = (
        checked(r)
        for r in listings
        if r["period"][:7] == kit.period[:7]
        and r["in_fit"]
        and r["unit_fit_rows"] == 1
        and r["pareto_k"] is not None
        and r["pareto_k"] < 0.5
        and r["building_id"] in buildings
    )
    rows = list(
        itertools.islice(
            (r for r in candidates if r is not None and r["pred_lower_80"] is not None),
            SCORE_ROWS,
        )
    )
    if len(rows) < SCORE_MIN_ROWS:
        return {
            "passes": False,
            "rows": len(rows),
            "reason": f"only {len(rows)} rows of {kit.period[:7]} to check against",
        }
    ratios = {"median": [], "pred_lower_80": [], "pred_upper_80": []}
    for r in rows:
        x = json.loads(r["inputs"])
        got = estimate.score(
            kit,
            buildings[r["building_id"]],
            x,
            round(r["bedrooms"]) if r["bedrooms"] is not None else 1,
            _date(r["price_at"], r["period"]),
            seed=r["audit_id"],
            samples=SCORE_SAMPLES,
        )
        ratios["median"].append(got["median"] / r["estimate_median"] - 1)
        ratios["pred_lower_80"].append(got["pred_lower_80"] / r["pred_lower_80"] - 1)
        ratios["pred_upper_80"].append(got["pred_upper_80"] / r["pred_upper_80"] - 1)
    medians = {k: statistics.median(v) for k, v in ratios.items()}
    passes = all(abs(v) <= SCORE_TOLERANCE for v in medians.values())
    out = {"passes": passes, "rows": len(rows), "median_difference": medians}
    if not passes:
        out["reason"] = "the kit's estimates differ from the bundle's"
    return out


def form_from_observation(obs: dict) -> estimate.Form:
    """The form a listing's own recorded fields would fill in."""
    label = (obs.get("canonical_unit_url") or "").rsplit("/", 1)[-1].upper()
    flags = {
        "penthouse": r"^PH|PENTHOUSE",
        "garden": r"GARDEN|GDN|^GF$|^GRDN|^GARD",
        "lower_level": r"BSMT|BASEMENT|^LL|LOWER|^CELLAR",
    }
    half = obs.get("reported_half_bathrooms")
    floor = obs.get("listed_floor")
    return estimate.Form(
        bedrooms=round(min(max(obs.get("bedrooms") or 0, 0), 5)),
        full_baths=int(min(max(obs.get("reported_full_bathrooms") or 1, 1), 4)),
        half_baths="unknown"
        if half is None
        else ("2" if half >= 2 else str(int(half))),
        square_feet=obs.get("square_feet"),
        floor=int(floor) if floor is not None and floor >= 1 else None,
        laundry=obs.get("laundry_type") or "unknown",
        label=next((k for k, p in flags.items() if re.search(p, label)), ""),
        views=[k for k, v in (obs.get("view_exposures") or {}).items() if v],
        windows=[k for k, v in (obs.get("window_exposures") or {}).items() if v],
    )


def check_encoding(kit: estimate.Kit, listings: list[dict], observations: dict) -> dict:
    group_of = dict(zip(kit.features, kit.groups))
    agree = {g: 0 for g in ENCODE_GROUPS if g in set(kit.groups)}
    counted = {g: 0 for g in agree}
    per_unit = Counter(r["unit_id"] for r in listings)
    for r in listings:
        if per_unit[r["unit_id"]] != 1:
            continue
        obs = observations.get(r["audit_id"])
        if obs is None:
            continue
        x = json.loads(r["inputs"])
        got = estimate.encode(form_from_observation(obs), kit, x)
        for g in agree:
            if g == "floor" and obs.get("listed_floor") is None:
                continue  # the model may take the floor from the unit's label
            if g == "size" and not _plain_size(obs):
                continue
            names = [n for n, gg in group_of.items() if gg == g and n not in SKIP]
            counted[g] += 1
            if all(abs(got.get(n, 0.0) - x.get(n, 0.0)) <= 1e-3 for n in names):
                agree[g] += 1
    shares = {g: agree[g] / counted[g] for g in agree if counted[g]}
    passes = all(v >= ENCODE_AGREEMENT for v in shares.values())
    out = {
        "passes": passes,
        "listings": max(counted.values(), default=0),
        "agreement": shares,
    }
    if not passes:
        out["reason"] = "the form's encoder disagrees with the model's inputs"
    return out


# Columns the form fixes rather than asks (a new apartment's own values).
SKIP = {"bedrooms_vs_unit"}


def _plain_size(obs: dict) -> bool:
    sqft = obs.get("square_feet")
    return sqft is None or estimate.SQFT_RANGE[0] <= sqft <= estimate.SQFT_RANGE[1]


def install(
    db, kit_dir: Path | None, listings: list[dict], observations: dict, likely=None
) -> dict:
    """Check the kit and, when it passes, write the kit tables. Returns the
    form's status for build.json: {available, reason?, kit?, checks}.
    `likely` is as in `check_scoring`."""
    db.executescript(SCHEMA)
    if kit_dir is None:
        return {"available": False, "reason": "no prediction kit for this run"}
    try:
        record, rows = load_kit(kit_dir)
    except (OSError, ValueError, KeyError, estimate.KitError, duckdb.Error) as error:
        return {
            "available": False,
            "reason": f"unreadable kit: {error}",
            "kit": str(kit_dir),
        }
    medians = estimate.sqft_medians(
        (r["bedrooms"], r["square_feet"], r["inputs"]) for r in listings
    )
    kit = estimate.Kit.from_record(record, medians)
    status = {"kit": str(kit_dir), "period": kit.period}
    unknown = kit.unknown_groups()
    if unknown:
        return status | {
            "available": False,
            "reason": "inputs the form does not know: " + ", ".join(unknown),
        }
    buildings = {
        b["building"]: estimate.Building(
            b["level"], b["bedroom_slope"], b["fslope"], {}
        )
        for b in rows
    }
    checks = {
        "scoring": check_scoring(kit, buildings, listings, likely),
        "encoding": check_encoding(kit, listings, observations),
    }
    status["checks"] = checks
    failed = [c["reason"] for c in checks.values() if not c["passes"]]
    if failed:
        return status | {"available": False, "reason": "; ".join(failed)}
    db.executemany(
        "INSERT INTO kit VALUES (?,?)",
        [
            ("record", json.dumps(record, separators=(",", ":"))),
            ("sqft_median", json.dumps(medians)),
        ],
    )
    db.executemany(
        "INSERT INTO kit_buildings VALUES (?,?,?,?)",
        (
            (
                b["building"],
                json.dumps(b["level"].tolist()),
                json.dumps(b["bedroom_slope"].tolist()),
                json.dumps(b["fslope"].tolist()),
            )
            for b in rows
        ),
    )
    return status | {"available": True}


def available(db) -> bool:
    try:
        return (
            db.execute("SELECT 1 FROM kit WHERE key = 'record'").fetchone() is not None
        )
    except sqlite3.OperationalError:
        return False


def read(db) -> tuple[estimate.Kit | None, str | None]:
    """The build's kit, or None with the reason the form is unavailable."""
    try:
        values = dict(db.execute("SELECT key, value FROM kit"))
    except sqlite3.OperationalError:  # an older build has no kit table
        return None, "this build has no prediction kit"
    if "record" not in values:
        return None, None
    return estimate.Kit.from_record(
        json.loads(values["record"]), json.loads(values["sqft_median"])
    ), None


def building(db, building_id: str) -> estimate.Building | None:
    row = db.execute(
        "SELECT level, bedroom_slope, fslope FROM kit_buildings WHERE building_id = ?",
        (building_id,),
    ).fetchone()
    newest = db.execute(
        "SELECT inputs FROM listings WHERE building_id = ? ORDER BY period DESC, id DESC LIMIT 1",
        (building_id,),
    ).fetchone()
    if row is None or newest is None:
        return None
    return estimate.Building(
        json.loads(row[0]),
        json.loads(row[1]),
        json.loads(row[2]),
        json.loads(newest[0]),
    )

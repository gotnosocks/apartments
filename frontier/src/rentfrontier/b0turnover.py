"""Write a B0 dataset with each row's count of its building's recent ads of other units, and its
lot's residential units in the MapPLUTO release out when the row's ad was priced.

    python -m rentfrontier.b0turnover SRC OUT

Screen S13 (`docs/notes/turnover-screen-2026-11-13.md`) found that j9, the backtest of the ads
on the market on 2025-11-10, prices too low the held-out ads in buildings whose other units
rarely come up for rent, and too high those in buildings whose units turn over often. The
screen counted each held-out ad's building's other ads in the two years before it and divided
by the lot's residential units in a single 2026 release. This script writes the two parts of
that rate as columns for every row, with the units read as of the row's price month.

For each row the script takes

1. its opening day, the ad's `on_day` in the ads file the SRC build read, or the UTC day of its
   price_at when that comes first, as `b0amenitycarry.opening_days` dates it;
2. its unit, the (building, unit_id) pair, with a row lacking a unit_id as a unit of its own;
3. `bld_opened_730`: the count of SRC's rows in the same building, of other units, opened in
   the `WINDOW_DAYS` days before the row's price day, from the price day less `WINDOW_DAYS` up
   to the day before the price day. Every row counts, training and held-out alike: the count
   reads opening days, never a rent, so a held-out ad's ask reaches no other row;
4. `res_units_asof`: `unitsres` of the building's lot (its BBL in the registry
   `building_attrs` reads) in the latest release of the all-lots release file published at
   least `features.PLUTO_RELEASE_BUFFER_DAYS` days before the first day of the month of the
   row's price_at, the release `b0coop` reads for the row's class. A release published later
   is never read, and neither is 22v2, which carries no publication date. The column is
   missing when the building has no lot, the row was priced before the first usable release,
   the lot is missing from its release, or the release leaves `unitsres` blank. A release's
   zero stays zero.

The rate, the count over two years and over the units, is left to a model.

OUT gets:

- `rows.parquet`: SRC's rows in SRC's order, with `bld_opened_730` (int32) and
  `res_units_asof` (float64) added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `turnover` entry giving SRC's
  path and rows SHA-256, the ads, registry and release files with their SHA-256, the rules,
  the rows read from each release, and counts of both columns.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .b0amenitycarry import opening_days, read_on_days
from .b0coop import RELEASES, months
from .b0data import sha256
from .building_attrs import REGISTRY
from .building_zones_kitchen_sink import days
from .features import PLUTO_RELEASE_BUFFER_DAYS

WINDOW_DAYS = 730
COUNT = f"bld_opened_{WINDOW_DAYS}"
UNITS = "res_units_asof"
# Why a row's units are missing, in the order the checks run.
STATUSES = ("read", "no lot", "no release", "lot not in release", "no units")


def unit_keys(frame: pd.DataFrame) -> np.ndarray:
    """Each row's unit: building and unit_id, or the row's own listing when it has no
    unit_id."""
    none = frame.unit_id.isna().to_numpy()
    unit = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    row = "row:" + frame.listing_id.astype(str)
    return np.where(none, row.to_numpy(object), unit.to_numpy(object))


def window_counts(
    keys: np.ndarray, opened: np.ndarray, q_keys: np.ndarray, q_day: np.ndarray
) -> np.ndarray:
    """For each query, the rows of `keys` with its key opened from `q_day - WINDOW_DAYS` up to
    the day before `q_day`."""
    codes, _ = pd.factorize(pd.Series(np.r_[keys, q_keys]).astype(str))
    ca, cq = codes[: len(keys)].astype(np.int64), codes[len(keys) :].astype(np.int64)
    # Days shifted to start at 0, and spaced so that one key's days never reach the next's.
    base = min(int(opened.min()), int(q_day.min()) - WINDOW_DAYS)
    span = max(int(opened.max()), int(q_day.max())) - base + 1
    on = ca * span + (opened.astype(np.int64) - base)
    day = cq * span + (q_day.astype(np.int64) - base)
    on.sort()
    hi = np.searchsorted(on, day, side="left")
    lo = np.searchsorted(on, day - WINDOW_DAYS, side="left")
    return hi - lo


def other_ads(frame: pd.DataFrame, opened: np.ndarray) -> np.ndarray:
    """Each row's count of its building's rows of other units opened in the `WINDOW_DAYS`
    days before its price day."""
    price_day = days(frame.price_at)
    building = frame.building.astype(str).to_numpy(object)
    units = unit_keys(frame)
    every = window_counts(building, opened, building, price_day)
    own = window_counts(units, opened, units, price_day)
    return every - own


def read_units(path: Path, bbls: set[str]) -> pd.DataFrame:
    """The release, BBL, residential units and publication date of each lot in `bbls` in every
    release of the file `path`."""
    t = pq.read_table(path, columns=["release", "bbl", "unitsres", "published"])
    t = t.filter(pc.is_in(t["bbl"], value_set=pa.array(sorted(bbls), t["bbl"].type)))
    return t.to_pandas()


def units_asof(
    frame: pd.DataFrame, lots: pd.Series, releases: pd.DataFrame
) -> pd.DataFrame:
    """For each row of `frame` (`building`, `price_at`): `bbl`, its building's lot in `lots`
    (BBL by building); `release`, the release it reads; `units`, the lot's `unitsres` in that
    release, NaN where there is none; and `status`, the reason for a NaN (`STATUSES`)."""
    dated = releases.dropna(subset=["published"])
    published = pd.to_datetime(
        dated.drop_duplicates("release").set_index("release").published
    ).sort_values()
    usable = (published + pd.Timedelta(days=PLUTO_RELEASE_BUFFER_DAYS)).to_numpy()
    order = np.searchsorted(usable, months(frame.price_at), side="right") - 1
    # A blank release or lot matches no line of the table.
    release = np.where(
        order >= 0, published.index.to_numpy(dtype=object)[np.maximum(order, 0)], ""
    )
    bbl = frame.building.astype(str).map(lots).fillna("").to_numpy(dtype=object)
    keys = pd.MultiIndex.from_arrays([release, bbl])
    # Rows share few (release, lot) pairs, so each pair is looked up once.
    pair, pairs = keys.factorize()
    table = dated.assign(bbl=dated.bbl.astype(str)).set_index(["release", "bbl"])
    found = pairs.isin(table.index)[pair]
    units = pd.to_numeric(table.unitsres, errors="coerce").reindex(pairs)
    units = units.to_numpy(dtype=float)[pair]
    status = np.select(
        [bbl == "", release == "", ~found, np.isnan(units)],
        list(STATUSES[1:]),
        STATUSES[0],
    )
    return pd.DataFrame(
        {
            "bbl": pd.Series(bbl, dtype=object).replace("", None),
            "release": pd.Series(release, dtype=object).replace("", None),
            "units": np.where(status == STATUSES[0], units, np.nan),
            "status": status,
        }
    )


def registry_lots(registry: Path, buildings: pd.Series) -> pd.Series:
    """The lot (BBL) of each building in `buildings` that the registry gives one, keeping a
    building's first listed lot as `building_attrs.nyc_lots` does."""
    reg = pd.read_parquet(registry, columns=["building", "bbl"])
    lots = reg.dropna(subset=["bbl"]).drop_duplicates("building")
    lots = lots.set_index(lots.building.astype(str)).bbl.astype(str)
    return lots[lots.index.isin(buildings.astype(str).unique())]


def turnover(
    src: Path, out: Path, registry: Path = REGISTRY, release_file: Path = RELEASES
) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    ads = manifest["build"]["ads"]
    ads_file = Path(ads["path"])
    if sha256(ads_file) != ads["sha256"]:
        raise SystemExit(f"{ads_file} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    opened = opening_days(
        frame, read_on_days(ads_file, set(frame.listing_id.astype(str)))
    )
    count = other_ads(frame, opened)
    lots = registry_lots(registry, frame.building)
    lot = units_asof(frame, lots, read_units(release_file, set(lots)))
    frame[COUNT] = count.astype(np.int32)
    frame[UNITS] = lot.units.to_numpy(float)
    # OUT is made after every read, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    units = lot.units.to_numpy(float)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "turnover": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "ads": {"path": str(ads_file), "sha256": sha256(ads_file)},
            "registry": {"path": str(registry), "sha256": sha256(registry)},
            "releases": {"path": str(release_file), "sha256": sha256(release_file)},
            "rule": {
                COUNT: "the dataset's rows (training and held-out alike) in the row's "
                "building, less those of its unit (building and unit_id, or the row "
                f"alone without a unit_id), opened from {WINDOW_DAYS} days before the "
                "row's price_at UTC day up to the day before it, where a row opens on the "
                "ads file's on_day or its price_at UTC day when that comes first; reads "
                "opening days only, never a rent",
                UNITS: "unitsres of the building's lot in the latest MapPLUTO release "
                f"published at least {PLUTO_RELEASE_BUFFER_DAYS} days before the first "
                "day of the month of the row's price_at (releases without a publication "
                "date are never read); missing where the row reads no units",
            },
            "window_days": WINDOW_DAYS,
            "buffer_days": PLUTO_RELEASE_BUFFER_DAYS,
            "rows": len(frame),
            "rows_by_status": {s: int((lot.status == s).sum()) for s in STATUSES},
            "releases_read": {
                str(r): int(n)
                for r, n in lot.release.dropna().value_counts().sort_index().items()
            },
            "rows_count_zero": int((count == 0).sum()),
            "count_quantiles": {
                str(q): float(np.quantile(count, q)) for q in (0.25, 0.5, 0.75, 0.9)
            },
            "rows_units_zero": int((units == 0).sum()),
            "units_median": float(np.nanmedian(units)) if len(units) else None,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(turnover(args.src, args.out)["turnover"], indent=2))


if __name__ == "__main__":
    main()

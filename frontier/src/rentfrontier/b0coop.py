"""Write a B0 dataset with columns marking the rows in co-op and condo buildings, each read
from the MapPLUTO release out when the row's ad was priced.

    python -m rentfrontier.b0coop SRC OUT

Part C of S5 in the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that co-op
and condo ads ask 1% to 4% more than j9 expects at every count of training ads. j9 and L1 read
a condo flag (`bld:condo`) and no co-op flag. Their designs take a building's tenure from
`building_zones_floor_asof.load_lots`, through `building_attrs.nyc_lots(REGISTRY, PLUTO)`,
which sorts the lot's class in MapPLUTO's 26v2 release (published 2026-08-17) for every row,
so an ad priced in 2015 reads a class from 2026. This script adds a
co-op column, and a condo column built the same way, both from the release a row could have
read when its ad was priced.

For each row I take

1. the building's lot (BBL) from the registry that `building_attrs` reads;
2. the latest release in the all-lots release file published at least
   `features.PLUTO_RELEASE_BUFFER_DAYS` days before the first day of the month of the row's
   price_at, as the plutoasof feature sets date a listing (`features.released_lots`);
3. the lot's class in that release, sorted as `building_attrs.attributes` sorts it:

       condo   a class starting with R
       coop    C6, C8, D0 or D4 (`building_attrs.COOP_CLASSES`)

I never read a release published later than that, and I never read 22v2, which carries no
publication date. A row gets false in both columns when its building has no lot in the
registry, when it was priced before the first usable release, or when its lot is missing from
its release or has no class there.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with the boolean columns `coop` and `condo` added;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and a `coop` entry giving SRC's path
  and rows SHA-256, the registry and release files with their SHA-256, the rule, and the rows,
  units and buildings marked.

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

from .b0data import sha256
from .building_attrs import COOP_CLASSES, REGISTRY
from .features import LOTS4_FILES, PLUTO_RELEASE_BUFFER_DAYS

RELEASES = Path(LOTS4_FILES["plutoreleases"])
# Why a row reads no line of the release out at its price month, in the order the checks run.
MISSING = ("no lot", "no release", "lot not in release")
# Why a row's class is blank, in the order the checks run.
STATUSES = ("read", *MISSING, "no class")


def months(price_at: pd.Series) -> np.ndarray:
    """The first day of the month of each price_at, in UTC, as tz-naive datetime64. The
    pipeline writes the same day as a row's `period`."""
    at = pd.DatetimeIndex(pd.to_datetime(price_at, utc=True)).tz_convert(None)
    return at.to_period("M").to_timestamp().to_numpy()


def registry_lots(registry: Path, buildings: pd.Series) -> pd.Series:
    """The lot (BBL) of each building in `buildings` that the registry gives one, keeping a
    building's first listed lot as `building_attrs.nyc_lots` does."""
    reg = pd.read_parquet(registry, columns=["building", "bbl"])
    lots = reg.dropna(subset=["bbl"]).drop_duplicates("building")
    lots = lots.set_index(lots.building.astype(str)).bbl.astype(str)
    return lots[lots.index.isin(buildings.astype(str).unique())]


def read_releases(
    path: Path, bbls: set[str], column: str = "bldgclass"
) -> pd.DataFrame:
    """The release, BBL, `column` and publication date of each lot in `bbls` in every release
    of the file `path`."""
    t = pq.read_table(path, columns=["release", "bbl", column, "published"])
    t = t.filter(pc.is_in(t["bbl"], value_set=pa.array(sorted(bbls), t["bbl"].type)))
    return t.to_pandas()


def as_of(
    frame: pd.DataFrame, lots: pd.Series, releases: pd.DataFrame, column: str
) -> pd.DataFrame:
    """Look up each row's lot in the release out at the row's price month.

    For each row of `frame` (`building`, `price_at`) the result gives

    - `bbl`: the building's lot in `lots` (BBL by building), blank without one;
    - `release`: the latest release in `releases` (as `read_releases` reads them) published
      at least `PLUTO_RELEASE_BUFFER_DAYS` days before the first day of the row's price
      month, blank when no release is that old. A release without a publication date is
      skipped;
    - `found`: whether that release lists the lot;
    - `column`: the lot's value in that release as the file gives it, missing where the
      release doesn't list the lot.
    """
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
    value = table[column].reindex(pairs).to_numpy(dtype=object)[pair]
    return pd.DataFrame(
        {
            "bbl": pd.Series(bbl, dtype=object),
            "release": pd.Series(release, dtype=object),
            "found": pairs.isin(table.index)[pair],
            column: pd.Series(value, dtype=object),
        }
    )


def status(lot: pd.DataFrame, blank: np.ndarray, statuses: tuple) -> np.ndarray:
    """Each row's status for its lookup `lot` from `as_of`: the first of `MISSING` that
    applies, then `statuses[-1]` where `blank` holds, and `statuses[0]` otherwise."""
    return np.select(
        [lot.bbl == "", lot.release == "", ~lot.found, blank],
        list(statuses[1:]),
        statuses[0],
    )


def classes(
    frame: pd.DataFrame, lots: pd.Series, releases: pd.DataFrame
) -> pd.DataFrame:
    """For each row of `frame` (`building`, `price_at`): `bbl`, its building's lot in `lots`
    (BBL by building); `release`, the release it reads; `bldgclass`, the lot's class in that
    release, blank where there is none; and `status`, the reason for a blank (`STATUSES`)."""
    lot = as_of(frame, lots, releases, "bldgclass")
    cls = lot.bldgclass.fillna("").astype(str).str.strip().to_numpy(dtype=object)
    reason = status(lot, cls == "", STATUSES)
    return pd.DataFrame(
        {
            "bbl": lot.bbl.replace("", None),
            "release": lot.release.replace("", None),
            "bldgclass": np.where(reason == STATUSES[0], cls, ""),
            "status": reason,
        }
    )


def tenure(cls: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Whether each MapPLUTO class marks a condo and whether it marks a co-op, as
    `building_attrs.attributes` sorts them: R first, then `COOP_CLASSES`."""
    c = pd.Series(cls, dtype=object).fillna("").astype(str)
    condo = c.str.startswith("R").to_numpy()
    coop = c.isin(COOP_CLASSES).to_numpy() & ~condo
    return condo, coop


def coop(
    src: Path, out: Path, registry: Path = REGISTRY, release_file: Path = RELEASES
) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    lots = registry_lots(registry, frame.building)
    lot = classes(frame, lots, read_releases(release_file, set(lots)))
    condo, co = tenure(lot.bldgclass.to_numpy())
    frame["coop"] = co
    frame["condo"] = condo
    # OUT is made after every read, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    unit = frame.unit_id.notna().to_numpy()
    units = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "coop": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "registry": {"path": str(registry), "sha256": sha256(registry)},
            "releases": {"path": str(release_file), "sha256": sha256(release_file)},
            "rule": "the building's lot class in the latest MapPLUTO release published "
            f"at least {PLUTO_RELEASE_BUFFER_DAYS} days before the first day of the month "
            "of the row's price_at (releases without a publication date are never read); "
            "condo for a class starting with R, coop for "
            + ", ".join(COOP_CLASSES)
            + ", as building_attrs sorts tenure; false where the row reads no class",
            "coop_classes": list(COOP_CLASSES),
            "buffer_days": PLUTO_RELEASE_BUFFER_DAYS,
            "rows_by_status": {s: int((lot.status == s).sum()) for s in STATUSES},
            "releases_read": {
                str(r): int(n)
                for r, n in lot.release.dropna().value_counts().sort_index().items()
            },
            "rows_coop": int(co.sum()),
            "units_coop": int(units[co & unit].nunique()),
            "buildings_coop": int(frame.building[co].nunique()),
            "rows_condo": int(condo.sum()),
            "units_condo": int(units[condo & unit].nunique()),
            "buildings_condo": int(frame.building[condo].nunique()),
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
    print(json.dumps(coop(args.src, args.out)["coop"], indent=2))


if __name__ == "__main__":
    main()

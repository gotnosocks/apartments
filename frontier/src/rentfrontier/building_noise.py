"""Each building's rate of outdoor noise complaints nearby, as a snapshot.

I ask NYC 311 (erm2-nwe9, which starts in 2020) for the outdoor noise complaints of each year
from FIRST_YEAR to LAST_YEAR, counted by the point they were geocoded to, a month per query. Socrata does the counting,
so I fetch about 100,000 rows a year instead of every complaint. The outdoor types are:

    Noise - Street/Sidewalk, Noise - Commercial, Noise - Vehicle   (NYPD)
    Noise                                                          (DEP: construction, jackhammers,
                                                                    alarms, air conditioners)

I leave out residential noise (neighbors), helicopters (geocoded to the caller, not the
source), parks and houses of worship. For every NYC registry building with a point I then sum
the complaints within RADIUS_M and divide by the number of years:

    noise_per_year   outdoor noise complaints a year within RADIUS_M

A count of complaints also measures how willing the neighbors are to call 311, which goes up
with rents. I accept that for this snapshot and read the fit's coefficient with it in mind.

    python -m rentfrontier.building_noise OUT_DIR
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import building_parks, external
from .registry import EXTERNAL_ROOT

DATASET = "erm2-nwe9"
TYPES = ("Noise - Street/Sidewalk", "Noise - Commercial", "Noise - Vehicle", "Noise")
FIRST_YEAR, LAST_YEAR = 2020, 2025
RADIUS_M = 150.0
PAGE = 50_000
REGISTRY = EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet"


def fetch_month(year: int, month: int) -> tuple[pd.DataFrame, list[str]]:
    """The month's outdoor noise complaints, counted by latitude and longitude."""
    kinds = ", ".join(f"'{t}'" for t in TYPES)
    start = pd.Timestamp(year, month, 1)
    end = start + pd.offsets.MonthBegin()
    where = (
        f"created_date >= '{start:%Y-%m-%dT00:00:00}' and "
        f"created_date < '{end:%Y-%m-%dT00:00:00}' and "
        f"complaint_type in ({kinds}) and latitude is not null"
    )
    rows, queries, offset = [], [], 0
    while True:
        params = {
            "$select": "latitude, longitude, count(*) as n",
            "$where": where,
            "$group": "latitude, longitude",
            "$order": "latitude, longitude",
            "$limit": PAGE,
            "$offset": offset,
        }
        q = urllib.parse.urlencode(params)
        with external._urlopen(
            f"{external.SOCRATA}/{DATASET}.json?{q}", timeout=600
        ) as r:
            got = json.loads(r.read())
        rows += got
        queries.append(f"{DATASET}?{q}")
        if len(got) < PAGE:
            break
        offset += PAGE
    t = pd.DataFrame(rows, columns=["latitude", "longitude", "n"]).astype(float)
    t["year"] = year
    return t, queries


def table(buildings: pd.DataFrame, points: pd.DataFrame, years: int) -> pd.DataFrame:
    """noise_per_year for each building with a point."""
    b = buildings.dropna(subset=["latitude", "longitude"]).drop_duplicates("building")
    homes = building_parks.metres(b.longitude, b.latitude)
    at = building_parks.metres(points.longitude, points.latitude)
    near = cKDTree(at).query_ball_point(homes, RADIUS_M)
    n = points.n.to_numpy(float)
    total = np.array([n[i].sum() for i in near])
    return pd.DataFrame(
        {"building": b.building.astype(str).to_numpy(), "noise_per_year": total / years}
    )


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    parts, queries = [], []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        for month in range(1, 13):
            t, q = fetch_month(year, month)
            parts.append(t)
            queries += q
        print(
            f"{year}: {int(sum(p.n.sum() for p in parts[-12:]))} complaints", flush=True
        )
    points = (
        pd.concat(parts, ignore_index=True)
        .groupby(["latitude", "longitude", "year"], as_index=False)
        .n.sum()
    )
    years = LAST_YEAR - FIRST_YEAR + 1
    b = pd.read_parquet(REGISTRY, columns=["building", "latitude", "longitude"])
    t = table(b, points, years)
    a.out.mkdir(parents=True, exist_ok=False)
    t.to_parquet(a.out / "noise.parquet")
    points.to_parquet(a.out / "points.parquet")
    (a.out / "provenance.json").write_text(
        json.dumps(
            {
                "source": f"{external.SOCRATA}/{DATASET}",
                "version": external._version(DATASET),
                "types": list(TYPES),
                "years": [FIRST_YEAR, LAST_YEAR],
                "radius_m": RADIUS_M,
                "registry": str(REGISTRY),
                "points": len(points),
                "complaints": int(points.n.sum()),
                "buildings": len(t),
                "queries": queries,
            },
            indent=2,
            default=str,
        )
    )
    print(
        f"{len(t)} buildings; noise_per_year median {t.noise_per_year.median():.1f}, "
        f"90th pct {t.noise_per_year.quantile(0.9):.1f}; wrote {a.out}"
    )


if __name__ == "__main__":
    main()

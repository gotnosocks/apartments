"""Unit size, laundry and dishwasher for every listing, and the through truck route each
building fronts.

I write two tables for `rentfrontier.building_zones_unit` into a snapshot directory,
EXTERNAL_ROOT/unit-features/<date>-<sha>/. `unit_features.parquet` has one row per listing of
the pipeline rows:

1. `sqft` and `size_source`. I take the ad's stated size first, keeping 100 to 10,000 sq ft.
   Where the ad states none, I fill it in two layers, as in
   `docs/notes/size-coverage-2026-10-21.md`:
   - `unit`: the median stated size over every listing of the same unit, from any date. A
     unit is its building plus the label from the ad's URL, upper-cased, with punctuation and
     an APT, UNIT or NO prefix removed.
   - `line`: the median, over the other units on the same line of the building with the same
     bedroom count, of each unit's median. The line is the letter of a label like 4B or B4,
     or the last two digits of a label like 412. I skip penthouse, garden, parlor and
     basement labels and the building's top two floors, where setbacks change the plan.
   `size_source` is `none` where neither layer has a size.
2. `log_size_rel`, the log of `sqft` over the median stated size for the listing's bedroom
   count (4 or more pooled), clipped to plus or minus log 2.5. It is 0 where the size is
   unknown.
3. `laundry`: `in_unit`, `in_building` or `unstated`, from the pipeline's `laundry_type`.
   StreetEasy has no code for a unit with no laundry, so the reference is unstated.
4. `dishwasher`: 1 where the listing's latest raw record lists the DISHWASHER feature.

`truck.parquet` has one row per registry building, with
`truck_through` set where the building faces an NYC DOT through truck route. I put the
routes in the frontage code's street points at a 30 ft width, so a building faces a route
within 15 ft plus REACH_M of its outline.

    python -m rentfrontier.unit_features OUT_DIR
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .registry import EXTERNAL_ROOT

ROWS = Path("/data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet")
RECORDS = Path("/data1/apartments/pipeline/datasets/records-086e22e48969b098.parquet")
TRUCK_ROUTES = EXTERNAL_ROOT / "truckroutes" / "raw" / "truck.geojson"
SQFT_RANGE = (100.0, 10_000.0)
CLIP = float(np.log(2.5))
SPECIAL = re.compile(
    r"PH|PENT|GARDEN|GDN|PARLOR|BSMT|BASEMENT|CELLAR|LOWER|^GF?$|^LL\d*$"
)


def unit_label(page: pd.Series) -> pd.Series:
    """The unit label at the end of each ad URL, upper-cased, with punctuation and an APT,
    UNIT or NO prefix removed."""
    lab = page.astype(str).str.extract(r"/([^/?#]+)/?$")[0].str.upper().fillna("")
    lab = lab.str.replace(r"^(APT|UNIT|NO)[-_.]?", "", regex=True)
    return lab.str.replace(r"[^0-9A-Z]", "", regex=True)


def floor_and_line(label: str) -> tuple[float, str | None]:
    """The floor and line of a label: 4B and B4 are floor 4 on line B, 412 is floor 4 on
    line 12. Any other label has neither."""
    m = re.fullmatch(r"(\d{1,2})([A-Z]{1,2})", label)
    if m:
        return float(m.group(1)), "L" + m.group(2)
    m = re.fullmatch(r"(\d{1,2})(\d{2})", label)
    if m:
        return float(m.group(1)), "D" + m.group(2)
    m = re.fullmatch(r"([A-Z]{1,2})(\d{1,2})", label)
    if m:
        return float(m.group(2)), "L" + m.group(1)
    return np.nan, None


def sizes(rows: pd.DataFrame) -> pd.DataFrame:
    """`sqft`, `size_source` and `log_size_rel` for each of `rows`' listings. `rows` needs
    listing_id, building, page, bedrooms, square_feet and building_floor_count."""
    r = rows.drop_duplicates("listing_id").reset_index(drop=True)
    lo, hi = SQFT_RANGE
    sq = r.square_feet.where((r.square_feet >= lo) & (r.square_feet <= hi))
    lab = unit_label(r.page)
    parsed = {s: floor_and_line(s) for s in lab.unique()}
    floor = lab.map(lambda s: parsed[s][0]).astype(float)
    line = lab.map(lambda s: parsed[s][1])
    top = (floor >= r.building_floor_count - 1).fillna(False)
    special = lab.str.contains(SPECIAL)
    building = r.building.astype(str)
    unit = pd.Series(np.where(lab != "", building + "|" + lab, None), index=r.index)
    beds = r.bedrooms.clip(upper=4)
    on_line = line.notna() & ~special & ~top & (lab != "")
    key = pd.Series(
        np.where(
            on_line, building + "|" + line.astype(str) + "|" + beds.astype(str), None
        ),
        index=r.index,
    )
    by_unit = sq[unit.notna()].groupby(unit[unit.notna()]).median()
    unit_sq = unit.map(by_unit)
    units = pd.DataFrame({"key": key, "unit": unit, "sq": unit_sq}).dropna()
    units = units.drop_duplicates("unit")
    by_line = units.groupby("key").sq.median()
    line_sq = key.map(by_line)
    out = sq.fillna(unit_sq).fillna(line_sq)
    source = np.select(
        [sq.notna(), unit_sq.notna(), line_sq.notna()],
        ["stated", "unit", "line"],
        "none",
    )
    med = sq.groupby(beds).median()
    rel = np.log(out / beds.map(med)).clip(-CLIP, CLIP).fillna(0.0)
    return pd.DataFrame(
        {
            "listing_id": r.listing_id.astype(str),
            "sqft": out,
            "size_source": source,
            "log_size_rel": rel,
        }
    )


def laundry(rows: pd.DataFrame) -> pd.Series:
    """Each listing's laundry level: in_unit, in_building or unstated."""
    t = rows.drop_duplicates("listing_id").laundry_type.astype("string")
    return t.where(t.isin(["in_unit", "in_building"]), "unstated").astype(str)


def dishwashers(records: Path = RECORDS) -> pd.Series:
    """1.0 for each listing whose latest raw record lists the DISHWASHER feature, by
    listing_id."""
    import pyarrow.parquet as pq

    f = pq.ParquetFile(records)
    latest: dict[str, tuple] = {}
    for i in range(f.num_row_groups):
        t = f.read_row_group(
            i, columns=["listing_id", "collected_at", "raw_listing_json"]
        ).to_pandas()
        for lid, at, raw in zip(
            t.listing_id.astype(str), t.collected_at, t.raw_listing_json
        ):
            if lid in latest and latest[lid][0] >= at:
                continue
            try:
                j = json.loads(raw)
            except (TypeError, ValueError):
                continue
            feats = ((j.get("propertyDetails") or {}).get("features") or {}).get("list")
            latest[lid] = (at, "DISHWASHER" in (feats or []))
    return pd.Series({k: float(v[1]) for k, v in latest.items()}, name="dishwasher")


def unit_table(rows: pd.DataFrame, dishwasher: pd.Series) -> pd.DataFrame:
    """The unit-features table of `rows`, with `dishwasher` by listing_id."""
    out = sizes(rows)
    out["laundry"] = laundry(rows).to_numpy()
    out["dishwasher"] = out.listing_id.map(dishwasher).fillna(0.0).to_numpy()
    return out


def truck_through(registry, footprints, pluto, routes: dict) -> pd.DataFrame:
    """`truck_through` for each registry building, from the truck routes GeoJSON."""
    from . import frontage as fr

    parts = []
    for k, feat in enumerate(routes["features"]):
        geo, p = feat["geometry"], feat["properties"]
        if geo is None or not str(p.get("routetype", "")).lower().startswith("thr"):
            continue
        lines = (
            geo["coordinates"]
            if geo["type"] == "MultiLineString"
            else [geo["coordinates"]]
        )
        for ln in lines:
            ln = np.asarray(ln, float)
            P, U = fr.densify(fr.metres(ln[:, 0], ln[:, 1]), fr.STREET_STEP_M)
            if len(P):
                parts.append(
                    pd.DataFrame(
                        {"x": P[:, 0], "y": P[:, 1], "ux": U[:, 0], "uy": U[:, 1]}
                    ).assign(width=30.0, name=p.get("street", ""), road=k)
                )
    t = fr.frontage(registry, footprints, pd.concat(parts, ignore_index=True), pluto)
    return pd.DataFrame(
        {
            "building": t.building.astype(str),
            "truck_through": t.front_width_ft.notna().astype(float),
        }
    )


def main(argv=None) -> None:
    """Write both snapshots: OUT_DIR/unit_features.parquet and OUT_DIR/truck.parquet."""
    from . import frontage as fr

    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    rows = pd.read_parquet(
        ROWS,
        columns=[
            "listing_id",
            "building",
            "page",
            "bedrooms",
            "square_feet",
            "building_floor_count",
            "laundry_type",
        ],
    )
    unit_table(rows, dishwashers()).to_parquet(out / "unit_features.parquet")
    registry = pd.read_parquet(fr.REGISTRY, columns=["building", "bbl", "bin"])
    footprints = pd.read_parquet(fr.FOOTPRINTS, columns=["bin", "geometry"])
    pluto = pd.read_parquet(fr.PLUTO, columns=["bbl", "lottype"])
    routes = json.loads(TRUCK_ROUTES.read_text())
    truck_through(registry, footprints, pluto, routes).to_parquet(out / "truck.parquet")


if __name__ == "__main__":
    main()

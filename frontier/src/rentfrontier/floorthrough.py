"""Floor-through apartments (windows at the front and the back, the whole depth
of the building), one row per apartment for the site, and the building-shape
terms `features.through_v1` (nb3-through-v1) adds to the rent model.

Ads say "floor-through" for 2.7% of apartments, and far more often where the
building's shape leaves room for one apartment per floor (2026-10-06, 43,035
apartments, unit-labels-v5):

- MapPLUTO residential units per floor (`units_per_floor`): 14% of apartments
  with at most one per floor, 13% up to 1.5, 6% up to 2, 1% above 3;
- every apartment label in the building a plain floor ("2", "PH", "3rd-floor";
  `PLAIN_LABEL`): 15%, against 1.2% where none is;
- a narrow lot (at most 22 ft of frontage): 12%, against 1% above 60 ft.
- its own listings show both a street and the rear (`exposure` "both"): 29%.

Ads under-report, so these are lower bounds on how often such apartments are
floor-throughs. Labels describe the evidence: "stated" (an ad says so), "whole
floor" (at most `WHOLE_FLOOR` units per floor, or a building of plain-floor
labels), "front and rear" (its own windows or ad show both a street and the
rear), "" otherwise. A current snapshot, pooled over every listing like
`exposure`.

    python -m rentfrontier.floorthrough      # writes WISHES/floor-through-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, exposure, features

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-lineface-v1"
THROUGH_TEXT = r"floor[- ]?thr(?:ough|u)\b"
PLAIN_LABEL = r"\d{1,2}|PH|GARDEN|PARLOR|\d+(?:ST|ND|RD|TH)-FLOOR|FLOOR-?\d+"
WHOLE_FLOOR = 1.5


def units_per_floor(frame: pd.DataFrame) -> np.ndarray:
    """Per row: its lot's MapPLUTO residential units over floors (NaN when
    either is missing or zero)."""
    lots = features.building_lots(frame)
    units = pd.to_numeric(lots.unitsres, errors="coerce").to_numpy()
    floors = pd.to_numeric(lots.numfloors, errors="coerce").to_numpy()
    ok = (units > 0) & (floors > 0)
    return np.where(ok, units / np.where(ok, floors, 1.0), np.nan)


def plain_labels(frame: pd.DataFrame) -> np.ndarray:
    """Per row: whether every apartment label seen in its building names a
    floor only (one apartment per floor)."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.upper()
    plain = label.fillna("").str.fullmatch(PLAIN_LABEL)
    return plain.groupby(frame.building.to_numpy()).transform("all").to_numpy()


def label(stated: bool, whole: bool, both: bool) -> str:
    if stated:
        return "stated"
    if whole:
        return "whole floor"
    return "front and rear" if both else ""


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    text = descriptions.attach(frame).fillna("").str.lower()
    phrase = text.str.extract(f"({THROUGH_TEXT})")[0]
    lots = features.building_lots(frame)
    rows = pd.DataFrame(
        {
            "unit_id": frame.unit_id.to_numpy(),
            "phrase": phrase.to_numpy(),
            "upf": units_per_floor(frame),
            "plain": plain_labels(frame),
            "front_ft": pd.to_numeric(lots.lotfront, errors="coerce").to_numpy(),
            "floor": pd.to_numeric(frame.listed_floor, errors="coerce").to_numpy(),
        }
    )
    units = rows.groupby("unit_id").agg(
        phrase=("phrase", "first"),
        upf=("upf", "median"),
        plain=("plain", "all"),
        front_ft=("front_ft", "median"),
        floor=("floor", "median"),
    )
    labels = exposure.compute(frame).set_index("unit_id")
    units = units.join(labels[["building", "url", "exposure", "source"]])
    out = []
    for u in units.itertuples():
        stated = isinstance(u.phrase, str)
        whole = bool(u.upf <= WHOLE_FLOOR) or bool(u.plain)
        both = u.exposure == "both" and u.source == "own"
        why = []
        if stated:
            why.append(f'ad says "{u.phrase}"')
        if not np.isnan(u.upf):
            why.append(f"{u.upf:.1f} units per floor (MapPLUTO)")
        if u.plain:
            why.append("every label in the building is a floor")
        if both:
            why.append("its own listings show a street and the rear")
        if not np.isnan(u.front_ft):
            why.append(f"lot frontage {u.front_ft:.0f} ft")
        out.append(
            {
                "unit_id": u.Index,
                "building": u.building,
                "url": u.url,
                "floor_through": label(stated, whole, both),
                "units_per_floor": round(u.upf, 2) if not np.isnan(u.upf) else np.nan,
                "plain_labels": bool(u.plain),
                "front_ft": u.front_ft,
                "exposure": u.exposure,
                "floor": u.floor,
                "evidence": "; ".join(why),
            }
        )
    return pd.DataFrame(out)


def build(frame: pd.DataFrame) -> pd.DataFrame:
    """`compute` with FEATURE_SET's lot, area and description files."""
    lots = features.lot_files(FEATURE_SET)
    area = features.area_files(FEATURE_SET)
    tokens = (
        (features._LOTS, features._LOTS.set((lots["registry"], lots["pluto"]))),
        (features._AREA, features._AREA.set((area["basemap"], area["footprints"]))),
        (
            descriptions.SOURCES,
            descriptions.SOURCES.set(
                tuple(Path(p) for p in features.description_files(FEATURE_SET).values())
            ),
        ),
    )
    try:
        return compute(frame)
    finally:
        for var, token in tokens:
            var.reset(token)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--rules", nargs="*", default=["unit-labels-v5"])
    parser.add_argument("--out", type=Path, default=WISHES)
    args = parser.parse_args(argv)
    frame = data.load()
    frame, _ = data.apply_rules(frame, np.zeros(len(frame), dtype=bool), args.rules)
    table = build(frame)
    args.out.mkdir(parents=True, exist_ok=True)
    base = args.out / f"floor-through-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(table)} apartments)")
    print(table.floor_through.value_counts().to_string())
    stated = table.floor_through.eq("stated")
    print(
        "stated among exposure both (own):",
        round(stated[table.exposure.eq("both")].mean(), 3),
    )


if __name__ == "__main__":
    main()

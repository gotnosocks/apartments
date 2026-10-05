"""Which way each apartment faces, for the site: the rear or a courtyard (usually
quieter), the street, or both, one row per apartment.

A current snapshot, pooled over every listing including the latest: a label to
show, not a model input (the model's as-of version is `features.lineface_v1`).
Sources, in order:

- own: the apartment's own listings (`features.unit_sides`: windows against the
  building's sides, F/R labels, ad text, views);
- line: no evidence of its own, but at least `features.LINE_AGREEMENT` of the
  other apartments of its line (`data.unit_line_key`) that show a side agree
  (89% agreement with apartments' own evidence, leave-one-unit-out, 2026-10-05);
- bedroom: separately, an ad that says which way the bedroom faces.

    python -m rentfrontier.exposure            # writes EXPOSURE/labels-<date>.parquet
                                               # and points labels.parquet at it
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, features

EXPOSURE = Path("/data1/apartments/exposure")
# The feature set whose lot, area and description files the labels read.
FEATURE_SET = "nb-lineface-v1"
LABELS = {(True, False): "street", (False, True): "rear", (True, True): "both"}
_REAR = r"(?:garden|courtyard|rear|back of the building|backyard|quiet)"
_STREET = r"(?:street|avenue|ave\b|front of the building)"
_LOOKS = r"(?:fac\w*|overlook\w*|view\w* of|look\w* (?:out )?(?:on|over))"
BEDROOM_REAR = (
    rf"bedrooms?\b[^.]{{0,40}}\b{_LOOKS}[^.]{{0,25}}{_REAR}"
    rf"|{_REAR}[^.]{{0,15}}-?facing bedroom"
    r"|quiet (?:rear |back )?bedroom"
)
BEDROOM_STREET = rf"bedrooms?\b[^.]{{0,40}}\b{_LOOKS}[^.]{{0,25}}{_STREET}"


def line_labels(unit_line: pd.Series, own: pd.Series) -> pd.DataFrame:
    """Per apartment (index): the label its line's other apartments agree on
    ("" when they don't, or none show a side) and how many of them vote."""
    voters = pd.DataFrame({"line": unit_line, "own": own})
    voters = voters[voters.line.notna() & voters.own.ne("")]
    counts = voters.groupby("line").own.value_counts().unstack(fill_value=0)
    counts = counts.reindex(columns=["street", "rear", "both"], fill_value=0)
    mine = counts.reindex(unit_line.to_numpy()).fillna(0).to_numpy().copy()
    for j, lab in enumerate(counts.columns):
        # An apartment never votes for itself (and one with no line never voted).
        mine[:, j] -= (own.eq(lab) & unit_line.notna()).to_numpy()
    total = mine.sum(axis=1)
    top = mine.argmax(axis=1)
    agree = (total > 0) & (mine.max(axis=1) >= features.LINE_AGREEMENT * total)
    label = np.where(agree, counts.columns.to_numpy()[top], "")
    return pd.DataFrame(
        {"line_label": label, "line_votes": total.astype(int)}, index=own.index
    )


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    sides = features.unit_sides(frame)
    street = sides[["avenue", "wide street", "side street"]].any(axis=1).to_numpy()
    rear = sides["none"].to_numpy()
    text = descriptions.attach(frame).fillna("").str.lower()
    rows = pd.DataFrame(
        {
            "unit_id": frame.unit_id.to_numpy(),
            "building": frame.building.to_numpy(),
            "url": frame.canonical_unit_url.to_numpy(),
            "line": data.unit_line_key(frame).to_numpy(),
            "own": [LABELS.get((s, r), "") for s, r in zip(street, rear)],
            "avenue": sides["avenue"].to_numpy(),
            "wide street": sides["wide street"].to_numpy(),
            "side street": sides["side street"].to_numpy(),
            "bed_rear": text.str.contains(BEDROOM_REAR, regex=True).to_numpy(),
            "bed_street": text.str.contains(BEDROOM_STREET, regex=True).to_numpy(),
            "at": pd.to_datetime(frame.price_at, utc=True).to_numpy(),
        }
    ).sort_values(["unit_id", "at"])
    units = rows.groupby("unit_id").agg(
        building=("building", "last"),
        url=("url", "last"),
        line=("line", "last"),
        own=("own", "first"),
        avenue=("avenue", "first"),
        wide=("wide street", "first"),
        side=("side street", "first"),
        bed_rear=("bed_rear", "any"),
        bed_street=("bed_street", "any"),
        listings=("own", "size"),
    )
    units = units.join(line_labels(units.line, units.own))
    has_own = units.own.ne("")
    units["exposure"] = np.where(has_own, units.own, units.line_label)
    units["source"] = np.where(
        has_own, "own", np.where(units.line_label.ne(""), "line", "")
    )
    kinds = units[["avenue", "wide", "side"]].to_numpy()
    names = np.array(["avenue", "wide street", "side street"])
    units["street_kind"] = [", ".join(names[k]) for k in kinds]
    units["bedroom"] = np.select(
        [units.bed_rear & ~units.bed_street, units.bed_street & ~units.bed_rear],
        ["rear", "street"],
        "",
    )
    cols = ["building", "url", "exposure", "source", "street_kind", "line"]
    cols += ["line_votes", "bedroom", "listings"]
    return units[cols].reset_index()


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
    parser.add_argument("--rules", nargs="*", default=["unit-labels-v3"])
    parser.add_argument("--out", type=Path, default=EXPOSURE)
    args = parser.parse_args(argv)
    frame = data.load()
    frame, _ = data.apply_rules(frame, np.zeros(len(frame), dtype=bool), args.rules)
    labels = build(frame)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"labels-{dt.date.today():%Y%m%d}.parquet"
    labels.to_parquet(path.with_suffix(".tmp"))
    os.replace(path.with_suffix(".tmp"), path)
    link = args.out / "labels.parquet"
    tmp_link = args.out / "labels.parquet.tmp"
    tmp_link.unlink(missing_ok=True)
    tmp_link.symlink_to(path.name)
    os.replace(tmp_link, link)
    print(f"wrote {path} ({len(labels)} apartments)")
    print(labels.source.value_counts().to_string())


if __name__ == "__main__":
    main()

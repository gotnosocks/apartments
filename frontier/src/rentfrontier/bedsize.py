"""Bed sizes from ad text: the largest bed a listing's own advertisement says
its bedroom (or a studio's sleeping area) takes, "full", "queen" or "king"
(twins and doubles count as "full"), by rule; the terms `features.bedsize_v1`
(nb3-bedsize-v1) add to the rent model, and one row per apartment for the
site.

A listing states a size when its ad says the room fits one ("fits a king
bed", "room for a queen-sized bed", "accommodates a full mattress"; with
"king or queen" the larger) or names the room by a king or queen ("king-size
bedroom": a "full-size bedroom" is only a real bedroom). Each row reads
only its own ad, so nothing travels from later listings of the apartment, and
the text adds these fields without overriding any coded one.

The 2026-10-06 photo pilot checked the rule against floor plans: on the 11
apartments with both, the stated bed never exceeded the largest that fits the
plan's bedroom with 24 inches of clearance on one long side and at the foot.
Ads stating a size: Chelsea 16%, West Village 24%, Greenwich Village 23%.

    python -m rentfrontier.bedsize      # writes WISHES/bed-size-<date>.parquet and .csv
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, features

WISHES = Path("/data1/apartments/wishes")
FEATURE_SET = "nb3-bedsize-v1"
SIZES = ("full", "queen", "king")
_SIZE = r"\b(?:california king|cal king|king|queen|full|double|twin)"
_ROOM_SIZE = r"\b(?:california king|cal king|king|queen)"
_SIZED = r"(?:[- ]?size[d]?)?"
# "fits a king or queen bed": every size named in the phrase counts. A room
# named by size counts for king and queen only: "full-size bedroom" means a
# real bedroom, not one that takes a full bed.
BED_TEXT = re.compile(
    r"\b(?:fits?|fitting|accommodates?|accommodating|room for|space for|holds?|"
    r"enough for)\s+(?:(?:a|an|your|up ?to|even)\s+)*(?:\w+[- ]?){0,2}?"
    + _SIZE
    + r"(?:"
    + _SIZED
    + r"\s*(?:/|or|and|,)\s*"
    + _SIZE
    + r")*"
    + _SIZED
    + r"(?:\s*(?:bed|mattress)\b)?"
    + r"|"
    + _ROOM_SIZE
    + _SIZED
    + r"\s*(?:bed)?room"
)
_BED = re.compile(r"\b(?:bed|mattress)\b")
_WORD = re.compile(r"\b(king|queen|full|double|twin)\b")
_RANK = {"twin": 0, "double": 0, "full": 0, "queen": 1, "king": 2}


def stated_size(text: str) -> str | None:
    """The largest bed size the (lower-cased) text states, or None."""
    best = -1
    for m in BED_TEXT.finditer(text):
        span = m.group(0)
        bed = _BED.search(span) is not None
        for word in _WORD.findall(span):
            # "fits a full kitchen": full, double and twin need the word bed.
            if bed or word in ("king", "queen"):
                best = max(best, _RANK[word])
    return SIZES[best] if best >= 0 else None


def stated_sizes(frame: pd.DataFrame) -> pd.Series:
    """Per row: the bed size its own ad states (None when it states none or
    has no text)."""
    return descriptions.attach(frame).map(stated_size)


def apartments(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per apartment that any of its ads states a size for: the
    largest stated, how many of its listings state one, and its latest ad's."""
    size = stated_sizes(frame)
    rows = frame.assign(size=size).loc[size.notna()].sort_values("period")
    rank = rows["size"].map(SIZES.index)
    return (
        rows.assign(rank=rank)
        .groupby("unit_id")
        .agg(
            building=("building", "first"),
            largest=("rank", "max"),
            listings=("rank", "size"),
            latest=("size", "last"),
        )
        .assign(largest=lambda t: t.largest.map(lambda r: SIZES[r]))
        .reset_index()
    )


def build(frame: pd.DataFrame) -> pd.DataFrame:
    """`apartments` with FEATURE_SET's description files."""
    token = descriptions.SOURCES.set(
        tuple(Path(p) for p in features.description_files(FEATURE_SET).values())
    )
    try:
        return apartments(frame)
    finally:
        descriptions.SOURCES.reset(token)


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
    base = args.out / f"bed-size-{dt.datetime.now(dt.UTC):%Y%m%d}"
    table.to_parquet(f"{base}.parquet")
    table.to_csv(f"{base}.csv", index=False)
    print(f"wrote {base}.parquet ({len(table)} apartments)")
    print(table.largest.value_counts().to_string())


if __name__ == "__main__":
    main()

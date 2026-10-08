"""The items inside two grouped feature tests, one by one, on the served fit's rows.

    python -m rentfrontier.groupitems RUN --out group-items.json

The ledger tests the 15 ad attributes (`features.ATTRIBUTE_FLAGS`,
nb3-attrs-v1) and the six walk-to places (`nearby.KINDS`, nb3-nearby-v1) each
as one group. For each item this records how common it is among the run's
rows (after its data rules) and a raw rent difference: the slope of log ask
on the item with only bedrooms and price basis held fixed, no other feature.
For an ad attribute that is the gap between ads that state it and ads that do
not; for a place it is per doubling of the walk. These are not model effects.
The site's research story reads the file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, descriptions, features, nearby

NEAR_M = 400.0


def raw_slope(x: np.ndarray, frame: pd.DataFrame) -> float | None:
    """Percent change in ask per unit of `x`, within bedroom count (4 and more
    pooled) and price basis (both demeaned in each cell); None where `x` does
    not vary within any cell."""
    cell = frame.bedrooms.clip(upper=4).astype(str) + "/" + frame.price_basis
    xs = pd.Series(x, index=frame.index, dtype=float)
    y = frame.log_rent
    xt = xs - xs.groupby(cell).transform("mean")
    yt = y - y.groupby(cell).transform("mean")
    spread = float((xt * xt).sum())
    if spread <= 1e-12:
        return None
    slope = float((xt * yt).sum()) / spread
    return round(100 * (np.exp(slope) - 1), 1)


def attributes(frame: pd.DataFrame) -> tuple[list[dict], int]:
    text = descriptions.attach(frame)
    known = (text.str.len() > 20).to_numpy()
    rows = frame[known]
    out = []
    for name, pattern in features.ATTRIBUTE_FLAGS.items():
        flag = text[known].str.contains(pattern, regex=True).to_numpy()
        out.append(
            {
                "item": name,
                "rows": int(flag.sum()),
                "share": round(float(flag.mean()), 4),
                "raw_pct": raw_slope(flag.astype(float), rows),
            }
        )
    return out, int(known.sum())


def places(frame: pd.DataFrame) -> list[dict]:
    walks = {k: np.exp(v) for k, v in nearby.terms(frame).items()}
    out = []
    for kind, words in nearby.KINDS.items():
        m = walks[kind]
        ok = ~np.isnan(m)
        out.append(
            {
                "item": kind,
                "words": words,
                "rows": int(ok.sum()),
                "median_m": int(round(float(np.median(m[ok])), -1)),
                "near_share": round(float((m[ok] <= NEAR_M).mean()), 4),
                "raw_pct_per_doubling": raw_slope(np.log2(m[ok]), frame[ok]),
            }
        )
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", help="a run name under the runs directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    record = json.loads(
        (data.OUTPUT_ROOT / "runs" / args.run / "result.json").read_text()
    )
    frame = data.load(Path(record["dataset"]))
    frame, _ = data.apply_rules(
        frame, np.zeros(len(frame), dtype=bool), data.recorded_rules(record)
    )
    name = record["feature_set"]
    lots = features.lot_files(name)
    lot_token = features._LOTS.set((lots["registry"], lots["pluto"]))
    text_token = descriptions.SOURCES.set(
        tuple(Path(p) for p in features.description_files(name).values())
    )
    try:
        attrs, with_text = attributes(frame)
        walk = places(frame)
    finally:
        features._LOTS.reset(lot_token)
        descriptions.SOURCES.reset(text_token)
    doc = {
        "run": args.run,
        "dataset": Path(record["dataset"]).name,
        "rows": int(len(frame)),
        "rows_with_text": with_text,
        "near_m": NEAR_M,
        "attributes": attrs,
        "places": walk,
    }
    args.out.write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    main()

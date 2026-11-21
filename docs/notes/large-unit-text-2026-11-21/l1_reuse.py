"""Large units (3 or more bedrooms) in the Nov 18 image read: how many, by group and pool."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deals-photos-2026-11-18"))
import pandas as pd
from pilot import OUT, reads
from score import traits

r = reads("haiku")
blind = pd.read_parquet(OUT / "blind.parquet")
draw = pd.read_parquet(OUT / "draw.parquet")
print(draw.columns.tolist())
x = (
    r.reset_index()
    .merge(blind, on="label")
    .merge(draw, on=[c for c in blind.columns if c != "label" and c in draw.columns])
)
print(len(x), x.columns.tolist()[:40])
big = x[x.bedrooms >= 3]
print(big.groupby([c for c in ["pool", "group"] if c in big.columns]).size())
t = traits(big)
print(
    t.groupby(big["group"] if "group" in big else big.iloc[:, 0])
    .mean()
    .round(3)
    .T.to_string()
)

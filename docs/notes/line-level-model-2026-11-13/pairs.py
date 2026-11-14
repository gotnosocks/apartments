"""Half the mean squared difference of two training ads of the sample's buildings, taken in
the same building and quarter, by how the two ads relate.

The script builds L1's design on the latest split's training rows of the 1-in-90 sample of
buildings from Y1's timing, takes the fixed columns' coefficients from the second half of a
short L1 run on the same rows (`beta-l1-150.npy`, 2 chains of 150 warmup and 150 draws), and
subtracts the fixed part from each ad's log ask. Two ads of a building in the same quarter
share the building's level and nearly all of its path. Under LN1 half their squared
difference holds:

- the noise, for two ads of a unit;
- the noise, plus the unit's lasting level and its drift, for two units of a line;
- all of those plus line_sd^2, for two lines.

The script prints each class's count of pairs and its half mean squared difference, over all
pairs and with each building's mean weighted equally, the same in the units' first ads
alone, and the buildings' means split by the building's count of units. It runs from the
worktree's root on the CPU."""

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import (  # noqa: E402
    building_zones_floor_asof,
    drift_building_phase,
    drift_line,
    splits,
)

D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"
BETA = "/data1/apartments/tmp/line-level-20261113/beta-l1-150.npy"

frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.load(open(D + "/manifest.json"))["rows_sha256"]
building_zones_floor_asof.SPLIT = "latest"
held = np.asarray(splits.SPLITS["latest"](frame))
full = drift_building_phase.design(frame)
train = drift_building_phase.subset(full, ~held)
beta = np.load(BETA)
beta = beta[:, beta.shape[1] // 2 :].mean(axis=(0, 1))
names = list(train.names)
beta[names.index("alpha")] = 0.0
r = np.asarray(train.y) - np.asarray(train.x) @ beta

line, _ = drift_line.line_index(frame, held)
unit = pd.factorize(drift_line.unit_keys(frame))[0]
day = pd.to_datetime(frame.latest_day)
t = pd.DataFrame(
    {
        "b": frame.building.astype(str).to_numpy(),
        "q": ((day - day.min()).dt.days // 91).to_numpy(),
        "line": np.asarray(line),
        "unit": unit,
        "day": day.to_numpy(),
    }
)[~held].reset_index(drop=True)
assert len(t) == len(r), (len(t), len(r))
t["r"] = r


def halves(rows, per_building=False):
    """Each class's count of pairs and half mean squared difference, over all pairs, or
    with each building's mean for the class weighted equally (`per_building`)."""
    sums = {}
    for (b, _), g in rows.groupby(["b", "q"]):
        if len(g) < 2:
            continue
        g = g.head(60)
        for (_, x), (_, z) in combinations(g.iterrows(), 2):
            k = "unit" if x.unit == z.unit else "line" if x.line == z.line else "other"
            cell = sums.setdefault((b if per_building else "", k), [0, 0.0])
            cell[0] += 1
            cell[1] += (x.r - z.r) ** 2 / 2
    out = {}
    for k in ("unit", "line", "other"):
        got = [(n, s / n) for (_, kk), (n, s) in sums.items() if kk == k]
        if got:
            out[k] = (
                sum(n for n, _ in got),
                round(float(np.mean([m for _, m in got])), 5),
            )
    return out


print("rows", len(t), "residual sd", round(float(t.r.std()), 4))
first = t.sort_values("day").groupby("unit").head(1)
for label, rows in (("all ads", t), ("first ads", first)):
    print(label, "by pair", halves(rows))
    print(label, "by building", halves(rows, per_building=True))
# The same by the building's count of units with training ads.
size = t.groupby("b").unit.nunique()
t["size"] = pd.cut(size.reindex(t.b).to_numpy(), [0, 8, 40, 10**6])
for k, rows in t.groupby("size", observed=True):
    print("units", k, "buildings", rows.b.nunique(), "by building", halves(rows, True))

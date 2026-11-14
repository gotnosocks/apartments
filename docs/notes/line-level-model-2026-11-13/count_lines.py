"""Counts of the lines `drift_line.line_index` gives L1's dataset under the latest split.

The script reads the columns the lines and the split need from the dataset's rows, numbers
each row's line, and prints the training lines per building, the training units per line,
the (line, quarter) pairs and pairs of pairs of the collapsed step, and the held-out rows by
the case `drift_line`'s prediction takes for them."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import drift_line, splits  # noqa: E402

D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
COLS = [
    "building",
    "unit_id",
    "bedrooms",
    "full_baths",
    "latest_day",
    "price_at",
    "audit_id",
]

frame = pd.read_parquet(D + "/rows.parquet", columns=COLS)
held = splits.SPLITS["latest"](frame)
train = ~held
line, lines = drift_line.line_index(frame, held)
key = drift_line.unit_keys(frame)
unit = pd.factorize(key)[0]
building = pd.factorize(frame.building.astype(str))[0]

print("rows", len(frame), "training", int(train.sum()), "held out", int(held.sum()))
print("training lines", lines)
tl, tb, tu = line[train], building[train], unit[train]
per_bld = pd.Series(tl).groupby(tb).nunique()
q = [0.5, 0.75, 0.9, 0.99, 1.0]
print("buildings with training rows", len(per_bld))
print(
    "lines per building: mean", round(per_bld.mean(), 2), per_bld.quantile(q).tolist()
)
units_per_line = pd.Series(tu).groupby(tl).nunique()
print(
    "units per line: mean",
    round(units_per_line.mean(), 2),
    units_per_line.quantile(q).tolist(),
)
one = units_per_line.eq(1)
print("lines with one unit", int(one.sum()), round(one.mean(), 3))
rows_in_one = np.isin(tl, units_per_line.index[one].to_numpy())
print("training rows in lines of one unit", round(rows_in_one.mean(), 3))
units_per_bld = pd.Series(tu).groupby(tb).nunique()
print("units per building: mean", round(units_per_bld.mean(), 2))

# The collapsed step's quarters, counted from the first row's day as `drift.groups_of`
# counts the buildings' quarters from the design's start.
day = pd.to_datetime(frame.latest_day)
step = np.floor((day - day.min()).dt.days.to_numpy() / 365.25 * 4).astype(np.int64)
ts = step[train]
pair = pd.DataFrame({"line": tl, "step": ts}).drop_duplicates()
n_k = pair.groupby("line").size()
print("(line, quarter) pairs", len(pair), "pairs of pairs", int((n_k**2).sum()))
cells = pd.DataFrame({"b": tb, "step": ts}).drop_duplicates()
print("(building, quarter) cells", len(cells))

# Each held-out row's case at prediction.
seen_unit = np.zeros(unit.max() + 1, bool)
seen_unit[tu] = True
hu, hl = unit[held], line[held]
known_unit = seen_unit[hu]
known_line = hl >= 0
print("held-out rows of a unit with training rows", int(known_unit.sum()))
print(
    "held-out rows of a new unit in a known line", int((~known_unit & known_line).sum())
)
print("held-out rows of a new line", int((~known_line).sum()))
other = pd.Series(tu).groupby(tl).nunique()
many = np.zeros(lines, bool)
many[other.index.to_numpy()] = other.to_numpy() >= 2
print(
    "held-out rows of a unit with training rows, in a line of two or more units",
    int((known_unit & known_line & many[np.maximum(hl, 0)]).sum()),
)

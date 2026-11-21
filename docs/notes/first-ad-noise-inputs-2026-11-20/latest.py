"""Count the latest split's held-out ads whose unit has no training ad.

Usage: latest.py RUN_DIR.
"""

import json
import sys

import numpy as np
import pandas as pd

run = sys.argv[1]
dataset = json.load(open(run + "/result.json"))["dataset"]
f = pd.read_parquet(dataset + "/rows.parquet", columns=["unit_id"])
held = np.load(run + "/posterior.npz")["heldout"]
train = set(f.unit_id[~held].dropna())
print(run.rsplit("/", 1)[-1])
print("held-out ads", int(held.sum()))
print("with no unit id", int(f.unit_id[held].isna().sum()))
print("with a unit that has no training ad", int((~f.unit_id[held].isin(train)).sum()))

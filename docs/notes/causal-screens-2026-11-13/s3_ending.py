"""S3: does the previous ad's ending still move the next ask once L1 knows the months since
that ad?

For each held-out ad the script takes the unit's previous ad in the dataset and its row of the
per-ad process table built from the raw status and price histories
(`/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet`). The ending counts only where
its status change is dated before the held-out ad opened; otherwise the ending is unknown.
Then the script moves each held-out ad by the cross-fitted mean gap of its cell and rescores L1's
predictive, for cells of phase alone (a level per phase, the TODO's L2) and of phase by
ending, by the previous ad's price path and by both."""

import json

import numpy as np
import pandas as pd

import common as c

PHASES = ["10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+"]
d = c.rows()
d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
d["prev_id"] = np.where(same, d.listing_id.shift(), None)
d["prev_at"] = d.priced.shift().where(same)
d = d.sort_index()
h = c.heldout(d)
dr = c.Draws()
h["phase"] = np.array(PHASES)[dr.ph]

p = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
    columns=[
        "listing_id",
        "end_st",
        "t_on",
        "t_off",
        "run_days",
        "n_cut",
        "p0",
        "p1",
        "pmax",
    ],
).drop_duplicates("listing_id")
p["t_on"] = p.t_on.dt.tz_convert(None)
p["t_off"] = p.t_off.dt.tz_convert(None)
cur = p[["listing_id", "t_on"]].rename(columns={"t_on": "cur_on"})
prv = p.rename(columns={c_: "prev_" + c_ for c_ in p.columns if c_ != "listing_id"})
h = h.merge(cur, on="listing_id", how="left")
h = h.merge(prv.rename(columns={"listing_id": "prev_id"}), on="prev_id", how="left")
assert len(h) == len(dr.ph)
opens = h.cur_on.fillna(h.priced).where(h.cur_on.fillna(h.priced) < h.priced, h.priced)
known = h.prev_t_off.notna() & (h.prev_t_off < opens)
END = {
    "RENTED": "deal",
    "IN_CONTRACT": "deal",
    "NO_LONGER_AVAILABLE": "nla",
    "DELISTED": "delisted",
    "TEMPORARILY_OFF_MARKET": "paused",
}
h["ending"] = np.where(known, h.prev_end_st.map(END).fillna("other"), "unknown")
h.loc[h.prev_id.isna(), "ending"] = "first"
raised = h.prev_pmax > h.prev_p0 * 1.001
cut5 = h.prev_p1 < h.prev_p0 * 0.95
known_path = h.prev_p0.notna() & known
h["path"] = np.where(
    ~known_path, "unknown", np.where(raised, "raised", np.where(cut5, "cut5", "flat"))
)
off = (opens - h.prev_t_off).dt.days
h["off"] = np.where(
    ~known,
    "unknown",
    np.where(
        off <= 30,
        "<=30",
        np.where(off <= 90, "31-90", np.where(off <= 365, "91-365", ">365")),
    ),
)
print(pd.crosstab(h.phase, h.ending).to_string(), flush=True)
print(pd.crosstab(h.ending, h.path).to_string(), flush=True)

gap = h.gap.to_numpy()
fold = h.fold.to_numpy()
sub = c.subfold(h.building)


idx = np.arange(len(h))
b = h.building.to_numpy()
res = {"n": len(h), "cells": {}}
designs = {
    "phase": h.phase,
    "phase_x_ending": h.phase + "|" + h.ending,
    "phase_x_path": h.phase + "|" + h.path,
    "phase_x_ending_x_path": h.phase + "|" + h.ending + "|" + h.path,
    "phase_x_ending_x_off": h.phase + "|" + h.ending + "|" + h.off,
}
gains = {}
for name, key in designs.items():
    dl, k = c.crossfit_shift(gap, key.to_numpy(), fold, sub)
    e = dr.gain(idx, delta=dl)
    gains[name] = e
    r = {
        "k": k,
        "elpd_gain": float(e.sum()),
        "se": c.cluster_se(e, b),
        "sd_shift": float(dl.std()),
    }
    if name != "phase":
        inc = e - gains["phase"]
        r["over_phase"] = float(inc.sum())
        r["over_phase_se"] = c.cluster_se(inc, b)
    res["cells"][name] = r
    print(name, json.dumps(r), flush=True)

# mean gap and coverage by phase and ending, with clustered SEs of the mean
tab = []
for (ph, en), g in h.groupby(["phase", "ending"]):
    if len(g) < 200:
        continue
    tab.append(
        {
            "phase": ph,
            "ending": en,
            "n": len(g),
            "gap": float(g.gap.mean()),
            "se": c.cluster_se(g.gap.to_numpy(), g.building.to_numpy()) / len(g),
            "cov80": float(g.in80.mean()),
        }
    )
res["table"] = tab
pd.DataFrame(tab).to_csv(c.OUT + "s3_table.csv", index=False)
tab2 = []
for (ph, en, pa), g in h.groupby(["phase", "ending", "path"]):
    if len(g) < 200 or pa == "unknown":
        continue
    tab2.append(
        {
            "phase": ph,
            "ending": en,
            "path": pa,
            "n": len(g),
            "gap": float(g.gap.mean()),
            "se": c.cluster_se(g.gap.to_numpy(), g.building.to_numpy()) / len(g),
            "cov80": float(g.in80.mean()),
        }
    )
pd.DataFrame(tab2).to_csv(c.OUT + "s3_table_path.csv", index=False)
h[["listing_id", "phase", "ending", "path", "off"]].to_parquet(
    c.OUT + "s3_cells.parquet"
)
json.dump(res, open(c.OUT + "s3.json", "w"), indent=1)

"""S6: do stabilized apartments follow the Rent Guidelines Board rather than the market
between two of their ads?

L1 carries a unit from its previous ad to the next by the citywide walk L(t), the same for
every unit. For each held-out ad with an earlier ad of its unit the script takes the walk's change
between the two latest-ask days (from the kept draws, interpolated as in `rentfrontier.b0`)
and the guideline change for one-year leases over the same span. Then the script regresses the gap on
both, for three groups of units:

1. stabilized by the ad's own text flag (`flag:rent_stabilized`);
2. in a lot where DOF's tax bills list stabilized units for at least half of PLUTO's
   residential units in the ad's year, without the text flag;
3. in a lot with no stabilized units on any bill from 2007 to 2024, without the flag.

A slope of b on the walk's change means the units move with 1 + b of the market; L1 assumes 1.
The tax-bill counts come from `/data1/apartments/tmp/suspect/opendata/` (2007 to 2017 in
`tb_joined.csv`, 2018 to 2024 in `rs2024.csv`)."""

import json

import numpy as np
import pandas as pd

import common as c

# one-year lease guidelines by the October that starts each guideline year (Orders 45 to 57);
# Order 53's 0% for six months then 1.5% counts as 0.75%. From October 2026 on, no order is
# applied.
RGB = {
    2013: 0.04,
    2014: 0.01,
    2015: 0.0,
    2016: 0.0,
    2017: 0.0125,
    2018: 0.015,
    2019: 0.015,
    2020: 0.0,
    2021: 0.0075,
    2022: 0.0325,
    2023: 0.03,
    2024: 0.0275,
    2025: 0.03,
}


def rgb_index(day):
    """Cumulative log guideline by date: each October's rate, spread over the following
    twelve months as leases renew."""
    t = pd.to_datetime(day)
    y = t.dt.year + (t.dt.month - 10) / 12.0  # years since the October of `year`
    out = np.zeros(len(t))
    for yr, r in RGB.items():
        out += np.log1p(r) * np.clip(y.to_numpy() - yr, 0, 1)
    return out


d = c.rows()
d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
d["prev_day"] = d.day.shift().where(same)
d["prev_stab"] = d.rent_stabilized.shift().where(same)
d = d.sort_index()
h = c.heldout(d)
h = h[h.prev_day.notna()].copy()
print("held-out ads with an earlier ad", len(h), flush=True)

z = np.load(c.RUN + "posterior.npz")
L = z["kept/L"].reshape(-1, z["kept/L"].shape[-1]).mean(axis=0)
res0 = json.load(open(c.RUN + "result.json"))
EPOCH = pd.Timestamp("2013-12-02")
start = pd.Timestamp(res0["grid_start"])
assert start == EPOCH, res0["grid_start"]


def walk(day):
    u = (pd.to_datetime(day) - start).dt.days.to_numpy() / 7.0
    w = np.clip(np.floor(u).astype(int), 0, len(L) - 2)
    f = np.clip(u - w, 0, 1)
    return L[w] * (1 - f) + L[w + 1] * f


h["dL"] = walk(h.day) - walk(h.prev_day)
h["dR"] = rgb_index(h.day) - rgb_index(h.prev_day)
h["years"] = (h.day - h.prev_day).dt.days / 365.25

# DOF stabilized counts by lot and year
od = "/data1/apartments/tmp/suspect/opendata/"
a = pd.read_csv(
    od + "rs2024.csv", usecols=lambda s: s == "ucbbl" or s.startswith("uc20")
)
a = a.rename(columns={f"uc{y}": y for y in range(2018, 2025)})
b = pd.read_csv(
    od + "tb_joined.csv", usecols=lambda s: s == "ucbbl" or s.endswith("uc")
)
b = b.rename(columns={f"{y}uc": y for y in range(2007, 2018)})
uc = b.merge(a, on="ucbbl", how="outer").set_index("ucbbl")
uc.index = uc.index.astype("int64").astype(str)
uc = uc[[y for y in range(2007, 2025) if y in uc.columns]].apply(
    pd.to_numeric, errors="coerce"
)
ever = uc.fillna(0).max(axis=1)
plu = pd.read_parquet(c.PLUTO, columns=["bbl", "unitsres"]).drop_duplicates("bbl")
plu["unitsres"] = pd.to_numeric(plu.unitsres, errors="coerce")
plu["bbl"] = plu.bbl.astype("string")
h["bbl"] = h.bbl.astype("string")
h = h.merge(plu, on="bbl", how="left")
yr = h.day.dt.year.clip(2007, 2024).to_numpy()
cnt = np.full(len(h), np.nan)
ix = uc.index.get_indexer(h.bbl.fillna("").astype(str))
ok = ix >= 0
cols = list(uc.columns)
vals = uc.to_numpy()
for j, y in enumerate(cols):
    m = ok & (yr == y)
    cnt[m] = vals[ix[m], j]
# carry the nearest earlier year's count where the ad's year is missing
filled = uc.ffill(axis=1).to_numpy()
miss = ok & np.isnan(cnt)
cnt[miss] = filled[ix[miss], np.searchsorted(cols, yr[miss]).clip(0, len(cols) - 1)]
h["dof_share"] = np.where(h.unitsres > 0, np.nan_to_num(cnt) / h.unitsres, np.nan)
h["dof_ever"] = np.where(ok, ever.reindex(h.bbl.fillna("").astype(str)).to_numpy(), 0)
flag = h.rent_stabilized.fillna(False).astype(bool)
h["group"] = np.where(
    flag,
    "text",
    np.where(
        h.dof_share >= 0.5,
        "dof_half",
        np.where((h.dof_ever == 0) & h.unitsres.notna(), "market", "other"),
    ),
)
print(h.group.value_counts().to_dict(), flush=True)

res = {"n": len(h), "groups": {}}
for g, x in h.groupby("group"):
    if g == "other":
        continue
    out = {"n": len(x), "mean_gap": float(x.gap.mean())}
    out["slope_dL"], out["se_dL"], _ = c.wls_slope(x.gap, x.dL, x.building)
    # both changes at once
    X = np.column_stack([np.ones(len(x)), x.dL, x.dR])
    beta, *_ = np.linalg.lstsq(X, x.gap.to_numpy(), rcond=None)
    e = x.gap.to_numpy() - X @ beta
    A = np.linalg.inv(X.T @ X)
    sc = pd.DataFrame(X * e[:, None]).groupby(x.building.to_numpy()).sum().to_numpy()
    V = A @ (sc.T @ sc) @ A
    out["joint"] = {
        "dL": [float(beta[1]), float(np.sqrt(V[1, 1]))],
        "dR": [float(beta[2]), float(np.sqrt(V[2, 2]))],
    }
    # the same within building
    wg = c.within(x.gap, x.building)
    wx = c.within(x.dL, x.building)
    out["slope_dL_within"], out["se_dL_within"], _ = c.wls_slope(wg, wx, x.building)
    # by era of the held-out ad, where the market's moves were largest
    for lo, hi in ((2016, 2019), (2020, 2021), (2022, 2023), (2024, 2026)):
        m = (x.day.dt.year >= lo) & (x.day.dt.year <= hi)
        if m.sum() > 300:
            s, se, _ = c.wls_slope(x.gap[m], x.dL[m], x.building[m])
            out[f"slope_{lo}_{hi}"] = [s, se, int(m.sum())]
    # gap by bins of the walk's change
    bins = pd.cut(x.dL, [-1, -0.05, 0, 0.05, 0.1, 0.2, 1])
    out["by_dL"] = {
        str(k): [
            float(v.gap.mean()),
            c.cluster_se(v.gap.to_numpy(), v.building.to_numpy()) / max(len(v), 1),
            len(v),
        ]
        for k, v in x.groupby(bins, observed=True)
    }
    res["groups"][g] = out
    print(g, json.dumps(out), flush=True)
h[["listing_id", "group", "dL", "dR", "years", "dof_share"]].to_parquet(
    c.OUT + "s6_rows.parquet"
)
json.dump(res, open(c.OUT + "s6.json", "w"), indent=1)

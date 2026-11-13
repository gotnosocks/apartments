"""S4: does competing supply at the moment an ad is priced move its ask against L1?

Each count uses only the dates ads opened, never a price. For each held-out ad the script counts

1. the building's other units with an ad opened in the 60 days before the held-out ad's
   price date, per residential unit of the lot in PLUTO;
2. the neighbourhood's ads opened in the 30 days before it, over the neighbourhood's mean
   30-day count across the two years before it (a log ratio).

An ad opens at the first ACTIVE event of its raw status history
(`/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet`), or at its price date where the
history is missing. Then the script reads the gap by decile of each count, the slope of the gap on
each, and the elpd from moving each ad by the cross-fitted mean gap of its decile."""

import json

import numpy as np
import pandas as pd

import common as c

d = c.rows()
p = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
    columns=["listing_id", "t_on"],
).drop_duplicates("listing_id")
p["t_on"] = p.t_on.dt.tz_convert(None)
d = d.merge(p, on="listing_id", how="left")
print("open date from history", float(d.t_on.notna().mean()), flush=True)
on = d.t_on.where(d.t_on.notna() & (d.t_on <= d.priced), d.priced)
DAY0 = np.datetime64("2000-01-01")
d["on_day"] = ((on.to_numpy() - DAY0) / np.timedelta64(1, "D")).astype(int)
d["at_day"] = ((d.priced.to_numpy() - DAY0) / np.timedelta64(1, "D")).astype(int)
SPAN = 100_000


def window_count(group, q_group, q_day, days, exclude=None, q_exclude=None):
    """Ads of each query's group opened in [q_day - days, q_day), less those of the query's
    own exclude key (its own unit)."""

    def count(g_all, g_q):
        codes, uniq = pd.factorize(pd.Series(np.r_[g_all, g_q]).astype(str))
        ca, cq = codes[: len(g_all)], codes[len(g_all) :]
        keys = np.sort(ca.astype(np.int64) * SPAN + d.on_day.to_numpy())
        hi = np.searchsorted(keys, cq.astype(np.int64) * SPAN + q_day, side="left")
        lo = np.searchsorted(
            keys, cq.astype(np.int64) * SPAN + q_day - days, side="left"
        )
        return hi - lo

    n = count(group, q_group)
    if exclude is not None:
        n = n - count(exclude, q_exclude)
    return n


h = c.heldout(d)
dr = c.Draws()
plu = pd.read_parquet(c.PLUTO, columns=["bbl", "unitsres"]).drop_duplicates("bbl")
plu["unitsres"] = pd.to_numeric(plu.unitsres, errors="coerce")
plu["bbl"] = plu.bbl.astype("string")
h["bbl"] = h.bbl.astype("string")
h = h.merge(plu, on="bbl", how="left")
assert len(h) == len(dr.ph)
qd = h.at_day.to_numpy()
h["bld60"] = window_count(
    d.building.to_numpy(),
    h.building.to_numpy(),
    qd,
    60,
    d.ukey.to_numpy(),
    h.ukey.to_numpy(),
)
h["units"] = h.unitsres.where(h.unitsres > 0)
h["bld60_per"] = h.bld60 / h.units
nb30 = window_count(d.neighbourhood.to_numpy(), h.neighbourhood.to_numpy(), qd, 30)
nb730 = window_count(d.neighbourhood.to_numpy(), h.neighbourhood.to_numpy(), qd, 730)
h["nb30"] = nb30
h["nb_ratio"] = np.log((nb30 + 1) / (nb730 * 30 / 730 + 1))
# only ads with two full years of earlier data in the dataset
h.loc[h.priced < pd.Timestamp("2016-01-01"), "nb_ratio"] = np.nan
print(h[["bld60", "bld60_per", "nb30", "nb_ratio"]].describe().to_string(), flush=True)

gap = h.gap.to_numpy()
b = h.building.to_numpy()
fold = h.fold.to_numpy()
sub = c.subfold(h.building)
res = {"n": len(h)}
wg = c.within(h.gap, h.building)


def deciles(x, name, zero_bin=False):
    x = pd.Series(x)
    ok = x.notna()
    if zero_bin:
        pos = ok & (x > 0)
        lab = pd.Series("none", index=x.index).where(ok, "missing")
        lab[pos] = pd.qcut(x[pos].rank(method="first"), 10, labels=False).astype(str)
    else:
        lab = pd.Series("missing", index=x.index)
        lab[ok] = pd.qcut(x[ok].rank(method="first"), 10, labels=False).astype(str)
    rows = []
    for L, g in h.groupby(lab.to_numpy()):
        rows.append(
            {
                "bin": L,
                "n": len(g),
                "x_lo": float(x[g.index].min()) if L != "missing" else None,
                "x_hi": float(x[g.index].max()) if L != "missing" else None,
                "gap": float(g.gap.mean()),
                "se": c.cluster_se(g.gap.to_numpy(), g.building.to_numpy()) / len(g),
                "within_bld": float(np.nanmean(wg[g.index])),
                "cov80": float(g.in80.mean()),
            }
        )
    t = pd.DataFrame(rows)
    t.to_csv(c.OUT + f"s4_{name}.csv", index=False)
    print(name, "\n", t.to_string(), flush=True)
    dl, k = c.crossfit_shift(gap, lab.to_numpy(), fold, sub)
    e = dr.gain(np.arange(len(h)), delta=dl)
    out = {"elpd_gain": float(e.sum()), "se": c.cluster_se(e, b), "k": k}
    inc = e - E0
    out["over_constant"] = [float(inc.sum()), c.cluster_se(inc, b)]
    m = ok.to_numpy()
    xs = x.to_numpy()[m]
    out["slope"], out["slope_se"], _ = c.wls_slope(gap[m], xs, b[m])
    wx = c.within(x.fillna(0), h.building)
    out["slope_within_bld"], out["slope_within_bld_se"], _ = c.wls_slope(
        wg[m], wx[m], b[m]
    )
    print(name, json.dumps(out), flush=True)
    return out


# a constant shift, fitted the same way: the gains above count over it
E0 = dr.gain(
    np.arange(len(h)), delta=c.crossfit_shift(gap, np.zeros(len(h)), fold, sub)[0]
)
res["constant"] = [float(E0.sum()), c.cluster_se(E0, b)]
pd.DataFrame({"listing_id": h.listing_id.to_numpy(), "e_const": E0}).to_parquet(
    c.OUT + "s4_const_gain.parquet"
)
res["bld60_per"] = deciles(h.bld60_per, "bld60_per", zero_bin=True)
res["bld60"] = deciles(h.bld60.where(h.units.notna()), "bld60", zero_bin=True)
res["nb_ratio"] = deciles(h.nb_ratio, "nb_ratio")
h[["listing_id", "bld60", "units", "bld60_per", "nb30", "nb_ratio"]].to_parquet(
    c.OUT + "s4_counts.parquet"
)
json.dump(res, open(c.OUT + "s4.json", "w"), indent=1)

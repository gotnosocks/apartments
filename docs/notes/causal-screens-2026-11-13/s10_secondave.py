"""S10: did the Second Avenue Subway (72 St, 86 St and 96 St, opened 2017-01-01) raise asks
near its stations?

For each building of the Upper East Side, Carnegie Hill, Yorkville, Lenox Hill and East
Harlem I take the straight-line distance to the nearest subway stop with and without the new
stops (`Q03`, `Q04`, `Q05` in `/data1/apartments/external/subway/20260929-8e7c364`), and
call the difference the building's gain.

Part A reads raw asks only. For consecutive ads of a unit with both latest-ask days in 2014 to
2019, I take the change in log ask, subtract its mean over the area's pairs with the same
pair of quarters, and regress what is left on the gain, the gain times a flag for pairs
spanning the opening, and that flag. The second coefficient is the difference in differences.
A placebo repeats it on pairs of 2013 to 2016 with a pretend opening on 2015-01-01.

Part B reads L1's held-out gap in the area by the gain and the period of the ad."""

import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import common as c

AREA = [
    "Upper East Side",
    "Upper Carnegie Hill",
    "Carnegie Hill",
    "Yorkville",
    "Lenox Hill",
    "East Harlem",
]
NEW = {"Q03", "Q04", "Q05"}
OPEN = pd.Timestamp("2017-01-01")

st = pd.read_parquet(
    "/data1/apartments/external/subway/20260929-8e7c364/subway.parquet"
)
reg = pd.read_parquet(
    c.REG, columns=["building", "latitude", "longitude"]
).drop_duplicates("building")


def xy(lat, lon):
    return np.column_stack(
        [np.asarray(lon) * np.cos(np.radians(40.78)) * 111.32, np.asarray(lat) * 110.54]
    )


def nearest(p, stops):
    return cKDTree(xy(stops.gtfs_latitude, stops.gtfs_longitude)).query(p)[0]


full = c.rows()
d = full[full.neighbourhood.isin(AREA)].copy()
d = d.merge(reg, on="building", how="left")
d = d[d.latitude.notna()]
p = xy(d.latitude, d.longitude)
old = st[~st.gtfs_stop_id.isin(NEW)]
d["km_before"] = nearest(p, old)
d["km_after"] = nearest(p, st)
d["gain"] = d.km_before - d.km_after
print(
    "area ads",
    len(d),
    "gain quantiles",
    d.gain.quantile([0.5, 0.75, 0.9, 0.99]).round(3).to_dict(),
    flush=True,
)
res = {
    "n_area_ads": len(d),
    "gain_q": d.gain.quantile([0.5, 0.75, 0.9]).round(3).to_dict(),
}

d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
d["prev_day"] = d.day.shift().where(same)
d["dy"] = (np.log(d.latest_ask) - np.log(d.latest_ask.shift())).where(same)
d = d.sort_index()


def joint(y, X, b):
    X = np.column_stack([np.ones(len(y))] + list(X))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    A = np.linalg.inv(X.T @ X)
    sc = pd.DataFrame(X * e[:, None]).groupby(np.asarray(b)).sum().to_numpy()
    V = A @ (sc.T @ sc) @ A * len(sc) / (len(sc) - 1)
    return [[float(beta[i]), float(np.sqrt(V[i, i]))] for i in range(1, X.shape[1])]


def did(lo, hi, opening):
    x = d[d.dy.notna() & (d.prev_day >= lo) & (d.day < hi) & (d.dy.abs() < 0.5)].copy()
    x["span"] = ((x.prev_day < opening) & (x.day >= opening)).astype(float)
    qq = lambda t: t.dt.year * 4 + (t.dt.month - 1) // 3  # noqa: E731
    x["cell"] = qq(x.prev_day).astype(str) + "|" + qq(x.day).astype(str)
    x["dyw"] = x.dy - x.groupby("cell").dy.transform("mean")
    x = x[x.groupby("cell").dy.transform("size") >= 5]
    g, gs, s = x.gain.to_numpy(), (x.gain * x.span).to_numpy(), x.span.to_numpy()
    b = joint(x.dyw.to_numpy(), [g, gs, s], x.building)
    out = {"n": len(x), "n_span": int(s.sum()), "buildings": int(x.building.nunique())}
    out.update(dict(zip(["gain", "gain_x_span", "span"], b)))
    # by gain bin, the mean of what is left for spanning pairs less non-spanning pairs
    x["bin"] = pd.cut(
        x.gain,
        [-0.01, 0.05, 0.2, 0.4, 2],
        labels=["0-0.05", "0.05-0.2", "0.2-0.4", "0.4+"],
    )
    out["by_bin"] = {}
    for k, v in x.groupby("bin", observed=True):
        dm, se = c.cluster_mean_diff(
            v.dyw.to_numpy(), v.span.to_numpy() > 0, v.building.to_numpy()
        )
        out["by_bin"][str(k)] = [dm, se, len(v), int(v.span.sum())]
    return out


res["A"] = did(pd.Timestamp("2014-01-01"), pd.Timestamp("2020-01-01"), OPEN)
print("A", json.dumps(res["A"]), flush=True)
res["placebo"] = did(
    pd.Timestamp("2013-01-01"), pd.Timestamp("2017-01-01"), pd.Timestamp("2015-01-01")
)
print("placebo", json.dumps(res["placebo"]), flush=True)

# Part B: L1's held-out gap in the area
h = c.heldout(full)
h = h.merge(d[["listing_id", "gain"]], on="listing_id", how="inner")
h["period"] = pd.cut(
    h.day.dt.year, [2000, 2016, 2019, 2030], labels=["to 2016", "2017-19", "2020+"]
).astype(str)
rows = []
for per, v in h.groupby("period"):
    s_, se_, _ = c.wls_slope(v.gap, v.gain, v.building)
    rows.append(
        {
            "period": per,
            "n": len(v),
            "slope_per_km": s_,
            "se": se_,
            "mean_gap": float(v.gap.mean()),
        }
    )
res["B"] = rows
print(pd.DataFrame(rows).to_string(), flush=True)
json.dump(res, open(c.OUT + "s10.json", "w"), indent=1)

import json, pickle, numpy as np, pandas as pd
from rentfrontier import cautions

r = pd.read_parquet("/data1/apartments/tmp/po-firstnet/recs.parquet")
ids = pickle.load(open("/data1/apartments/tmp/po-firstnet/ids.pkl", "rb"))
r["c"] = pd.to_datetime(r.collected_at, unit="s")
s = r[r.listing_id.isin(ids["m3"])].sort_values("c").copy()
s["mf"] = s.mf.fillna(0)
s["ratio"] = np.where(s.mf > 0, s.ner / s.price, 1.0)
g = s.groupby("listing_id")
f, l = g.head(1).set_index("listing_id"), g.tail(1).set_index("listing_id")
d = pd.DataFrame(
    {
        "n": g.size(),
        "mf0": f.mf,
        "mf1": l.mf,
        "r0": f.ratio,
        "r1": l.ratio,
        "c0": f.c,
        "c1": l.c,
        "p0": f.price,
        "p1": l.price,
        "on": pd.to_datetime(l.on, utc=True).dt.tz_localize(None),
    }
)
d["span"] = (d.c1 - d.c0).dt.days
d["lag"] = (d.c0 - d.on).dt.days
m = d[d.n > 1]
print("multi", len(m), "median span", m.span.median())


def tab(x, lab):
    a = (x.mf0 == 0) & (x.mf1 > 0)
    b = (x.mf0 > 0) & (x.mf1 == 0)
    c = (x.mf0 > 0) & (x.mf1 > 0) & ((x.r0 - x.r1).abs() > 0.002)
    k = (x.mf0 > 0) & (x.mf1 > 0) & ~c
    print(
        lab,
        "n",
        len(x),
        "added",
        a.sum(),
        "removed",
        b.sum(),
        "changed",
        c.sum(),
        "kept",
        k.sum(),
        "latest free",
        (x.mf1 > 0).sum(),
        "| of latest-free, differ from first snap: %.1f%%"
        % (100 * (a | c).sum() / max((x.mf1 > 0).sum(), 1)),
        "| median |dratio| among differing: %.3f"
        % ((x.r1 - x.r0).abs()[a | b | c].median()),
    )


tab(m, "all multi")
for lo, hi in ((0, 10), (11, 25), (26, 40)):
    tab(m[(m.span >= lo) & (m.span <= hi)], f"span {lo}-{hi}d")
near = m[(m.lag <= 3)]
tab(near, "first snapshot within 3 days of opening")
tab(near[near.span >= 14], " ...and span>=14d")
x = near
a = (x.mf0 == 0) & (x.mf1 > 0)
print(
    "added: r1 quantiles",
    x.r1[a].quantile([0.1, 0.5, 0.9]).round(3).tolist(),
    "price cut too",
    (x.p1[a] < x.p0[a]).mean().round(2),
)
# live net_ask
ads = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet",
    columns=["listing_id", "first_ask", "page_price", "months_free", "first_day"],
).drop_duplicates()
ads = ads[ads.listing_id.astype(int).isin(ids["m3"])].set_index(
    ads.listing_id.astype(int)[ads.listing_id.astype(int).isin(ids["m3"])]
)
na = cautions.net_ask(ads.first_ask, ads.page_price, ads.months_free)
print(
    "live net_ask now",
    na.sum(),
    "of",
    len(ads),
    "coded free",
    (ads.months_free.fillna(0) > 0).sum(),
)
ever = g.mf.max().reindex(ads.index).fillna(0) > 0
print(
    "net_ask ads with a concession coded in an earlier snapshot",
    (na & ever.to_numpy()).sum(),
)
unc = (ads.months_free.fillna(0) == 0).to_numpy() & ever.to_numpy()
print(
    "no coded free now but coded earlier",
    unc.sum(),
    "; page price below first ask among them",
    (ads.page_price[unc] < ads.first_ask[unc]).sum(),
)
d.to_parquet("/data1/apartments/tmp/po-firstnet/live_snap.parquet")

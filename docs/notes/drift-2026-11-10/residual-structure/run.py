import pandas as pd, numpy as np

D = "/data1/apartments/tmp/overhaul/taskE/"
a = pd.read_parquet(D + "fit4.parquet")
b = pd.read_parquet(D + "fit8.parquet", columns=["listing_id", "mu", "u"]).rename(
    columns={"mu": "mu8", "u": "u8"}
)
assert (a.listing_id.values == b.listing_id.values).all()
a["mu8"] = b.mu8.values
a = a[~a.held].copy()
a["r4"] = a.y - a.mu - a.u.fillna(0)
a["r8"] = a.y - a.mu8
print(
    "train rows",
    len(a),
    "var r4",
    a.r4.var(),
    "var r8",
    a.r8.var(),
    "u8 nonzero",
    (b.u8.fillna(0) != 0).mean(),
)
rows = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet",
    columns=["listing_id", "neighbourhood"],
)
a = a.merge(rows.drop_duplicates("listing_id"), on="listing_id", how="left")
reg = pd.read_parquet(
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet",
    columns=["building", "bbl"],
).drop_duplicates("building")
a = a.merge(reg, on="building", how="left")
nob = a.bbl.isna() | (a.bbl.astype(str).str.len() == 0)
print(
    "rows no bbl",
    nob.sum(),
    "of",
    len(a),
    "; no neighbourhood",
    a.neighbourhood.isna().sum(),
)
a["zone"] = np.where(
    nob, None, np.where(a.bbl.astype(str).str[0] == "1", "Manhattan", "outer")
)
d = pd.to_datetime(a.latest_day)
a["q"] = d.dt.year.astype(str) + "Q" + d.dt.quarter.astype(str)
a["yr"] = d.dt.year
a = a[(a.yr >= 2014) & (a.yr <= 2026)]
a["bg"] = (
    np.minimum(a.bedrooms.fillna(0), 3).astype(int).astype(str).replace({"3": "3+"})
)
print("rows 2014-2026", len(a))


def series(df, key, r, minn=10):
    g = df.groupby(["q"])[r].agg(["mean", "var", "count"])
    g = g[g["count"] >= minn]
    m = g["mean"].values
    n = g["count"].values
    sdr = m.std(ddof=1)
    noise = np.mean(g["var"].values / n)
    sig = np.sqrt(max(0, m.var(ddof=1) - noise))
    top = g["mean"].abs().sort_values(ascending=False).head(3).index
    t = "; ".join(f"{q} {g.loc[q, 'mean']:+.3f} (n={g.loc[q, 'count']})" for q in top)
    last = g.sort_index().tail(8)
    l = " ".join(
        f"{q[2:]}:{x:+.3f}/{c}"
        for q, x, c in zip(last.index, last["mean"], last["count"])
    )
    return f"{key:12s} sd_raw={sdr:.4f} sd_sig={sig:.4f} nq={len(g)} | top3 {t}\n    last8 {l}"


for r in ["r4", "r8"]:
    print(f"\n== TASK1 {r}")
    for k, df in a[a.zone.notna()].groupby("zone"):
        print(series(df, "zone=" + k, r))
    for k, df in a.groupby("bg"):
        print(series(df, "bed=" + k, r))
# task2
print("\n== TASK2 neighbourhood x year, r4, cells>=200")
c = (
    a.dropna(subset=["neighbourhood"])
    .groupby(["neighbourhood", "yr"])["r4"]
    .agg(["mean", "var", "count"])
    .reset_index()
)
c = c[c["count"] >= 200].copy()
w = c["count"]
noise = (w * c["var"] / c["count"]).sum() / w.sum()
nm = a.groupby("neighbourhood").r4.mean()
c["dm"] = c["mean"] - c.neighbourhood.map(nm)
v1 = (w * c.dm**2).sum() / w.sum()
gm = (w * c["mean"]).sum() / w.sum()
v2 = (w * (c["mean"] - gm) ** 2).sum() / w.sum()
print(f"cells={len(c)} rows={w.sum()} noise={noise:.2e}")
print(
    f"sd_signal demeaned={np.sqrt(max(0, v1 - noise)):.4f} (raw sd {np.sqrt(v1):.4f}); not demeaned={np.sqrt(max(0, v2 - noise)):.4f} (raw sd {np.sqrt(v2):.4f})"
)
t = (
    c[c.yr >= 2024]
    .assign(ab=lambda x: x.dm.abs())
    .sort_values("ab", ascending=False)
    .head(15)
)
print(
    t[["neighbourhood", "yr", "dm", "count"]].to_string(
        index=False, float_format=lambda x: f"{x:+.3f}"
    )
)
# task3
print("\n== TASK3")
a = a[a.unit_id.notna() & a.building.notna()].copy()
nu = a.groupby("building").unit_id.nunique()
a["nu"] = a.building.map(nu)
rng = np.random.default_rng(0)
a = a.sort_values("building").reset_index(drop=True)
bs = a.building.values
starts = np.r_[0, np.flatnonzero(bs[1:] != bs[:-1]) + 1, len(a)]
day = (
    pd.to_datetime(a.latest_day)
    .values.astype("datetime64[D]")
    .astype("int64")
    .astype(float)
    / 365.25
)
uid = pd.factorize(a.unit_id)[0]
R4 = a.r4.values
R8 = a.r8.values
NU = a.nu.values
sel = []
for s, e in zip(starts[:-1], starts[1:]):
    idx = np.arange(s, e)
    if len(idx) > 200:
        idx = np.sort(rng.choice(idx, 200, replace=False))
    sel.append(idx)


def npairs(idx):
    n = len(idx)
    _, k = np.unique(uid[idx], return_counts=True)
    return n * (n - 1) // 2 - (k * (k - 1) // 2).sum()


tot = sum(npairs(i) for i in sel)
p = min(1, 3e6 / tot)
print("buildings", len(sel), "total cross-unit pairs", tot, "keep prob", round(p, 5))
edges = [0, 0.25, 0.5, 1, 2, 3, 5, 8, 1e9]
labs = ["<0.25", "0.25-0.5", "0.5-1", "1-2", "2-3", "3-5", "5-8", "8+"]
sizes = lambda n: 0 if n < 20 else (1 if n < 100 else 2)
slab = ["<20 units", "20-99", "100+"]
acc = {}  # (size,bucket,fit)-> [n,sx,sy,sxx,syy,sxy]
S = np.zeros((3, 8, 2, 6))
for idx in sel:
    n = len(idx)
    if n < 2:
        continue
    i, j = np.triu_indices(n, 1)
    i = idx[i]
    j = idx[j]
    m = uid[i] != uid[j]
    if p < 1:
        m &= rng.random(len(m)) < p
    i = i[m]
    j = j[m]
    if len(i) == 0:
        continue
    bk = np.searchsorted(edges, np.abs(day[i] - day[j]), side="right") - 1
    bk = np.clip(bk, 0, 7)
    sz = sizes(NU[idx[0]])
    for f, R in enumerate((R4, R8)):
        x = R[i]
        y = R[j]
        for arr in (np.bincount(bk, minlength=8),):
            S[sz, :, f, 0] += arr
        S[sz, :, f, 1] += np.bincount(bk, x + y, 8)
        S[sz, :, f, 3] += np.bincount(bk, x * x + y * y, 8)
        S[sz, :, f, 5] += np.bincount(bk, 2 * x * y, 8)
        # symmetrized: counts 2n; sums handled below


def stats(Sx):
    n = Sx[0]
    if n == 0:
        return 0, np.nan, np.nan
    N = 2 * n
    mx = Sx[1] / N
    vx = Sx[3] / N - mx**2
    cov = Sx[5] / N - mx**2  # 2xy sum / 2n
    return n, cov / vx if vx > 0 else np.nan, cov


for f, nm_ in enumerate(["r4", "r8"]):
    print(f"\n{nm_}: pearson (pairs) [cov] by gap years")
    print("gap".ljust(9) + "".join(f"{s:>26s}" for s in ["all"] + slab))
    for b_ in range(8):
        row = labs[b_].ljust(9)
        for z in [None, 0, 1, 2]:
            Sx = S[:, b_, f, :].sum(0) if z is None else S[z, b_, f, :]
            n, r, c = stats(Sx)
            row += f"{int(n):>10d} {r:+.3f} [{c:+.4f}]  "
        print(row)
# task4 building
Sx = S.sum(0)[:, 0, :]
Sa = S.sum(0)[:, 0, :]


def pooled(bks):
    T = S.sum(0)[bks, 0, :].sum(0)
    return stats(T)


sv, lv = pooled([0, 1]), pooled([5, 6, 7])
print(
    "\nr4 cov short(<0.5y) %.4f (n=%d) long(3y+) %.4f (n=%d); var r4 %.4f"
    % (sv[2], sv[0], lv[2], lv[0], np.var(R4))
)

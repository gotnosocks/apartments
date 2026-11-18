"""Free check: concession, furnished and short-term state against the unit's previous training ad."""
import numpy as np, pandas as pd, pyarrow.parquet as pq
from scipy.stats import norm
from rentfrontier import drift_building_bedtext_layout as M
OUT = "/data1/apartments/tmp/low-outliers-2026-11-18/"
d = np.load("/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz", allow_pickle=True)
fr = pd.read_parquet("/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet",
    columns=["listing_id", "building", "unit_id", "price_at", "bedrooms", "full_baths", "half_baths", "income_restricted", "furnished", "short_term"])
held = d["heldout"]; assert (fr.listing_id[held].to_numpy() == d["listing"]).all()
a = pq.read_table("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet", columns=["listing_id", "months_free"]).to_pandas().drop_duplicates("listing_id")
a["listing_id"] = a.listing_id.astype(fr.listing_id.dtype)
fr["free"] = (fr.listing_id.map(a.set_index("listing_id").months_free).fillna(0) > 0).astype(float)
fr["furn"] = fr.furnished.fillna(False).astype(float); fr["short"] = fr.short_term.fillna(False).astype(float)
lay = M.changes(fr, ~held).sum(1) > 0
# previous training ad's state, with the module's own lookup: put the state in the bedrooms slot
cols = {}
for c in ("free", "furn", "short"):
    g = fr.assign(bedrooms=fr[c]); p = M.previous(g, ~held).prev_beds.to_numpy()
    cols[c + " gained"] = (fr[c].to_numpy() > p); cols[c + " lost"] = (fr[c].to_numpy() < p)
    cols[c + " now, no prev ad"] = (fr[c].to_numpy() > 0) & np.isnan(p); cols[c + " kept"] = (fr[c].to_numpy() > 0) & (p > 0)
h = fr[held].reset_index(drop=True); qs = list(d["quantiles"])
h["gap"] = d["y"] - d["pred"]; h["cdf"] = d["cdf"]
h["z"] = np.clip(h.gap / ((d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]) / (2 * norm.ppf(0.75))), -6, 6)
half = pd.read_parquet(OUT + "held_b9.parquet", columns=["listing_id", "half"]); half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
h = h.merge(half, on="listing_id", how="left", validate="1:1")
keep = ~h.income_restricted.fillna(False).to_numpy(bool)
rng = np.random.default_rng(20261118)
def cv(z, x, fold):
    pred = np.empty_like(z)
    for k in range(5):
        tr = fold != k; A = np.c_[np.ones(tr.sum()), x[tr]]; b = np.linalg.lstsq(A, z[tr], rcond=None)[0]; pred[~tr] = b[0] + b[1] * x[~tr]
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()
for name in ("read", "unread"):
    m = keep & (h.half == name).to_numpy(); u = h[m].reset_index(drop=True)
    b = u.building.unique(); fold = u.building.map(dict(zip(b, rng.permutation(np.arange(len(b)) % 5)))).to_numpy(); z = u.z.to_numpy()
    lo, ct, hi = (u.cdf < .01).to_numpy(), ((u.cdf > .25) & (u.cdf < .75)).to_numpy(), (u.cdf > .99).to_numpy()
    print(name, len(u))
    for k, v in cols.items():
        f = v[held][m]; x = f.astype(float)
        if f.sum() < 30: print(f"  {k:22s} n {f.sum()}"); continue
        e = cv(z, x, fold); n95 = np.quantile([cv(z, rng.permutation(x), fold) for _ in range(100)], .95)
        print(f"  {k:22s} n {f.sum():6d} below {100*f[lo].mean():5.1f} ctl {100*f[ct].mean():5.1f} above {100*f[hi].mean():5.1f} gap {u.gap[f].mean():+.4f} other {u.gap[~f].mean():+.4f} expl {e:+.5f} null95 {n95:.5f} {'pass' if e > max(0, n95) else 'fail'}")

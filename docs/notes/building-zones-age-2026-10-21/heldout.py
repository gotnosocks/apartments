"""Held-out log score, RMSE and coverage on the latest split for the age, gym and unit runs."""

import json
import numpy as np, pandas as pd
from scipy.special import gammaln, logsumexp
from rentfrontier import (
    b0,
    splits,
    building_zones as bz,
    building_zones_attrs as bza,
    building_zones_unit as bzu,
    building_zones_gym as bzy,
    building_zones_age as bzs,
)
from common import RUNS, DATASET, AGE, GYM, UNIT

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
THIN = 8
SAVED = bza.DROPPED_STEPS
out = {}
for tag, run, mod in (("unit", UNIT, bzu), ("gym", GYM, bzy), ("age", AGE, bzs)):
    z = np.load(RUNS + run + "/posterior.npz")
    assert (z["heldout"] == held).all()
    full = mod.design(frame)
    assert list(full.names) == [str(n) for n in z["names"]], tag
    t = mod.subset(full, ~held)
    h = mod.subset(full, held)
    th = 12 if tag == "age" else THIN
    k = lambda s: (
        z["kept/" + s][:, ::th].reshape(-1, *z["kept/" + s].shape[2:]).astype(float)
    )
    beta, L, w, bld, sig, nu = (
        k("beta"),
        k("L"),
        k("gp_w"),
        k("bld"),
        k("sigma"),
        k("nu"),
    )
    B, _ = bz.wave_matrix(t)
    site = h.site
    mu = h.x @ beta.T
    mu += (1 - h.frac)[:, None] * L[:, h.week].T + h.frac[:, None] * L[:, h.week + 1].T
    mu += (B[site] @ w.T) + bld[:, site].T
    s = sig[:, h.group].T
    r = (h.y[:, None] - mu) / s
    lp = (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
        - 0.5 * np.log(nu * np.pi)
        - np.log(s)
        - (nu + 1) / 2 * np.log1p(r * r / nu)
    )
    elpd = logsumexp(lp, axis=1) - np.log(lp.shape[1])
    rng = np.random.default_rng(0)
    yrep = mu + s * rng.standard_t(nu, size=mu.shape)
    lo, hi = np.quantile(yrep, [0.05, 0.95], axis=1)
    lo50, hi50 = np.quantile(yrep, [0.25, 0.75], axis=1)
    med = np.median(mu, 1)
    out[tag] = pd.DataFrame(
        {
            "elpd": elpd,
            "err": h.y - med,
            "pred": med,
            "in90": (h.y >= lo) & (h.y <= hi),
            "in50": (h.y >= lo50) & (h.y <= hi50),
            "zone": bz.site_zone(full)[site],
        }
    )
    print(tag, len(h.y), lp.shape, flush=True)
    del mu, yrep, lp, r, s
hf = frame[held].reset_index(drop=True)
gy = (
    pd.read_parquet(bzy.GYM_SNAPSHOT / "gym.parquet")
    .drop_duplicates("building")
    .set_index("building")
)
gymb = hf.building.astype(str).map(gy.gym).fillna(0).to_numpy() == 1
tr = (
    pd.read_parquet(bzu.SNAPSHOT / "truck.parquet")
    .drop_duplicates("building")
    .set_index("building")
    .truck_through
)
truck = hf.building.astype(str).map(tr).fillna(0).to_numpy() == 1
ag = (
    pd.read_parquet(bzs.AGE_SNAPSHOT / "age.parquet")
    .drop_duplicates("building")
    .set_index("building")
    .reindex(hf.building.astype(str))
)
retail = ag.retail.fillna(0).to_numpy() == 1
new = ag.year_built.to_numpy() >= 2000
g = out["age"]
res = {}


def summ(m, label):
    res[label] = {"rows": int(m.sum())}
    for base in ("gym", "unit"):
        b = out[base]
        d = g.elpd[m] - b.elpd[m]
        res[label][f"elpd_vs_{base}"] = float(d.sum())
        res[label][f"se_vs_{base}"] = float(d.std() * np.sqrt(m.sum()))
    for tag, d in out.items():
        res[label][tag] = {
            "rmse": float(np.sqrt((d.err[m] ** 2).mean())),
            "mae": float(d.err[m].abs().median()),
            "cover90": float(d.in90[m].mean()),
            "cover50": float(d.in50[m].mean()),
            "bias_mean": float(d.err[m].mean()),
            "bias_median": float(d.err[m].median()),
        }


summ(np.ones(len(g), bool), "all")
for zk, zn in ((0, "manhattan"), (1, "outer")):
    summ(g.zone.to_numpy() == zk, zn)
summ(gymb, "gym buildings")
summ(~gymb, "no-gym buildings")
summ(truck, "truck through")
summ(retail, "retail")
summ(new, "built 2000 on")
res["truck_through_pred_change_age_minus_gym"] = {
    "mean": float((g.pred - out["gym"].pred)[truck].mean()),
    "mean_abs": float((g.pred - out["gym"].pred)[truck].abs().mean()),
    "others_mean": float((g.pred - out["gym"].pred)[~truck].mean()),
}
json.dump(res, open("heldout.json", "w"), indent=1)
pd.DataFrame(
    {
        "listing_id": hf.listing_id.astype(str),
        "building": hf.building,
        "gym": gymb,
        "truck": truck,
        "retail": retail,
        "new": new,
        **{f"{t}_{c}": d[c] for t, d in out.items() for c in ("elpd", "err", "pred")},
    }
).to_parquet("heldout_rows.parquet")
for k_, v in res.items():
    print(k_, json.dumps(v))

"""Data for the floor run's data page and explainer: floor-data.json."""

import json, re, numpy as np, pandas as pd
from common import RUNS, FLOOR, AGE


def sig(v, n=4):
    a = np.asarray(v, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.where(a == 0, 0, np.floor(np.log10(np.abs(np.where(a == 0, 1, a)))))
        r = np.round(a / 10**mag, n - 1) * 10**mag
    r = np.where(np.isfinite(a), r, np.nan)
    return (
        [None if np.isnan(x) else float(x) for x in r.ravel()]
        if r.ndim
        else (None if np.isnan(r) else float(r))
    )


def sig2(m):
    return [sig(row) for row in np.asarray(m)]


z = np.load(RUNS + FLOOR + "/posterior.npz")
za = np.load(RUNS + AGE + "/posterior.npz")
names = [str(n) for n in z["names"]]
anames = [str(n) for n in za["names"]]
beta = z["kept/beta"]
abeta = za["kept/beta"]  # chains x kept x p
an = json.load(open("analysis.json"))
ho = json.load(open("heldout.json"))
mom = pd.read_parquet("x_moments.parquet")
r = json.load(open(RUNS + FLOOR + "/result.json"))
pq = r["diagnostics"]["per_quantity"]
pct = lambda b: 100 * np.expm1(b)
out = {
    "run": FLOOR,
    "age_run": AGE,
    "draws": {
        "chains": int(beta.shape[0]),
        "kept_per_chain": int(beta.shape[1]),
        "note": "kept every 5th of 1,000 sweeps after 300 warmup",
    },
    "timing": an["seconds"],
    "wall_seconds": 1105.2,
    "usd": 0.73,
    "convergence": an["convergence"],
    "convergence_gp": an["convergence_gp"],
    "convergence_worst": an["convergence_worst"],
    "convergence_least_ess": an["convergence_least_ess"],
}
# Curves with chain medians, a spaghetti of draws, and the data count per floor.
curves = {}
rng = np.random.default_rng(1)
pick = rng.choice(beta.shape[1], 15, replace=False)
for g, cap in (("elev", 47), ("walkup", 6)):
    cols = [names.index(f"unit:{g}_f{k}") for k in range(2, cap + 1)]
    b = pct(beta[:, :, cols])
    flat = b.reshape(-1, len(cols))
    curves[g] = {
        "floors": list(range(1, cap + 1)),
        "med": [0.0] + sig(np.median(flat, 0)),
        "q05": [0.0] + sig(np.quantile(flat, 0.05, 0)),
        "q95": [0.0] + sig(np.quantile(flat, 0.95, 0)),
        "chain_med": [[0.0] + sig(np.median(b[c], 0)) for c in range(b.shape[0])],
        "draws": [[[0.0] + sig(b[c, i], 3) for i in pick] for c in range(b.shape[0])],
        "share": [None] + [sig(mom.share[f"unit:{g}_f{k}"]) for k in range(2, cap + 1)],
        "rhat": [None]
        + [sig(pq[f"beta[unit:{g}_f{k}]"]["rhat"]) for k in range(2, cap + 1)],
        "ess": [None]
        + [sig(pq[f"beta[unit:{g}_f{k}]"]["ess"], 3) for k in range(2, cap + 1)],
    }
    p = np.array([mom.share[f"unit:{g}_f{k}"] for k in range(2, cap + 1)])
    m = np.median(beta[:, :, cols].reshape(-1, len(cols)), 0)
    curves[g]["contribution"] = sig(float((p * m * m).sum() - (p * m).sum() ** 2))
out["curves"] = curves
gp = {}
for i, g in enumerate(("elev", "walkup")):
    gp[g] = {
        q: {
            "q": sig(an["gp"][g][q]),
            "trace": sig2(z[f"kept/gp_{q}"][:, :, i]),
            "chain_med": sig(np.median(z[f"kept/gp_{q}"][:, :, i], 1)),
            "rhat": sig(pq[f"gp_{q}[{g}]"]["rhat"]),
            "ess": sig(pq[f"gp_{q}[{g}]"]["ess"], 3),
        }
        for q in ("amp", "ls")
    }
out["gp"] = gp
out["gp_prior"] = {
    "amp2_invgamma": [2.0, 0.04],
    "amp_median": 0.15,
    "amp_90": [0.09, 0.34],
    "log_ls_normal": [float(np.log(0.7)), 0.5],
    "ls_median": 0.7,
    "ls_90": [0.31, 1.59],
    "nugget": 0.01,
    "input": "log floor",
}
# Every column: share, premium, contribution, and the age run's premium for the same column.
feat = []
for j, n in enumerate(names):
    if (
        n == "alpha"
        or n[:3] in ("sin", "cos")
        or re.fullmatch(r"unit:(elev|walkup)_f\d+", n)
    ):
        continue
    b = beta[:, :, j]
    f = an["features"][n]
    row = {
        "name": n,
        "share": sig(f["share"]),
        "pct": sig([f["pct_med"], f["pct_q05"], f["pct_q95"]]),
        "contribution": sig(f["contribution"]),
        "chain_med_pct": sig(pct(np.median(b, 1))),
        "rhat": sig(pq[f"beta[{n}]"]["rhat"]),
        "ess": sig(pq[f"beta[{n}]"]["ess"], 3),
    }
    if n in anames:
        ab = abeta[:, :, anames.index(n)].ravel()
        row["age_pct"] = sig(
            [pct(np.median(ab)), pct(np.quantile(ab, 0.05)), pct(np.quantile(ab, 0.95))]
        )
    if n in (
        "bld:elevator",
        "unit:penthouse",
        "unit:elev_top",
        "unit:elev_floor_unknown",
        "unit:garden",
        "unit:lower",
        "unit:walkup_top",
        "unit:walkup_floor_unknown",
    ):
        row["trace_pct"] = sig2(pct(b))
    feat.append(row)
out["features"] = feat
out["variance"] = an["variance"]
out["bld_change"] = an["bld_change"]
out["heldout"] = ho
# Surfaces: map amplitude in each zone, both runs.
out["surface_amp"] = {
    tag: {
        zn: sig(np.quantile(zz["kept/amp"][:, :, i].ravel(), [0.5, 0.05, 0.95]))
        for i, zn in enumerate(("manhattan", "outer"))
    }
    for tag, zz in (("age", za), ("floor", z))
}
F_, A_ = (
    pd.read_parquet("resid_floor.parquet", columns=["site", "F"]),
    pd.read_parquet("resid_age.parquet", columns=["F"]),
)
s = pd.DataFrame({"site": F_.site, "f": F_.F, "a": A_.F}).groupby("site").first()
out["surface_change"] = {
    "corr": float(np.corrcoef(s.f, s.a)[0, 1]),
    "sd_change": float((s.f - s.a).std()),
    "sd_age": float(s.a.std()),
}
out["predictions"] = json.load(open("floor-data.json"))["predictions"]
json.dump(out, open("floor-data.json", "w"), separators=(",", ":"))
print(
    out["surface_amp"],
    out["surface_change"],
    {g: curves[g]["contribution"] for g in curves},
)
import os

print(os.path.getsize("floor-data.json"))

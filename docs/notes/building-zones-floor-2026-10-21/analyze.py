"""Per-feature table, T and within-building error variance, building d change, floor curves,
hyperparameters and convergence for the floor run."""

import json, numpy as np, pandas as pd
from common import RUNS, FLOOR, AGE

z = np.load(RUNS + FLOOR + "/posterior.npz")
names = [str(n) for n in z["names"]]
k = lambda s: z["kept/" + s].reshape(-1, *z["kept/" + s].shape[2:])
beta = k("beta")
mom = pd.read_parquet("x_moments.parquet")
assert list(mom.index) == names
out = {"features": {}}
for j, n in enumerate(names):
    if n == "alpha" or n[:3] in ("sin", "cos"):
        continue
    b = beta[:, j]
    p = float(mom.share[n])
    v = float(mom["var"][n])
    out["features"][n] = {
        "share": p,
        "var_x": v,
        "beta_med": float(np.median(b)),
        "pct_med": float(100 * np.expm1(np.median(b))),
        "pct_q05": float(100 * np.expm1(np.quantile(b, 0.05))),
        "pct_q95": float(100 * np.expm1(np.quantile(b, 0.95))),
        "contribution": float(np.median(b) ** 2 * v),
    }
# Floor curves with 90% bands, floor 1 at 0.
curves = {}
for g, cap in (("elev", 47), ("walkup", 6)):
    rows = [{"floor": 1, "med": 0.0, "lo": 0.0, "hi": 0.0}]
    for f in range(2, cap + 1):
        b = 100 * np.expm1(beta[:, names.index(f"unit:{g}_f{f}")])
        rows.append(
            {
                "floor": f,
                "med": float(np.median(b)),
                "lo": float(np.quantile(b, 0.05)),
                "hi": float(np.quantile(b, 0.95)),
            }
        )
    curves[g] = rows
out["curves"] = curves
ga, gl = k("gp_amp"), k("gp_ls")
q = lambda v: [float(x) for x in np.quantile(v, [0.5, 0.05, 0.95])]
out["gp"] = {
    g: {"amp": q(ga[:, i]), "ls": q(gl[:, i])} for i, g in enumerate(("elev", "walkup"))
}
r = json.load(open(RUNS + FLOOR + "/result.json"))
dg = r["diagnostics"]
out["convergence"] = {kk: v for kk, v in dg.items() if kk != "per_quantity"}
out["convergence_gp"] = {
    n: v for n, v in dg["per_quantity"].items() if n.startswith("gp_")
}
out["convergence_worst"] = sorted(
    ((n, v["rhat"], v["ess"]) for n, v in dg["per_quantity"].items()),
    key=lambda x: -x[1],
)[:8]
out["convergence_least_ess"] = sorted(
    ((n, v["rhat"], v["ess"]) for n, v in dg["per_quantity"].items()),
    key=lambda x: x[2],
)[:8]
out["seconds"] = r.get("seconds")
out["cost_usd"] = r.get("cost_usd")
# Variance of T (zone-demeaned) and within-building residual variance, both runs.
F_, A_ = pd.read_parquet("resid_floor.parquet"), pd.read_parquet("resid_age.parquet")
assert (F_.listing_id.to_numpy() == A_.listing_id.to_numpy()).all()
fb = F_.band.to_numpy()
known = fb != "unknown"
xf = pd.DataFrame(
    z["kept/beta"].reshape(-1, len(names)).mean(0)[None, :], columns=names
)


def zvar(v, zone):
    v = v - pd.Series(v).groupby(zone).transform("mean").to_numpy()
    return float(v.var())


def wvar(r, b):
    return float((r - pd.Series(r).groupby(b).transform("mean").to_numpy()).var())


var = {}
for lab, m in (
    ("all", np.ones(len(F_), bool)),
    ("floor known", known),
    ("floor known elev", known & (F_.group == "elev").to_numpy()),
    ("floor known walkup", known & (F_.group == "walkup").to_numpy()),
):
    row = {"ads": int(m.sum())}
    for tag, R in (("age", A_), ("floor", F_)):
        T = (R.r + R.bld + R.F).to_numpy()[m]
        row[tag] = {
            "T_var": zvar(T, R.zone.to_numpy()[m]),
            "resid_var": float(R.r.to_numpy()[m].var()),
            "within_bld_var": wvar(R.r.to_numpy()[m], R.site.to_numpy()[m]),
        }
    for kk in ("T_var", "resid_var", "within_bld_var"):
        row[kk + "_drop_pct"] = 100 * (1 - row["floor"][kk] / row["age"][kk])
    var[lab] = row
out["variance"] = var
# Building d change, buildings with any training ad with a known floor.
d = (
    pd.DataFrame({"site": F_.site, "known": known, "bf": F_.bld, "ba": A_.bld})
    .groupby("site")
    .agg(
        known=("known", "max"),
        n=("known", "size"),
        bf=("bf", "first"),
        ba=("ba", "first"),
    )
)
dd = {}
for lab, m in (("with floor data", d.known), ("without", ~d.known)):
    x = d[m]
    ch = x.bf - x.ba
    dd[lab] = {
        "buildings": int(len(x)),
        "change_mean": float(ch.mean()),
        "change_sd": float(ch.std()),
        "change_abs_median": float(ch.abs().median()),
        "sd_d_age": float(x.ba.std()),
        "sd_d_floor": float(x.bf.std()),
        "corr": float(np.corrcoef(x.ba, x.bf)[0, 1]),
    }
out["bld_change"] = dd
json.dump(out, open("analysis.json", "w"), indent=1)
for n, v in out["features"].items():
    if n.startswith("unit:") and "_f" not in n or n.startswith("bld:elev"):
        print(n, {kk: round(vv, 5) for kk, vv in v.items()})
print(
    json.dumps(
        {
            kk: out[kk]
            for kk in (
                "gp",
                "convergence",
                "convergence_gp",
                "variance",
                "bld_change",
                "seconds",
                "cost_usd",
            )
        },
        indent=1,
    )
)
for g in curves:
    print(g, [(c["floor"], round(c["med"], 1)) for c in curves[g][::3]])

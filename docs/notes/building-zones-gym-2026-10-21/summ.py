import json, numpy as np
from common import RUNS, GYM, UNIT, ATTRS

Z = ["manhattan", "outer"]
out = {}
for tag, run in (("gym", GYM), ("unit", UNIT), ("attrs", ATTRS)):
    p = RUNS + run
    z = np.load(p + "/posterior.npz")
    nm = [str(n) for n in z["names"]]
    k = lambda s: z["kept/" + s].reshape(-1, *z["kept/" + s].shape[2:])
    b = k("beta")
    co = {}
    for j, n in enumerate(nm):
        if n == "alpha" or n[:3] in ("sin", "cos"):
            continue
        pct = 100 * np.expm1(b[:, j])
        co[n] = {
            "pct_med": round(float(np.median(pct)), 2),
            "pct_q05": round(float(np.quantile(pct, 0.05)), 2),
            "pct_q95": round(float(np.quantile(pct, 0.95)), 2),
        }
    vf, vb, bs, amp = k("zone_var_f"), k("zone_var_b"), k("bld_sd"), k("amp")
    qq = lambda v: [round(float(x), 4) for x in np.quantile(v, [0.5, 0.05, 0.95])]
    zz = {
        zn: {
            "bld_sd": qq(bs[:, i]),
            "bld_share": qq(vb[:, i] / (vf[:, i] + vb[:, i])),
            "amp": qq(amp[:, i]),
        }
        for i, zn in enumerate(Z)
    }
    zl = k("zone_level")
    gap = 100 * np.expm1(zl[:, 0] - zl[:, 1])
    out[tag] = {
        "run": run,
        "coef": co,
        "zones": zz,
        "nu": qq(k("nu")),
        "sigma": [round(float(x), 4) for x in np.median(k("sigma"), 0)],
        "zone_gap_pct": qq(gap),
    }
r = json.load(open(RUNS + GYM + "/result.json"))
out["gym"]["convergence"] = {
    k: v for k, v in r["diagnostics"].items() if k != "per_quantity"
}
out["gym"]["seconds"] = r["seconds"]
out["gym"]["cost_usd"] = r["cost_usd"]
json.dump(out, open("summ.json", "w"), indent=1)
a, u, at = out["gym"], out["unit"], out["attrs"]
for n, v in a["coef"].items():
    o = u["coef"].get(n)
    o2 = at["coef"].get(n)
    print(
        f"{n:28s} {v['pct_med']:7.2f} [{v['pct_q05']:6.2f},{v['pct_q95']:6.2f}]  unit {o['pct_med'] if o else '':>7}  attrs {o2['pct_med'] if o2 else '':>7}"
    )
for t in ("unit", "attrs"):
    for n in out[t]["coef"]:
        if n not in a["coef"]:
            print("only in", t, n, out[t]["coef"][n])
for zn in Z:
    print(zn, "gym", a["zones"][zn], "unit", u["zones"][zn])
print(
    "nu",
    a["nu"],
    u["nu"],
    "sigma",
    a["sigma"],
    u["sigma"],
    "gap",
    a["zone_gap_pct"],
    u["zone_gap_pct"],
)
print("conv", json.dumps(a["convergence"])[:1500])
print(a["seconds"], a["cost_usd"])

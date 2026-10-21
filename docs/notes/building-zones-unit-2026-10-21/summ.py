import json, numpy as np

RUNS = "/data1/apartments/frontier/runs/"
NEW = RUNS + "building-zones-unit-b0-latest-a3aec3ff-dense-w650"
OLD = RUNS + "building-zones-attrs-b0-latest-9bd8c1a3-dense-w650"
Z = ["manhattan", "outer"]


def load(p):
    z = np.load(p + "/posterior.npz")
    nm = [str(n) for n in z["names"]]
    k = lambda s: z["kept/" + s].reshape(-1, *z["kept/" + s].shape[2:])
    return z, nm, k


out = {}
for tag, p in (("after", NEW), ("before", OLD)):
    z, nm, k = load(p)
    b = k("beta")
    co = {}
    for j, n in enumerate(nm):
        if n == "alpha" or n[:3] in ("sin", "cos"):
            continue
        g = b[:, j]
        pct = 100 * np.expm1(g)
        co[n] = {
            "log_med": round(float(np.median(g)), 4),
            "pct_med": round(float(np.median(pct)), 2),
            "pct_q05": round(float(np.quantile(pct, 0.05)), 2),
            "pct_q95": round(float(np.quantile(pct, 0.95)), 2),
        }
    vf, vb, bs, amp = k("zone_var_f"), k("zone_var_b"), k("bld_sd"), k("amp")
    zz = {}
    for i, zn in enumerate(Z):
        qq = lambda v: [round(float(x), 4) for x in np.quantile(v, [0.5, 0.05, 0.95])]
        zz[zn] = {
            "bld_sd": qq(bs[:, i]),
            "bld_share": qq(vb[:, i] / (vf[:, i] + vb[:, i])),
            "amp": qq(amp[:, i]),
            "surface_sd_rw": qq(np.sqrt(vf[:, i])),
            "bld_sd_realised_rw": qq(np.sqrt(vb[:, i])),
        }
    zl = k("zone_level")
    gap = 100 * np.expm1(zl[:, 0] - zl[:, 1])
    out[tag] = {
        "run": p.split("/")[-1],
        "coef": co,
        "zones": zz,
        "nu": [round(float(x), 3) for x in np.quantile(k("nu"), [0.5, 0.05, 0.95])],
        "sigma": [round(float(x), 4) for x in np.median(k("sigma"), 0)],
        "zone_gap_pct": [
            round(float(x), 2) for x in np.quantile(gap, [0.5, 0.05, 0.95])
        ],
    }
r = json.load(open(NEW + "/result.json"))
out["after"]["convergence"] = {
    k: v for k, v in r["diagnostics"].items() if k != "per_quantity"
}
out["after"]["seconds"] = r["seconds"]
out["after"]["cost_usd"] = r["cost_usd"]
json.dump(out, open("summ.json", "w"), indent=1)
a, bf = out["after"], out["before"]
for n, v in a["coef"].items():
    o = bf["coef"].get(n)
    print(
        f"{n:28s} {v['pct_med']:7.2f} [{v['pct_q05']:6.2f},{v['pct_q95']:6.2f}]   before {o['pct_med'] if o else '':>7}"
    )
for zn in Z:
    print(zn, "after", a["zones"][zn])
    print(zn, "before", bf["zones"][zn])
print(
    "nu",
    a["nu"],
    bf["nu"],
    "sigma",
    a["sigma"],
    bf["sigma"],
    "gap",
    a["zone_gap_pct"],
    bf["zone_gap_pct"],
)
print(a["seconds"], a["cost_usd"])

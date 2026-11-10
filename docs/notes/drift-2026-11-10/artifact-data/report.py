"""Report on a landed drift fit: run facts, gate, posterior scales, held-out scores and, on
the latest split, elpd differences against the reference fits.

    python report.py RUN [--base RUN]   (--base adds the B1-against-F2 breakdown)
"""

import argparse
import json

import numpy as np

import common as c


def scalars(run):
    r = c.result(run)
    z = np.load(c.RUNS / run / "posterior.npz", allow_pickle=True)
    pq = r["diagnostics"]["per_quantity"]
    names = list(z["names"])
    out = {}

    def add(label, x, diag):
        d = pq.get(diag, {})
        lo, med, hi = c.q(x)
        out[label] = {
            "median": med,
            "lo90": lo,
            "hi90": hi,
            "mean": float(np.mean(x)),
            "sd": float(np.std(x)),
            "rhat": d.get("rhat"),
            "ess": d.get("ess"),
        }
        x = np.asarray(x, float)
        if "_ar_sd" in label:
            out[label]["sd_log"] = float(np.log(x).std())
        if "_ar_rho" in label:
            out[label]["sd_logit"] = float(np.log(x / (1 - x)).std())

    tr = {k[6:]: z[k] for k in z.files if k.startswith("trace/")}
    for k in ("unit_sd", "drift_sd", "drift_tau", "nu", "tau"):
        if k in tr:
            add(k, tr[k], k)
    for k in sorted(tr):
        if k.endswith(("_ar_sd", "_ar_rho")):
            x = tr[k]
            if x.ndim == 2:
                add(k, x, k)
            else:
                for j in range(x.shape[-1]):
                    add(f"{k}[{j}]", x[..., j], f"{k}[{j}]")
    for j, g in enumerate(c.GROUPS):
        add(f"sigma[{g}]", tr["sigma"][..., j], f"sigma[{j}]")
    for j, zn in enumerate(("manhattan", "outer")):
        add(f"bld_sd[{zn}]", tr["bld_sd"][..., j], f"bld_sd[{zn}]")
    j = names.index("ad:months_free")
    add("beta[ad:months_free]", tr["beta"][..., j], "beta[ad:months_free]")
    return out


def facts(run):
    r = c.result(run)
    d = r["diagnostics"]
    pq = d["per_quantity"]
    miss = sorted(k for k, v in pq.items() if v["rhat"] > 1.01 or v["ess"] <= 400)
    return {
        "run": run,
        "rows": r["sizes"],
        "seconds_per_sweep": r["gibbs"]["seconds_per_sweep"],
        "seconds": r["seconds"],
        "cost_usd": r.get("cost_usd"),
        "gpu": r["hardware"]["gpu"],
        "gate": {
            "passes": d["passes"],
            "max_rhat": [d["max_rhat"], d["max_rhat_name"]],
            "min_ess": [d["min_ess"], d["min_ess_name"]],
            "missing": miss,
        },
    }


def compare(run, base=None):
    s = c.scores(run)
    _, _, h = c.held_frame(run)
    assert (h.listing_id.astype(str).to_numpy() == s["listing"].astype(str)).all()
    out = {}
    bins, labels = c.gap_bins(h.gap.to_numpy())
    for name in c.REFS:
        rz = c.ref(name)
        ia, ib = c.align(s["listing"], rz["listing"])
        assert np.allclose(s["y"][ia], rz["y"][ib])
        x = s["elpd"][ia] - rz["elpd"][ib]
        row, bld = c.diff_se(x, s["building"][ia].astype(str))
        out[name] = {
            "rows": int(len(x)),
            "diff": float(x.sum()),
            "row_se": row,
            "building_se": bld,
        }
        if name == "fit4":
            out["by_gap_vs_fit4"] = [
                {
                    "gap_years": lab,
                    "rows": int((bins[ia] == k).sum()),
                    "diff": float(x[bins[ia] == k].sum()),
                }
                for k, lab in enumerate(labels)
            ]
    if base:
        b = c.scores(base)
        ia, ib = c.align(s["listing"], b["listing"])
        x = s["elpd"][ia] - b["elpd"][ib]
        near = h.bld_near.to_numpy()[ia]
        rows = []
        for lab, m in (("another unit within 6 months", near), ("none", ~near)):
            row, bld = c.diff_se(x[m], s["building"][ia][m].astype(str))
            rows.append(
                {
                    "building": lab,
                    "rows": int(m.sum()),
                    "diff": float(x[m].sum()),
                    "row_se": row,
                    "building_se": bld,
                }
            )
        out[f"vs_{base}"] = rows
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--base")
    a = p.parse_args()
    rep = facts(a.run) | {"params": scalars(a.run)}
    s = c.scores(a.run)
    if c.result(a.run)["split"] == "latest":
        rep["compare"] = compare(a.run, a.base)
    print(json.dumps(rep, indent=1, default=float))

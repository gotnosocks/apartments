"""Collect the drift fits' numbers for the explainer artifact into one small JSON file.

    python extract.py --latest F3=RUN --latest P4=RUN [--backtest RUN] [--market RUN] \
        --out data.json

Each `--latest LABEL=RUN` adds a latest-split fit under its label. The winner is the
passing fit with the highest held-out elpd, or the highest elpd when none passes.
`--backtest` takes a market run fitted as of a past day, `--market` a current one.

Every float is rounded to 4 significant digits. Log-scale quantities stay in logs
unless a key says dollars.
"""

import argparse
import glob
import json
import math

import numpy as np
import pandas as pd

import common as c
import pscore
from rentfrontier import drift_deals, drift_score

pscore.patch()

SEED = 20261110
GAP_EDGES = (0.25, 0.5, 1, 2, 4, 8)
BOROUGHS = {
    "1": "Manhattan",
    "2": "Bronx",
    "3": "Brooklyn",
    "4": "Queens",
    "5": "Staten Island",
}
USD_PER_SECOND = 1.33 / 1903.65  # F2's settled cost over its wall seconds, A100-40GB
REGISTRY = (
    "/data1/apartments/external/registry/20261110-f1fc080-extend/registry.parquet"
)


def sig(x, n=4):
    if isinstance(x, dict):
        # A total elpd is compared by its difference from another, so it keeps its digits.
        return {
            k: round(v, 1) if k == "elpd" and isinstance(v, float) else sig(v, n)
            for k, v in x.items()
        }
    if isinstance(x, (list, tuple)):
        return [sig(v, n) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        if not math.isfinite(x) or x == 0:
            return None if not math.isfinite(x) else 0.0
        return round(x, n - 1 - int(math.floor(math.log10(abs(x)))))
    if isinstance(x, np.ndarray):
        return sig(x.tolist(), n)
    return x


def modal_record(run):
    """The fit's final Modal record: wall seconds and settled dollars. A fit whose client
    was lost before the record has only the run's modal.json, and its dollars come from
    the wall seconds at the rate of the fits with a record."""
    for path in sorted(glob.glob("/data1/apartments/modal/logs/modal-fit-*.log"))[::-1]:
        with open(path) as f:
            for line in f:
                if (
                    line.startswith("{")
                    and f'"name": "{run}"' in line
                    and "wall_seconds" in line
                ):
                    return json.loads(line)
    meta = json.loads((c.RUNS / run / "modal" / "modal.json").read_text())
    return {
        "wall_seconds": meta["wall_seconds"],
        "usd_estimate": round(meta["wall_seconds"] * USD_PER_SECOND, 2),
    }


def boroughs(buildings, registry=REGISTRY):
    """Each building's borough from the first digit of its BBL in the registry."""
    reg = pd.read_parquet(registry, columns=["building", "bbl"]).drop_duplicates(
        "building"
    )
    bbl = reg.set_index("building").bbl.reindex(pd.Index(buildings).astype(str))
    return [
        BOROUGHS.get(str(b)[:1], "unknown") if pd.notna(b) else "unknown" for b in bbl
    ]


def run_entry(run, with_beta=False):
    r = c.result(run)
    d = r["diagnostics"]
    z = np.load(c.RUNS / run / "posterior.npz", allow_pickle=True)
    names = list(z["names"])
    trace = {}
    for k in z.files:
        if not k.startswith("trace/"):
            continue
        key = k[6:]
        x = np.asarray(z[k], float)
        if key == "beta":
            if not with_beta:
                continue
            labels = [f"beta[{n}]" for n in names]
        elif x.ndim == 2:
            labels = [key]
        else:
            labels = [f"{key}[{j}]" for j in range(x.shape[-1])]
        flat = x.reshape(x.shape[0] * x.shape[1], -1)
        for j, lab in enumerate(labels):
            v = flat[:, j]
            if np.ptp(v) > 0:
                trace[lab] = [v.mean(), *np.quantile(v, (0.05, 0.95))]
    if not with_beta:
        j = names.index("ad:months_free")
        v = z["trace/beta"][..., j].ravel()
        trace["beta[ad:months_free]"] = [v.mean(), *np.quantile(v, (0.05, 0.95))]
    # A fit pooled from several containers (`rentfrontier.drift_pool`) costs their sum.
    parts = [p["name"] for p in r.get("pooled_from", [])] or [run]
    records = [modal_record(p) for p in parts]
    m = {
        k: sum(x[k] for x in records)
        if all(x.get(k) is not None for x in records)
        else None
        for k in ("wall_seconds", "usd_estimate")
    }
    return {
        "name": run,
        "model": r["model"]["name"],
        "split": r["split"],
        "rows_trained": r["sizes"]["train"],
        "rows_predicted": r["sizes"]["heldout"],
        "seconds_per_sweep": r["gibbs"]["seconds_per_sweep"],
        "chains": r["sampler_settings"]["chains"],
        "containers": len(parts),
        "wall_seconds": m.get("wall_seconds"),
        "cost_usd": m.get("usd_estimate"),
        "gate": {
            "passes": d["passes"],
            "max_rhat": d["max_rhat"],
            "max_rhat_name": d["max_rhat_name"],
            "min_ess": d["min_ess"],
            "min_ess_name": d["min_ess_name"],
        },
        "sigma_groups": list(c.GROUPS),
        "traced_mean_p5_p95": trace,
    }


def gap_table(s, gap, unit_sd=None):
    idx, labels = c.gap_bins(gap, GAP_EDGES)
    y, q, pred = s["y"], s["q"], s["pred"]
    rows = []
    for k, lab in enumerate(labels):
        m = idx == k
        if not m.any():
            continue
        row = {
            "gap_years": lab,
            "rows": int(m.sum()),
            "elpd_per_row": s["elpd"][m].mean(),
            "median_abs_error": np.median(np.abs(y[m] - pred[m])),
            "width80": (q[m, 5] - q[m, 2]).mean(),
            "coverage80": np.mean((y[m] >= q[m, 2]) & (y[m] <= q[m, 5])),
            "coverage95": np.mean((y[m] >= q[m, 0]) & (y[m] <= q[m, 7])),
        }
        if unit_sd is not None:
            row["unit_sd"] = unit_sd[m].mean()
        rows.append(row)
    return rows


def pick_units(frame, held, s, n=6, rng=None):
    """Units with at least 6 ads over at least 5 years, whose last ad is held out,
    one per borough first."""
    hpos = {lid: i for i, lid in enumerate(s["listing"].astype(str))}
    f = frame.assign(held=held, listing_id=frame.listing_id.astype(str))
    f = f[~f.unit_key.str.startswith("#row")]
    g = f.groupby("unit_key").agg(
        n=("day", "size"),
        lo=("day", "min"),
        hi=("day", "max"),
        nh=("held", "sum"),
        building=("building", "first"),
    )
    g = g[(g.n >= 6) & ((g.hi - g.lo).dt.days >= 5 * c.YEAR) & (g.nh == 1)]
    g = g.assign(borough=boroughs(g.building))
    order = g.sample(frac=1, random_state=SEED)
    chosen = []
    for b in order.borough.unique():
        chosen.append(order[order.borough == b].index[0])
    chosen = (chosen + [k for k in order.index if k not in chosen])[:n]
    out = []
    for key in chosen:
        u = f[f.unit_key == key].sort_values("day")
        h = u[u.held].iloc[0]
        i = hpos[h.listing_id]
        qs = np.exp(
            [
                s["q"][i, 0],
                s["q"][i, 2],
                s["q"][i, 3],
                s["pred"][i],
                s["q"][i, 4],
                s["q"][i, 5],
                s["q"][i, 7],
            ]
        )
        out.append(
            {
                "borough": g.loc[key, "borough"],
                "neighbourhood": str(h.neighbourhood),
                "bedrooms": float(h.bedrooms),
                "ads": [
                    {
                        "day": str(r.day.date()),
                        "ask": float(r.latest_ask),
                        "held_out": bool(r.held),
                    }
                    for r in u.itertuples()
                ],
                "held_quantiles_dollars": dict(
                    zip(
                        ("2.5", "10", "25", "50", "75", "90", "97.5"),
                        qs.round(0).tolist(),
                    )
                ),
                "held_cdf": float(s["cdf"][i]),
            }
        )
    return out


def backtest(run):
    """F4's validate table, then the same bins for ads of units with and without a
    training ad."""
    market = drift_deals._manifest(c.RUNS / run)
    full = drift_deals.validate(c.RUNS / run, drift_deals.Path(market["ads"]))
    frame, h, held = drift_deals._held_frame(c.RUNS / run)
    a = drift_deals._ads(drift_deals.Path(market["ads"]), h.listing_id)
    first = a.first_ask.to_numpy(float)
    final = h.latest_ask.to_numpy(float)
    ok = np.isfinite(first) & (first > 0)
    res = drift_score.score_run(c.RUNS / run, at=np.log(np.where(ok, first, final)))
    place = res["cdf_at"]
    unit_key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    train_units = set(unit_key[~held & frame.unit_id.notna().to_numpy()])
    seen = unit_key[held].isin(train_units).to_numpy()
    day = pd.to_datetime(h.final_day if "final_day" in h else h.latest_day)
    off = pd.to_datetime(a.off_day).to_numpy()
    end = np.where(np.isnat(off), day.to_numpy(), off)
    days = (end - pd.to_datetime(a.first_day).to_numpy()) / np.timedelta64(1, "D")
    ok &= np.isfinite(days) & (days >= 0)
    change = final / np.where(ok, first, 1.0) - 1
    split = {}
    for lab, mask in (("with_training_ad", seen), ("without_training_ad", ~seen)):
        rows = []
        for lo in np.arange(10) / 10:
            hi = lo + 0.1
            m = ok & mask & (place >= lo) & ((place < hi) | (hi >= 0.999))
            if m.any():
                rows.append(
                    {
                        "place": f"{lo:.1f} to {hi:.1f}",
                        "ads": int(m.sum()),
                        "median_days_on_market": np.median(days[m]),
                        "share_cut": (change[m] < -0.001).mean(),
                        "median_change_pct": 100 * np.median(change[m]),
                    }
                )
        split[lab] = rows
    return full | {"scoring_day": market["scoring_day"], "split": split}


def market(run, registry):
    ads = drift_deals.Path(drift_deals._manifest(c.RUNS / run)["ads"])
    t = drift_deals.deals(c.RUNS / run, ads, registry)
    seen = t.unit_ads > 0
    edges = np.linspace(0, 1, 21)
    width = 100 * (t.model_hi80 - t.model_lo80) / t.model_median
    cols = [
        "neighbourhood",
        "bedrooms",
        "ask",
        "model_median",
        "model_lo80",
        "model_hi80",
        "below_share",
        "unit_ads",
        "days_on_market",
        "months_free",
        "url",
    ]
    return {
        "ads": int(len(t)),
        "below_share_bins": np.histogram(t.below_share, edges)[0].tolist(),
        "below_share_bins_with_training_ad": np.histogram(t.below_share[seen], edges)[
            0
        ].tolist(),
        "median_width80_pct": {
            "with_training_ad": float(width[seen].median()),
            "without_training_ad": float(width[~seen].median()),
        },
        "by_bedrooms": {
            str(k): int(v) for k, v in t.bedrooms.value_counts().sort_index().items()
        },
        "lowest": json.loads(t.head(25)[cols].to_json(orient="records")),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--latest", action="append", required=True, metavar="LABEL=RUN")
    p.add_argument("--backtest")
    p.add_argument("--market")
    p.add_argument("--registry", default=REGISTRY)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    latest = dict(x.split("=", 1) for x in a.latest)
    sc = {k: c.scores(v) for k, v in latest.items()}
    gates = {k: c.result(v)["diagnostics"]["passes"] for k, v in latest.items()}
    elpd = {k: float(s["elpd"].sum()) for k, s in sc.items()}
    passing = [k for k in latest if gates[k]]
    win = max(passing or latest, key=elpd.get)
    out = {
        "winner": {
            "fit": win,
            "run": latest[win],
            "passes_gate": bool(passing),
            "note": None
            if passing
            else "no latest-split fit passed the gate; the winner is the highest elpd",
        }
    }
    out["runs"] = [
        run_entry(v, with_beta=(k == win)) | {"fit": k} for k, v in latest.items()
    ]
    out["runs"] += [
        run_entry(v) | {"fit": k}
        for k, v in (("backtest", a.backtest), ("market", a.market))
        if v
    ]
    refs = {"fit4": c.ref("fit4"), "fit8": c.ref("fit8"), "ks_a": c.ref("ks_a")}
    out["scores"] = {
        k: drift_score.summary(s) | {"run": latest[k]} for k, s in sc.items()
    }
    out["scores"] |= {k: drift_score.summary(r) for k, r in refs.items()}

    frame, held, h = c.held_frame(latest[win])
    gap = h.gap.to_numpy()
    lid = h.listing_id.astype(str).to_numpy()
    out["by_gap"] = {}
    for k, s in sc.items():
        assert (s["listing"].astype(str) == lid).all()
        out["by_gap"][k] = gap_table(s, gap, s["unit_sd"])
    for k in ("fit4", "ks_a"):
        r = refs[k]
        ia, ib = c.align(lid, r["listing"])
        sub = {f: r[f][ib] for f in ("y", "q", "pred", "elpd")}
        out["by_gap"][k] = gap_table(sub, gap[ia])

    out["pit"] = {
        k: np.histogram(s["cdf"], np.linspace(0, 1, 21))[0].tolist()
        for k, s in sc.items()
    }

    s = sc[win]
    rng = np.random.default_rng(SEED)
    pick = np.sort(rng.choice(len(lid), 1500, replace=False))
    out["sample"] = {
        "fields": ["y", "median", "q10", "q90", "cdf", "gap_years", "bedrooms"],
        "dollars": True,
        "rows": [
            [
                float(np.exp(s["y"][i])),
                float(np.exp(s["pred"][i])),
                float(np.exp(s["q"][i, 2])),
                float(np.exp(s["q"][i, 5])),
                float(s["cdf"][i]),
                float(gap[i]),
                float(h.bedrooms[i]),
            ]
            for i in pick
        ],
    }
    out["units"] = pick_units(frame, held, s)

    z = np.load(c.RUNS / latest[win] / "posterior.npz")
    if "kept/L" in z.files:
        L = np.asarray(z["kept/L"], float)
        L = L.reshape(-1, L.shape[-1])
        weeks = np.arange(0, L.shape[1], 4)
        start = pd.Timestamp(c.result(latest[win])["grid_start"])
        out["walk"] = {
            "week_start": [
                str((start + pd.Timedelta(weeks=int(w))).date()) for w in weeks
            ],
            "mean": L.mean(0)[weeks],
            "p5": np.quantile(L, 0.05, 0)[weeks],
            "p95": np.quantile(L, 0.95, 0)[weeks],
        }
    if a.backtest:
        out["backtest"] = backtest(a.backtest)
    if a.market:
        out["market"] = market(a.market, drift_deals.Path(a.registry))
    text = json.dumps(sig(out), separators=(",", ":"))
    open(a.out, "w").write(text)
    print(f"{len(text) / 1024:.1f} KB to {a.out}")


if __name__ == "__main__":
    main()

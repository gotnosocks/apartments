"""Standard errors clustered by building and by tax lot, beside the iid ones.

    python -m rentfrontier.clusterse loo BASE OTHER [OTHER ...]
    python -m rentfrontier.clusterse rows BASE_DIR OTHER_DIR [OTHER_DIR ...]
    python -m rentfrontier.clusterse strata DIR
    python -m rentfrontier.clusterse labels RUN

Rows of a building share its terms, so their score differences move
together, and an SE that treats them as independent understates the noise of
a paired difference. Each command reports the SE of a sum three ways: over
rows (the board's), over buildings and over tax lots (buildings of a lot go
together; a building with no lot is its own lot). All of it is report-only:
the board's tie tolerance keeps the iid SE.

loo     Paired PSIS-LOO, BASE minus each OTHER, on the rows both keep (as
        `leaderboard.paired_loo`), from the LOO records' directory names. The
        verdict (win, loss or tie at 2 combined SEs) is given under each SE.
rows    Paired new-building log predictive density from `newbuilding`'s
        rows.parquet: OTHER minus BASE, building-weighted (each building's
        mean, summed) and row-summed.
strata  New-building 80%/95% coverage of a rows.parquet by listing-year band
        within each building-rows bin, overall and split by the lot's
        residential-units tercile and PLUTO class family.
labels  The neighbourhood labels' term in a run's kept draws: its variance
        over training rows per draw, against the log ask's variance.

loo, rows and labels write JSON under /data1/apartments/frontier/clusterse/.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, features, leaderboard, newbuilding

OUT_ROOT = data.OUTPUT_ROOT / "clusterse"


def cluster_se(d, groups):
    """SE of sum(d) when rows of a group move together: sqrt(G / (G - 1)
    times the sum over groups of (group sum - mean group sum) squared). With
    every row its own group this is the iid SE, d.std(ddof=1) * sqrt(n)."""
    d = np.asarray(d, float)
    _, g = np.unique(np.asarray(groups).astype(str), return_inverse=True)
    sums = np.bincount(g, weights=d)
    n_g = len(sums)
    if n_g < 2:
        return float("nan")
    return float(math.sqrt(n_g / (n_g - 1) * np.sum((sums - sums.mean()) ** 2)))


def lots_of(buildings):
    """Each building's tax lot (NB8 registry), or the building itself if it
    has none."""
    bbl, _, _ = newbuilding.lot_attributes(np.asarray(buildings))
    b = np.asarray(buildings).astype(str)
    return np.where(np.isin(bbl, ("nan", "None", "")), "b:" + b, bbl)


def lot_se(d, buildings):
    """`cluster_se` over the buildings' tax lots, or None where the lot
    registry is not on disk (a remote fit)."""
    try:
        lots = lots_of(buildings)
    except FileNotFoundError:
        return None
    return cluster_se(d, lots)


def row_clusters(dataset=None):
    """audit_id -> (building, lot) over the dataset's rows."""
    frame = data.load(Path(dataset)) if dataset else data.load()
    b = frame.building.to_numpy()
    return pd.DataFrame(
        {"building": b.astype(str), "lot": lots_of(b)},
        index=frame.audit_id.to_numpy(),
    )


def verdict(d, se, mc):
    tol = leaderboard.tie_tolerance(se, mc)
    return "win" if d > tol else ("loss" if d < -tol else "tie")


def paired_loo(a_dir, b_dir, clusters):
    """Paired PSIS-LOO a - b with iid, building and lot SEs, and the verdict
    under each."""
    ai, a_elpd, a_mcse = leaderboard.pointwise(a_dir)
    bi, b_elpd, b_mcse = leaderboard.pointwise(b_dir)
    keys = leaderboard.shared_rows(ai, bi, "Training", a_dir, b_dir)
    ia = np.array([ai[k] for k in keys])
    ib = np.array([bi[k] for k in keys])
    d = a_elpd[ia] - b_elpd[ib]
    mc = math.sqrt(float(np.sum(a_mcse[ia] ** 2) + np.sum(b_mcse[ib] ** 2)))
    c = clusters.reindex(keys)
    if c.building.isna().any():
        raise ValueError(f"{int(c.building.isna().sum())} rows not in the dataset")
    se = {
        "iid": float(d.std(ddof=1) * math.sqrt(len(d))),
        "building": cluster_se(d, c.building),
        "lot": cluster_se(d, c.lot),
    }
    return {
        "a": Path(a_dir).name,
        "b": Path(b_dir).name,
        "rows": len(d),
        "buildings": int(c.building.nunique()),
        "lots": int(c.lot.nunique()),
        "elpd_diff": float(d.sum()),
        "mcse": mc,
        "se": se,
        "ratio_building": se["building"] / se["iid"],
        "ratio_lot": se["lot"] / se["iid"],
        "verdict": {k: verdict(float(d.sum()), v, mc) for k, v in se.items()},
    }


def paired_rows(base_dir, other_dir, rung="new building"):
    """Paired new-building log predictive density, other minus base, from two
    rows.parquet files: building-weighted (rows weigh 1 / their building's
    rows) and row-summed, each with iid, building and lot SEs."""

    def read(p):
        r = pd.read_parquet(Path(p) / "rows.parquet")
        return r[r.rung == rung].set_index("audit_id")

    b, o = read(base_dir), read(other_dir)
    keys = b.index.intersection(o.index)
    b, o = b.loc[keys], o.loc[keys]
    d = o.lpd.to_numpy() - b.lpd.to_numpy()
    building = b.building.astype(str).to_numpy()
    lot = np.where(
        b.bbl.astype(str).isin(("nan", "None", "")), "b:" + building, b.bbl.astype(str)
    )
    n_b = pd.Series(building).map(pd.Series(building).value_counts()).to_numpy()
    out = {"base": Path(base_dir).name, "other": Path(other_dir).name, "rung": rung}
    out["rows"] = len(d)
    out["buildings"] = int(len(set(building)))
    out["lots"] = int(len(set(lot)))
    for name, v in (("building_weighted", d / n_b), ("row_sum", d)):
        out[name] = {
            "lpd_diff": float(v.sum()),
            "se_iid": float(v.std(ddof=1) * math.sqrt(len(v))),
            "se_building": cluster_se(v, building),
            "se_lot": cluster_se(v, lot),
        }
    return out


def strata(rows, rung="new building"):
    """Coverage tables of a per-row frame: {split: DataFrame} with rows
    (split value, row bin, year band) and columns rows, cover_80, cover_95."""
    r = rows[rows.rung == rung].copy()
    r["band"] = ""
    for label, lo, hi in newbuilding.YEARS:
        r.loc[(r.year >= lo) & (r.year <= hi), "band"] = label
    r["c80"] = (r.pit > 0.10) & (r.pit < 0.90)
    r["c95"] = (r.pit > 0.025) & (r.pit < 0.975)
    r["all"] = "all"
    out = {}
    for split in ("all", "unitsres_tercile", "class_family"):
        g = r.groupby([split, "row_bin", "band"])
        out[split] = pd.DataFrame(
            {
                "rows": g.size(),
                "cover_80": 100 * g.c80.mean(),
                "cover_95": 100 * g.c95.mean(),
            }
        )
    return out


def year_gap(rows, rung="new building", late="2024-26", early="2014-16"):
    """80% coverage of `late` rows minus `early` rows within each row bin,
    and their row-weighted mean (weights: the smaller of the two counts)."""
    t = strata(rows, rung)["all"].droplevel(0)
    gaps, weights = {}, {}
    for b in t.index.get_level_values(0).unique():
        if (b, late) in t.index and (b, early) in t.index:
            gaps[b] = float(
                t.loc[(b, late), "cover_80"] - t.loc[(b, early), "cover_80"]
            )
            weights[b] = float(min(t.loc[(b, late), "rows"], t.loc[(b, early), "rows"]))
    w = np.array(list(weights.values()))
    mean = float(np.dot(list(gaps.values()), w) / w.sum()) if len(w) else float("nan")
    return {"by_bin": gaps, "weights": weights, "weighted_mean": mean}


def labels(name):
    """The `neighbourhood` group's term in run `name`: per draw, its variance
    over training rows (b' cov(X) b), its SD, and its share of the log ask's
    variance; the posterior median and 90% interval of each, and each label's
    coefficient (% against the reference area)."""
    run_dir, result, kept, config, frame, heldout = newbuilding._load(name)
    feats = features.build(result["feature_set"], frame, ~heldout)
    groups = np.asarray([str(g) for g in feats.groups])
    cols = np.flatnonzero(groups == "neighbourhood")
    if not len(cols):
        raise SystemExit(f"{name}: no neighbourhood group")
    x = np.asarray(feats.values, float)[~heldout][:, cols]
    y = frame.log_rent.to_numpy()[~heldout]
    cov = np.atleast_2d(np.cov(x, rowvar=False))
    beta = kept["beta"][:, cols]
    var = np.einsum("di,ij,dj->d", beta, cov, beta)

    def q(v):
        lo, mid, hi = np.quantile(v, [0.05, 0.5, 0.95])
        return {"median": float(mid), "q05": float(lo), "q95": float(hi)}

    names = [str(feats.names[c]) for c in cols]
    return {
        "source_run": name,
        "rows": int(len(y)),
        "labels": names,
        "variance": q(var),
        "sd": q(np.sqrt(var)),
        "share_of_log_ask_variance": q(var / np.var(y)),
        "log_ask_variance": float(np.var(y)),
        "coefficient_pct": {
            n: q(100 * np.expm1(beta[:, i])) for i, n in enumerate(names)
        },
    }


def _write(name, record):
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUT_ROOT / f"{name}.json"
    path.write_text(json.dumps(record, indent=2))
    print(f"wrote {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=("loo", "rows", "strata", "labels"))
    parser.add_argument("names", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "loo":
        clusters = row_clusters()
        base = leaderboard.LOO_ROOT / args.names[0]
        out = [
            paired_loo(base, leaderboard.LOO_ROOT / o, clusters) for o in args.names[1:]
        ]
        for r in out:
            se = r["se"]
            print(
                f"{r['b'][:70]}: {r['elpd_diff']:+.1f}, SE iid {se['iid']:.1f}, "
                f"building {se['building']:.1f}, lot {se['lot']:.1f} "
                f"(x{r['ratio_lot']:.2f}); {r['verdict']}"
            )
        _write("loo-" + args.names[0], {"base": args.names[0], "pairs": out})
    elif args.command == "rows":
        out = [paired_rows(args.names[0], o) for o in args.names[1:]]
        for r in out:
            w = r["building_weighted"]
            print(
                f"{r['other'][:70]}: building-weighted {w['lpd_diff']:+.1f} nats, "
                f"SE iid {w['se_iid']:.1f}, building {w['se_building']:.1f}, "
                f"lot {w['se_lot']:.1f}"
            )
        _write("rows-" + Path(args.names[0]).name, {"pairs": out})
    elif args.command == "strata":
        rows = pd.read_parquet(Path(args.names[0]) / "rows.parquet")
        for split, t in strata(rows).items():
            for col in ("cover_80", "cover_95", "rows"):
                print(f"\n{split}: {col} by listing year\n")
                print(t[col].unstack("band").round(1).to_string())
        print(json.dumps(year_gap(rows), indent=2))
    else:
        record = labels(args.names[0])
        print(json.dumps({k: record[k] for k in ("variance", "sd")}, indent=2))
        _write("labels-" + args.names[0], record)


if __name__ == "__main__":
    main()

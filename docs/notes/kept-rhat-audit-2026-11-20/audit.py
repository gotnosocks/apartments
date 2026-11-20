"""Split R-hat and bulk ESS of the kept quantities the convergence gate does not read.

    audit.py RUN [RUN ...] [--runs-dir DIR] [--deals deals.json] [--out FILE]

The gate (`rentfrontier.run.RHAT_GATE`, `ESS_GATE`) reads the traced scalars and
coefficients, every sweep of every chain. A drift fit also keeps, at every 20th sweep, the
per-building levels (`kept/bld`) and each predicted ad's location (`kept/pred_loc`), both
(chains, kept draws, items), and the Deals order is made from the second. This script reads a
run's posterior.npz and nothing else of the fit, and reports for each run:

- `bld`, `pred_loc`: `rentfrontier.run.building_diagnostics` (the repo's `split_rhat` and
  `ess`) over the items.
- `below_share`: the same for each ad's per-draw predictive cdf at its ask, the quantity whose
  mean over draws is `below_share` (`drift_score._density`, the function `score_rows`
  averages). Its Monte Carlo standard error is sd / sqrt(ESS).
- `null`: the same for independent normal draws of the kept shape, which is what a perfectly
  mixed fit would give. Shares over a threshold mean something only against this.
- `order`: over the lowest tenth of the order and its first 100, the Monte Carlo error against
  the gap to the nearer neighbour in the order, how many places one error moves an ad, and how
  far the order from one chain alone agrees with the other's.
- `bld_over_1.05`: the buildings whose level has R-hat over 1.05, named through
  `drift_diagnostics.levels`: how far apart the chains' means are, how many training rows they
  have, and the predicted ads in them with their place in the order.
- `worst`: the ads with the largest R-hat of `pred_loc`, with their place in the order.

With --deals, the published table's cautions mark the ads the Deals page lists by default,
and the order figures are repeated over those for the run the table was made from (matched on
listing_id through the run's dataset).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from rentfrontier import drift_diagnostics, drift_score
from rentfrontier import run as run_module

CHUNK = 500
NULL_ITEMS = 20_000
WORST = 20


def find(runs: Path, name: str) -> Path:
    hits = [
        p for p in runs.iterdir() if name in p.name and (p / "posterior.npz").exists()
    ]
    if len(hits) != 1:
        raise SystemExit(f"{name}: {len(hits)} runs match under {runs}")
    return hits[0]


def spread(d: dict) -> dict:
    """The distribution of one `building_diagnostics` result over its varying items."""
    r, e = d["rhat"], d["ess"]
    live = ~np.isnan(r)
    r, e = r[live], e[live]
    return {
        "items": int(len(live)),
        "varying": int(live.sum()),
        "rhat_max": float(r.max()),
        "rhat_p99": float(np.quantile(r, 0.99)),
        "rhat_median": float(np.median(r)),
        "share_rhat_over_1.01": float((r > 1.01).mean()),
        "share_rhat_over_1.05": float((r > 1.05).mean()),
        "share_rhat_over_1.10": float((r > 1.10).mean()),
        "ess_min": float(e.min()),
        "ess_median": float(np.median(e)),
        "share_ess_under_400": float((e < 400).mean()),
        "share_ess_under_100": float((e < 100).mean()),
    }


def cdf_draws(z) -> np.ndarray:
    """Each kept draw's predictive cdf at each predicted ad's y: (chains, draws, ads)."""
    chains, draws = z["kept/nu"].shape
    flat = lambda k: z["kept/" + k].reshape(chains * draws, -1)  # noqa: E731
    loc, usd, sig = flat("pred_loc"), flat("pred_unit_sd"), flat("sigma")
    nu = z["kept/nu"].reshape(-1)
    y, group = z["kept/pred_y"], z["kept/pred_group"]
    factor = phase = None
    if "kept/pred_phase" in z:
        phase, factor = z["kept/pred_phase"], flat("phase_scale")
    lam, logw = drift_score.mixture(nu)
    out = np.empty((chains * draws, len(y)))
    for a in range(0, len(y), CHUNK):
        sl = slice(a, a + CHUNK)
        s = sig[:, group[sl]]
        if phase is not None:
            s = s * factor[:, phase[sl]]
        out[:, sl] = drift_score._density(
            y[sl], loc[:, sl].astype(float), usd[:, sl].astype(float), s, lam, logw
        )[1]
    return out.reshape(chains, draws, len(y))


def order_stats(share, mcse, rhat, keep) -> dict:
    """Monte Carlo error against the order, over the ads `keep` marks, lowest share first."""
    idx = np.flatnonzero(keep)
    idx = idx[np.argsort(share[idx], kind="stable")]
    s, m = share[idx], mcse[idx]
    gaps = np.diff(s)
    near = np.minimum(np.r_[np.inf, gaps], np.r_[gaps, np.inf])
    # The places one Monte Carlo error moves an ad: the ads whose share is within it.
    within = (
        np.searchsorted(s, s + m, side="right")
        - np.searchsorted(s, s - m, side="left")
        - 1
    )
    r = rhat[idx]
    out = {"ads": int(len(idx))}
    for label, top in (("lowest_tenth", len(idx) // 10), ("first_100", 100)):
        t = slice(0, top)
        out[label] = {
            "ads": int(top),
            "share_at_cut": float(s[top - 1]),
            "mcse_median": float(np.median(m[t])),
            "mcse_max": float(m[t].max()),
            "gap_median": float(np.median(near[t])),
            "mcse_over_gap_median": float(np.median(m[t] / np.maximum(near[t], 1e-12))),
            "share_mcse_over_gap": float((m[t] > near[t]).mean()),
            "places_within_one_mcse_median": float(np.median(within[t])),
            "places_within_one_mcse_p90": float(np.quantile(within[t], 0.9)),
            "places_within_one_mcse_max": int(within[t].max()),
            "share_rhat_over_1.01": float((r[t] > 1.01).mean()),
            "share_rhat_over_1.05": float((r[t] > 1.05).mean()),
            "rhat_max": float(r[t].max()),
        }
    return out


def chain_agreement(draws, keep) -> dict:
    """How far the order from each chain alone agrees with the other's."""
    from scipy.stats import spearmanr

    per = draws.mean(axis=1)[:, keep]
    a, b = per[0], per[1]
    out = {"spearman": float(spearmanr(a, b).statistic)}
    for label, top in (("lowest_tenth", per.shape[1] // 10), ("first_100", 100)):
        sa, sb = (set(np.argsort(v, kind="stable")[:top]) for v in (a, b))
        out[f"{label}_shared"] = len(sa & sb) / top
    ra, rb = (np.argsort(np.argsort(v, kind="stable")) for v in (a, b))
    first = np.argsort((a + b) / 2, kind="stable")[:100]
    move = np.abs(ra[first] - rb[first])
    out["first_100_places_apart_median"] = float(np.median(move))
    out["first_100_places_apart_max"] = int(move.max())
    return out


def rows(run_dir: Path):
    """The listing and building of each of the run's dataset rows, or None without it."""
    dataset = drift_score.dataset_dir(run_dir)
    if dataset is None:
        return None
    import pandas as pd

    return pd.read_parquet(
        dataset / "rows.parquet", columns=["listing_id", "building"]
    ).astype(str)


def stuck_buildings(run_dir, z, bld, frame, ad) -> dict:
    """The buildings with R-hat of the level over 1.05, and the predicted ads in them. `ad`
    holds each predicted ad's place, R-hat of `pred_loc` and Monte Carlo error."""
    record = json.loads((run_dir / "result.json").read_text())
    names, why = drift_diagnostics.levels(run_dir, record, frame.building.to_numpy())
    if names is None:
        return {"unnamed": why}
    held = z["heldout"]
    bad = np.flatnonzero(np.nan_to_num(bld["rhat"]) > 1.05)
    x = z["kept/bld"][:, :, bad].astype(float)
    apart = np.ptp(x.mean(axis=1), axis=0)
    train = frame.building[~held].value_counts()
    n_train = np.array([int(train.get(b, 0)) for b in names.index[bad]])
    held_building = frame.building[held].to_numpy()
    ads = []
    for b, r in zip(names.index[bad], bld["rhat"][bad]):
        for i in np.flatnonzero(held_building == b):
            ads.append(
                {"building": b, "rhat_bld": float(r)} | {k: v[i] for k, v in ad.items()}
            )
    tenth = len(held_building) // 10
    return {
        "buildings": int(len(bad)),
        "chain_means_apart_median": float(np.median(apart)),
        "chain_means_apart_max": float(apart.max()),
        "chain_means_apart_over_0.3": int((apart > 0.3).sum()),
        "training_rows_median": float(np.median(n_train)),
        "training_rows_at_most_3": int((n_train <= 3).sum()),
        "training_rows_max": int(n_train.max()),
        "with_predicted_ads": len({a["building"] for a in ads}),
        "predicted_ads": len(ads),
        "predicted_ads_in_lowest_tenth": sum(a["place"] <= tenth for a in ads),
        "ads": sorted(ads, key=lambda a: a["place"]),
    }


def audit(run_dir: Path, deals) -> dict:
    z = np.load(run_dir / "posterior.npz")
    gate = json.loads((run_dir / "result.json").read_text())["diagnostics"]
    chains, draws = z["kept/nu"].shape
    out = {
        "run": run_dir.name,
        "chains": chains,
        "kept_draws_per_chain": draws,
        "traced_draws_per_chain": int(z["trace/nu"].shape[1]),
        "gate": {
            k: gate[k] for k in ("max_rhat", "max_rhat_name", "min_ess", "passes")
        },
    }
    bld = run_module.building_diagnostics(z["kept/bld"])
    out["bld"] = spread(bld)
    loc = run_module.building_diagnostics(z["kept/pred_loc"])
    out["pred_loc"] = spread(loc)
    c = cdf_draws(z)
    cd = run_module.building_diagnostics(c)
    out["below_share"] = spread(cd)
    rng = np.random.default_rng(0)
    null = rng.standard_normal((chains, draws, NULL_ITEMS))
    out["null"] = spread(run_module.building_diagnostics(null))

    share = c.mean(axis=(0, 1))
    mcse = c.reshape(-1, c.shape[2]).std(axis=0, ddof=1) / np.sqrt(cd["ess"])
    everything = np.ones(len(share), bool)
    out["order"] = {
        "all": order_stats(share, mcse, loc["rhat"], everything)
        | {"chains": chain_agreement(c, everything)}
    }
    frame = rows(run_dir)
    ids = None if frame is None else frame.listing_id[z["heldout"]].to_numpy()
    if deals is not None and ids is not None:
        plain = {str(d["listing_id"]) for d in deals if not d["cautions"]}
        known = {str(d["listing_id"]) for d in deals}
        if known == set(ids):
            keep = np.array([i in plain for i in ids])
            out["order"]["uncautioned"] = order_stats(
                share, mcse, loc["rhat"], keep
            ) | {"chains": chain_agreement(c, keep)}

    rank = np.argsort(np.argsort(share, kind="stable"))
    tenth = len(share) // 10
    over = loc["rhat"] > 1.01
    out["rhat_over_1.01"] = {
        "ads": int(over.sum()),
        "in_lowest_tenth": int((over & (rank < tenth)).sum()),
        "in_first_100": int((over & (rank < 100)).sum()),
    }
    s = np.sort(share)
    gaps = np.diff(s)
    near = np.minimum(np.r_[np.inf, gaps], np.r_[gaps, np.inf])[rank]
    if frame is not None:
        ad = {
            "listing_id": ids.tolist(),
            "place": (rank + 1).tolist(),
            "below_share": share.tolist(),
            "rhat_pred_loc": loc["rhat"].tolist(),
            "rhat_below_share": cd["rhat"].tolist(),
            "mcse": mcse.tolist(),
            "chain_shares": c.mean(axis=1).T.tolist(),
        }
        out["bld_over_1.05"] = stuck_buildings(run_dir, z, bld, frame, ad)
    out["worst"] = [
        {
            "listing_id": None if ids is None else str(ids[i]),
            "rhat_pred_loc": float(loc["rhat"][i]),
            "ess_pred_loc": float(loc["ess"][i]),
            "rhat_below_share": float(cd["rhat"][i]),
            "below_share": float(share[i]),
            "place": int(rank[i]) + 1,
            "in_lowest_tenth": bool(rank[i] < tenth),
            "mcse": float(mcse[i]),
            "gap_to_nearer_neighbour": float(near[i]),
        }
        for i in np.argsort(-loc["rhat"])[:WORST]
    ]
    return out


def main(argv=None):
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("runs", nargs="+")
    p.add_argument("--runs-dir", type=Path, default=run_module.RUNS)
    p.add_argument("--deals", type=Path)
    p.add_argument("--out", type=Path, default=here / "audit.json")
    args = p.parse_args(argv)
    deals = json.loads(args.deals.read_text()) if args.deals else None
    out = [audit(find(args.runs_dir, name), deals) for name in args.runs]
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    for r in out:
        print(json.dumps(r["bld_over_1.05"], indent=1))


if __name__ == "__main__":
    main()

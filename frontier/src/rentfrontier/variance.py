"""Variance decomposition of a recorded run's fit, from its kept draws.

    python -m rentfrontier.variance <run-name> [<run-name> ...]

No refit. Over the run's training rows, each kept draw's fitted log rent
mu_i splits into the additive terms of `explain.log_terms`, grouped as

    market and time     intercept, month trend, season, bedroom-group curves
    features            every feature group (bedrooms, size, floor, ...)
    building            the building's level
    building over time  the building's half-year walk
    building slopes     per-building bedroom and size/bath slopes
    unit                the unit's own effect and drift

and the residual r_i = y_i - mu_i. For each draw the total variance
Var(mu) + Var(r) is split exactly:

    share_g = Cov(term_g, mu) / (Var(mu) + Var(r)),   share_resid = Var(r) / (...)

The shares sum to 1 in every draw (covariance attribution: correlated groups
split their joint variance, and a share can be slightly negative). The
residual uses observed residuals rather than sigma^2, which is infinite under
Student-t noise with nu <= 2 (the Bayesian R^2 of Gelman et al. 2019).

Reading it: a higher PSIS-LOO bought by a larger "unit" share explains
less: the rent is attributed to the apartment's identity, not to named
features. Rows in the fit are in-sample; the decomposition describes the
fit, not held-out prediction.

Writes /data1/apartments/frontier/variance/<run>-<commit>/result.json
(posterior mean and 90% interval of each share). Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from . import data, explain, features, model, splits
from .run import git, hardware

VARIANCE_ROOT = data.OUTPUT_ROOT / "variance"
CHUNK = 8000
GROUPS = (
    "market and time",
    "features",
    "building",
    "building over time",
    "building slopes",
    "unit",
)
FIXED = {
    "market": "market and time",
    "bedroom_market_curve": "market and time",
    "building": "building",
    "building_drift": "building over time",
    "building_bedroom_premium": "building slopes",
    "building_feature_slopes": "building slopes",
    "unit": "unit",
    "unit_drift": "unit",
}


def group_of(term: str) -> str:
    return FIXED.get(term, "features")


class Moments:
    """Per-draw streaming sums for exact covariance shares over row chunks."""

    def __init__(self, draws):
        def z():
            return np.zeros(draws)

        self.n = 0
        self.s_mu, self.s_mu2, self.s_r, self.s_r2 = z(), z(), z(), z()
        self.s_g = {g: z() for g in GROUPS}
        self.s_gmu = {g: z() for g in GROUPS}

    def add(self, groups: dict, y: np.ndarray):
        mu = sum(groups.values())
        r = y[None, :] - mu
        self.n += y.shape[0]
        self.s_mu += mu.sum(1)
        self.s_mu2 += (mu * mu).sum(1)
        self.s_r += r.sum(1)
        self.s_r2 += (r * r).sum(1)
        for g, v in groups.items():
            self.s_g[g] += v.sum(1)
            self.s_gmu[g] += (v * mu).sum(1)

    def shares(self):
        n = self.n
        var_mu = self.s_mu2 / n - (self.s_mu / n) ** 2
        var_r = self.s_r2 / n - (self.s_r / n) ** 2
        total = var_mu + var_r
        out = {
            g: (self.s_gmu[g] / n - (self.s_g[g] / n) * (self.s_mu / n)) / total
            for g in GROUPS
        }
        out["residual"] = var_r / total
        out["_r2"] = var_mu / total
        return out


def decompose(y, terms: dict):
    """Shares (per draw) for one block of rows: y (rows,), terms {name: (draws, rows)}."""
    draws = next(iter(terms.values())).shape[0]
    m = Moments(draws)
    m.add(grouped(terms, draws, y.shape[0]), y)
    return m.shares()


def grouped(terms, draws, rows):
    out = {g: np.zeros((draws, rows)) for g in GROUPS}
    for k, v in terms.items():
        out[group_of(k)] += v
    return out


def summarize(per_draw: dict):
    out = {}
    for k, v in per_draw.items():
        lo, hi = np.quantile(v, [0.05, 0.95])
        out[k.lstrip("_")] = {
            "mean": float(v.mean()),
            "lower_90": float(lo),
            "upper_90": float(hi),
        }
    return out


def score_run(name: str):
    _, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    heldout = splits.SPLITS[result["split"]](frame)
    frame = data.apply_rules(frame, result.get("data_rules", ()))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    names = [str(n) for n in feats.names]
    fslope_index = [names.index(n) for n in config.feature_slopes]
    draws = kept["alpha"].shape[0]
    moments = Moments(draws)
    train_idx = np.flatnonzero(~heldout)
    rows_per_chunk = min(CHUNK, max(500, 6_000_000 // draws))
    for chunk in np.array_split(train_idx, max(1, len(train_idx) // rows_per_chunk)):
        mask = np.zeros(len(frame), dtype=bool)
        mask[chunk] = True
        a = model.row_arrays(prep, frame, mask)
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            model.walk_spacing(config),
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
        )
        # Constants do not change variances; drop the offset for stability.
        terms["market"] = terms["market"] - prep.offset
        moments.add(grouped(terms, draws, a.y.shape[0]), a.y)
    return {
        "source_run": name,
        "source_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "rows": moments.n,
        "draws": int(draws),
        "groups": list(GROUPS),
        "shares": summarize(moments.shares()),
        "method": "covariance attribution of Var(mu) + Var(y - mu) over training rows, per kept draw",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for name in args.runs:
        out_dir = VARIANCE_ROOT / f"{name}-{commit[:7]}"
        if (out_dir / "result.json").exists():
            print(f"skip {name}: {out_dir} exists")
            continue
        t0 = time.perf_counter()
        record = score_run(name)
        record.update(
            commit=commit,
            dirty=False,
            seconds=time.perf_counter() - t0,
            hardware=hardware(),
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        sh = record["shares"]
        print(
            f"{name}: "
            + ", ".join(
                f"{g} {100 * sh[g]['mean']:.1f}%" for g in (*GROUPS, "residual")
            )
            + f" ({record['seconds']:.0f} s)",
            flush=True,
        )


if __name__ == "__main__":
    main()

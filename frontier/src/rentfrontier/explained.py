"""Explained share of building levels by candidate features, against a permutation null.

    python -m rentfrontier.explained <run-name> <candidate-feature-set> [...]

No refit. The run's building levels (the per-building intercepts of its kept
draws) are what its features leave unexplained about each building. For each
feature family of the candidate set that the run's own set lacks (its
feature group, e.g. "trees"), the family's columns are averaged over each
building's training rows and the levels are regressed on them with the
buildings held out in grouped 5-fold cross-validation:

    weights      1 / (posterior SD of the level^2 + between-building variance
                 left after the regression, net of posterior noise)
    explained    out-of-fold weighted R^2: how much of a building's level the
                 family predicts for a building the regression has not seen
                 (also the "new building" answer)
    null         the same R^2 with the family's building rows permuted across
                 buildings (PERMUTATIONS times): what a family of that many
                 columns explains by chance
    excess       explained minus the null mean

A family whose excess is near zero has nothing for the building level, so a
fit adding it is unlikely to move PSIS-LOO except through within-building
variation. The Fable research review (2026-10-08, §3) recommends this screen
before a candidate takes a full fit.

Writes /data1/apartments/frontier/explained/<run>-<set>-<commit>/result.json.
Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from . import data, explain, features, model
from .run import git, hardware

EXPLAINED_ROOT = data.OUTPUT_ROOT / "explained"
FOLDS = 5
PERMUTATIONS = 50
RIDGE = 1e-6


def _design(x):
    sd = x.std(0)
    keep = sd > 0
    z = (x[:, keep] - x[:, keep].mean(0)) / sd[keep]
    return np.column_stack([np.ones(len(x)), z])


def _wls(X, y, w):
    XtW = X.T * w
    return np.linalg.solve(XtW @ X + RIDGE * np.eye(X.shape[1]), XtW @ y)


def residual_variance(X, y, sd2, rounds=5):
    """Between-building variance left after the regression, net of posterior noise."""
    tau2 = max(y.var() - sd2.mean(), 1e-6)
    for _ in range(rounds):
        r = y - X @ _wls(X, y, 1 / (sd2 + tau2))
        tau2 = max(np.mean(r * r) - sd2.mean(), 1e-6)
    return tau2


def cv_r2(level, sd2, x, folds):
    """Out-of-fold weighted R^2 of level (B,) on x (B, k), folds (B,) in 0..K-1."""
    X = _design(x)
    pred = np.empty_like(level)
    for f in np.unique(folds):
        train = folds != f
        tau2 = residual_variance(X[train], level[train], sd2[train])
        beta = _wls(X[train], level[train], 1 / (sd2[train] + tau2))
        pred[~train] = X[~train] @ beta
    w = 1 / (sd2 + residual_variance(X[:, :1], level, sd2))
    mean = np.sum(w * level) / w.sum()
    return 1 - np.sum(w * (level - pred) ** 2) / np.sum(w * (level - mean) ** 2)


def screen(level, sd2, x, rng, folds=FOLDS, permutations=PERMUTATIONS):
    """Explained share of the levels by x, its permutation null and the excess."""
    fold = rng.permutation(np.arange(len(level)) % folds)
    r2 = cv_r2(level, sd2, x, fold)
    null = np.array(
        [
            cv_r2(level, sd2, x[rng.permutation(len(x))], fold)
            for _ in range(permutations)
        ]
    )
    return {
        "explained": float(r2),
        "null_mean": float(null.mean()),
        "null_95": float(np.quantile(null, 0.95)),
        "excess": float(r2 - null.mean()),
    }


def building_means(values, building, n_buildings):
    """Mean of each column over each building's rows: values (rows, k) -> (B, k)."""
    counts = np.bincount(building, minlength=n_buildings).astype(float)
    sums = np.zeros((n_buildings, values.shape[1]))
    np.add.at(sums, building, values)
    return sums / np.maximum(counts, 1)[:, None]


def score_run(name: str, candidate_set: str, seed=0):
    _, result, kept = explain.load_run(name)
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    frame, heldout = data.split_and_rules(
        frame, result["split"], data.recorded_rules(result)
    )
    train = ~heldout
    own = features.build(result["feature_set"], frame, train)
    cand = features.build(candidate_set, frame, train)
    prep = model.prepare(frame, heldout, own)
    a = model.row_arrays(prep, frame, train)
    levels = kept["building"]
    level, sd2 = levels.mean(0), levels.var(0)
    have = set(map(str, own.names))
    groups = np.asarray(cand.groups)
    names = np.asarray([str(n) for n in cand.names])
    x_train = cand.values[train]
    rng = np.random.default_rng(seed)
    families = {}
    for g in dict.fromkeys(cand.groups):
        cols = np.flatnonzero((groups == g) & ~np.isin(names, list(have)))
        if not len(cols):
            continue
        x = building_means(
            np.asarray(x_train[:, cols], dtype=float), a.building, len(level)
        )
        families[g] = {"columns": names[cols].tolist(), **screen(level, sd2, x, rng)}
    return {
        "source_run": name,
        "source_commit": result["commit"],
        "feature_set": result["feature_set"],
        "candidate_set": candidate_set,
        "buildings": int(len(level)),
        "folds": FOLDS,
        "permutations": PERMUTATIONS,
        "families": families,
        "method": "grouped 5-fold weighted R^2 of posterior-mean building levels, weights "
        "1/(posterior var + residual var), minus a permutation null",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    parser.add_argument("candidate_sets", nargs="+")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for cs in args.candidate_sets:
        out_dir = EXPLAINED_ROOT / f"{args.run}-{cs}-{commit[:7]}"
        if (out_dir / "result.json").exists():
            print(f"skip {cs}: {out_dir} exists")
            continue
        t0 = time.perf_counter()
        record = score_run(args.run, cs)
        record.update(
            commit=commit, seconds=time.perf_counter() - t0, hardware=hardware()
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        for g, f in record["families"].items():
            print(
                f"{cs} {g}: explained {f['explained']:.3f}, null {f['null_mean']:.3f} "
                f"(95% {f['null_95']:.3f}), excess {f['excess']:+.3f}",
                flush=True,
            )


if __name__ == "__main__":
    main()

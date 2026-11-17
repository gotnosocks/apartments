"""Score L2's held-out ads from subsets of the kept draws and compare with the whole pool.

python check.py RUN

RUN is the pooled run's directory. Its containers' directories are RUN-a, RUN-b, RUN-c.
"""

import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from rentfrontier import drift_score

CHUNK = 20000


def load(run):
    z = np.load(Path(run) / "posterior.npz")
    return {k: z["kept/" + k] for k in KEYS}


KEYS = (
    "pred_loc",
    "pred_unit_sd",
    "sigma",
    "nu",
    "phase_scale",
    "pred_y",
    "pred_group",
    "pred_phase",
)


def score(a, chains, draws):
    """Scores from the first `draws` kept draws of each of `chains`."""
    pick = lambda k: a[k][list(chains), :draws].reshape(-1, *a[k].shape[2:])  # noqa: E731
    loc, usd, sig, nu, fac = (
        pick(k) for k in ("pred_loc", "pred_unit_sd", "sigma", "nu", "phase_scale")
    )
    y, g, ph = a["pred_y"], a["pred_group"], a["pred_phase"]
    parts = []
    for i in range(0, len(y), CHUNK):
        s = slice(i, i + CHUNK)
        parts.append(
            drift_score.score_rows(
                loc[:, s], usd[:, s], sig[:, g[s]] * fac[:, ph[s]], nu, y[s], seed=i
            )
        )
    out = {k: np.concatenate([p[k] for p in parts]) for k in ("elpd", "cdf", "pred")}
    out["y"] = y
    return out


def lowest(cdf, share):
    return set(np.argsort(cdf)[: int(len(cdf) * share)])


def line(name, s, ref):
    cover = np.mean((s["cdf"] > 0.1) & (s["cdf"] < 0.9))
    rho = spearmanr(s["cdf"], ref["cdf"]).statistic
    over = [
        len(lowest(s["cdf"], p) & lowest(ref["cdf"], p)) / len(lowest(ref["cdf"], p))
        for p in (0.01, 0.1)
    ]
    print(
        f"{name:28s} elpd {s['elpd'].sum():10.1f} ({s['elpd'].sum() - ref['elpd'].sum():+8.1f})"
        f"  cover80 {100 * cover:5.2f}  |dmedian| {np.abs(s['pred'] - ref['pred']).mean():.4f}"
        f"  rho {rho:.4f}  low1% {100 * over[0]:5.1f}  low10% {100 * over[1]:5.1f}"
    )


def main(run):
    pool = load(run)
    ref = score(pool, range(pool["pred_loc"].shape[0]), pool["pred_loc"].shape[1])
    line("pool, 432 draws", ref, ref)
    del pool
    for tag in ("a", "b"):
        part = load(run + "-" + tag)
        for n in (1, 2, 4, 8):
            line(f"{tag}: chain 0, {n} draws", score(part, [0], n), ref)
        line(f"{tag}: both chains, 4 draws", score(part, [0, 1], 4), ref)
        line(f"{tag}: both chains, 72 draws", score(part, [0, 1], 72), ref)


if __name__ == "__main__":
    main(sys.argv[1])

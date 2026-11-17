"""Autocorrelation of pred_loc over sweeps, and scores from thinned stretches of a chain.

python keep1.py RUN_DIR

RUN_DIR holds the posterior.npz of a run with every sweep kept.
"""

import sys
from pathlib import Path

import numpy as np

import check

CHUNK = 60


def acf(x, lag):
    """Each row's autocorrelation at `lag` along axis 0 of x (draws, rows)."""
    d = x - x.mean(axis=0)
    return (d[lag:] * d[:-lag]).sum(axis=0) / (d * d).sum(axis=0)


def main(run):
    check.CHUNK = CHUNK
    z = np.load(Path(run) / "posterior.npz")
    a = {k: z["kept/" + k] for k in check.KEYS}
    loc = a["pred_loc"][0].astype(float)
    for lag in (1, 2, 4, 8, 16, 40):
        r = acf(loc, lag)
        print(
            f"lag {lag:3d}: median acf {np.median(r):.3f}, 90th pct {np.quantile(r, 0.9):.3f}"
        )
    n = len(a["pred_y"])
    ref = check.score(a, [0, 1], a["pred_loc"].shape[1])
    check.line(f"reference, {2 * a['pred_loc'].shape[1]} draws", ref, ref)
    for sweeps in (320, 160):
        for thin in (1, 2, 4, 8, 40):
            b = {
                k: (v[:, thin - 1 : sweeps : thin] if k in check.KEYS[:5] else v)
                for k, v in a.items()
            }
            s = check.score(b, [0], sweeps // thin)
            check.line(f"{sweeps} sweeps, 1 in {thin}", s, ref)
            print(f"    elpd an ad {(s['elpd'].sum() - ref['elpd'].sum()) / n:+.4f}")


if __name__ == "__main__":
    main(sys.argv[1])

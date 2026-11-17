"""Compare the bedroom-text pool with L2's pool on the held-out ads of the latest split.

    python docs/notes/bed-text-2026-11-16/cmp.py DATASET L2_RUN BEDTEXT_RUN

DATASET is the copy `rentfrontier.b0bedtext` wrote. Both runs hold `pred_scores.npz` from
`rentfrontier.drift_score`. I print the paired elpd difference with its SE clustered by
building, over all held-out ads and within each flag, then the median absolute errors, the
coverages, and the agreement of the two cdfs at the ask.
"""

import sys

import numpy as np
import pyarrow.parquet as pq
from scipy.stats import spearmanr

FLAGS = ("bed_flex_at", "bed_text_fewer", "bed_text_more")


def clustered(d, building):
    _, cl = np.unique(building, return_inverse=True)
    sums = np.bincount(cl, weights=d - d.mean())
    return float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))


def main(argv):
    dataset, old, new = argv
    a, b = np.load(f"{old}/pred_scores.npz"), np.load(f"{new}/pred_scores.npz")
    assert np.allclose(a["y"], b["y"], atol=1e-12)
    assert np.array_equal(a["listing"], b["listing"])
    rows = pq.read_table(f"{dataset}/rows.parquet", columns=list(FLAGS)).to_pandas()
    h = rows[a["heldout"]].reset_index(drop=True)
    h["smaller"] = h.bed_flex_at | h.bed_text_fewer
    h["unflagged"] = ~(h.smaller | h.bed_text_more)
    building = a["building"].astype(str)
    d = b["elpd"] - a["elpd"]
    print(f"ads {len(d)}, elpd L2 {a['elpd'].sum():.1f}, bedtext {b['elpd'].sum():.1f}")
    for name in ("all", "smaller", *FLAGS, "unflagged"):
        m = np.ones(len(d), bool) if name == "all" else h[name].to_numpy()
        print(
            f"{name:15s} ads {m.sum():7d}  elpd diff {d[m].sum():8.1f}"
            f"  SE {clustered(d[m], building[m]):6.1f}"
            f"  mean |miss| L2 {np.abs(a['y'][m] - a['pred'][m]).mean():.4f}"
            f" bedtext {np.abs(b['y'][m] - b['pred'][m]).mean():.4f}"
            f"  mean pred shift {(b['pred'][m] - a['pred'][m]).mean():+.4f}"
        )
    for s, name in ((a, "L2"), (b, "bedtext")):
        qs = dict(zip([float(x) for x in s["quantiles"]], s["q"].T, strict=True))
        cov = [
            100 * np.mean((s["y"] >= qs[lo]) & (s["y"] <= qs[hi]))
            for lo, hi in ((0.25, 0.75), (0.1, 0.9), (0.05, 0.95), (0.025, 0.975))
        ]
        print(
            f"{name}: median |miss| {np.median(np.abs(s['y'] - s['pred'])):.4f},"
            f" mean |miss| {np.abs(s['y'] - s['pred']).mean():.4f},"
            f" coverage {' / '.join(f'{c:.2f}' for c in cov)}"
        )
    n = len(d) // 100
    for k, share in ((n, "1%"), (10 * n, "10%")):
        lo_a, lo_b = set(np.argsort(a["cdf"])[:k]), set(np.argsort(b["cdf"])[:k])
        gone = np.array(sorted(lo_a - lo_b))
        print(
            f"lowest {share}: {len(lo_a & lo_b)} of {k} shared,"
            f" {h.smaller.to_numpy()[gone].sum()} of the {len(gone)} leaving are smaller-flagged"
        )
    print(f"spearman of cdfs {spearmanr(a['cdf'], b['cdf']).statistic:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])

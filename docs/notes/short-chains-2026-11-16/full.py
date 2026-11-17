"""Scores of a short full-data fit against a pool, and of each of its chains alone.

    python full.py SHORT_RUN POOL_RUN

Both runs hold `pred_scores.npz` from `rentfrontier.drift_score` on the same held-out ads.
SHORT_RUN also holds the posterior.npz of a run with every sweep kept. I print the short
fit's elpd lost to the pool, the coverage of both, the agreement of their cdfs at the ask,
and the elpd from each chain's draws alone.
"""

import sys

import numpy as np
from scipy.stats import spearmanr

import check


def main(short, pool):
    s, p = np.load(f"{short}/pred_scores.npz"), np.load(f"{pool}/pred_scores.npz")
    assert (s["listing"].astype(str) == p["listing"].astype(str)).all()
    d = s["elpd"] - p["elpd"]
    print(f"ads {len(d)}  elpd short {s['elpd'].sum():.1f}  pool {p['elpd'].sum():.1f}")
    print(f"short minus pool {d.sum():.1f}  an ad {d.mean():.5f}")
    for name, z in (("short", s), ("pool", p)):
        print(
            name, "80% coverage", f"{np.mean((z['cdf'] > 0.1) & (z['cdf'] < 0.9)):.4%}"
        )
    print(f"spearman of cdf {spearmanr(s['cdf'], p['cdf'])[0]:.5f}")
    for share in (0.01, 0.1):
        ref = check.lowest(p["cdf"], share)
        found = len(ref & check.lowest(s["cdf"], share)) / len(ref)
        print(f"lowest {share:.0%} of the pool found {found:.2%} of {len(ref)}")
    a = check.load(short)
    chains = a["pred_loc"].shape[0]
    each = [check.score(a, [c], a["pred_loc"].shape[1]) for c in range(chains)]
    for c, e in enumerate(each):
        print(f"chain {c} elpd {e['elpd'].sum():.1f}")
    gap = each[0]["elpd"] - each[1]["elpd"]
    print(f"chain 0 minus chain 1 {gap.sum():.1f}  sd an ad {gap.std():.5f}")
    print(
        f"spearman of the chains' cdf {spearmanr(each[0]['cdf'], each[1]['cdf'])[0]:.5f}"
    )
    for share in (0.01, 0.1):
        ref = check.lowest(each[0]["cdf"], share)
        found = len(ref & check.lowest(each[1]["cdf"], share)) / len(ref)
        print(f"lowest {share:.0%} shared by the chains {found:.2%}")


if __name__ == "__main__":
    main(*sys.argv[1:])

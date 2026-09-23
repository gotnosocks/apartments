"""Paired held-out comparison of runs against reference models.

    python -m rentfrontier.compare --split rows \
        --ref promoted=/path/nuts-hwalk/heldout.npz --ref latest=/path/nuts-latest-rows/heldout.npz \
        m5-quarterly-base-v1-rows-4226f40 m5-nu5-rows-33e8bad ...

For every (run, reference) pair: the ELPD difference summed over held-out
rows present in both, its standard error from the per-row differences, and
the number of paired rows. References can be any heldout.npz with audit_id
and lpd (log-rent scale).
"""

from __future__ import annotations

import argparse
import math

import numpy as np

from .run import RUNS


def load(path):
    z = np.load(path, allow_pickle=True)
    return dict(zip(z["audit_id"].tolist(), z["lpd"].astype(float)))


def paired(a: dict, b: dict):
    keys = sorted(set(a) & set(b))
    d = np.array([a[k] - b[k] for k in keys])
    return float(d.sum()), float(d.std(ddof=1) * math.sqrt(len(d))), len(keys)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ref", action="append", default=[], help="name=path/to/heldout.npz"
    )
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    refs = {k: load(v) for k, v in (r.split("=", 1) for r in args.ref)}
    runs = {name: load(RUNS / name / "heldout.npz") for name in args.runs}
    everything = {**{f"[ref] {k}": v for k, v in refs.items()}, **runs}
    print(f"{'model':48s} " + " ".join(f"{'vs ' + k:>24s}" for k in refs))
    for name, lpd in everything.items():
        cells = []
        for rname, ref in refs.items():
            d, se, n = paired(lpd, ref)
            cells.append(f"{d:+9.1f} ± {se:5.1f} ({n})")
        print(f"{name:48s} " + " ".join(f"{c:>24s}" for c in cells))


if __name__ == "__main__":
    main()

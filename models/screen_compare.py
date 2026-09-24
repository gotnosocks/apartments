"""Paired held-out comparison of structure screens.

Aligns candidate and baseline ``heldout.npz`` files (from `structure_screen`)
by audit ID and reports the summed log predictive density difference with
its paired standard error (sqrt(n) times the standard deviation of the
per-row differences).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def load(path):
    path = Path(path)
    data = np.load(path / "heldout.npz" if path.is_dir() else path, allow_pickle=True)
    return dict(zip(data["audit_id"].tolist(), data["lpd"]))


def compare(baseline, candidate):
    base, cand = load(baseline), load(candidate)
    if set(base) != set(cand):
        raise ValueError("Screens were scored on different held-out rows")
    ids = sorted(base)
    diff = np.array([cand[i] - base[i] for i in ids])
    return {
        "rows": len(ids),
        "delta": float(diff.sum()),
        "se": float(np.sqrt(len(diff)) * diff.std(ddof=1)),
        "better_rows": float((diff > 0).mean()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidates", type=Path, nargs="+")
    args = parser.parse_args()
    for candidate in args.candidates:
        r = compare(args.baseline, candidate)
        print(
            f"{candidate.name}: Δ={r['delta']:+.1f} ± {r['se']:.1f} "
            f"({r['delta'] / r['se']:+.1f} SE, n={r['rows']}, "
            f"{r['better_rows']:.0%} rows better)"
        )


if __name__ == "__main__":
    main()

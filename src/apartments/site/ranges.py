"""A listing's likely ask range, worked out from the summary's range atoms.

A summary run with FRONTIER_RANGE_ATOMS=1 (`rentfrontier.summary`) gives each
listing ATOMS weighted quantiles of its estimate's total log rent, at the
probabilities (i + 0.5) / ATOMS, and writes noise.json beside rows.parquet:
for each noise group, the CDF of the residual noise mixed over every draw of
Student-t(nu) noise scaled by that group's sigma, tabulated on a uniform grid.
Here the predictive CDF of the log ask at y is taken as the mean, over the
atoms, of the group's noise CDF at y less the atom, read off the grid by
linear interpolation; each range bound is found by bisecting that CDF.

On NB9 (1,529 rows in 68 groups, 2026-10-17) the bounds came within 0.00032
log units of the summary's exact solve at the median and 0.0034 at the 95th
percentile, against a Monte Carlo error of 0.0014 at the median, at 2.9 ms a
listing for the four bounds. Only the standard library is used, since the
site's environments have no numpy; the frontier tests load this file by its
path and check it against `rentfrontier.summary.predictive_quantiles`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ATOMS = 64
NOISE_FILE = "noise.json"
# The likely ask ranges the listing page shows, as (name, lower, upper).
RANGES = (("95", 0.025, 0.975), ("80", 0.10, 0.90))
STEPS = 40


class Noise:
    """A noise group's tabulated CDF: values at lower + i * step."""

    def __init__(self, lower: float, step: float, cdf: list[float]):
        self.lower, self.step, self.cdf = lower, step, cdf
        self.last = len(cdf) - 1

    def at(self, e: float) -> float:
        x = (e - self.lower) / self.step
        if x <= 0:
            return self.cdf[0]
        if x >= self.last:
            return self.cdf[-1]
        j = int(x)
        return self.cdf[j] + (x - j) * (self.cdf[j + 1] - self.cdf[j])

    @property
    def upper(self) -> float:
        return self.lower + self.last * self.step


def load_noise(path: Path) -> dict[int, Noise]:
    """noise.json as written by the summary: {"groups": {group: {"lower",
    "step", "cdf"}}}."""
    groups = json.loads(Path(path).read_text())["groups"]
    return {
        int(g): Noise(float(t["lower"]), float(t["step"]), [float(c) for c in t["cdf"]])
        for g, t in groups.items()
    }


def quantile(atoms: list[float], noise: Noise, p: float) -> float:
    """The p-quantile of the log ask, in log units."""
    lo, hi = min(atoms) + noise.lower, max(atoms) + noise.upper
    n = len(atoms)
    for _ in range(STEPS):
        mid = 0.5 * (lo + hi)
        if sum(noise.at(mid - a) for a in atoms) / n < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def likely_ask(atoms: list[float], noise: Noise) -> dict[str, float]:
    """The ranges in dollars: {"pred_lower_95": ..., "pred_upper_95": ...,
    "pred_lower_80": ..., "pred_upper_80": ...}."""
    out = {}
    for name, lower, upper in RANGES:
        out[f"pred_lower_{name}"] = math.exp(quantile(atoms, noise, lower))
        out[f"pred_upper_{name}"] = math.exp(quantile(atoms, noise, upper))
    return out

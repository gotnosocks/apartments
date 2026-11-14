"""line_sd's posterior on simulated designs with no line spread and with a small one.

The script plants unit levels and line levels on the tests' simulated design (6,000 rows,
two lines a building), as `test_a_run_recovers_a_planted_line_sd` does with a line spread of
0.15, and prints the 5%, 50% and 95% quantiles of line_sd's and unit_sd's draws from 2 chains
of 150 warmup and 300 draws. It runs from the worktree's root on the CPU."""

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "frontier"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import numpy as np  # noqa: E402
import test_drift as td  # noqa: E402
import test_drift_building_phase_line as tt  # noqa: E402

from rentfrontier import building_zones, drift, drift_line  # noqa: E402

for line_truth, unit_truth in ((0.0, 0.06), (0.03, 0.10)):
    full = td._design(n=6000, per_unit=4)
    line = tt._lines(full, k=2)
    rng = np.random.default_rng(8)
    u = unit_truth * rng.standard_normal(full.units)
    lv = line_truth * rng.standard_normal(line.max() + 1)
    full = dataclasses.replace(full, y=full.y + u[full.unit] + lv[line])
    train, test, held = tt._split(full, line)
    settings = drift_line.Settings(chains=2, warmup=150, draws=300, keep_every=5)
    groups = drift.groups_of(train, ("building",))
    out = drift_line.run(
        train,
        building_zones.Priors(),
        settings,
        log=lambda m: None,
        gp=None,
        groups=groups,
    )
    for k in ("line_sd", "unit_sd"):
        q = np.quantile(out["trace"][k], [0.05, 0.5, 0.95]).round(4)
        print("planted line_sd", line_truth, "unit_sd", unit_truth, k, q, flush=True)

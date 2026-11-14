"""How far a segment model's run narrows each path's lengthscale from its prior, and how
far a sweep can move it.

For each segment the script reads the run's draws of the path's lengthscale and amplitude
and prints:

- the mean and sd of log lengthscale within each chain, beside the prior's Normal(0, 0.5).
  An sd near 0.5 with a mean near 0 says the rows leave the lengthscale to its prior.
- the correlation of log amplitude with log lengthscale within each chain.
- the median sd of the density `drift.update_gp` draws log lengthscale from: the density
  given the path's coefficients, with the amplitude integrated out. The script evaluates it
  on a grid at every 80th draw. A conditional sd well under the chain's own sd says a sweep
  moves the lengthscale by a small part of its posterior width.
- the split R-hat and bulk ESS of the lengthscale and the amplitude.

    python docs/notes/unitkn-rehearsals-2026-11-14/lengthscale.py RUN
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import drift_building_phase_segment as segment  # noqa: E402
from rentfrontier import run  # noqa: E402
from rentfrontier.building_zones_gibbs import gp_cov  # noqa: E402

RUN = Path(sys.argv[1])
GRID = np.linspace(-3.0, 2.5, 221)
post = np.load(RUN / "posterior.npz", allow_pickle=True)
names = list(post["names"])
beta = post["trace/beta"]
trace = {k[len("trace/") :]: post[k] for k in post.files if k.startswith("trace/")}
extras = segment._segment_extras(trace, names)
col = {n: j for j, n in enumerate(names)}


def conditional_sd(f, x, amp, ls):
    """The sd over GRID of log lengthscale's density given the coefficients `f` at inputs
    `x`, with the amplitude integrated out under its InvGamma prior `amp` and the Normal
    prior `ls` on the log lengthscale."""
    logp = np.empty(len(GRID))
    for i, ll in enumerate(GRID):
        L = np.linalg.cholesky(gp_cov(np, x, np.exp(ll)))
        z = np.linalg.solve(L, f)
        logp[i] = (
            -np.log(np.diag(L)).sum()
            - (amp[0] + len(f) / 2) * np.log(amp[1] + z @ z / 2)
            - (ll - ls[0]) ** 2 / (2 * ls[1] ** 2)
        )
    p = np.exp(logp - logp.max())
    p /= p.sum()
    mean = p @ GRID
    return float(np.sqrt(p @ (GRID - mean) ** 2))


for spec in segment.segment_spec(names):
    a = np.log(extras[f"gp_amp[{spec['name']}]"])
    ls = np.log(extras[f"gp_ls[{spec['name']}]"])
    cols = [col[c] for c in spec["cols"]]
    chains = range(ls.shape[0])
    cond = [
        np.median(
            [
                conditional_sd(beta[c, i, cols], spec["x"], spec["amp"], spec["ls"])
                for i in range(0, ls.shape[1], 80)
            ]
        )
        for c in chains
    ]
    corr = [np.corrcoef(a[c], ls[c])[0, 1] for c in chains]
    print(
        f"{spec['name'][4:]}: log ls mean "
        + "/".join(f"{ls[c].mean():+.2f}" for c in chains)
        + " sd "
        + "/".join(f"{ls[c].std():.2f}" for c in chains)
        + " conditional sd "
        + "/".join(f"{s:.2f}" for s in cond)
        + " corr with log amp "
        + "/".join(f"{r:+.2f}" for r in corr)
        + f"; ls R-hat {run.split_rhat(np.exp(ls)):.3f} ESS {run.ess(np.exp(ls)):.0f}"
        + f"; amp R-hat {run.split_rhat(np.exp(a)):.3f} ESS {run.ess(np.exp(a)):.0f}"
    )

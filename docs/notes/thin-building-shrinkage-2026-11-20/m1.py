"""What the prior's degrees of freedom do to one thin building's level, by quadrature.

One building, its level eta with prior scale b and Student-t dof, and the mean residual r of
its ads with Gaussian variance v (unit level, unit drift, building path and row noise at the
held scales, the rows' own heavy tail left out). For a posterior mean L under dof 4, find r,
then the posterior mean of the same building under other dofs."""

import numpy as np
from scipy import optimize, stats

S = dict(unit=0.0613, drift=0.0443, path=0.0766, sigma=0.03)


def post_mean(r, b, v, dof):
    g = np.linspace(-1.5, 2.5, 20001)
    lp = stats.norm.logpdf(r, g, np.sqrt(v))
    lp += stats.norm.logpdf(g, 0, b) if dof is None else stats.t.logpdf(g / b, dof)
    w = np.exp(lp - lp.max())
    return (g * w).sum() / w.sum()


def v_of(n):
    # n ads in n different units, one path shared
    return (S["unit"] ** 2 + S["drift"] ** 2 + S["sigma"] ** 2) / n + S["path"] ** 2


print(
    "zone   ads  L(dof 4)   r     dof 6  dof 8  dof 12 dof 30 normal | ratio to dof 4"
)
for zone, b in (("manhattan", 0.1127), ("outer", 0.0687)):
    for n in (1, 3, 5, 10, 30):
        v = v_of(n)
        for L in (0.05, 0.15, 0.3, 0.45, 0.6):
            r = optimize.brentq(lambda x: post_mean(x, b, v, 4) - L, 0, 3)
            out = [post_mean(r, b, v, k) for k in (6, 8, 12, 30, None)]
            print(
                f"{zone:9s} {n:3d}  {L:5.2f}  {r:6.3f}  "
                + " ".join(f"{x:6.3f}" for x in out)
                + " | "
                + " ".join(f"{x / L:5.2f}" for x in out)
            )

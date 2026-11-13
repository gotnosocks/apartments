"""The shift of L1's held-out gaps in each lease phase, as a mean, a median and a Student-t
location.

The script reads L1's pool and takes each held-out ad's gap from the mean of its kept
pred_loc draws. Its scale combines the unit's predictive sd with sigma for its bedroom group
times its phase's factor, all at their posterior medians. For each phase it prints the mean
and median gap and the shift that maximizes the Student-t likelihood of the gaps at L1's
median nu. L2's fitted levels follow its Student-t noise, so the t locations show where they
are likely to fall better than the mean gaps do."""

import numpy as np
from scipy import optimize, stats

R = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")

z = np.load(R + "posterior.npz")
nu = np.median(z["kept/nu"])
sigma = np.median(z["kept/sigma"].reshape(-1, z["kept/sigma"].shape[-1]), axis=0)
factor = np.median(z["kept/phase_scale"].reshape(-1, len(PHASES)), axis=0)
print("nu", nu, "sigma", sigma.round(4), "factors", factor.round(4))
y, group, phase = z["kept/pred_y"], z["kept/pred_group"], z["kept/pred_phase"]
loc = z["kept/pred_loc"].reshape(-1, len(y)).mean(axis=0)
unit_sd = np.sqrt((z["kept/pred_unit_sd"].reshape(-1, len(y)) ** 2).mean(axis=0))
scale = np.sqrt(unit_sd**2 + (sigma[group] * factor[phase]) ** 2)
gap = y - loc
for k, name in enumerate(PHASES):
    m = phase == k
    if not m.any():
        continue

    def loss(d, m=m):
        return -stats.t.logpdf((gap[m] - d) / scale[m], nu).sum()

    shift = optimize.minimize_scalar(loss, bounds=(-0.1, 0.1), method="bounded").x
    print(
        f"{name}: {m.sum()} ads, mean {100 * gap[m].mean():.2f}%, "
        f"median {100 * np.median(gap[m]):.2f}%, t location {100 * shift:.2f}%"
    )

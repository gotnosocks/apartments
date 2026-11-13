"""Mixing of the subsample runs: per quantity, the pooled split R-hat, bulk ESS and
tau = chains * draws / ESS, the block-mean correlation of nu with unit_sd, and the
extrapolation to L1T's full pool. argv: npz files (label=path)."""

import sys
import numpy as np
from rentfrontier.run import split_rhat, ess

Q = ("nu", "unit_sd", "drift_sd", "drift_tau", "x_mlk", "x_vlk", "x_mll")
FULL = {"nu": (1.0251, 567), "unit_sd": (1.0187, 449), "drift_sd": (1.0051, 942)}
runs = {}
for arg in sys.argv[1:]:
    label, path = arg.split("=")
    z = np.load(path)
    runs[label] = {q: np.asarray(z[q], np.float64) for q in Q if q in z}
    for i in range(z["sigma"].shape[-1]):
        runs[label][f"sigma[{i}]"] = np.asarray(z["sigma"][..., i], np.float64)
qs = [q for q in runs[next(iter(runs))]]
print("quantity", *[f"{l}:rhat ess tau" for l in runs], sep=" | ")
tau = {}
for q in qs:
    row = [q]
    for l, r in runs.items():
        x = r[q]
        if np.ptp(x) == 0:
            row.append("const")
            continue
        e = ess(x)
        t = x.size / e
        tau[l, q] = t
        row.append(f"{split_rhat(x):.4f} {e:.0f} {t:.1f}")
    print(*row, sep=" | ")
for l, r in runs.items():
    b = 200

    def blocks(x):
        c, n = x.shape
        return x[:, : n // b * b].reshape(c, -1, b).mean(-1).ravel()

    print(
        l,
        "block corr nu~unit_sd",
        round(np.corrcoef(blocks(r["nu"]), blocks(r["unit_sd"]))[0, 1], 2),
        "unit_sd~drift_sd",
        round(np.corrcoef(blocks(r["unit_sd"]), blocks(r["drift_sd"]))[0, 1], 2),
    )
if "l1t" in runs and "l1tk" in runs:
    print("extrapolated to the full 6-chain pool (L1T's draws):")
    for q, (rh, es) in FULL.items():
        f = tau["l1t", q] / tau["l1tk", q]
        print(
            q,
            f"tau ratio {f:.2f}",
            f"ESS {es} -> {es * f:.0f}",
            f"R-hat {rh} -> {np.sqrt(1 + (rh**2 - 1) / f):.4f}",
        )

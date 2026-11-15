"""Between-chain offsets of the quarter coefficients in a two-chain rehearsal.

The script reads RUN's `posterior.npz`. For each segment it averages the quarter
coefficients before 2021 on every draw of the trace, then prints each chain's mean of that
average in thousandths of log rent, the chains' sd, and the average's autocorrelation at
lags 1, 40 and 400. It then takes the Manhattan studio, 1br and 2br averages together on
the kept draws and prints their correlation with each segment amplitude and lengthscale.

    python docs/notes/unitkn-segment-k10-2026-11-14/offsets.py RUN
"""

import sys
from pathlib import Path

import numpy as np


def autocorrelation(chain, lag):
    return float(np.corrcoef(chain[:-lag], chain[lag:])[0, 1])


def early(names, prefix):
    return [
        i
        for i, n in enumerate(names)
        if n.startswith(prefix) and n.split(":")[-1][:4] < "2021"
    ]


def main(run):
    posterior = np.load(Path(run) / "posterior.npz", allow_pickle=True)
    names = [str(n) for n in posterior["names"]]
    trace = posterior["trace/beta"]
    segments = sorted(
        {":".join(n.split(":")[1:3]) for n in names if n.startswith("seg:")}
    )
    for segment in segments:
        average = trace[:, :, early(names, f"seg:{segment}:")].mean(-1)
        lags = [
            round(np.mean([autocorrelation(c, lag) for c in average]), 2)
            for lag in (1, 40, 400)
        ]
        print(
            f"{segment}: chain means {np.round(average.mean(1) * 1000, 2).tolist()},"
            f" chain sd {np.round(average.std(1) * 1000, 2).tolist()},"
            f" autocorrelation at lags 1/40/400 {lags}"
        )
    kept = posterior["kept/beta"]
    manhattan = [
        i
        for i in early(names, "seg:manhattan:")
        if not names[i].startswith("seg:manhattan:3br+")
    ]
    average = kept[:, :, manhattan].mean(-1).reshape(-1)
    for key in ("gp_amp", "gp_ls"):
        values = posterior[f"kept/{key}"]
        correlations = [
            round(float(np.corrcoef(average, values[:, :, j].reshape(-1))[0, 1]), 2)
            for j in range(values.shape[-1])
        ]
        print(f"Manhattan studio-2br early average against {key}: {correlations}")


if __name__ == "__main__":
    main(sys.argv[1:][0])

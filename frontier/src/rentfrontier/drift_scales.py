"""Sets of scales for `rentfrontier.drift`'s sweep to hold in place of drawing them
(`drift.Settings.scales_fixed`, `--scales-fixed NAME` on the command line).

A set gives a value to each scale of one or more of the sweep's scale steps
(`drift.HELD_STEPS`). The sampler starts every chain at those values, skips the steps, and
draws the coefficients, the market's weekly level, the buildings' levels and paths, the
units' levels and the rows' mixing weights given them. With the scales held, the rest of the
model is Gaussian given the mixing weights. On the k50 subsample a sweep took 63% of an
ordinary sweep's time, and the slowest quantity left was a coefficient
(`docs/notes/scales-fixed-2026-11-17.md`).

Each value below is the mean of a scale's draws in a pool of the base model
(`drift-building`, Student-t(4) building levels) that passed the convergence gate. Every
scale held here had a posterior sd under 6% of its mean in that pool. The wave amplitudes
(`amp`) and the floor curves' amplitudes and lengthscales (`gp_amp`, `gp_ls`) had sds of 11%
to 44% of their means, so the sets leave them for the sweep to draw.

A fit with held scales treats them as known. Its intervals leave out the scales' own
uncertainty, and its gate covers the quantities the sweep draws. A backtest takes the set of
the pool fitted on the same training rows, so that no rent after the scoring day reaches it
through a scale.

`SOURCES` names each set's pool, and a run's result records the set, its source and its
values.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import run as run_module

SETS = {
    # The market split: every ad to date.
    "base-n9": {
        "nu": 1.7257513434161218,
        "sigma": [
            0.0203229012992943,
            0.019107108991231293,
            0.022733146093709158,
            0.028626390743474093,
        ],
        "unit_sd": 0.06129716043473202,
        "drift_sd": 0.04426767931762685,
        "drift_tau": 8.898691532416901,
        "bld_sd": [0.11266033376720432, 0.06869990818652631],
        "building_ar_sd": 0.07662960021093765,
        "building_ar_rho": 0.8944791418236825,
        "tau": 0.003357891234989467,
    },
    # The backtest as of 2025-11-10.
    "base-j9": {
        "nu": 1.7223646637469514,
        "sigma": [
            0.02062192891973642,
            0.019277193612707487,
            0.02272302479328061,
            0.028575838108767074,
        ],
        "unit_sd": 0.06039016866105182,
        "drift_sd": 0.04504629870009311,
        "drift_tau": 9.176242242153204,
        "bld_sd": [0.11286166616432691, 0.06993578930332685],
        "building_ar_sd": 0.07414869021517113,
        "building_ar_rho": 0.8794664001522584,
        "tau": 0.003467799780454648,
    },
}

SOURCES = {
    "base-n9": "the pool drift-building-b0-market-67d14e17-n9 (market split, 17,360 draws)",
    "base-j9": "the pool drift-building-b0-market-67d14e17-j9 "
    "(dataset b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110, 19,840 draws)",
}


def resolve(spec: str) -> tuple[dict, str]:
    """Load a held-scale set from either `SETS[spec]` or a converged run directory.

    When `spec` names an existing run directory (or a run under `run.RUNS`), extracts the
    posterior means of the scale parameters (`nu`, `sigma`, `unit_sd`, `drift_sd`,
    `drift_tau`, `bld_sd`, `building_ar_sd`, `building_ar_rho`, `tau`, and optional
    `phase_scale`) directly from `posterior.npz` and `result.json` so any converged
    unified base fit can power fast held-scales refreshes or backtests."""
    if spec in SETS:
        return dict(SETS[spec]), SOURCES[spec]
    cand = Path(spec)
    if not cand.exists():
        cand = run_module.RUNS / spec
    npz_path = cand / "posterior.npz"
    res_path = cand / "result.json"
    if not npz_path.exists() or not res_path.exists():
        raise KeyError(
            f"unknown scales_fixed set {spec!r}: not in drift_scales.SETS and no "
            f"posterior.npz/result.json at {cand}"
        )
    rec = json.loads(res_path.read_text())
    scales: dict = {}
    with np.load(npz_path) as z:
        for key in (
            "nu",
            "unit_sd",
            "drift_sd",
            "drift_tau",
            "building_ar_sd",
            "building_ar_rho",
            "tau",
        ):
            if f"kept/{key}" in z:
                scales[key] = float(np.mean(z[f"kept/{key}"]))
        if "nu" not in scales and rec.get("row_dof_fixed") is not None:
            scales["nu"] = float(rec["row_dof_fixed"])
        for key in ("sigma", "bld_sd"):
            if f"kept/{key}" in z:
                arr = np.asarray(z[f"kept/{key}"], float)
                scales[key] = np.mean(arr, axis=tuple(range(arr.ndim - 1))).tolist()
        if "kept/phase_factor" in z:
            arr = np.asarray(z["kept/phase_factor"], float)
            scales["phase_scale"] = np.mean(
                arr, axis=tuple(range(arr.ndim - 1))
            ).tolist()
        elif "kept/phase_scale" in z:
            arr = np.asarray(z["kept/phase_scale"], float)
            # Drop the fixed reference slot 0 when phase_scale stores full (1 + free) cells
            if arr.shape[-1] > 1 and np.allclose(arr[..., 0], 1.0):
                scales["phase_scale"] = np.mean(
                    arr[..., 1:], axis=tuple(range(arr.ndim - 1))
                ).tolist()
    source = f"run {cand.name} (split={rec.get('split')})"
    return scales, source

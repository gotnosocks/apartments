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
    # Full-NYC c2-monthly backtest as of 2025-11-10 (39 phase/mark/sv_gp_mo/attr_changes factors).
    "c2mo-j": {
        "nu": 2.0,
        "sigma": [
            0.011422050161074797,
            0.011422050161074797,
            0.011422050161074797,
            0.011422050161074797,
        ],
        "unit_sd": 0.04207362061472837,
        "drift_sd": 0.029670772213478438,
        "drift_tau": 3.141398651062231,
        "bld_sd": [0.11023313351279981, 0.07376077544034264],
        "building_ar_sd": 0.06680006523417908,
        "building_ar_rho": 0.9375323439813805,
        "tau": 0.00367844282931678,
        "phase_scale": [
            1.5631780273701261,
            1.07153946545396,
            1.421484635803438,
            1.174805934672596,
            0.9834452947382035,
            1.1134008436300777,
            1.525984067741542,
            1.4598278740235218,
            2.9538210203571826,
            1.1047159729923004,
            1.7568438918640878,
            1.530392405405086,
            0.9979354106053162,
            0.7252754430275109,
            0.9418641928921672,
            1.4617564127393239,
            1.0685458493803055,
            0.7137291489326821,
            0.8946067226154946,
            1.7511825705944275,
            1.0972100226969885,
            0.647844463372168,
            0.808652820363854,
            1.2649423988013841,
            1.1583117067711555,
            0.6885712948702776,
            0.4861342737847454,
            1.4199851132293133,
            0.7338770925349631,
            0.8003128318951398,
            0.5301711839198692,
            0.47574955995383045,
            0.6257110095107645,
            0.7616523109548623,
            1.1999502438270822,
            0.9927640999580795,
            1.159153562636025,
            1.2090055641981412,
            1.3365252566884624,
        ],
    },
}
# Full-NYC c2-monthly backtest with wave amp and segment GP scales also held (for EM-Laplace / ultra-fast refreshes).
SETS["c2mo-j-all"] = {
    **SETS["c2mo-j"],
    "amp": [0.8379816034092314, 0.4728971594497194],
    "gp_amp": [
        0.05479311538422436,
        0.014387025600123112,
        0.02266828995443265,
        0.05365115140080262,
    ],
    "gp_ls": [
        1.039026941269524,
        0.7340111817686347,
        0.7176299510934335,
        0.7988080116893519,
    ],
}

SOURCES = {
    "base-n9": "the pool drift-building-b0-market-67d14e17-n9 (market split, 17,360 draws)",
    "base-j9": "the pool drift-building-b0-market-67d14e17-j9 "
    "(dataset b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110, 19,840 draws)",
    "c2mo-j": "run drift-building-phase-unitkn-ablate-b0-market-e87b2e2e-pf-full-c2mo "
    "(dataset b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext, 8,800 draws)",
    "c2mo-j-all": "run drift-building-phase-unitkn-ablate-b0-market-e87b2e2e-pf-full-c2mo "
    "(all scales incl. amp and gp_amp/gp_ls held, 8,800 draws)",
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

"""Check that the page's per-row reconstruction reproduces a fit's saved residuals.

The main page (``src/apartments/bayesian_analysis.py``) rebuilds each row's mu
from posterior draws plus version-specific location terms
(``bayesian_location_terms_v2``) and refuses a fit whose reconstruction
differs from ``residuals.jsonl``. It only opens fits that pass their
convergence gates, so this script runs the same arithmetic on any fit,
including short smoke fits:

    python -m models.reader_parity_check <experiment> <dataset> [--rows 60]

It prints the maximum relative difference of the 2.5/50/97.5% latent rent
quantiles over randomly chosen rows (about 1e-15 when the reader matches).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments import bayesian_analysis as page

from . import bayesian_feature_report as report
from . import bayesian_location_terms_v2 as location_terms
from .bayesian_feature_design_v2 import load_design


def values(array):
    return np.asarray(array.values, float).reshape((-1, *array.shape[2:]))


def max_relative_difference(experiment, dataset, rows=60, seed=0):
    experiment, dataset = Path(experiment), Path(dataset)
    protocol = json.loads((experiment / "protocol/protocol.json").read_text())
    source = report.jsonl((dataset / "observations.jsonl").read_bytes())
    data = page._frame(source)
    with threadpool_limits(limits=1, user_api="blas"):
        design = load_design(experiment / "fit", data, protocol)
    posterior = xr.open_dataset(
        experiment / "fit/posterior.nc", group="posterior", engine="h5netcdf"
    )
    draws = {
        name: values(posterior[name])
        for name in (
            "alpha",
            "beta",
            "trend_coefficients",
            "annual_drift",
            "season_coefficients",
            "sigma_unit",
        )
    }
    for name in location_terms.variable_dims(protocol):
        draws[name] = values(posterior[name])
    context = location_terms.prepare(protocol, design, data)

    def select(name, start, stop):
        variable = posterior[name]
        return values(variable.isel({variable.dims[-1]: slice(start, stop)}))

    saved = {
        r["audit_id"]: r
        for r in report.jsonl((experiment / "fit/residuals.jsonl").read_bytes())
    }
    chosen = np.random.default_rng(seed).choice(len(source), rows, replace=False)
    worst = 0.0
    d = design.time
    for i in chosen:
        row = source[i]
        frame = page._frame([row])
        a = d.arrays(frame)
        x = design.matrix(frame)[0]
        period, month = a["period"][0], a["season"][0]
        mu = (
            draws["alpha"]
            + draws["beta"] @ x
            + draws["trend_coefficients"] @ (d.time_matrix - d.time_center)[period]
            + draws["annual_drift"] * (d.linear_time - d.linear_center)[period]
            + draws["season_coefficients"]
            @ (d.season_matrix - d.season_weights @ d.season_matrix)[month]
            + values(posterior["building_effect"].sel(building=row["building"]))
            + draws["sigma_unit"] * values(posterior["unit_z"].sel(unit=row["unit_id"]))
        )
        terms = location_terms.row_terms(
            protocol, draws, frame, design, select, context
        )
        for value in terms.values():
            mu = mu + value
        quantiles = np.exp(np.quantile(mu, [0.025, 0.5, 0.975]))
        s = saved[row["audit_id"]]
        expected = np.array(
            [s["latent_rent_lower_95"], s["fitted_rent"], s["latent_rent_upper_95"]]
        )
        worst = max(worst, float(np.max(np.abs(quantiles / expected - 1))))
    posterior.close()
    return worst


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--rows", type=int, default=60)
    args = parser.parse_args()
    worst = max_relative_difference(args.experiment, args.dataset, args.rows)
    print(f"rows {args.rows} max relative difference {worst:.3g}")


if __name__ == "__main__":
    main()

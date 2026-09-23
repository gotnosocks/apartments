"""Sampler-efficiency benchmark on the promoted building-drift specification.

Research-plan items E1/E2 (iteration speed): short full-data NUTS runs that
measure wall time, leapfrog steps per iteration, tree depth and ESS per
second for the slow directions (intercept, global scales). Not a fit
protocol; it saves only a small JSON of timings and diagnostics.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as v3
from . import bayesian_floor_spline_design as floor
from . import bayesian_structure_graph_v3 as graph

GLOBALS = (
    "alpha",
    "sigma",
    "sigma_unit",
    "sigma_building",
    "annual_drift",
    "trend_scale",
    "season_scale",
    "bedroom_walk_scale",
    "building_time_scale",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adaptation", choices=("diag", "low_rank"), default="diag")
    parser.add_argument("--tune", type=int, default=500)
    parser.add_argument("--draws", type=int, default=500)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--target-accept", type=float, default=0.93)
    parser.add_argument(
        "--unit-centering", choices=("none", "building"), default="none"
    )
    parser.add_argument(
        "--intercept", choices=("global", "building_mean"), default="global"
    )
    parser.add_argument(
        "--walk-centering", choices=("none", "across_buildings"), default="none"
    )
    parser.add_argument(
        "--feature-basis", choices=("identity", "qr"), default="identity"
    )
    args = parser.parse_args()
    import arviz as az
    import nutpie

    # A directory output (the Modal worker's convention) gets result.json.
    if args.output.suffix != ".json":
        args.output.mkdir(parents=True, exist_ok=True)
        args.output = args.output / "result.json"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data, _ = v3.load_data(args.dataset)
    design = floor.FeatureDesign(data, "full_half_balance", floor_prior_scale=0.10)
    model = graph.build_model(
        data,
        design,
        building_time="walk",
        building_knot_years=0.5,
        building_scale_prior=0.1,
        unit_centering=args.unit_centering,
        intercept=args.intercept,
        walk_centering=args.walk_centering,
        feature_basis=args.feature_basis,
    )
    started = time.monotonic()
    compiled = nutpie.compile_pymc_model(model, backend="numba")
    compiled_at = time.monotonic()
    trace = nutpie.sample(
        compiled,
        draws=args.draws,
        tune=args.tune,
        chains=args.chains,
        cores=args.chains,
        seed=args.seed,
        adaptation=args.adaptation,
        target_accept=args.target_accept,
        progress_bar=False,
    )
    sampled_at = time.monotonic()
    posterior = trace["posterior"].to_dataset()
    stats = trace["sample_stats"].to_dataset()
    sampling_seconds = sampled_at - compiled_at
    per_draw = sampling_seconds / (args.tune + args.draws)
    ess = {}
    for name in GLOBALS:
        summary = az.summary(posterior[[name]], kind="diagnostics", round_to="none")
        ess[name] = {
            "ess_bulk": float(summary.ess_bulk.iloc[0]),
            "ess_tail": float(summary.ess_tail.iloc[0]),
            "r_hat": float(summary.r_hat.iloc[0]),
            "ess_bulk_per_second": float(summary.ess_bulk.iloc[0])
            / (sampling_seconds * args.draws / (args.tune + args.draws)),
        }
    beta = az.summary(posterior[["beta"]], kind="diagnostics", round_to="none")
    result = {
        "adaptation": args.adaptation,
        "unit_centering": args.unit_centering,
        "intercept": args.intercept,
        "walk_centering": args.walk_centering,
        "feature_basis": args.feature_basis,
        "tune": args.tune,
        "draws": args.draws,
        "chains": args.chains,
        "compile_seconds": compiled_at - started,
        "sampling_seconds": sampling_seconds,
        "seconds_per_iteration": per_draw,
        "mean_steps_per_draw": float(stats["n_steps"].mean()),
        "max_depth": float(stats["depth"].max()) if "depth" in stats else None,
        "mean_depth": float(stats["depth"].mean()) if "depth" in stats else None,
        "divergences": int(stats["diverging"].sum()),
        "globals": ess,
        "beta_min_ess_bulk": float(beta.ess_bulk.min()),
        "beta_slowest": {
            name: float(value)
            for name, value in beta.ess_bulk.sort_values().head(6).items()
        },
        "beta_max_r_hat": float(beta.r_hat.max()),
    }
    args.output.write_text(json.dumps(result, indent=1) + "\n")
    slowest = min(ess, key=lambda k: ess[k]["ess_bulk"])
    print(
        json.dumps(
            {
                "adaptation": args.adaptation,
                "sampling_seconds": round(sampling_seconds),
                "steps_per_draw": round(result["mean_steps_per_draw"], 1),
                "slowest": slowest,
                "slowest_ess_per_second": round(ess[slowest]["ess_bulk_per_second"], 3),
            }
        )
    )


if __name__ == "__main__":
    with threadpool_limits(limits=1, user_api="blas"):
        main()

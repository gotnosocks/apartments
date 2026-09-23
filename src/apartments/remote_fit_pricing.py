"""Reproduce a local ``fit-pricing`` run on Modal with an identical runner Namespace.

``fit-pricing`` defaults differ from the runners' own argparse defaults, so every
option is passed explicitly. Parsing the returned argv with the runner's parser must
yield the Namespace the local path builds; that is what makes the remote protocol hash
equal a local one. Only the Modal path imports ``models.modal_remote_fit``.
"""

from __future__ import annotations

from pathlib import Path

RUNNERS = {
    "spline": "models.bayesian_floor_spline_experiment",
    "increments": "models.bayesian_disk_experiment",
    "linear": "models.bayesian_disk_experiment",
}
# Keys the local path sets that a runner's parser lacks and that runner never reads.
IGNORED_BY_RUNNER = {
    "spline": {"floor_increments", "floor_increment_prior_scale"},
    "increments": {"floor_prior_scale"},
    "linear": {"floor_prior_scale"},
}
MODAL_DEFAULTS = {"cpu": 4.0, "memory": 16384, "timeout": 6 * 3600}


def runner_argv(args, floor):
    """Runner argv (without --dataset/--output) for the post-processed local Namespace."""
    argv = [
        "--draws", str(args.draws),
        "--tune", str(args.tune),
        "--chains", str(args.chains),
        "--seed", str(args.seed),
        "--spec", args.spec,
        "--residual-scale", args.residual_scale,
        "--target-accept", repr(float(args.target_accept)),
        "--adaptation", args.adaptation,
        "--prior-multiplier", repr(float(args.prior_multiplier)),
        "--building-prior-scale", repr(float(args.building_prior_scale)),
        "--unit-prior-scale", repr(float(args.unit_prior_scale)),
        "--residual-parameterization", args.residual_parameterization,
    ]  # fmt: skip
    if args.graph_validation is not None:
        argv += ["--graph-validation", str(Path(args.graph_validation).resolve())]
    if args.maxdepth is not None:
        argv += ["--maxdepth", str(args.maxdepth)]
    if floor == "spline":
        argv += ["--floor-prior-scale", repr(float(args.floor_prior_scale))]
    else:
        argv += [
            "--floor-increment-prior-scale",
            repr(float(args.floor_increment_prior_scale)),
        ]
        if floor == "increments":
            argv.append("--floor-increments")
    return argv


def submit_argv(
    args, floor, *, cpu=None, memory=None, timeout=None, full=False, detach=False
):
    """``models.modal_remote_fit`` argv that runs ``floor``'s runner on Modal."""
    inputs = (
        []
        if args.graph_validation is None
        else ["--input", str(Path(args.graph_validation).resolve())]
    )
    return [
        "run",
        "--dataset", str(Path(args.dataset).resolve()),
        "--output", str(args.output),
        "--runner", RUNNERS[floor],
        "--label", f"fit-pricing-{floor}",
        "--cpu", repr(float(MODAL_DEFAULTS["cpu"] if cpu is None else cpu)),
        "--memory", str(MODAL_DEFAULTS["memory"] if memory is None else memory),
        "--timeout", str(MODAL_DEFAULTS["timeout"] if timeout is None else timeout),
        *inputs,
        *(["--full"] if full else []),
        *(["--detach"] if detach else []),
        "--",
        *runner_argv(args, floor),
    ]  # fmt: skip

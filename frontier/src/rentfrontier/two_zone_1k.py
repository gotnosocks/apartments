"""Two-zone location at a 1 km length-scale.

This is the two-zone model (`rentfrontier.two_zone`) with each surface's kernel length-scale
at 1 km in place of 500 m, and nothing else changed. I keep the zones, the rotated boxes, the
widening C = 1.5, the centred coefficients, the HalfNormal(0.3) amplitudes, the row-weighted
centring and the registry.

At 500 m the Manhattan surface took amplitude 3.7 and put its largest coefficients, up to 25
prior sds, on the fastest waves in its box. Those waves correlated up to 0.97 with their
neighbours, ChEES-HMC's step size fell to 0.0016, and every other parameter stalled with it.
At 1 km I take half as many waves per axis, ceil(1.75 C S / 1), and the kernel's spectral sd
falls off twice as fast with frequency. So the surface has no waves shorter than about 1.3 km
across Manhattan, and rent changes between neighbouring blocks go to the residual.

    python -m rentfrontier.two_zone_1k prior DATASET [--rows N]
    python -m rentfrontier.run --model two-zone-1k --split latest --name NAME [--chains 16 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import b0, b0_1, two_zone
from .two_zone import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    KEPT,
    PROGRESS,
    REGISTRY,
    TRACED,
    ZONES,
    Design,
    Priors,
    cell_log_premiums,
    diagnostics,
    initial_values,
    log_density,
    modal_contrasts,
    model,
    prior_arrays,
    prior_draws,
    prior_predictive,
    run_record,
    site_share,
    split_index,
    subset,
    summarize,
    surface_draws,
)

NAME = "two-zone-1k"
LENGTHSCALE = 1.0  # km


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
) -> Design:
    """The two-zone design of `frame` with 1 km surfaces."""
    return two_zone.design(frame, start, registry, lengthscale=LENGTHSCALE)


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the two-zone model at 1 km."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model two-zone-1k`: fit on the split's training rows and save."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--max-leapfrog-steps", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=b0_1.Settings,
        sample=run,
        line="baseline-blackjax",
        spec=sys.modules[__name__],
    )


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prior", help="prior predictive check")
    pp.add_argument("dataset", type=Path)
    pp.add_argument("--rows", type=int, default=50_000)
    pp.add_argument("--draws", type=int, default=200)
    args = p.parse_args(argv)
    if args.cmd == "prior":
        frame = b0.load_frame(args.dataset)
        print(
            json.dumps(
                prior_predictive(design(frame), Priors(), args.draws, args.rows),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

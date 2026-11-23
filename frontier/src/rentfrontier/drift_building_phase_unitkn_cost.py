"""The ablate model (`drift_building_phase_unitkn_ablate`) with arms that make a fit cheaper.

    python -m rentfrontier.run --model drift-building-phase-unitkn-cost \
        --variant layrng,size,sv_gp_mo,marks,bld_semi ...

`--variant` takes every ablate token and these:

- `bld_semi`: the buildings' AR(1) paths in half-years, not quarters. A building then has
  at most 26 cells in place of 52, and the collapsed step's dense factors shrink with it.
  The quarterly rho came out near 0.83 a quarter (`drift.groups_of`), so half-years lose
  the path's within-half-year wiggle and keep the rest.
- `bld_annual`: the same in years (at most 13 cells).
- `no_slow`: no `update_slow` step (`Settings.slow_columns` empty). The `bld:` columns are
  then drawn only with the rest of theta. The model is the same; only the sweep changes,
  so this arm is judged on time and ESS, not elpd.

Everything else is the ablate module's, read through it, so an ablate token means the same
here as there.
"""

from __future__ import annotations

import dataclasses
import sys

from . import drift
from . import drift_building_phase_unitkn_ablate as ablate
from .drift import Design, Priors, Settings

NAME = "drift-building-phase-unitkn-cost"
STEPS_PER_YEAR = {"bld_semi": 2, "bld_annual": 1}
COST_TOKENS = (*STEPS_PER_YEAR, "no_slow")
# The cost tokens of the current CLI run (set in `main_run`).
ACTIVE_COST: tuple[str, ...] = ()


def __getattr__(name):
    # The spec drift.main_run and b0 read (design, summarize, run_record's helpers and the
    # rest) is the ablate module's.
    return getattr(ablate, name)


def split_variant(tokens) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`tokens` as (ablate tokens, cost tokens). Two step sizes are refused."""
    cost = tuple(t for t in tokens if t in COST_TOKENS)
    if sum(t in STEPS_PER_YEAR for t in cost) > 1:
        raise ValueError(f"pick one building step size, not {cost}")
    rest = ablate.parse_variant(",".join(t for t in tokens if t not in COST_TOKENS))
    return rest, cost


def groups(d: Design, cost=None) -> list[dict]:
    """The ablate model's local-drift terms, with the buildings' steps a year set by a
    step token in `cost`."""
    cost = ACTIVE_COST if cost is None else cost
    out = drift.groups_of(d, ablate.GROUPS)
    for t in cost:
        if t in STEPS_PER_YEAR:
            for g in out:
                if g["name"] == "building":
                    g["per_year"] = STEPS_PER_YEAR[t]
    return out


def settings_for(settings: Settings, cost=None) -> Settings:
    cost = ACTIVE_COST if cost is None else cost
    if "no_slow" in cost:
        return dataclasses.replace(settings, slow_columns=())
    return settings


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """The ablate model's sweep with the cost tokens applied."""
    return drift.run(
        d,
        priors,
        settings_for(settings),
        log,
        checkpoint,
        gp=ablate.gp_spec(d.names) or "spec",
        groups=groups(d),
        unit_t=True,
        unit_dof_fixed=ablate.UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ablate.ROW_DOF,
        phase_collapsed=d.phase_map is not None and d.phase_map.shape[1] > 0,
    )


def run_record(d: Design) -> dict:
    return ablate.run_record(d) | {"cost_variant": list(ACTIVE_COST)}


def strip_cost(argv) -> tuple[list[str], tuple[str, ...]]:
    """`argv` with the cost tokens taken out of `--variant`, and those tokens."""
    out, cost = [], ()
    argv = list(argv)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--variant" and i + 1 < len(argv):
            flag, spec, i = "--variant", argv[i + 1], i + 2
        elif a.startswith("--variant="):
            flag, spec, i = None, a.split("=", 1)[1], i + 1
        else:
            out.append(a)
            i += 1
            continue
        tokens = [t.strip() for t in spec.split(",") if t.strip()]
        rest, cost = split_variant(tokens)
        value = ",".join(rest)
        out += [flag, value] if flag else [f"--variant={value}"]
    return out, cost


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-cost --variant ...`."""
    global ACTIVE_COST
    argv, ACTIVE_COST = strip_cost(argv)
    ablate.ACTIVE_VARIANT, rest = ablate._extract_variant(argv)
    drift.main_run(
        rest,
        name=NAME,
        sample=run,
        spec=sys.modules[__name__],
        level_dof=ablate.LEVEL_DOF,
    )

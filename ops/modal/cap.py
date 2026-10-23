"""The Modal budget: dollars accrue at the rate of 10 full fits a day; a fit launches only once
the balance covers its estimated cost.

Ben, 2026-10-07 21:59Z: "we should accumulate Modal dollars at a rate consistent with 10 full
fits per day, and only spend on a partial or full fit after we have accumulated enough for the
estimated cost. If our estimate is too low, the accumulation should continue from the negative
balance. e.g. $0 -> $10 -> -$0.50 -> $3 -> $1 -> $10 etc."

The balance starts at $0 at START and accrues at the rates in RATES: 10 x the estimated cost of
the NB5 served full fit ($8.80) a day, then $10 a day from Ben's message of 2026-10-10 16:25Z. A launch is charged its estimate when it takes its turn (reserve); when the fit returns,
the launcher settles it at the container's list-price cost (or the time it ran, if it failed), so
an estimate that was too low leaves the balance negative and accrual continues from there. Ben,
2026-10-07 22:23Z: "I would like to cap the balance on the dollar budget at ~10 full fits", so
the balance stops accruing at CEILING = USD_PER_DAY. Launches before START (the old daily cap) are not charged.

Ben, 2026-10-14 09:57Z, on a single fit: "I'm pretty hard capped at about 1 hour or maybe $2 of
modal compute." A launch whose estimated container time is over PER_FIT_SECONDS is refused
however much balance there is. Ben confirmed on 2026-10-14 (18:42Z) that the cap is the hour and
that C-sized fits at about $2.60 are fine, so PER_FIT_USD stays None and no launch is refused on
its dollar estimate.

    python3 ops/modal/cap.py                                  # balance, rate, recent launches
    python3 ops/modal/cap.py --check [CHAINS WARMUP DRAWS]    # exit 1 until the balance covers that
                                                              # fit (default: the served full fit),
                                                              # exit 2 if it is over the per-fit cap
    python3 ops/modal/cap.py --check-launch ARGS...           # the same, from ops/modal-fit's ARGS

Ben approved fits outside the budget for the full all-scraped dataset (2026-10-16 14:55Z). A
launch with --outside-budget goes in the ledger as an "outside" row carrying its estimate, and it
settles like any other launch, so its cost stays on record. The balance skips those rows, and the
balance check lets such a launch through.
"""

import datetime
import fcntl
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

LEDGER = Path(
    "/data1/apartments/modal/ledger.jsonl"
)  # fixed: no other ledger, no override
ZONE = ZoneInfo("America/New_York")
START = datetime.datetime(2026, 10, 7, 21, 59, 49, tzinfo=datetime.UTC)  # Ben's message
# Container list price per hour, app.usd_per_second(gpu) * 3600 (kept equal by a test; app.py
# imports modal, so the launcher's plain python3 can't import it).
USD_PER_HOUR = {"L4": 1.0851, "A100-40GB": 2.3851, "A100-80GB": 2.7841, "H100": 4.2351}
# The same for a large fit's container, app.usd_per_second(gpu, large=True) * 3600.
USD_PER_HOUR_LARGE = {
    "A100-40GB": 4.0107,
    "A100-80GB": 4.4097,
    "H100": 5.8607,
    "H200": 6.4517,
}
# Wall time of a fit's GPU container: OVERHEAD_SECONDS for the upload, image, PSIS-LOO and the
# post-fit statistics, plus the fit stage at SECONDS_PER_ITERATION an iteration per pair of
# chains, or at the model's own rate on its last Modal fit if that was slower (measured_rate).
# The 2 x 4,800-iteration A100 fits of 2026-10-12..13 spent 580 to 784 s outside the fit stage
# and 0.30 to 0.50 s an iteration in it; areatime spent 0.70 s on 2026-10-11. Fits whose summary
# bundle hit its 1,200 s cap ran 3,020 to 4,154 s in all and settle above their estimate;
# TIMEOUT in app.py stops a runaway.
OVERHEAD_SECONDS, SECONDS_PER_ITERATION = 800, 0.42
RUNS = (
    Path(os.environ.get("FRONTIER_OUTPUT_ROOT", "/data1/apartments/frontier")) / "runs"
)
# The new-building score's CPU container (app.newbuilding_cpu) after each finished fit: 202 to
# 227 s, $0.14, on 2026-10-13, at app.nb_usd_per_second() * 3600 an hour (kept equal by a test).
NEWBUILDING_SECONDS, NEWBUILDING_USD_PER_HOUR = 240, 2.5321
# The baseline scoring's CPU container (app.score_cpu, fit.py --cpu-score) after a GPU stage that
# leaves its draws on the Volume: the container's staging and start (SCORE_OVERHEAD_SECONDS), then
# SCORE_SECONDS_PER_DRAW a kept draw, measured on 8 of thelio's 12 cores (80.8 s) for B0.1's 656-draw,
# 1.2M-row w1500 run, with the 16 cores of the container taken as no faster. USD_PER_HOUR is
# app.score_usd_per_second() * 3600 (kept equal by a test).
SCORE_OVERHEAD_SECONDS, SCORE_SECONDS_PER_DRAW, SCORE_USD_PER_HOUR = 90, 0.12, 1.0103
# PSIS-LOO inside the GPU container, per kept draw, when no earlier fit of the model measured it:
# B0.1's w1500 run took 1,215 s for its 656 draws (2026-10-18).
GPU_LOO_SECONDS_PER_DRAW = 1.9
SERVED_FIT = (
    2,
    300,
    4500,
)  # chains, warmup, draws: the full fit since #432 ($2.17, 3,256 s)
# The per-fit cap, on the estimate before launch (Ben, 2026-10-14 09:57Z): an hour. There is no
# dollar cap per fit (Ben, 2026-10-14 18:42Z: C-sized fits at about $2.60 are fine).
PER_FIT_SECONDS = 3600
PER_FIT_USD = None
# What the ledger's history was priced at: the accrual rate before 2026-10-10 16:25Z and a launch
# row from the old launcher (no estimate) are 10 x and 1 x the NB5 served-fit estimate, kept
# fixed so recalibrating the estimate never reprices the past.
NB5_SERVED_FIT_USD = 0.88
# A BlackJAX model with no Modal fit yet is estimated from the model it runs beside on the same
# sampler: B0.2 has B0.1's rows, sampler and about as many parameters, with the 15 bed-bath
# interaction steps in place of the slope walk's scale and its smoothness. B0.3 has B0.2's
# parameters with the bath steps regrouped, and B0.4 B0.3's with 915 location coefficients
# (340 Manhattan, 575 Brooklyn) evaluated at 68k buildings, which makes each gradient dearer
# than B0.3's, so its first fit can run over the estimate.
STAND_IN = {"b0.2": "b0.1", "b0.3": "b0.1", "b0.4": "b0.3"}
# The centered walk has B0.3's parameters, with the 672 levels in place of its 672 shocks.
STAND_IN["centered-walk"] = "b0.3"
# The level walk has the centered walk's parameters, with the intercept moved into the levels.
STAND_IN["level-walk"] = "centered-walk"
# The total walk has them too, with the season moved into the levels.
STAND_IN["total-walk"] = "centered-walk"
# The normal walk has the total walk's, with each bath step sampled directly in place of the
# pooled steps, their means and their spread, and no shock degrees of freedom.
STAND_IN["normal-walk"] = "centered-walk"
# Two-zone location has the normal walk's, with 780 location coefficients over the same 68k
# buildings, so B0.4's fit stands in for it.
STAND_IN["two-zone"] = "b0.4"
# At 1 km it has 195 location coefficients in place of 780, and the 500 m fit stands in for it.
STAND_IN["two-zone-1k"] = "two-zone"
# Whitened zones has two-zone-1k's gradient plus the NJ rows, its zone and a matrix product
# per zone, and the stalled 1 km fit stands in for it.
STAND_IN["whitened-zones"] = "two-zone-1k"
# Building zones adds a level per building to whitened zones' gradient, and the whitened fit
# stands in for it.
STAND_IN["building-zones"] = "whitened-zones"
# Building attributes adds twelve fixed columns to the normal walk's design, and the normal
# walk's fit stands in for it.
STAND_IN["building-attrs"] = "normal-walk"
# Seconds an iteration per pair of chains for a model with no Modal fit of its own yet. Building
# zones on the Gibbs sampler swept the v36 dense dataset's 1.77M training rows at 1.36 s for two
# chains on thelio's GPU (2026-10-20), and an A100's double precision runs no slower.
STATED_RATE = {"building-zones-gibbs": 1.4}
# At 500 m the two zones carry 780 waves against 1 km's 195, and the global block grows from 908
# coefficients to 1,493. On thelio's GPU a two-chain sweep took 2.44 s against 1.34 s at 1 km
# (2026-10-21), and the 1 km model's Modal fit ran at 0.33 s an iteration per pair of chains.
# 0.7 s allows for the A100 scaling worse than thelio's card on the bigger dense factor.
STATED_RATE["building-zones-attrs-500m"] = 0.7
# A Gibbs model with no Modal fit of its own takes the rate of its stand-in's latest one.
# Building zones with attributes drops NJ's zone from building zones on Gibbs and adds eight
# columns, which leaves its global block at 908 coefficients against the three-zone run's 922.
RATE_STAND_IN = {"building-zones-attrs": "building-zones-gibbs"}
# Building zones with frontage adds six columns to the 1 km model with attributes.
RATE_STAND_IN["building-zones-front"] = "building-zones-attrs"
# Building zones with unit features adds seven columns to the 1 km model with attributes.
RATE_STAND_IN["building-zones-unit"] = "building-zones-attrs"
# Building zones with a gym swaps the unit model's truck column for a gym column.
RATE_STAND_IN["building-zones-gym"] = "building-zones-attrs"
# Building zones with building age adds ten columns to the unit model.
RATE_STAND_IN["building-zones-age"] = "building-zones-attrs"
# Building zones with the unit's floor adds 51 floor curve columns and seven flags to the age
# model.
RATE_STAND_IN["building-zones-floor"] = "building-zones-attrs"
# Building zones with building means adds nine building columns to the floor model.
RATE_STAND_IN["building-zones-mundlak"] = "building-zones-attrs"
# Building zones with transit adds two building columns to the floor model.
RATE_STAND_IN["building-zones-transit"] = "building-zones-attrs"
# Building zones with parks adds three building columns to the floor model.
RATE_STAND_IN["building-zones-parks"] = "building-zones-attrs"
# Building zones with noise adds one building column to the floor model.
RATE_STAND_IN["building-zones-noise"] = "building-zones-attrs"
# Building zones with location adds the transit, parks and noise columns together.
RATE_STAND_IN["building-zones-location"] = "building-zones-attrs"
# Building zones with avenue adds one building column to the location model.
RATE_STAND_IN["building-zones-avenue"] = "building-zones-attrs"
# Building zones with park frontage adds one building column to the location model.
RATE_STAND_IN["building-zones-parkfront"] = "building-zones-attrs"
# Building zones with waterfront adds one building column to the location model.
RATE_STAND_IN["building-zones-waterfront"] = "building-zones-attrs"
# Building zones with elevated track adds one building column to the location model.
RATE_STAND_IN["building-zones-elevated"] = "building-zones-attrs"
# Building zones with the floor and park frontage adds one building column to the floor model.
RATE_STAND_IN["building-zones-floor-parkfront"] = "building-zones-attrs"
# Building zones with the floor as of the split has the floor model's columns, and the version
# with building means adds nine building columns to it.
RATE_STAND_IN["building-zones-floor-asof"] = "building-zones-attrs"
RATE_STAND_IN["building-zones-mundlak-asof"] = "building-zones-attrs"
# The as-of floor model with a wider amplitude prior has the same columns.
RATE_STAND_IN["building-zones-floor-asof-amp1"] = "building-zones-attrs"
# So does the as-of floor model on the later pipeline build.
RATE_STAND_IN["building-zones-floor-asof2"] = "building-zones-attrs"
# The version with the elevator curve to floor 64 adds 17 curve columns.
RATE_STAND_IN["building-zones-floor-asof2-cap64"] = "building-zones-attrs"
# So do both on the build after the #1242 ledger rows.
RATE_STAND_IN["building-zones-floor-asof3"] = "building-zones-attrs"
RATE_STAND_IN["building-zones-floor-asof3-cap64"] = "building-zones-attrs"
# The version with a random effect per unit has the columns of the as-of floor model.
RATE_STAND_IN["building-zones-floor-asof3-unit"] = "building-zones-attrs"
# The baselines, whose fits skip their scoring unless the launch asks for it with --score
# (Ben, 2026-10-19 14:30Z: fit-only by default).
BASELINES = (
    "b0",
    "b0.1",
    "b0.2",
    "b0.3",
    "b0.4",
    "centered-walk",
    "level-walk",
    "total-walk",
    "normal-walk",
    "two-zone",
    "two-zone-1k",
    "whitened-zones",
    "building-zones",
    "building-attrs",
    "building-zones-gibbs",
    "building-zones-attrs",
    "building-zones-attrs-500m",
    "building-zones-front",
    "building-zones-unit",
    "building-zones-gym",
    "building-zones-age",
    "building-zones-floor",
    "building-zones-mundlak",
    "building-zones-transit",
    "building-zones-parks",
    "building-zones-noise",
    "building-zones-location",
    "building-zones-avenue",
    "building-zones-parkfront",
    "building-zones-waterfront",
    "building-zones-elevated",
    "building-zones-floor-parkfront",
    "building-zones-floor-asof",
    "building-zones-floor-asof-amp1",
    "building-zones-floor-asof2",
    "building-zones-floor-asof2-cap64",
    "building-zones-floor-asof3",
    "building-zones-floor-asof3-cap64",
    "building-zones-floor-asof3-unit",
    "building-zones-mundlak-asof",
)


def scoring_steps(model, large=False, score=False, no_loo=False, no_heldout=False):
    """(PSIS-LOO, held-out scoring) for a fit of `model`: both for a frontier or large fit,
    which score in their own way, and for a baseline only those --score asks for."""
    if model not in BASELINES or large:
        return True, True
    if not score:
        return False, False
    return not no_loo, not no_heldout


class CapReached(RuntimeError):
    pass


def measured_rate(model, features, runs=RUNS):
    """Seconds an iteration per pair of chains in the fit stage of the latest Modal fit of
    `model` on `features` under `runs`, or None if there is none."""
    latest = None
    for meta in runs.glob(f"{model}-{features}-*/modal/modal.json"):
        try:
            m = json.loads(meta.read_text())
            result = json.loads((meta.parents[1] / "result.json").read_text())
            if (result["model"]["name"], result["feature_set"]) != (model, features):
                continue  # a longer model or feature-set name with the same prefix
            fit = m["stages"]["fit"]
            s = result["sampler_settings"]
            iterations = (s["warmup"] + s["draws"]) * s["chains"] / 2
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if m.get("fit_exit", m.get("exit")) != 0 or not iterations:
            continue
        mtime = meta.stat().st_mtime
        if latest is None or mtime > latest[0]:
            latest = (mtime, fit / iterations)
    return latest and latest[1]


# A large fit with no measured rate yet runs at the default rate scaled by its rows: the
# all-scraped data holds 4.9 times NB9's fit rows, and Gibbs sweeps scale with the rows.
LARGE_SECONDS_PER_ITERATION = 2.1


def gpu_seconds(chains, warmup, draws, rate=None, large=False):
    """Estimated wall time of a fit's GPU container, at `rate` seconds an iteration if that is
    slower than the default."""
    default = LARGE_SECONDS_PER_ITERATION if large and rate is None else 0
    per = max(SECONDS_PER_ITERATION, rate or 0, default)
    return OVERHEAD_SECONDS + per * (int(warmup) + int(draws)) * (int(chains) / 2)


def seconds(chains, warmup, draws, rate=None, large=False):
    """Estimated Modal time of a fit: its GPU container, then the new-building container (none
    for a large fit)."""
    nb = 0 if large else NEWBUILDING_SECONDS
    return round(gpu_seconds(chains, warmup, draws, rate, large) + nb)


def estimate(chains, warmup, draws, gpu="A100-40GB", rate=None, large=False):
    """Estimated list-price cost of a fit and its new-building score, in USD."""
    per_hour = (USD_PER_HOUR_LARGE if large else USD_PER_HOUR)[gpu]
    gpu_usd = gpu_seconds(chains, warmup, draws, rate, large) * per_hour
    nb_usd = 0 if large else NEWBUILDING_SECONDS * NEWBUILDING_USD_PER_HOUR
    return round((gpu_usd + nb_usd) / 3600, 2)


def measured_gradients(model, features, runs=RUNS):
    """The latest successful Modal fit of a BlackJAX `model` on `features` under `runs`: its
    fit-stage seconds a gradient, mean leapfrog steps a warmup iteration and a draw, the
    PSIS-LOO seconds a kept draw in its GPU container (None if its draws were scored on a CPU
    container), the scoring container's overhead and seconds a kept draw (None if there was
    none), other seconds in the GPU container outside the fit stage, chains and leapfrog limit.
    None if there is no such fit."""
    latest = None
    for meta in runs.glob(f"{model}-{features}-*/modal/modal.json"):
        try:
            m = json.loads(meta.read_text())
            result = json.loads((meta.parents[1] / "result.json").read_text())
            # A baseline (b0.1) records its own name as its feature set.
            if result["model"]["name"] != model or result["feature_set"] not in (
                features,
                model,
            ):
                continue
            # A fit that left out a scoring step still measured its gradients, but too little
            # of its PSIS-LOO to price the next one's.
            scored = all(m.get("steps", {}).values())
            chees, s = result["chees"], result["sampler_settings"]
            fit, loo = m["stages"]["fit"], m["stages"].get("loo")
            kept = s["chains"] * (s["draws"] // s["keep_every"])
            score = m.get("score") or {}
            if "score_seconds" not in score or not scored:
                score = {}
            measured = {
                "per_gradient": fit / chees["gradients"],
                "warm_steps": chees["warmup_mean_steps"],
                "draw_steps": chees["mean_steps"],
                "loo_per_draw": loo / kept if loo is not None and scored else None,
                "score_overhead": (
                    score["wall_seconds"] - score["score_seconds"] if score else None
                ),
                "score_per_draw": score["score_seconds"] / kept if score else None,
                "other": m["wall_seconds"] - fit - (loo or 0),
                "chains": s["chains"],
                "max_leapfrog_steps": s["max_leapfrog_steps"],
            }
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            continue
        if m.get("fit_exit", m.get("exit")) != 0:
            continue
        mtime = meta.stat().st_mtime
        if latest is None or mtime > latest[0]:
            latest = (mtime, measured)
    return latest and latest[1]


def fit_estimate(
    model,
    features,
    chains,
    warmup,
    draws,
    gpu,
    large=False,
    runs=RUNS,
    keep=1,
    max_leapfrog_steps=None,
    cpu_score=False,
    scoring=True,
):
    """Estimated (USD, seconds) of a Modal fit: `fit_stages` summed, the GPU container then the
    scoring container, which run one after the other."""
    stages = fit_stages(
        model,
        features,
        chains,
        warmup,
        draws,
        gpu,
        large,
        runs,
        keep,
        max_leapfrog_steps,
        cpu_score,
        scoring,
    )
    return (
        round(sum(usd for usd, _ in stages.values()), 2),
        sum(secs for _, secs in stages.values()),
    )


def fit_stages(
    model,
    features,
    chains,
    warmup,
    draws,
    gpu,
    large=False,
    runs=RUNS,
    keep=1,
    max_leapfrog_steps=None,
    cpu_score=False,
    scoring=True,
):
    """Estimated {container: (USD, seconds)} of a Modal fit, each stage at its own price: "gpu",
    plus "score" for a baseline scored on a CPU container (`cpu_score`). A BlackJAX fit with the
    chains and leapfrog limit of its model's last Modal fit is estimated from that fit's time a
    gradient and step counts, with PSIS-LOO scaled by the kept draws, since its time an
    iteration follows its trajectory lengths and not the Gibbs rate. A model in STAND_IN with no
    such fit of its own is estimated from its stand-in's. Every other fit comes from `estimate`
    and `seconds`, with the scoring container added to them. In the GPU container, scoring on
    the CPU container takes the place of PSIS-LOO."""
    hmc = measured_gradients(model, features, runs)
    if hmc is None and model in STAND_IN:
        hmc = measured_gradients(STAND_IN[model], features, runs)
    kept = int(chains) * (int(draws) // int(keep))
    if (
        hmc
        and not large
        and int(chains) == hmc["chains"]
        and max_leapfrog_steps is not None
        and int(max_leapfrog_steps) == hmc["max_leapfrog_steps"]
    ):
        steps = int(warmup) * hmc["warm_steps"] + int(draws) * hmc["draw_steps"]
        secs = hmc["other"] + hmc["per_gradient"] * steps
        if scoring and not cpu_score:
            secs += (hmc["loo_per_draw"] or GPU_LOO_SECONDS_PER_DRAW) * kept
        secs = round(secs)
        stages = {"gpu": (round(secs * USD_PER_HOUR[gpu] / 3600, 2), secs)}
    else:
        rate = (
            measured_rate(model, features, runs)
            or (
                model in RATE_STAND_IN
                and measured_rate(RATE_STAND_IN[model], features, runs)
            )
            or STATED_RATE.get(model)
            or STATED_RATE.get(RATE_STAND_IN.get(model))
        )
        stages = {
            "gpu": (
                estimate(chains, warmup, draws, gpu, rate, large),
                seconds(chains, warmup, draws, rate, large),
            )
        }
    if cpu_score and scoring:
        # A measured scoring container, or the constants.
        overhead = (hmc or {}).get("score_overhead") or SCORE_OVERHEAD_SECONDS
        per_draw = (hmc or {}).get("score_per_draw") or SCORE_SECONDS_PER_DRAW
        secs = round(overhead + per_draw * kept)
        stages["score"] = (round(secs * SCORE_USD_PER_HOUR / 3600, 2), secs)
    return stages


def max_leapfrog_steps(argv):
    """The --max-leapfrog-steps value in a fit's arguments, or None."""
    for i, arg in enumerate(argv):
        if arg == "--max-leapfrog-steps" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--max-leapfrog-steps="):
            return arg.split("=", 1)[1]
    return None


def over_cap(usd, secs, large=False):
    """Why a fit estimated at `usd` and `secs` is over the per-fit cap, or None. A large fit
    (fit.py --large) has no time cap (Ben, 2026-10-16 06:37Z: the all-scraped fit is not
    held to the hour)."""
    if secs is not None and secs > PER_FIT_SECONDS and not large:
        return (
            f"this fit's estimated {secs / 60:.0f} min of Modal time is over the per-fit cap "
            f"of {PER_FIT_SECONDS / 60:.0f} min (Ben, 2026-10-14 09:57Z)"
        )
    if PER_FIT_USD is not None and usd > PER_FIT_USD:
        return (
            f"this fit's ${usd:.2f} estimate is over the per-fit cap of ${PER_FIT_USD:.2f} "
            "(Ben, 2026-10-14 09:57Z)"
        )
    return None


# The accrual rate, in USD a day, from each time on. Ben, 2026-10-07 22:32Z: $8.80 a day (10 x
# the served full fit's estimate). Ben, 2026-10-10 16:25Z: "OK: run the fit queue at $10/day".
RATES = (
    (START, 10 * NB5_SERVED_FIT_USD),
    (datetime.datetime(2026, 10, 10, 16, 25, 53, tzinfo=datetime.UTC), 10.0),
)
USD_PER_DAY = RATES[-1][1]
CEILING = USD_PER_DAY  # Ben, 2026-10-07 22:23Z: cap the balance at ~10 full fits (a day's accrual)


def rate_at(at):
    """The accrual rate in force at `at` (the first rate before START)."""
    return next((r for since, r in reversed(RATES) if since <= at), RATES[0][1])


def ceiling_at(at):
    """The balance cap in force at `at`: a day's accrual at the rate then."""
    return rate_at(at)


def accrued(start, end):
    """Dollars accrued from start to end at the rates in force."""
    total = 0.0
    for i, (since, rate) in enumerate(RATES):
        until = RATES[i + 1][0] if i + 1 < len(RATES) else end
        a, b = max(start, since), min(end, until)
        total += max((b - a).total_seconds(), 0) / 86400 * rate
    return total


def _now(now=None):
    return (now or datetime.datetime.now(ZONE)).astimezone(ZONE)


def _rows(lines):
    return [json.loads(line) for line in lines if line.strip()]


def launches(ledger=LEDGER):
    """Every ledger row, oldest first: launches, and settlements of their cost."""
    return _rows(ledger.read_text().splitlines()) if ledger.exists() else []


def balance(rows, now=None):
    """Dollars accrued since START, held to the ceiling then in force, less what launches since
    START cost.

    Walks the ledger in time order: accrual stops while the balance is at the ceiling (a day's
    accrual at the rate in force, so time spent at an old ceiling is not repriced); a launch
    takes its estimate and its settlement the difference between what it cost and the estimate."""
    now = _now(now)
    events, estimates = [], {}
    for row in rows:
        at = datetime.datetime.fromisoformat(row["at"])
        if row.get("kind") == "settle":
            if row["id"] in estimates:  # launches before START aren't charged
                events.append((at, estimates[row["id"]] - row["usd"]))
        elif at >= START and row.get("kind") != "outside":
            # A row from the old launcher (no estimate) counts as a served full fit.
            usd = row.get("usd_estimate", NB5_SERVED_FIT_USD)
            estimates[row.get("id", f"{row['name']}@{row['at']}")] = usd
            events.append((at, -usd))
    # Rate changes are events too, so each step between events accrues at one rate.
    events += [(since, 0.0) for since, _ in RATES[1:] if since <= now]
    have, last = 0.0, START
    for at, change in sorted(events, key=lambda e: e[0]) + [(max(now, START), 0.0)]:
        have = min(ceiling_at(last), have + accrued(last, at))
        have = min(ceiling_at(at), have + change)
        last = max(at, last)
    return have


def ready_at(rows, usd, now=None):
    """When the balance will cover `usd`: now, the time accrual reaches it, or None if it never
    will (an estimate over the ceiling)."""
    now = _now(now)
    short = usd - balance(rows, now)
    if short <= 0:
        return now
    if usd > CEILING:
        return None
    at = now + datetime.timedelta(days=short / rate_at(now))
    return at.replace(second=0, microsecond=0) + datetime.timedelta(
        minutes=1
    )  # round up


def when(rows, usd, now=None):
    """ready_at, for a message."""
    at = ready_at(rows, usd, now)
    return (
        f"{at:%Y-%m-%d %H:%M} ET" if at else f"never: over the ${CEILING:.2f} ceiling"
    )


def _append(ledger, decide, now):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # two launchers can't both spend the same dollars
        f.seek(0)
        entry = decide(_rows(f))
        entry = {
            "day": now.date().isoformat(),
            "at": now.isoformat(timespec="seconds"),
            **entry,
        }
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def reserve(
    name, gpu, usd, ledger=LEDGER, now=None, secs=None, large=False, outside=False
):
    """Charge a launch of `name` its estimate `usd`, or raise CapReached if the estimate (`usd`,
    or `secs` of Modal time) is over the per-fit cap or the balance is short. With `outside`, the
    launch is recorded outside the budget: no balance check, and the balance leaves it out.

    Returns the launch's id, for settle, and the balance left."""
    if why := over_cap(usd, secs, large):
        raise CapReached(f"refused: {why}")
    now = _now(now)
    left = {}

    def decide(rows):
        have = balance(rows, now)
        if outside:
            left["usd"] = have
            return {
                "kind": "outside",
                "id": launch,
                "name": name,
                "gpu": gpu,
                "usd_estimate": usd,
            }
        if have < usd:
            raise CapReached(
                f"the Modal balance is ${have:.2f}, short of this fit's ${usd:.2f} estimate; "
                f"enough from {when(rows, usd, now)}"
            )
        left["usd"] = have - usd
        return {"id": launch, "name": name, "gpu": gpu, "usd_estimate": usd}

    launch = (
        f"{name}@{now.isoformat(timespec='seconds')}"  # a retry reuses the run's name
    )
    _append(ledger, decide, now)
    return launch, left["usd"]


def settle(launch, usd, ledger=LEDGER, now=None):
    """Replace a launch's estimate with what it cost."""
    name = launch.rsplit("@", 1)[0]
    _append(
        ledger,
        lambda rows: {
            "kind": "settle",
            "id": launch,
            "name": name,
            "usd": round(usd, 2),
        },
        _now(now),
    )


def _positional(argv):
    positional, gpu, args = [], "A100-40GB", iter(argv)
    for arg in args:
        if arg in ("--gpu", "--dataset", "--input", "--split", "--chain-batch"):
            value = next(args, "")
            gpu = value if arg == "--gpu" else gpu
        elif arg.startswith("--gpu="):
            gpu = arg.split("=", 1)[1]
        elif not arg.startswith("-"):
            positional.append(arg)
        if len(positional) == 8:  # COMMIT LABEL MODEL FEATURES CHAINS WARMUP DRAWS KEEP
            break
    return positional, gpu


def fit_size(argv):
    """(chains, warmup, draws, gpu) from ops/modal-fit's arguments, as fit.py parses them."""
    positional, gpu = _positional(argv)
    return (*positional[4:7], gpu)


def fit_model(argv):
    """(model, features) from ops/modal-fit's arguments."""
    return tuple(_positional(argv)[0][2:4])


if __name__ == "__main__":
    rows = launches()
    if "--check" in sys.argv:
        fit = sys.argv[sys.argv.index("--check") + 1 :][:3] or SERVED_FIT
        if why := over_cap(estimate(*fit), seconds(*fit)):  # at the default rate
            print(f"refused: {why}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0 if balance(rows) >= estimate(*fit) else 1)
    if (
        "--check-launch" in sys.argv
    ):  # ops/modal-fit's pre-check, with its own arguments
        try:
            argv = sys.argv[sys.argv.index("--check-launch") + 1 :]
            *fit, gpu = fit_size(argv)
            large = "--large" in argv
            usd, secs = fit_estimate(
                *fit_model(argv),
                *fit,
                gpu,
                large,
                keep=_positional(argv)[0][7],
                max_leapfrog_steps=max_leapfrog_steps(argv),
                cpu_score="--cpu-score" in argv,
                scoring=any(
                    scoring_steps(
                        fit_model(argv)[0],
                        large,
                        "--score" in argv,
                        "--no-loo" in argv,
                        "--no-heldout" in argv,
                    )
                ),
            )
        except (TypeError, ValueError, KeyError, IndexError):
            sys.exit(
                0
            )  # bad arguments: fit.py reports them, and reserves before any launch
        if why := over_cap(usd, secs, large):
            print(f"refused: {why}", file=sys.stderr)
            sys.exit(2)
        if balance(rows) < usd and "--outside-budget" not in argv:
            sys.exit(
                f"refused: the Modal balance is ${balance(rows):.2f}, short of this fit's "
                f"${usd:.2f} estimate; enough from {when(rows, usd)}"
            )
        sys.exit(0)
    for row in rows[-6:]:
        cost = row.get("usd", row.get("usd_estimate"))
        print(
            f"{row['at']}  {row.get('kind', 'launch'):<6} {cost if cost is not None else '':>6}  {row['name']}"
        )
    usd = estimate(*SERVED_FIT)
    print(
        f"balance ${balance(rows):.2f}, accruing ${USD_PER_DAY:.2f} a day up to ${CEILING:.2f}"
    )
    print(
        f"a served full fit (${usd:.2f}, {seconds(*SERVED_FIT) / 60:.0f} min) may launch from "
        f"{when(rows, usd)}"
    )
    print(
        f"per-fit cap: {PER_FIT_SECONDS / 60:.0f} min, "
        + (f"${PER_FIT_USD:.2f}" if PER_FIT_USD is not None else "no dollar cap yet")
    )

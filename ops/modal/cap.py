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
    """From the latest Modal fit of a BlackJAX `model` on `features` under `runs`: its fit-stage
    seconds a gradient, its mean leapfrog steps a warmup iteration and a draw, and its seconds
    outside the fit stage (PSIS-LOO and scoring). None if there is no such fit."""
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
            chees = result["chees"]
            fit = m["stages"]["fit"]
            measured = (
                fit / chees["gradients"],
                chees["warmup_mean_steps"],
                chees["mean_steps"],
                m["wall_seconds"] - fit,
            )
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            continue
        if m.get("fit_exit", m.get("exit")) != 0:
            continue
        mtime = meta.stat().st_mtime
        if latest is None or mtime > latest[0]:
            latest = (mtime, measured)
    return latest and latest[1]


def fit_estimate(model, features, chains, warmup, draws, gpu, large=False, runs=RUNS):
    """Estimated (USD, seconds) of a Modal fit. A BlackJAX model measured on Modal before is
    estimated from its time a gradient and its step counts, since its time an iteration
    follows its trajectory lengths and not the Gibbs rate; every other fit from `estimate`
    and `seconds`."""
    if (hmc := measured_gradients(model, features, runs)) and not large:
        per_gradient, warm_steps, draw_steps, outside = hmc
        secs = round(
            outside
            + per_gradient * (int(warmup) * warm_steps + int(draws) * draw_steps)
        )
        return round(secs * USD_PER_HOUR[gpu] / 3600, 2), secs
    rate = measured_rate(model, features, runs)
    return (
        estimate(chains, warmup, draws, gpu, rate, large),
        seconds(chains, warmup, draws, rate, large),
    )


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
            usd, secs = fit_estimate(*fit_model(argv), *fit, gpu, large)
        except (TypeError, ValueError, KeyError):
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

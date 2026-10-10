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

    python3 ops/modal/cap.py                                  # balance, rate, recent launches
    python3 ops/modal/cap.py --check [CHAINS WARMUP DRAWS]    # exit 1 until the balance covers that
                                                              # fit (default: the served full fit)
    python3 ops/modal/cap.py --check-launch ARGS...           # the same, from ops/modal-fit's ARGS
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
# Wall time of a fit's container: upload, image, fit, PSIS-LOO and the post-fit statistics, from
# the eight-neighbourhood A100 fits of 2026-10-10 (2 x 4,800 iterations: fit about 2,015 s,
# PSIS-LOO 373 s, 2,413 s in all, settled at $1.27 to $1.85), plus about 4 minutes for the
# post-fit statistics (#678). The NB5 calibration (800 s + 0.11 s an iteration, $0.88 a served
# fit) underestimated NB8 fits by about 40%.
OVERHEAD_SECONDS, SECONDS_PER_ITERATION = 700, 0.42
SERVED_FIT = (2, 300, 4500)  # chains, warmup, draws: the full fit since #432 ($1.80)
# What the ledger's history was priced at: the accrual rate before 2026-10-10 16:25Z and a launch
# row from the old launcher (no estimate) are 10 x and 1 x the NB5 served-fit estimate, kept
# fixed so recalibrating the estimate never reprices the past.
NB5_SERVED_FIT_USD = 0.88


class CapReached(RuntimeError):
    pass


def estimate(chains, warmup, draws, gpu="A100-40GB"):
    """Estimated list-price cost of one fit, in USD."""
    seconds = OVERHEAD_SECONDS + SECONDS_PER_ITERATION * (int(warmup) + int(draws)) * (
        int(chains) / 2
    )
    return round(seconds * USD_PER_HOUR[gpu] / 3600, 2)


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
        elif at >= START:
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


def reserve(name, gpu, usd, ledger=LEDGER, now=None):
    """Charge a launch of `name` its estimate `usd`, or raise CapReached if the balance is short.

    Returns the launch's id, for settle, and the balance left."""
    now = _now(now)
    left = {}

    def decide(rows):
        have = balance(rows, now)
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


def fit_size(argv):
    """(chains, warmup, draws, gpu) from ops/modal-fit's arguments, as fit.py parses them."""
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
    return (*positional[4:7], gpu)


if __name__ == "__main__":
    rows = launches()
    if "--check" in sys.argv:
        fit = sys.argv[sys.argv.index("--check") + 1 :][:3] or SERVED_FIT
        sys.exit(0 if balance(rows) >= estimate(*fit) else 1)
    if (
        "--check-launch" in sys.argv
    ):  # ops/modal-fit's pre-check, with its own arguments
        try:
            *fit, gpu = fit_size(sys.argv[sys.argv.index("--check-launch") + 1 :])
            usd = estimate(*fit, gpu)
        except (TypeError, ValueError, KeyError):
            sys.exit(
                0
            )  # bad arguments: fit.py reports them, and reserves before any launch
        if balance(rows) < usd:
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
    print(f"a served full fit (${usd:.2f}) may launch from {when(rows, usd)}")

"""The Modal budget: dollars accrue at the rate of 10 full fits a day; a fit launches only once
the balance covers its estimated cost.

Ben, 2026-10-07 21:59Z: "we should accumulate Modal dollars at a rate consistent with 10 full
fits per day, and only spend on a partial or full fit after we have accumulated enough for the
estimated cost. If our estimate is too low, the accumulation should continue from the negative
balance. e.g. $0 -> $10 -> -$0.50 -> $3 -> $1 -> $10 etc."

The balance starts at $0 at START and accrues USD_PER_DAY = 10 x the estimated cost of the served
full fit. A launch is charged its estimate when it takes its turn (reserve); when the fit returns,
the launcher settles it at the container's list-price cost (or the time it ran, if it failed), so
an estimate that was too low leaves the balance negative and accrual continues from there. There is
no ceiling on the balance. Launches before START (the old daily cap) are not charged.

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
# Wall time of a fit's container: upload, image, fit and PSIS-LOO, from A100 fits of 2026-10-06/07
# (the served design, 2 x 3,900 iterations, took 846 to 1,488 s; 2 x 12,300 took about 2,100 s).
OVERHEAD_SECONDS, SECONDS_PER_ITERATION = 800, 0.11
SERVED_FIT = (2, 300, 3600)  # chains, warmup, draws


class CapReached(RuntimeError):
    pass


def estimate(chains, warmup, draws, gpu="A100-40GB"):
    """Estimated list-price cost of one fit, in USD."""
    seconds = OVERHEAD_SECONDS + SECONDS_PER_ITERATION * (int(warmup) + int(draws)) * (
        int(chains) / 2
    )
    return round(seconds * USD_PER_HOUR[gpu] / 3600, 2)


USD_PER_DAY = 10 * estimate(*SERVED_FIT)


def _now(now=None):
    return (now or datetime.datetime.now(ZONE)).astimezone(ZONE)


def _rows(lines):
    return [json.loads(line) for line in lines if line.strip()]


def launches(ledger=LEDGER):
    """Every ledger row, oldest first: launches, and settlements of their cost."""
    return _rows(ledger.read_text().splitlines()) if ledger.exists() else []


def balance(rows, now=None):
    """Dollars accrued since START less what launches since START cost (settled, else estimated)."""
    now = _now(now)
    accrued = max((now - START).total_seconds(), 0) / 86400 * USD_PER_DAY
    charged = {}  # launches since START: their estimate, replaced by what they cost once settled
    for row in rows:
        if row.get("kind") == "settle":
            if row["id"] in charged:
                charged[row["id"]] = row["usd"]
        elif datetime.datetime.fromisoformat(row["at"]) >= START:
            # A row from the old launcher (no estimate) counts as a served full fit.
            usd = row.get("usd_estimate", estimate(*SERVED_FIT))
            charged[row.get("id", f"{row['name']}@{row['at']}")] = usd
    return accrued - sum(charged.values())


def ready_at(rows, usd, now=None):
    """When the balance will cover `usd`: now, or the time accrual reaches it."""
    now = _now(now)
    short = usd - balance(rows, now)
    if short <= 0:
        return now
    at = now + datetime.timedelta(days=short / USD_PER_DAY)
    return at.replace(second=0, microsecond=0) + datetime.timedelta(
        minutes=1
    )  # round up


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
                f"enough from {ready_at(rows, usd, now):%Y-%m-%d %H:%M} ET"
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
                f"${usd:.2f} estimate; enough from {ready_at(rows, usd):%Y-%m-%d %H:%M} ET"
            )
        sys.exit(0)
    for row in rows[-6:]:
        cost = row.get("usd", row.get("usd_estimate"))
        print(
            f"{row['at']}  {row.get('kind', 'launch'):<6} {cost if cost is not None else '':>6}  {row['name']}"
        )
    usd = estimate(*SERVED_FIT)
    print(
        f"balance ${balance(rows):.2f}, accruing ${USD_PER_DAY:.2f} a day (10 x ${usd:.2f})"
    )
    print(
        f"a served full fit (${usd:.2f}) may launch from {ready_at(rows, usd):%Y-%m-%d %H:%M} ET"
    )

"""The Modal launch limit: at most one launch every GAP_MINUTES, with no daily cap.

Ben, 2026-10-07 20:22Z: "Change the Modal limit to 1 fit per 144 min with no daily cap".
Every launch takes its turn before its container starts, whether the fit later succeeds,
fails or is stopped, so the ledger is an upper bound on what was billed. A launch less than
GAP_MINUTES after the previous one is refused until the gap has passed.

    python3 ops/modal/cap.py            # recent launches and when the next may start
    python3 ops/modal/cap.py --check    # exit 1 if the gap since the last launch hasn't passed
"""

import datetime
import fcntl
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

GAP_MINUTES = 144
LEDGER = Path(
    "/data1/apartments/modal/ledger.jsonl"
)  # fixed: no other ledger, no override
ZONE = ZoneInfo("America/New_York")


class CapReached(RuntimeError):
    pass


def _now(now=None):
    return (now or datetime.datetime.now(ZONE)).astimezone(ZONE)


def _rows(lines):
    return [json.loads(line) for line in lines if line.strip()]


def launches(ledger=LEDGER):
    """Every launch in the ledger, oldest first."""
    return _rows(ledger.read_text().splitlines()) if ledger.exists() else []


def next_allowed(rows):
    """The earliest time the next launch may start, or None if it may start now."""
    if not rows:
        return None
    last = max(datetime.datetime.fromisoformat(row["at"]) for row in rows)
    return last + datetime.timedelta(minutes=GAP_MINUTES)


def reserve(name, gpu, ledger=LEDGER, now=None):
    """Record a launch of `name`, or raise CapReached within GAP_MINUTES of the last one.

    Returns the earliest time the launch after this one may start."""
    now = _now(now)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # two launchers can't both take the same turn
        f.seek(0)
        start = next_allowed(_rows(f))
        if start is not None and now < start:
            raise CapReached(
                f"the last Modal launch was less than {GAP_MINUTES} min ago; "
                f"the next may start at {start.astimezone(ZONE):%Y-%m-%d %H:%M} ET"
            )
        entry = {
            "day": now.date().isoformat(),
            "at": now.isoformat(timespec="seconds"),
            "name": name,
            "gpu": gpu,
        }
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return now + datetime.timedelta(minutes=GAP_MINUTES)


if __name__ == "__main__":
    rows = launches()
    start = next_allowed(rows)
    ready = start is None or _now() >= start
    if "--check" in sys.argv:
        sys.exit(0 if ready else 1)
    for row in rows[-5:]:
        print(f"{row['at']}  {row['gpu']:<10} {row['name']}")
    print(
        "next Modal launch: now"
        if ready
        else f"next Modal launch: {start.astimezone(ZONE):%Y-%m-%d %H:%M} ET"
    )

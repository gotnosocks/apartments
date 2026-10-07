"""The daily cap on Modal fits: at most MAX_PER_DAY launches per New York calendar day.

Ben, 2026-10-06: full fits may run on Modal, but no more than 10 Modal fits in a day.
Every launch takes a slot before its container starts, whether the fit later succeeds,
fails or is stopped, so the count is an upper bound on what was billed. There is no
override: a launch past the cap is refused until midnight ET.

    python3 ops/modal/cap.py            # today's launches and slots left
    python3 ops/modal/cap.py --check    # exit 1 if today's slots are used up
"""

import datetime
import fcntl
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_PER_DAY = 10
LEDGER = Path(
    "/data1/apartments/modal/ledger.jsonl"
)  # fixed: no other ledger, no override
ZONE = ZoneInfo("America/New_York")


class CapReached(RuntimeError):
    pass


def _today(now=None):
    return (now or datetime.datetime.now(ZONE)).astimezone(ZONE).date().isoformat()


def launches(day=None, ledger=LEDGER):
    """The ledger's entries for one ET day (default today)."""
    day = day or _today()
    if not ledger.exists():
        return []
    rows = [
        json.loads(line) for line in ledger.read_text().splitlines() if line.strip()
    ]
    return [row for row in rows if row["day"] == day]


def reserve(name, gpu, ledger=LEDGER, now=None):
    """Record a launch of `name`, or raise CapReached when today already has MAX_PER_DAY."""
    now = (now or datetime.datetime.now(ZONE)).astimezone(ZONE)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # two launchers can't both take the last slot
        f.seek(0)
        day = _today(now)
        used = sum(1 for line in f if line.strip() and json.loads(line)["day"] == day)
        if used >= MAX_PER_DAY:
            raise CapReached(
                f"{used} Modal fits already launched on {day} (ET); the cap is {MAX_PER_DAY} a day"
            )
        entry = {
            "day": day,
            "at": now.isoformat(timespec="seconds"),
            "name": name,
            "gpu": gpu,
        }
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return MAX_PER_DAY - used - 1


if __name__ == "__main__":
    today = launches()
    for row in [] if "--check" in sys.argv else today:
        print(f"{row['at']}  {row['gpu']:<10} {row['name']}")
    print(f"{len(today)} of {MAX_PER_DAY} Modal fits launched today ({_today()} ET)")
    sys.exit(1 if "--check" in sys.argv and len(today) >= MAX_PER_DAY else 0)

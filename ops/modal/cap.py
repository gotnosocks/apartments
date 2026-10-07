"""The daily cap on Modal fits: at most MAX_PER_DAY launches per New York calendar day.

Ben, 2026-10-06: full fits may run on Modal, but no more than 10 Modal fits in a day.
Every launch takes a slot before its container starts, whether the fit later succeeds,
fails or is stopped, so the count is an upper bound on what was billed. A launch past the
cap is refused until midnight ET. The only way past it is a grant from Ben for one day,
recorded in GRANTS (reviewed PRs only) with his words: that day's cap is MAX_PER_DAY plus
the grant.

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
# Extra Modal fits Ben allowed on one ET day: {"YYYY-MM-DD": {"extra": n, "by": ..., "words": ...}}.
GRANTS = Path(__file__).with_name("grants.json")


class CapReached(RuntimeError):
    pass


def _today(now=None):
    return (now or datetime.datetime.now(ZONE)).astimezone(ZONE).date().isoformat()


def limit(day=None, grants=None):
    """The cap for one ET day (default today): MAX_PER_DAY plus Ben's grant for that day."""
    day = day or _today()
    grants = GRANTS if grants is None else grants
    extra = (
        json.loads(grants.read_text()).get(day, {}).get("extra", 0)
        if grants.exists()
        else 0
    )
    return MAX_PER_DAY + int(extra)


def launches(day=None, ledger=LEDGER):
    """The ledger's entries for one ET day (default today)."""
    day = day or _today()
    if not ledger.exists():
        return []
    rows = [
        json.loads(line) for line in ledger.read_text().splitlines() if line.strip()
    ]
    return [row for row in rows if row["day"] == day]


def reserve(name, gpu, ledger=LEDGER, now=None, grants=None):
    """Record a launch of `name`, or raise CapReached when today's cap (`limit`) is used."""
    now = (now or datetime.datetime.now(ZONE)).astimezone(ZONE)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # two launchers can't both take the last slot
        f.seek(0)
        day = _today(now)
        used = sum(1 for line in f if line.strip() and json.loads(line)["day"] == day)
        cap = limit(day, grants)
        if used >= cap:
            raise CapReached(
                f"{used} Modal fits already launched on {day} (ET); the cap is {cap} that day"
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
    return cap - used - 1


if __name__ == "__main__":
    today = launches()
    for row in [] if "--check" in sys.argv else today:
        print(f"{row['at']}  {row['gpu']:<10} {row['name']}")
    print(f"{len(today)} of {limit()} Modal fits launched today ({_today()} ET)")
    sys.exit(1 if "--check" in sys.argv and len(today) >= limit() else 0)

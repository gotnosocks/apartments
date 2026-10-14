"""Space Oxylabs submissions on a fixed grid of slots.

OxylabsDownloadHandler._submission_slot sleeps until the next slot, then sets the following slot
one interval after the moment it woke. Whenever parse work on the crawler's main thread holds the
event loop, the coroutine wakes late, and that lateness carries into every later slot. In Midtown
West (Oct 2026) 128 submissions a minute nominal gave about 113.

steady_slot sets the following slot one interval after the slot it waited for, so a submission
that goes out a little late leaves the schedule where it was. It also keeps consecutive submissions
at least MIN_SPACING intervals apart, so a late submission and the next one on time never go out
together. Over a long run, the rate stays at or below the setting: slots stay one interval apart,
and no submission goes out before its slot. Over a short run, 128 a minute allows at most 3
submissions in any second, as before. When parse work holds the event loop for more than 15% of
an interval, the rate falls below the setting, by less than before. When a submission goes out a
whole interval or more after its slot, the crawl has stalled, and steady_slot starts a new grid
from that moment instead of sending the missed slots in a burst. When _defer_submissions moves the
next slot later during the sleep, steady_slot waits again. ORIGINAL_SLOT overwrites that deferral.

oxylabs.py is hashed by saved datasets, so the change lives here. cli applies it with
steady_pacer() for crawl commands.
"""

import asyncio
import time
from contextlib import contextmanager

from .oxylabs import OxylabsDownloadHandler

ORIGINAL_SLOT = OxylabsDownloadHandler._submission_slot
MIN_SPACING = 0.85


async def steady_slot(self):
    async with self._submission_lock:
        while True:
            slot = self._next_submission
            wait = slot - time.monotonic()
            if wait <= 0:
                break
            await asyncio.sleep(wait)
        now = time.monotonic()
        late = now - slot
        interval = self._submission_interval
        start = slot if late < interval else now
        self._next_submission = max(start + interval, now + MIN_SPACING * interval)


@contextmanager
def steady_pacer():
    """Use steady_slot for Oxylabs submissions inside the block."""
    previous = OxylabsDownloadHandler._submission_slot
    OxylabsDownloadHandler._submission_slot = steady_slot
    try:
        yield
    finally:
        OxylabsDownloadHandler._submission_slot = previous

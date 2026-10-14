"""Space Oxylabs submissions on a fixed grid of slots.

OxylabsDownloadHandler._submission_slot sleeps until the next slot, then sets the following slot
one interval after the moment it woke. Whenever parse work on the crawler's main thread holds the
event loop, the coroutine wakes late, and that lateness carries into every later slot. In Midtown
West (Oct 2026) 128 submissions a minute nominal gave about 113.

steady_slot sets the following slot one interval after the slot it waited for, so a submission
that goes out late leaves the schedule where it was. Slots stay one interval apart, and no
submission goes out before its slot, so a window of any length T holds at most T / interval + 1
submissions, the same bound as before. When a submission goes out a whole interval or more after
its slot, the crawl has stalled, and steady_slot starts a new grid from that moment instead of
sending the missed slots in a burst. It also waits again when _defer_submissions moved the next
slot later during the sleep, where the original slot overwrote that deferral.

oxylabs.py is hashed by saved datasets, so the change lives here. cli applies it with
steady_pacer() for crawl commands.
"""

import asyncio
import time
from contextlib import contextmanager

from .oxylabs import OxylabsDownloadHandler

ORIGINAL_SLOT = OxylabsDownloadHandler._submission_slot


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
        start = slot if late < self._submission_interval else now
        self._next_submission = start + self._submission_interval


@contextmanager
def steady_pacer():
    """Use steady_slot for Oxylabs submissions inside the block."""
    previous = OxylabsDownloadHandler._submission_slot
    OxylabsDownloadHandler._submission_slot = steady_slot
    try:
        yield
    finally:
        OxylabsDownloadHandler._submission_slot = previous

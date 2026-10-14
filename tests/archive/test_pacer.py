import asyncio
import random

import pytest

from streeteasy_archive import pacer
from streeteasy_archive.oxylabs import OxylabsDownloadHandler


class Clock:
    def __init__(self, oversleep):
        self.now = 100.0
        self.oversleep = oversleep
        self.during_sleep = None

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds + self.oversleep
        if self.during_sleep:
            self.during_sleep()
            self.during_sleep = None


@pytest.fixture
def clock(monkeypatch):
    clock = Clock(oversleep=0.3)
    monkeypatch.setattr(pacer.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pacer.asyncio, "sleep", clock.sleep)
    return clock


def handler():
    h = OxylabsDownloadHandler()
    h._submission_interval = 1.0
    return h


def sends(h, clock, n, work=0.0):
    async def run():
        times = []
        for _ in range(n):
            await pacer.steady_slot(h)
            times.append(clock.now)
            clock.now += work
        return times

    return asyncio.run(run())


def test_window_bound(clock, monkeypatch):
    # Lateness varies from wake to wake, as parse work on the main thread does.
    rng = random.Random(5)
    monkeypatch.setattr(clock, "oversleep", 0.0)

    async def sleep(seconds):
        clock.now += seconds + rng.uniform(0, 0.99)

    monkeypatch.setattr(pacer.asyncio, "sleep", sleep)
    times = sends(handler(), clock, 400, work=0.0)
    for i, start in enumerate(times):
        for length, most in [(1, 2), (2.5, 3), (10, 11)]:
            assert len([t for t in times[i:] if t < start + length]) <= most


def test_late_send_keeps_min_spacing(clock):
    h = handler()
    clock.oversleep = 0.0
    times = sends(h, clock, 3)
    clock.now += 0.99
    times += sends(h, clock, 4)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert min(gaps) >= pacer.MIN_SPACING - 1e-9
    assert all(t >= 100.0 + i for i, t in enumerate(times))


def test_small_lateness_keeps_the_rate(clock):
    clock.oversleep = 0.1
    times = sends(handler(), clock, 50)
    assert times[-1] == pytest.approx(149.1)
    # No submission goes before its slot, and slots are one interval apart.
    assert all(t >= 100.0 + i for i, t in enumerate(times))


def test_stall_starts_a_new_grid(clock):
    clock.oversleep = 0.1
    h = handler()
    sends(h, clock, 3)
    clock.now += 5
    times = sends(h, clock, 3)
    assert times == pytest.approx([107.1, 108.2, 109.2])


def test_deferral_during_sleep_is_kept(clock):
    h = handler()
    sends(h, clock, 1)
    clock.during_sleep = lambda: h._defer_submissions("20", 0)
    (t,) = sends(h, clock, 1)
    assert t == pytest.approx(121.6)


def test_steady_pacer_is_scoped():
    with pacer.steady_pacer():
        assert OxylabsDownloadHandler._submission_slot is pacer.steady_slot
    assert OxylabsDownloadHandler._submission_slot is pacer.ORIGINAL_SLOT

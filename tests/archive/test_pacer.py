import asyncio

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


def test_lateness_does_not_accumulate(clock):
    times = sends(handler(), clock, 50)
    assert times[0] == 100.0
    assert times[-1] == pytest.approx(149.3)
    # No submission goes before its slot, and slots are one interval apart.
    assert all(t >= 100.0 + i for i, t in enumerate(times))


def test_window_bound(clock):
    times = sends(handler(), clock, 200, work=0.05)
    for i, start in enumerate(times):
        inside = [t for t in times[i:] if t < start + 10]
        assert len(inside) <= 11


def test_stall_starts_a_new_grid(clock):
    h = handler()
    sends(h, clock, 3)
    clock.now += 5
    times = sends(h, clock, 3)
    assert times == pytest.approx([107.3, 108.6, 109.6])


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

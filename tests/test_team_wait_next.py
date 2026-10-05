import argparse
import importlib.machinery
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "team" / "wait-next"


def load():
    loader = importlib.machinery.SourceFileLoader("wait_next", str(SCRIPT))
    spec = importlib.util.spec_from_loader("wait_next", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def args(**kw):
    base = dict(unit=["frontier-*"], gpu=False, pr=[], file=[], max=120.0, poll=60.0, idle_grace=30.0, batch=15.0)
    base.update(kw)
    return argparse.Namespace(**base)


class Fake:
    """Replays one probe value per poll; the last value repeats."""

    def __init__(self, **series):
        self.series = series
        self.calls = {k: 0 for k in series}
        self.t = 0.0

    def probe(self, name):
        def f(*_):
            values = self.series[name]
            i = min(self.calls[name], len(values) - 1)
            self.calls[name] += 1
            return values[i]
        return f

    def probes(self):
        return {
            "units": self.probe("units"), "gpu": self.probe("gpu"),
            "pr": self.probe("pr"), "file": self.probe("file"),
            "result": lambda u: "result=success status=0",
        }

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


def run(fake, a):
    return load().wait(a, fake.probes(), clock=fake.clock, sleep=fake.sleep)


def test_unit_finishing_ends_the_wait():
    fake = Fake(units=[{"frontier-full11.service"}, {"frontier-full11.service"}, set()],
                gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args()) == ["finished: frontier-full11.service (result=success status=0)"]


def test_gpu_idle_needs_two_idle_polls_after_busy():
    fake = Fake(units=[set()], gpu=[["fit"], ["fit"], [], []], pr=[""], file=["missing"])
    events = run(fake, args(gpu=True))
    assert events == ["gpu idle: no gpu-class job is running or holding the GPU lock"]
    assert fake.t == 120.0


def test_gpu_idle_when_armed_fires_after_the_grace_period():
    fake = Fake(units=[set()], gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args(gpu=True)) == ["gpu idle: nothing has used the GPU for 30 min"]
    assert fake.t == 1800.0


def test_failed_unit_listing_is_not_a_finish():
    fake = Fake(units=[{"frontier-a.service"}, None, {"frontier-a.service"}],
                gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args(max=5)) == [
        "heartbeat: nothing changed in 5 min; check state and keep work queued"]


def test_pr_change_and_failed_lookup():
    fake = Fake(units=[set()], gpu=[[]], pr=["OPEN head=abc", "", "MERGED head=abc"], file=["missing"])
    assert run(fake, args(pr=[178], poll=1)) == ["PR #178: OPEN head=abc -> MERGED head=abc"]


def test_file_appearing():
    fake = Fake(units=[set()], gpu=[[]], pr=[""], file=["missing", "missing", "10 bytes"])
    assert run(fake, args(file=["/x/summary.json"])) == ["file /x/summary.json: missing -> 10 bytes"]


def test_failed_first_pr_lookup_sets_the_baseline_silently():
    fake = Fake(units=[set()], gpu=[[]], pr=["", "OPEN head=abc"], file=["missing"])
    assert run(fake, args(pr=[7], poll=1, max=0.5)) == [
        "heartbeat: nothing changed in 0.5 min; check state and keep work queued"]


def test_unit_finish_waits_for_the_other_watched_units():
    fake = Fake(units=[{"frontier-a.service", "frontier-b.service"}, {"frontier-b.service"},
                       {"frontier-b.service"}, set()],
                gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args()) == ["finished: frontier-a.service (result=success status=0)",
                                 "finished: frontier-b.service (result=success status=0)"]
    assert fake.t == 120.0


def test_batch_window_caps_the_hold():
    fake = Fake(units=[{"frontier-a.service", "frontier-b.service"}, {"frontier-b.service"}],
                gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args(batch=5)) == ["finished: frontier-a.service (result=success status=0)"]
    assert fake.t == 300.0


def test_gpu_idle_ends_the_batch_at_once():
    fake = Fake(units=[{"frontier-a.service", "frontier-b.service"}, {"frontier-b.service"}],
                gpu=[["fit"], ["fit"], [], []], pr=[""], file=["missing"])
    assert run(fake, args(gpu=True)) == [
        "finished: frontier-a.service (result=success status=0)",
        "gpu idle: no gpu-class job is running or holding the GPU lock"]
    assert fake.t == 120.0


def test_batch_zero_wakes_on_the_first_event():
    fake = Fake(units=[{"frontier-a.service", "frontier-b.service"}, {"frontier-b.service"}],
                gpu=[[]], pr=[""], file=["missing"])
    assert run(fake, args(batch=0)) == ["finished: frontier-a.service (result=success status=0)"]
    assert fake.t == 0.0


def test_units_default_to_frontier_only_with_gpu(monkeypatch):
    mod = load()
    seen = []
    monkeypatch.setattr(mod, "wait", lambda a: seen.append(a.unit) or ["x"])
    monkeypatch.setattr(mod, "gpu_jobs", list)
    mod.main([])
    mod.main(["--gpu"])
    assert seen == [[], ["frontier-*"]]

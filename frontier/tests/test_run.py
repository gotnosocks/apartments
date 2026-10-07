import os
import time

from rentfrontier.run import contention, cpu_clock


def test_contention_counts_own_work_as_own():
    # Spin until this thread has used 0.2 s of CPU, however busy the machine
    # is (light jobs run at low priority beside others). thread_time is exact
    # and can't run ahead of the wall clock; the process counters in the
    # record (os.times, /proc/stat) count whole clock ticks.
    tick = 1 / os.sysconf("SC_CLK_TCK")
    clock = cpu_clock()
    start = time.thread_time()
    x = 0
    while time.thread_time() - start < 0.2:
        x += 1
    load = contention(clock)
    wall = load["wall_seconds"]
    assert wall >= 0.2
    assert load["own_cpu_seconds"] >= 0.2 - 2 * tick
    assert load["other_cpu_seconds"] >= 0.0
    assert load["other_cores"] == load["other_cpu_seconds"] / wall
    assert load["fit_cpus"] == sorted(os.sched_getaffinity(0))
    # Each of the fit's CPUs may round up by a tick, and the own total (os.times)
    # down by one, which shows up as "other".
    n = len(load["fit_cpus"])
    assert 0.0 <= load["other_cores_on_fit_cpus"] <= n + (n + 1) * tick / wall


def test_contention_on_fit_cpus_ignores_other_cpus():
    # Pinned to one CPU, the fit's own CPUs can't be busier than that one CPU.
    before = os.sched_getaffinity(0)
    cpu = min(before)
    os.sched_setaffinity(0, {cpu})
    try:
        clock = cpu_clock()
        time.sleep(0.3)
        load = contention(clock)
    finally:
        os.sched_setaffinity(0, before)
    assert load["fit_cpus"] == [cpu]
    # /proc/stat and os.times count whole clock ticks, and each rounds several
    # fields separately: allow three ticks.
    tick = 1 / os.sysconf("SC_CLK_TCK")
    assert load["other_cores_on_fit_cpus"] <= 1.0 + 3 * tick / load["wall_seconds"]


def test_data_rules_are_validated_when_parsed():
    import argparse

    import pytest
    from rentfrontier.run import _data_rules

    assert _data_rules("unit-labels-v1") == ("unit-labels-v1",)
    with pytest.raises(argparse.ArgumentTypeError, match="unknown data rules"):
        _data_rules("unit-labels-v1,no-such-rule")


def test_only_the_unit_merge_is_refused_on_the_units_split():
    import pytest
    from rentfrontier.run import check_rules_for_split

    check_rules_for_split(("unit-labels-v1", "quarantine-v1"), "rows")
    check_rules_for_split(("quarantine-v1",), "units")
    with pytest.raises(SystemExit, match="unit-labels-v1"):
        check_rules_for_split(("unit-labels-v1",), "units")


def test_unit_merging_rules_are_refused_on_the_units_split():
    import pytest
    from rentfrontier import run

    for rule in ("unit-labels-v1", "unit-labels-v2"):
        with pytest.raises(SystemExit, match="merges units"):
            run.check_rules_for_split([rule, "quarantine-v2"], "units")
        run.check_rules_for_split([rule], "rows")
    run.check_rules_for_split(["quarantine-v2"], "units")


def test_noise_provenance_records_each_sets_own_311_file(monkeypatch):
    from rentfrontier import features, run

    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    noise = {f: run.feature_sources(f)["noise311"]["path"] for f in features.NOISE}
    assert noise["nb3-noise-v1"] == features.NB3_NOISE_FILE
    assert noise["unitnoise-v1"] == features.NOISE_FILE

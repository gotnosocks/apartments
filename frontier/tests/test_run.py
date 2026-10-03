import os
import time

from rentfrontier.run import contention, cpu_clock


def test_contention_counts_own_work_as_own():
    clock = cpu_clock()
    end = time.perf_counter() + 0.3
    x = 0
    while time.perf_counter() < end:
        x += 1
    load = contention(clock)
    assert load["wall_seconds"] >= 0.3
    assert load["own_cpu_seconds"] > 0.2
    assert load["other_cpu_seconds"] >= 0.0
    assert load["other_cores"] == load["other_cpu_seconds"] / load["wall_seconds"]
    assert load["fit_cpus"] == sorted(os.sched_getaffinity(0))
    assert 0.0 <= load["other_cores_on_fit_cpus"] <= len(load["fit_cpus"])


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
    # /proc/stat counts whole 10 ms ticks, so allow one tick over the wall time.
    assert load["other_cores_on_fit_cpus"] <= 1.1


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

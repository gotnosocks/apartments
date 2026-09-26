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


def test_the_deprecated_gibbs_sampler_is_refused_for_new_runs():
    import pytest
    from rentfrontier import run

    with pytest.raises(SystemExit, match="deprecated"):
        run.main(["--split", "rows", "--sampler", "gibbs", "--name", "never-written"])


def test_data_rules_are_validated_when_parsed():
    import argparse

    import pytest
    from rentfrontier.run import _data_rules

    assert _data_rules("unit-labels-v1") == ("unit-labels-v1",)
    with pytest.raises(argparse.ArgumentTypeError, match="unknown data rules"):
        _data_rules("unit-labels-v1,no-such-rule")

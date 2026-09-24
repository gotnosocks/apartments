import numpy as np
import pandas as pd
import pytest
import xarray as xr

from models.sampler_efficiency import (
    efficiency,
    normalized_statistics,
    retained_wall_bounds,
    warmup_boundary_bounds,
)


def test_rates_keep_bulk_tail_and_denominators_separate():
    table = pd.DataFrame(
        {"ess_bulk": [800.0, 1200.0], "ess_tail": [400.0, 700.0]}, index=["a", "b"]
    )
    result = efficiency(table, {"retained": 200.0, "including_warmup": 400.0})
    assert result.loc["a", "ess_bulk_per_second_retained"] == 4.0
    assert result.loc["a", "ess_tail_per_second_retained"] == 2.0
    assert result.loc["b", "ess_bulk_per_second_including_warmup"] == 3.0
    assert len(table.columns) == 2


@pytest.mark.parametrize("seconds", [0, -1, np.nan, np.inf, "200"])
def test_invalid_times_cannot_produce_a_speed_claim(seconds):
    with pytest.raises(ValueError):
        efficiency(
            pd.DataFrame({"ess_bulk": [500], "ess_tail": [500]}), {"retained": seconds}
        )


def test_depth_saturation_is_normalized_without_changing_saved_stats():
    stats = xr.Dataset({"tree_depth": ("draw", [9, 10, 11])})
    result = normalized_statistics(stats, 10)
    assert result.maxdepth_reached.values.tolist() == [False, True, True]
    assert "maxdepth_reached" not in stats
    assert normalized_statistics(result, 10) is result


def events():
    return [
        {
            "chains": [
                {
                    "chain": i,
                    "finished_draws": n,
                    "runtime_seconds": t + i,
                    "tuning": n < 4000,
                }
                for i in range(2)
            ]
        }
        for n, t in [(3900, 500), (4200, 530), (10000, 1200)]
    ]


def test_warmup_boundary_is_interval_not_false_precision():
    rows = warmup_boundary_bounds(events(), 4000, 6000, 2)
    assert [r["retained_seconds_lower"] for r in rows] == [670, 670]
    assert [r["retained_seconds_upper"] for r in rows] == [700, 700]


@pytest.mark.parametrize("indices", [[0, 1], [1, 2], [0]])
def test_no_timing_from_unfinished_or_unbracketed_chains(indices):
    with pytest.raises(ValueError):
        warmup_boundary_bounds([events()[i] for i in indices], 4000, 6000, 2)


def wall_events():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Chain 0 warms up sooner; chain 1 finishes last. Neither individual
    # chain's elapsed time, nor their sum, is the shared sampling interval.
    return [
        {
            "updated_at": (start + timedelta(seconds=t)).isoformat(),
            "chains": [{"chain": i, "finished_draws": n} for i, n in enumerate(ns)],
        }
        for t, ns in [
            (0, [0, 0]),
            (100, [3999, 3000]),
            (120, [4100, 3999]),
            (140, [4200, 4100]),
            (600, [10000, 9900]),
            (620, [10000, 10000]),
        ]
    ]


def test_pooled_ess_uses_shared_wall_bounds_not_chain_runtime_sum():
    bounds = retained_wall_bounds(wall_events(), 4000, 6000, 2)
    assert bounds["retained_wall_seconds_lower"] == 480
    assert bounds["retained_wall_seconds_upper"] == 520
    rates = efficiency(
        pd.DataFrame({"ess_bulk": [1040.0], "ess_tail": [520.0]}),
        {
            "lower_rate": bounds["retained_wall_seconds_upper"],
            "upper_rate": bounds["retained_wall_seconds_lower"],
        },
    )
    assert rates.loc[0, "ess_bulk_per_second_lower_rate"] == 2
    assert rates.loc[0, "ess_bulk_per_second_upper_rate"] == pytest.approx(1040 / 480)


@pytest.mark.parametrize(
    "change",
    ["unfinished", "unbracketed", "backward", "duplicate", "missing_chain", "naive"],
)
def test_wall_bounds_reject_incomplete_or_invalid_callbacks(change):
    records = wall_events()
    if change == "unfinished":
        records.pop()
    elif change == "unbracketed":
        records = records[3:]
    elif change == "backward":
        records[2]["chains"][0]["finished_draws"] = 10
    elif change == "duplicate":
        records[2]["updated_at"] = records[1]["updated_at"]
    elif change == "missing_chain":
        records[2]["chains"].pop()
    elif change == "naive":
        records[2]["updated_at"] = "2026-01-01T00:02:00"
    with pytest.raises(ValueError):
        retained_wall_bounds(records, 4000, 6000, 2)

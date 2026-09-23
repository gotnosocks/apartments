"""Sequential forecast policies must not borrow current or future outcomes."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest

from models import rolling_rent_validation as rolling
from models import amenity_rent_model as amenities
from models import minimal_rent_model as baseline


def sample():
    rows = []
    for period in pd.date_range("2017-01-01", "2019-12-01", freq="MS"):
        for unit in range(6):
            rent = 3000.0 + 100 * unit + 5 * (period.year - 2017)
            rows.append(
                dict(
                    unit_id=f"u{unit}",
                    building=f"b{unit // 2}",
                    audit_id=f"{period.date()}-{unit}",
                    period=period,
                    asking_rent=rent,
                    log_rent=np.log(rent),
                    bedrooms=1.0,
                    bathrooms=1.0,
                    square_feet=600.0,
                    laundry_type="in_unit" if unit % 2 else "in_building",
                )
            )
    return pd.DataFrame(rows)


def history():
    rows = []
    for month in range(1, 7):
        for unit in range(40):
            rows.append(
                dict(
                    unit_id=str(unit),
                    building=str(unit // 2),
                    audit_id=f"{month}-{unit}",
                    period=f"2019-{month:02d}-01",
                    stratum="seen_unit",
                    asking_rent=3000.0 * np.exp(0.01 * month),
                    monthly=3000.0,
                    annual_frozen=2900.0,
                    monthly_recent=3100.0,
                )
            )
    return pd.DataFrame(rows)


def test_current_and_future_targets_cannot_change_forecasts_or_intervals():
    data = sample()
    origin = pd.Timestamp("2019-04-01")
    train = data[data.period < origin]
    test = data[data.period.eq(origin)]
    hist = history()
    log_pred = np.full(len(test), np.log(3000.0))
    table, rules = rolling.forecast_table(train, test, log_pred, log_pred, hist, origin)
    changed = hist.copy()
    changed.loc[changed.period >= "2019-04-01", "asking_rent"] = 1e8
    changed_test = test.copy()
    changed_test["asking_rent"] = 1e9
    replay, replayed_rules = rolling.forecast_table(
        train, changed_test, log_pred, log_pred, changed, origin
    )
    assert rules == replayed_rules
    pd.testing.assert_frame_equal(
        table.drop(columns="asking_rent"), replay.drop(columns="asking_rent")
    )
    assert rules["recent_adjustment"]["log_offset"] == pytest.approx(0.02)
    assert rules["interval_rules"]["monthly"]["seen_unit"]["end"] == "2019-03-01"
    assert (
        rules["interval_rules"]["monthly"]["new_building"]["scope"] == "pooled_fallback"
    )
    empty = rolling.interval_rules(hist, pd.Timestamp("2019-03-01"))
    assert empty["monthly"]["seen_unit"]["status"] == "unavailable"


def test_calendar_windows_strata_and_tail_scoring():
    hist = history()
    assert (
        rolling.earlier_history(hist, pd.Timestamp("2020-04-01"), 12).period.min()
        == "2019-04-01"
    )
    data = sample()
    train = data[data.period < "2019-01-01"]
    test = data[data.period.eq("2019-01-01")].copy()
    test.loc[test.index[0], "unit_id"] = "new-unit"
    test.loc[test.index[1], ["unit_id", "building"]] = ["new-unit-2", "new-building"]
    assert rolling.familiarity(train, test).tolist()[:3] == [
        "new_unit_seen_building",
        "new_building",
        "seen_unit",
    ]
    # Scoring must not drop uncalibrated rows from point-prediction denominators.
    table, _ = rolling.forecast_table(
        train,
        test,
        np.log(test.asking_rent.to_numpy()),
        np.log(test.asking_rent.to_numpy()),
        pd.DataFrame(),
        pd.Timestamp("2019-01-01"),
    )
    scored = rolling.score(table)["policies"]["monthly"]
    assert scored["observations"] == 6
    assert scored["intervals"]["95"]["available_rows"] == 0
    assert scored["intervals"]["95"]["unavailable_rows"] == 6
    for policy in rolling.POLICIES:
        for level in (80, 95):
            table[f"{policy}_{level}_lower"] = table.asking_rent * 0.9
            table[f"{policy}_{level}_upper"] = table.asking_rent * 1.1
    scored = rolling.score(table)["policies"]["monthly"]["intervals"]["80"]
    assert scored["coverage_percent"] == 100
    assert scored["median_width_percent_of_prediction"] == pytest.approx(20)


def test_monthly_checkpoint_resume_and_swapped_forecast_rejection(
    tmp_path, monkeypatch
):
    data = sample()
    monkeypatch.setattr(
        amenities, "load_analytical", lambda _: (data, {"fixture": True}, {})
    )
    root = tmp_path / "run"
    kwargs = dict(start_year=2019, end_year=2019, min_rows=1)
    prepared = rolling.run(tmp_path, root, prepare_only=True, **kwargs)
    assert prepared["months"] == 12
    partial = rolling.run(tmp_path, root, max_new_months=2, **kwargs)
    assert partial == {"phase": "paused_at_declared_limit", "completed_months": 2}
    assert not (root / "summary" / "complete.json").exists()
    result = rolling.run(tmp_path, root, **kwargs)
    report = json.loads((root / "summary" / "report.json").read_text())
    assert report["months"] == 12
    assert report["pooled"]["rows"] == 72
    assert (
        report["pooled"]["policies"]["monthly"]["intervals"]["80"]["unavailable_rows"]
        == 18
    )
    january = pd.read_json(
        root / "2019-01" / "forecast" / "predictions.jsonl", lines=True
    )
    np.testing.assert_allclose(january.annual_frozen, january.monthly)

    def forbidden(*args, **kwargs):
        raise AssertionError("Completed fits must not be repeated")

    monkeypatch.setattr(baseline, "fit", forbidden)
    assert rolling.run(tmp_path, root, **kwargs) == result
    source = root / "2019-01" / "forecast"
    target = root / "2019-02" / "forecast"
    shutil.rmtree(target)
    shutil.copytree(source, target)
    with pytest.raises(ValueError, match="membership or dependency"):
        rolling.run(tmp_path, root, **kwargs)


def test_protocol_change_and_incomplete_months_rejected(tmp_path, monkeypatch):
    data = sample()
    monkeypatch.setattr(
        amenities, "load_analytical", lambda _: (data, {"fixture": True}, {})
    )
    rolling.run(
        tmp_path,
        tmp_path / "run",
        start_year=2019,
        end_year=2019,
        min_rows=1,
        prepare_only=True,
    )
    with pytest.raises(ValueError, match="identity changed"):
        rolling.run(
            tmp_path,
            tmp_path / "run",
            start_year=2019,
            end_year=2019,
            min_rows=2,
            prepare_only=True,
        )
    data = data[~data.period.eq("2019-06-01")]
    with pytest.raises(ValueError, match="Insufficient rows"):
        rolling.run(
            tmp_path,
            tmp_path / "missing",
            start_year=2019,
            end_year=2019,
            min_rows=1,
            prepare_only=True,
        )

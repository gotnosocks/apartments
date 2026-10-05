from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from rentfrontier import explain, kit, model


def toy(seed=0, draws=12, buildings=5, months=20, slopes=("f1", "f2")):
    rng = np.random.default_rng(seed)
    names = ["f1", "f2", "f3", "f4"]
    feats = SimpleNamespace(names=names, groups=["a", "a", "b", "c"])
    prep = SimpleNamespace(
        buildings=np.array([f"b{i}" for i in range(buildings)]),
        periods=pd.period_range("2025-01", periods=months, freq="M").to_timestamp(),
        offset=8.3,
    )
    config = SimpleNamespace(
        building_walk=True,
        walk_knot_months=6,
        bedroom_time=True,
        bedroom_slope=True,
        feature_slopes=list(slopes),
    )
    knots = model.n_knots(months, 6)
    kept = {
        "alpha": rng.normal(0, 0.1, draws),
        "trend": rng.normal(0, 0.1, (draws, months)),
        "season_daily_coef": rng.normal(0, 0.05, (draws, 4)),
        "beta": rng.normal(0, 0.2, (draws, len(names))),
        "bedroom_time": rng.normal(0, 0.05, (draws, 4, months)),
        "building": rng.normal(0, 0.3, (draws, buildings)),
        "walk": rng.normal(0, 0.1, (draws, buildings, knots)),
        "bedroom_slope": rng.normal(0, 0.1, (draws, buildings)),
        "fslope": rng.normal(0, 0.1, (draws, buildings, len(slopes))),
        "sigma": rng.uniform(0.05, 0.1, (draws, 4)),
        "nu": rng.uniform(3, 8, draws),
        "unit_scale": rng.uniform(0.05, 0.2, draws),
        "unit_nu": rng.uniform(3, 8, draws),
        "unit": rng.normal(0, 0.1, (draws, 7)),
    }
    return kept, prep, config, feats


def kit_total(record, buildings, x, b, bedrooms, year_frac):
    """The site's formula, in numpy: every term but the unit level."""
    beta = np.array(record["beta"])
    coef = np.array(record["season"]["coef"])
    season = coef @ model.day_basis(np.array([year_frac]), coef.shape[1] // 2)[0]
    group = min(max(round(bedrooms), 0), 3)
    centered = min(max(round(bedrooms), 0), 4) - 1.0
    row = buildings.iloc[b]
    slope_cols = [record["features"].index(n) for n in record["slopes"]]
    fslope = np.array(row.fslope).reshape(len(beta), -1)
    return (
        np.array(record["market"])
        + season
        + beta @ x
        + np.array(record["bedroom_time"])[:, group]
        + np.array(row.level)
        + np.array(row.bedroom_slope) * centered
        + fslope @ x[slope_cols]
    )


@pytest.mark.parametrize("slopes", [("f1", "f2"), ()])
def test_kit_reproduces_log_terms_at_the_last_month(slopes):
    kept, prep, config, feats = toy(slopes=slopes)
    if not slopes:
        kept.pop("fslope")
    record, buildings = kit.kit_tables(kept, prep, config, feats)
    rng = np.random.default_rng(1)
    n = 30
    month = len(prep.periods) - 1
    bedrooms = rng.integers(0, 6, n)
    year_frac = rng.uniform(0, 1, n)
    a = model.Arrays(
        y=np.zeros(n),
        x=rng.normal(0, 1, (n, len(feats.names))),
        month=np.full(n, month, np.int32),
        calendar=np.full(n, prep.periods[-1].month - 1, np.int32),
        building=rng.integers(0, len(prep.buildings), n).astype(np.int32),
        unit=np.full(n, -1, np.int32),
        knot=np.full(n, month // model.KNOT_MONTHS, np.int32),
        knot_frac=np.full(n, (month % model.KNOT_MONTHS) / model.KNOT_MONTHS),
        bed_group=np.minimum(bedrooms.clip(0, 3), 3).astype(np.int32),
        beds_centered=bedrooms.clip(0, 4) - 1.0,
        unit_time=np.zeros(n),
        year_frac=year_frac,
    )
    fidx = [feats.names.index(s) for s in slopes]
    terms = explain.log_terms(kept, a, feats.groups, 6, True, True, prep.offset, fidx)
    expected = sum(v for k, v in terms.items() if k != "unit")
    for i in range(n):
        got = kit_total(
            record, buildings, a.x[i], a.building[i], bedrooms[i], year_frac[i]
        )
        np.testing.assert_allclose(got, expected[:, i], rtol=0, atol=1e-12)


def test_thinning_keeps_evenly_spaced_draws():
    assert (
        kit.thin(1000).tolist() == np.linspace(0, 999, 250).round().astype(int).tolist()
    )
    assert kit.thin(10).tolist() == list(range(10))
    kept, prep, config, feats = toy(draws=600)
    record, buildings = kit.kit_tables(kept, prep, config, feats)
    assert record["draws"] == 250 and len(record["nu"]) == 250
    assert len(buildings.level[0]) == 250


def test_unsupported_designs_are_refused():
    kept, prep, config, feats = toy()
    with pytest.raises(SystemExit, match="line-effects"):
        kit.kit_tables(kept | {"line_scale": np.full(12, 0.1)}, prep, config, feats)
    with pytest.raises(SystemExit, match="unit-drift"):
        kit.kit_tables(kept | {"unit_drift": np.zeros((12, 3))}, prep, config, feats)

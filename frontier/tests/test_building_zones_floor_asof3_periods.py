import numpy as np
import pandas as pd
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import b0_3, normal_walk, splits
from rentfrontier import building_zones_floor_asof as bzfa
from rentfrontier import building_zones_floor_asof3 as asof3
from rentfrontier import building_zones_floor_asof3_periods as periods


def _designs(tmp_path, monkeypatch):
    """The asof3 design and the period design of a frame spanning all three periods."""
    frame, tables, units, trucks = tbu._design(n=3000, weeks=200)
    tables.pop("attrs")
    ads = tbfa.ads_for(frame)
    ads.to_parquet(tmp_path / "rows.parquet")
    monkeypatch.setattr(asof3, "ROWS", tmp_path / "rows.parquet")
    kw = dict(
        held=splits.latest_split(frame),
        amenities=tbfa.amenities_for(ads),
        lots=tbfa.lots_for(frame),
        units=units,
        trucks=trucks,
        ages=tbs.ages_for(frame),
        **tables,
    )
    return frame, asof3.design(frame, **kw), periods.design(frame, **kw)


def test_periods_are_disjoint_and_cover_every_day():
    day = pd.to_datetime(
        [
            "2019-06-01",
            "2020-02-29",
            "2020-03-01",
            "2021-12-31",
            "2022-01-01",
            "2026-10-01",
        ]
    )
    m = periods.period_masks(pd.DataFrame({"latest_day": day}))
    np.testing.assert_array_equal(m.sum(axis=1), 1)
    np.testing.assert_array_equal(m.argmax(axis=1), [0, 0, 1, 1, 2, 2])


def test_split_columns_sum_to_the_original(tmp_path, monkeypatch):
    frame, base, d = _designs(tmp_path, monkeypatch)
    assert periods.NAME == "building-zones-floor-asof3-periods"
    assert periods.run is bzfa.run
    masks = periods.period_masks(frame)
    assert masks.any(axis=0).all()
    np.testing.assert_array_equal(masks.sum(axis=1), 1)
    split = [n for n in periods.SPLIT_COLUMNS if n in base.names]
    assert {"unit:laundry_in_unit", "unit:dishwasher", "unit:garden"} <= set(split)
    assert any(n.startswith("bld:doorman_") for n in split)
    assert not set(periods.SPLIT_COLUMNS) & set(d.names)
    for n in split:
        orig = base.x[:, base.names.index(n)]
        total = np.zeros(len(frame))
        for k, (p, _, _) in enumerate(periods.PERIODS):
            name = periods.period_name(n, p)
            if name in d.names:
                v = d.x[:, d.names.index(name)]
                np.testing.assert_array_equal(v[~masks[:, k]], 0)
                total += v
            else:
                assert d.count[name] == 0
                np.testing.assert_array_equal(orig[masks[:, k]], 0)
        np.testing.assert_array_equal(total, orig)
    rest = [n for n in base.names if n not in periods.SPLIT_COLUMNS]
    assert [n for n in d.names if "@" not in n] == rest
    for n in rest:
        np.testing.assert_array_equal(
            d.x[:, d.names.index(n)], base.x[:, base.names.index(n)]
        )
    np.testing.assert_array_equal(d.y, base.y)
    np.testing.assert_array_equal(d.week, base.week)


def test_split_columns_keep_the_original_prior(tmp_path, monkeypatch):
    _, base, d = _designs(tmp_path, monkeypatch)
    pri = periods.Priors()

    def prior(names):
        kept = [n for n in names if not b0_3.is_bath_step(n)]
        m, s = normal_walk.prior_arrays(pri, names)
        return dict(zip(kept, zip(m, s)))

    p0, p1 = prior(base.names), prior(d.names)
    assert any("@" in n for n in p1)
    for n, v in p1.items():
        assert v == p0[n.split("@")[0]]
    rec = periods.run_record(d)
    assert rec["periods"]["day"] == "latest_day"
    assert rec["asof"]["pipeline_rows"] == str(tmp_path / "rows.parquet")

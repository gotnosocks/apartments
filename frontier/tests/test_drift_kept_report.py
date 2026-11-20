import json

import numpy as np
import pandas as pd
import pytest
from test_drift_deals import _run
from test_drift_diagnostics import _with_lots

from rentfrontier import drift_kept_report


def _levels(level):
    names = pd.Index([f"b{i}" for i in range(len(level))], name="building")
    return pd.DataFrame({"zone": "manhattan", "level": level}, index=names)


def test_places_follow_the_deals_order():
    # Shares equal to four places keep the rows' order, as the deals table's sort does.
    share = [0.50004, 0.1, 0.5, 0.02]
    assert drift_kept_report.places(share).tolist() == [3, 2, 4, 1]


def test_ads_over_lists_only_the_ads_past_the_bound_worst_first():
    t = drift_kept_report.ads_over(
        [11, 12, 13, 14],
        [1, 2, 3, 4],
        [0.1, 0.2, 0.3, 0.4],
        [1.2, 1.05, np.nan, np.inf],
    )
    assert t.listing_id.tolist() == ["14", "11"] and t.place.tolist() == [4, 1]


def test_buildings_listed_takes_far_thin_levels_and_unmixed_ones():
    level = [0.6, -0.7, 0.6, 0.5, 0.1, 0.2, 2.0]
    rhat = [1.0, 1.0, 1.0, 1.0, 1.3, np.nan, 1.06]
    rows = [9, 0, 10, 1, 500, 1, 3]
    ads = [0, 2, 1, 1, 0, 0, 0]
    t = drift_kept_report.buildings_listed(_levels(level), rhat, rows, ads)
    t = t.set_index("building")
    # b2 has ten training rows and b3 a level of exactly 0.5: neither is far and thin.
    # b5's draws are constant, so it has no R-hat and is not counted as unmixed.
    assert t.index.tolist() == ["b6", "b1", "b0", "b4"]
    assert t.far_thin.tolist() == [True, True, True, False]
    assert t.rhat_over.tolist() == [True, False, False, True]
    assert t.train_rows.tolist() == [3, 0, 9, 500] and t.scored_ads["b1"] == 2


def _kept(tmp_path):
    """`_run`'s fit with building levels: a high on one training row, b unmixed between
    its chains, c near zero. Listing 3's predicted location is unmixed too."""
    run, _, reg = _run(tmp_path)
    _with_lots(reg)
    nj = tmp_path / "nj.parquet"
    pd.DataFrame(
        {"building": ["z"], "latitude": [40.7], "longitude": [-74.05]}
    ).to_parquet(nj)
    z = dict(np.load(run / "posterior.npz"))
    rng = np.random.default_rng(2)
    bld = 0.01 * rng.standard_normal((2, 50, 3)) + np.array([0.8, 0.1, 0.0])
    bld[1, :, 1] += 0.3
    z["kept/bld"] = bld
    z["kept/pred_loc"][1, :, 1] += 0.05
    np.savez(run / "posterior.npz", **z)
    record = json.loads((run / "result.json").read_text())
    record |= {
        "registry": str(reg),
        "nj_registry": str(nj),
        "surfaces": [
            {"name": "manhattan", "first": 0, "sites": 1},
            {"name": "outer", "first": 1, "sites": 2},
        ],
    }
    (run / "result.json").write_text(json.dumps(record))
    return run


def test_report_reads_a_runs_kept_draws(tmp_path, capsys):
    run = _kept(tmp_path)
    out = drift_kept_report.report(run)
    # The held-out ads are 2 (building a), 3 and 4 (b) and 6 (c); training rows 1 and 5.
    assert [a["listing_id"] for a in out["ads"]] == ["3"]
    assert out["ads"][0]["rhat"] > 1.05 and 1 <= out["ads"][0]["place"] <= 4
    b = pd.DataFrame(out["buildings"]).set_index("building")
    assert b.index.tolist() == ["a", "b"]
    assert b.far_thin.tolist() == [True, False] and b.rhat_over.tolist() == [
        False,
        True,
    ]
    assert b.train_rows.tolist() == [1, 1] and b.scored_ads.tolist() == [1, 2]
    assert abs(b.level["a"] - 0.8) < 0.01 and b.zone.tolist() == ["manhattan", "outer"]
    assert out["counts"] == {
        "scored_ads": 4,
        "ads_rhat_over": 1,
        "buildings": 3,
        "buildings_rhat_over": 1,
        "buildings_rhat_over_with_scored_ads": 1,
        "buildings_far_thin": 1,
        "buildings_far_thin_with_scored_ads": 1,
        "scored_ads_in_far_thin_buildings": 1,
        "buildings_level_over_far_with_scored_ads": 1,
        "scored_ads_in_buildings_level_over_far": 1,
    }
    before = {p.name for p in run.iterdir()}
    drift_kept_report.main([run.name, "--runs", str(run.parent)])
    assert {p.name for p in run.iterdir()} - before == {"kept_report.json"}
    assert json.loads((run / "kept_report.json").read_text()) == out
    assert "buildings: 2" in capsys.readouterr().out


def test_report_refuses_a_run_without_kept_levels(tmp_path):
    run, _, _ = _run(tmp_path)
    with pytest.raises(SystemExit, match="does not keep kept/bld"):
        drift_kept_report.report(run)

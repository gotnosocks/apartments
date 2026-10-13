import math

import numpy as np
import pandas as pd
import pytest

from rentfrontier import clusterse


def test_singleton_clusters_give_the_iid_se():
    d = np.random.default_rng(0).normal(size=200)
    se = clusterse.cluster_se(d, np.arange(200))
    assert se == pytest.approx(d.std(ddof=1) * math.sqrt(200))


def test_rows_moving_together_widen_the_clustered_se():
    rng = np.random.default_rng(1)
    groups = np.repeat(np.arange(100), 20)
    d = rng.normal(size=100)[groups] + 0.1 * rng.normal(size=2000)
    iid = d.std(ddof=1) * math.sqrt(len(d))
    assert clusterse.cluster_se(d, groups) > 3 * iid


def test_verdict_uses_two_combined_ses():
    assert clusterse.verdict(10.0, 4.0, 0.0) == "win"
    assert clusterse.verdict(-10.0, 4.0, 0.0) == "loss"
    assert clusterse.verdict(10.0, 6.0, 0.0) == "tie"


def test_year_gap_compares_late_and_early_bands_within_bins():
    rows = pd.DataFrame(
        {
            "rung": "new building",
            "row_bin": ["1-5"] * 4 + ["101+"] * 4,
            "year": [2015, 2015, 2025, 2025] * 2,
            # 1-5: early covered 2/2, late 1/2; 101+: all covered.
            "pit": [0.5, 0.5, 0.5, 0.95, 0.5, 0.5, 0.5, 0.5],
            "unitsres_tercile": "small",
            "class_family": "D",
        }
    )
    gap = clusterse.year_gap(rows)
    assert gap["by_bin"] == {"1-5": -50.0, "101+": 0.0}
    assert gap["weighted_mean"] == pytest.approx(-25.0)


def test_paired_rows_weights_each_building_once(tmp_path):
    def write(path, lpd):
        path.mkdir()
        pd.DataFrame(
            {
                "audit_id": ["r1", "r2", "r3"],
                "rung": "new building",
                "building": ["a", "a", "b"],
                "bbl": ["1", "1", "2"],
                "lpd": lpd,
            }
        ).to_parquet(path / "rows.parquet")

    write(tmp_path / "base", [0.0, 0.0, 0.0])
    write(tmp_path / "other", [1.0, 3.0, -1.0])
    out = clusterse.paired_rows(tmp_path / "base", tmp_path / "other")
    assert out["row_sum"]["lpd_diff"] == pytest.approx(3.0)
    assert out["building_weighted"]["lpd_diff"] == pytest.approx(2.0 - 1.0)

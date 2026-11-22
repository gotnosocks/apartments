"""Tests for `rentfrontier.drift_building_phase_unitkn_ablate`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import building_attrs
from rentfrontier import drift_building_phase_unitkn_ablate as ablate


def test_parse_and_extract_variant():
    assert ablate.parse_variant(None) == ()
    assert ablate.parse_variant("y1, marks , covid_mean") == (
        "y1",
        "marks",
        "covid_mean",
    )
    with pytest.raises(ValueError, match="unknown variant"):
        ablate.parse_variant("not_a_real_token")

    toks, rest = ablate._extract_variant(
        ["--split", "carried", "--variant", "y1,sbf", "--seed", "1"]
    )
    assert toks == ("y1", "sbf")
    assert rest == ["--split", "carried", "--seed", "1"]

    toks2, rest2 = ablate._extract_variant(["--variant=covid_vol", "--seed", "2"])
    assert toks2 == ("covid_vol",)
    assert rest2 == ["--seed", "2"]


def test_concession_gap_is_strictly_causal(tmp_path: Path):
    rows_pq = tmp_path / "rows.parquet"
    pd.DataFrame(
        {
            "listing_id": ["L1", "L2", "L3", "L4"],
            "months_free": [0.0, 2.0, 0.0, 1.0],
        }
    ).to_parquet(rows_pq, index=False)
    frame = pd.DataFrame(
        {
            "listing_id": ["L1", "L2", "L3", "L4"],
            "building": ["B1", "B1", "B1", "B1"],
            "price_at": [
                "2020-05-01T00:00:00Z",
                "2020-06-01T00:00:00Z",
                "2020-07-01T00:00:00Z",
                "2023-07-01T00:00:00Z",
            ],
        }
    )
    # L2 is held out, so L3 must NOT see L2's concession!
    train = np.array([True, False, True, True])
    mat, names = ablate.concession_gap_features(frame, train, rows_path=rows_pq)
    assert names == [
        "ad:concess_2020_22_bld",
        "ad:concess_2020_22_missing",
        "ad:concess_2020_22_rate",
    ]
    assert np.allclose(mat, 0.0)

    # Now L2 is in training: L1 (before L2) sees 0, L3 (after L2, no concession in 2020) sees 1,
    # and L4 (2023, outside 2020-2022) sees 0.
    train2 = np.array([True, True, False, True])
    mat2, _ = ablate.concession_gap_features(frame, train2, rows_path=rows_pq)
    assert mat2[0, 0] == 0.0
    assert mat2[2, 0] == 1.0  # bld_ever in 2020-2022
    assert mat2[2, 1] == 1.0  # missing concession on L3
    assert mat2[2, 2] == pytest.approx(0.5)  # 1 of 2 prior training ads
    assert mat2[3, 0] == 0.0  # 2023 outside 2020-2022


def test_rentstab_dhcr_uses_strictly_prior_year(tmp_path: Path, monkeypatch):
    reg = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": ["B1", "B2"], "bbl": [1000000001, 3000000002]}
    ).to_parquet(reg, index=False)
    monkeypatch.setattr(building_attrs, "REGISTRY", reg)

    rs = tmp_path / "rentstab.parquet"
    pd.DataFrame(
        {
            "bbl": [1000000001, 1000000001],
            "year": [2019, 2021],
            "units": [0, 12],
        }
    ).to_parquet(rs, index=False)

    frame = pd.DataFrame(
        {
            "building": ["B1", "B1", "B2"],
            "price_at": [
                "2021-03-01T00:00:00Z",  # ad_yr-1 = 2020 -> sees 2019 (0 units), NOT 2021!
                "2022-03-01T00:00:00Z",  # ad_yr-1 = 2021 -> sees 2021 (12 units)
                "2022-03-01T00:00:00Z",  # not in rentstab
            ],
            "rent_stabilized": [False, False, True],
        }
    )
    mat, names = ablate.rentstab_dhcr_features(frame, rentstab_path=rs)
    assert len(names) == 4
    assert mat[0, 0] == 0.0  # strictly prior year: 2021 ad does NOT peek at 2021 DHCR
    assert mat[1, 0] == 1.0  # 2022 ad sees 2021 DHCR (12 units)
    assert mat[1, 3] == 1.0  # stab:x_2022_on active
    assert mat[2, 0] == 0.0  # B2 not in DHCR
    assert mat[2, 3] == 1.0  # B2 still active via text rent_stabilized


def test_covid_features_are_causal_and_zero_pre_pandemic(tmp_path: Path, monkeypatch):
    reg = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": ["B_MN", "B_BK"], "bbl": [1000000001, 3000000002]}
    ).to_parquet(reg, index=False)
    monkeypatch.setattr(building_attrs, "REGISTRY", reg)

    csv_p = tmp_path / "covid.csv"
    pd.DataFrame(
        {
            "date_of_interest": ["03/01/2020", "04/01/2020"],
            "HOSP_COUNT_7DAY_AVG": [10.0, 500.0],
            "CASE_COUNT_7DAY_AVG": [50.0, 4000.0],
            "MN_HOSPITALIZED_COUNT_7DAY_AVG": [4.0, 120.0],
            "BX_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 100.0],
            "BK_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 160.0],
            "QN_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 100.0],
            "SI_HOSPITALIZED_COUNT_7DAY_AVG": [0.0, 20.0],
            "MN_CASE_COUNT_7DAY_AVG": [20.0, 900.0],
            "BX_CASE_COUNT_7DAY_AVG": [10.0, 800.0],
            "BK_CASE_COUNT_7DAY_AVG": [10.0, 1200.0],
            "QN_CASE_COUNT_7DAY_AVG": [10.0, 900.0],
            "SI_CASE_COUNT_7DAY_AVG": [0.0, 200.0],
        }
    ).to_csv(csv_p, index=False)

    frame = pd.DataFrame(
        {
            "building": ["B_MN", "B_MN", "B_BK"],
            "price_at": [
                "2019-06-01T00:00:00Z",  # pre-pandemic -> all zero
                "2020-04-10T00:00:00Z",  # 14d lag = 2020-03-27 -> sees 03/01 (hosp=10), NOT 04/01!
                "2020-04-20T00:00:00Z",  # 14d lag = 2020-04-06 -> sees 04/01 (hosp=500 -> surge!)
            ],
            "bedrooms": [1, 2, 2],
        }
    )

    class _DummyDesign:
        names = ("bld:doorman_full", "unit:private_outdoor_space")
        x = np.array([[1.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
        y = np.zeros(3)

    mean_mat, names, vol_mat = ablate.covid_features(
        frame, _DummyDesign(), csv_path=csv_p
    )
    assert len(names) == 6
    assert np.allclose(mean_mat[0], 0.0)
    assert np.allclose(vol_mat[0], 0.0)
    # Row 1 (2020-04-10, lagged to 03/27) must NOT see the 04/01 surge!
    assert vol_mat[1, 0] == 0.0
    # Row 2 (2020-04-20, lagged to 04/06) sees hosp=500 -> surge=1, elevated=0
    assert vol_mat[2, 0] == 1.0
    assert vol_mat[2, 1] == 0.0
    assert mean_mat[2, 3] > 0.0  # hosp_x_2pbr active

import pandas as pd

from rentfrontier import features, run


def test_building_violations_reads_the_given_snapshot(tmp_path):
    registry = pd.DataFrame(
        {"building": ["a", "b"], "bin": ["1000001", "1000000"], "bbl": ["11", "22"]}
    )
    hpd = pd.DataFrame(
        {
            "bin": ["1000001", "1000001", "1000001", "9", "9"],
            "bbl": ["11", "11", "11", "22", "22"],
            "class": ["B", "C", "A", "B", "C"],
            "inspectiondate": [
                "2020-03-10",
                "2019-01-05",
                "2020-03-20",
                "2020-02-01",
                "2020-06-01",
            ],
        }
    )
    registry.to_parquet(tmp_path / "r.parquet")
    hpd.to_parquet(tmp_path / "h.parquet")
    frame = pd.DataFrame(
        {"building": ["a", "b", "c"], "period": pd.to_datetime(["2020-04-01"] * 3)}
    )
    got = features.building_violations(
        frame,
        hpd_file=str(tmp_path / "h.parquet"),
        registry_file=str(tmp_path / "r.parquet"),
    )
    # a: the B in the year before (not the 2019 C, not class A); b has a
    # placeholder BIN, so its lot: the February B only; c is not registered.
    assert got.tolist() == [1, 1, 0]


def test_nb5_hpd_reads_and_hashes_the_five_neighbourhood_snapshot():
    assert features.FEATURE_SETS["nb5-hpd-v1"].keywords["file"] == (
        features.NB4_HPD_FILE
    )
    assert features.NB4_SETS["nb5-hpd-v1"] == "nb5-plutoasof-v3"
    assert "nb5-hpd-v1" in features.HPD
    assert features.HPD_SNAPSHOTS["nb5-hpd-v1"] == features.NB4_HPD_FILE
    assert "unitdescplutohpd-v1" not in features.HPD_SNAPSHOTS
    assert run.feature_sources("nb5-hpd-v1")["hpd"]["path"] == features.NB4_HPD_FILE

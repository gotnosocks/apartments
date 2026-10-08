import numpy as np
import pytest
from rentfrontier import effects, features


def test_items_read_indicators_per_ad_and_log_distances_per_doubling():
    rng = np.random.default_rng(0)
    beta = np.column_stack(
        [rng.normal(0.05, 0.01, 4000), rng.normal(-0.02, 0.005, 4000), np.zeros(4000)]
    )
    values = np.column_stack(
        [rng.integers(0, 2, 100), rng.normal(6, 1, 100), np.ones(100)]
    )
    names = ["text:skylight", "log m to dog run", "base"]
    out = effects.item_effects(
        beta, names, ["description", "nearby", "x"], values, [0, 1]
    )
    ad, dog = out
    assert [ad["kind"], dog["kind"]] == ["indicator", "log"]
    assert ad["pct"] == pytest.approx(100 * np.expm1(0.05), abs=0.1)
    assert ad["rows"] == int(values[:, 0].sum())
    assert dog["pct"] == pytest.approx(100 * (2**-0.02 - 1), abs=0.05)
    assert dog["pct_lower_95"] < dog["pct_lower_90"] < dog["pct"] < dog["pct_upper_90"]
    assert dog["probability_positive"] < 0.01 and "median" in dog


def test_a_feature_test_reports_only_the_columns_it_adds():
    assert effects.base_of("nb3-attrs-v1") == "nb3-flagfix-v1"
    assert effects.base_of("nb3-nearby-v1") == "nb3-coded-v2"
    assert effects.base_of(next(iter(features.FEATURE_SETS))) in (
        None,
        *features.FEATURE_SETS,
    )

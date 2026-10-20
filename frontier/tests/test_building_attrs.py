import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0, building_attrs, normal_walk
from test_b0 import frame_of


def _attrs(buildings):
    """A building table over `buildings` with every level present, and one building left out."""
    rng = np.random.default_rng(3)
    n = len(buildings)
    return pd.DataFrame(
        {
            "building": buildings,
            "floors": np.where(rng.random(n) < 0.1, np.nan, rng.integers(2, 40, n)),
            "elevator": rng.choice(["yes", "no", "unknown"], n),
            "doorman": rng.choice(["full", "part", "virtual", "none"], n),
            "tenure": rng.choice(["condo", "coop", "rental"], n),
            "year_built": np.where(
                rng.random(n) < 0.1, np.nan, rng.integers(1880, 2025, n)
            ),
            "ads": 1,
        }
    ).iloc[1:]


def test_design_appends_building_columns_to_the_normal_walk():
    frame, _ = frame_of(n=800, weeks=30, seed=2)
    attrs = _attrs(sorted(frame.building.unique()))
    d = building_attrs.design(frame, attrs=attrs)
    base = normal_walk.design(frame)
    k = len(base.names)
    assert d.names[:k] == base.names
    assert d.names[k:] == list(building_attrs.COLUMNS)
    np.testing.assert_array_equal(d.x[:, :k], base.x)
    x = pd.DataFrame(d.x[:, k:], columns=building_attrs.COLUMNS)
    a = attrs.set_index("building").reindex(frame.building)
    missing = a.elevator.isna().to_numpy()
    assert missing.any()
    # A building with no record takes every unknown level and no known one.
    assert (x.loc[missing, "bld:floors_unknown"] == 1).all()
    assert (x.loc[missing, "bld:elevator_unknown"] == 1).all()
    assert (x.loc[missing, "bld:built_unknown"] == 1).all()
    known = ~missing & a.floors.notna().to_numpy()
    np.testing.assert_allclose(
        x.loc[known, "bld:log_floors"], np.log(a.floors[known] / 5).to_numpy()
    )
    assert (x.loc[~known, "bld:log_floors"] == 0).all()
    year = a.year_built.to_numpy()
    np.testing.assert_array_equal(x["bld:built_2005_on"], (year >= 2005).astype(float))
    np.testing.assert_array_equal(
        x["bld:built_1980_2004"], ((year >= 1980) & (year < 2005)).astype(float)
    )
    np.testing.assert_array_equal(
        x["bld:doorman_virtual"], (a.doorman == "virtual").to_numpy(float)
    )


def test_unset_columns_are_dropped_and_priors_are_the_flag_prior():
    frame, _ = frame_of(n=400, weeks=20, seed=5)
    attrs = _attrs(sorted(frame.building.unique())).assign(tenure="rental")
    d = building_attrs.design(frame, attrs=attrs)
    assert "bld:condo" not in d.names and "bld:coop" not in d.names
    assert d.count["bld:condo"] == 0
    mean, sd = building_attrs.prior_arrays(building_attrs.Priors(), d.names)
    fixed, _, _ = building_attrs.split_index(d.names)
    names = [d.names[j] for j in fixed]
    for j, n in enumerate(names):
        if n.startswith("bld:"):
            assert (mean[j], sd[j]) == b0.Priors.flag


def test_attributes_prefer_the_ads_and_fall_back_to_the_lot():
    rows = pd.DataFrame(
        {
            "building": ["tower"] * 4 + ["walkup"] * 2 + ["quiet"],
            "elevator": [True, True, None, False, None, None, None],
            "doorman_type": ["full_time", None, None, "virtual", None, None, None],
            "building_floor_count": [76, 76, np.nan, 75, np.nan, 5, np.nan],
        }
    )
    lots = pd.DataFrame(
        {
            "numfloors": [8.0, 4.0, 6.0, np.nan],
            "bldgclass": ["I1", "C4", "D6", "R"],
            "yearbuilt": [1968.0, 1910.0, 0.0, np.nan],
        },
        index=["tower", "walkup", "quiet", "nj-condo"],
    )
    t = building_attrs.attributes(building_attrs.ad_attributes(rows), lots)
    t = t.set_index("building")
    assert t.loc["tower", "floors"] == 76  # the ads win over the lot's primary building
    assert t.loc["walkup", "floors"] == 5
    assert t.loc["quiet", "floors"] == 6
    assert np.isnan(t.loc["nj-condo", "floors"])
    assert t.loc["tower", "elevator"] == "yes"  # 2 of 3 stating ads
    assert t.loc["walkup", "elevator"] == "no"  # class C, nothing stated
    assert t.loc["quiet", "elevator"] == "yes"  # class D
    assert t.loc["nj-condo", "elevator"] == "unknown"
    assert t.loc["tower", "doorman"] == "full"  # 1 of 4 ads, over a fifth
    assert t.loc["walkup", "doorman"] == "none"
    assert t.loc["nj-condo", "tenure"] == "condo"
    assert t.loc["walkup", "tenure"] == "rental"
    assert np.isnan(t.loc["quiet", "year_built"])
    assert t.loc["walkup", "year_built"] == 1910


def test_summary_and_scorecard_read_building_premiums(monkeypatch):
    names = ["alpha", "bld:elevator", "bld:built_2005_on"]
    beta = np.zeros((2, 50, 3))
    beta[..., 1] = np.log(1.15)
    beta[..., 2] = np.log(0.7)
    monkeypatch.setattr(normal_walk, "summarize", lambda kept, names: {})
    monkeypatch.setattr(normal_walk, "scorecard", lambda *a: [])
    summary = building_attrs.summarize({"beta": beta}, names)
    assert set(summary["building"]) == {"bld:elevator", "bld:built_2005_on"}
    assert summary["building"]["bld:elevator"]["median"] == pytest.approx(15.0)
    rows = {r["n"]: r for r in building_attrs.scorecard(summary, None, None)}
    assert set(rows) == {"B1", "B7"}  # claims about absent columns are skipped
    assert rows["B1"]["hit"] and rows["B1"]["value"] == "+15.0%"
    assert not rows["B7"]["hit"]  # -30% lies outside -18% to -3%


def test_normal_walk_model_takes_the_wider_design():
    """The normal walk's starting values and density size themselves from the design."""
    pytest.importorskip("numpyro")
    import jax
    from numpyro.infer.util import initialize_model

    jax.config.update("jax_enable_x64", True)
    frame, _ = frame_of(n=600, weeks=25, seed=4)
    attrs = _attrs(sorted(frame.building.unique()))
    d = building_attrs.design(frame, attrs=attrs)
    priors = building_attrs.Priors()
    init = building_attrs.initial_values(d, priors, chains=2, seed=0)
    fixed, _, _ = building_attrs.split_index(d.names)
    assert init["main"].shape == (2, len(fixed) - 1)
    density, post = building_attrs.log_density(d, priors)
    info = initialize_model(jax.random.PRNGKey(0), building_attrs.model(d, priors))
    assert np.isfinite(float(density(info.param_info.z)))
    assert post(info.param_info.z)["beta"].shape == (len(d.names),)

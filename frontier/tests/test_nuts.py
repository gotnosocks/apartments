"""The model ladder's designs and the NUTS sampler (one model definition,
`model.build_model`, scored by the Gibbs sampler's bookkeeping)."""

from dataclasses import replace

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from numpyro import handlers
from rentfrontier import gibbs, model, nuts
from test_gibbs import synthetic

jax.config.update("jax_enable_x64", True)

BASE = {"alpha", "sigma", "nu"}
SITES = {
    "L0-mean": BASE,
    "L1-drift": BASE | {"market_drift"},
    "L2-trend": BASE | {"trend_scale", "trend_step"},
    "L3-season": BASE | {"trend_scale", "trend_step", "season_scale", "season_raw"},
}
SITES["L4-features"] = SITES["L3-season"] | {"beta"}
SITES["L5-building"] = SITES["L4-features"] | {"building_scale", "building"}


def sites(config, prep):
    if config.feature_slopes:  # the synthetic data's own feature columns
        config = replace(config, feature_slopes=tuple(prep.features.names))
    tr = handlers.trace(handlers.seed(model.build_model(prep, config), 0)).get_trace()
    return {k for k, v in tr.items() if v["type"] == "sample" and not v["is_observed"]}


def test_ladder_designs_sample_exactly_their_terms():
    prep = synthetic()
    for name, expected in SITES.items():
        assert sites(model.MODELS[name], prep) == expected, name
    prev = SITES["L5-building"]
    for name in model.LADDER[len(SITES) :]:
        cur = sites(model.MODELS[name], prep)
        assert prev < cur, name
        prev = cur


def test_market_drift_is_a_linear_trend_about_the_mean_month():
    prep = synthetic()
    config = model.MODELS["L1-drift"]
    p = model.constants(prep, config) | {
        "alpha": 0.3,
        "market_drift": 0.05,
        "sigma": 0.1,
        "nu": 5.0,
    }
    mu = model.linear_predictor(p, prep.train.map(jnp.asarray))
    month = prep.train.month
    np.testing.assert_allclose(mu, 0.3 + 0.05 * (month - month.mean()) / 12, atol=1e-12)


@pytest.mark.parametrize(
    "name",
    [
        "L0-mean",
        "L5-building",
        "m0q-btrend",
        "m1-btrend-walk24",
        "m1-twalk24",
        "m0q-btrend-lines",
    ],
)
def test_gibbs_needs_every_base_term(name):
    with pytest.raises(ValueError, match="--sampler nuts"):
        gibbs.build_design(synthetic(), model.MODELS[name])


@pytest.mark.parametrize(
    "coordinates",
    [
        (),
        ("trend_levels", "season_zerosum", "unit_totals"),
        (
            "trend_levels",
            "building_totals",
            "unit_totals",
            "unit_partial",
            "walk_levels",
        ),
    ],
    ids=["default", "levels", "totals"],
)
def test_dense_globals_covers_the_global_sites_only(coordinates):
    from numpyro.infer.util import initialize_model

    prep = synthetic()
    out = nuts.run(
        prep,
        model.MODELS["m1q"],
        nuts.Settings(
            chains=2,
            warmup=50,
            draws=20,
            keep_every=10,
            dense_globals=True,
            coordinates=coordinates,
        ),
        log=lambda *_: None,
    )
    trend = "trend_absolute" if coordinates else "trend_step"
    assert "beta" in out["dense_sites"] and trend in out["dense_sites"]
    if "building_totals" in coordinates:
        assert "building_total_mean" in out["dense_sites"]
    # Every latent site as nuts.run samples it (unconstrained sizes: a zero-sum
    # site over the buildings has one fewer): the dense block holds the small
    # global ones, and every per-building or per-unit array is left out.
    config = replace(
        model.MODELS["m1q"],
        coordinates=coordinates,
        noncentered=() if "walk_levels" in coordinates else ("walk_step",),
    )
    z = initialize_model(
        jax.random.PRNGKey(0), model.build_model(prep, config)
    ).param_info.z
    for k, v in z.items():
        assert (k in out["dense_sites"]) == (v.size < len(prep.buildings) - 1), k
    assert np.isfinite(out["lpd"]).all()


@pytest.mark.parametrize("name", ["L1-drift", "m1q"])
def test_nuts_run_matches_plain_numpyro_mcmc(name):
    """nuts.run's bookkeeping (constants, non-centred walk, collect) gives the
    posterior that NumPyro's own MCMC gives on the same model."""
    from numpyro.infer import MCMC, NUTS

    prep = synthetic()
    config = model.MODELS[name]
    out = nuts.run(
        prep,
        config,
        nuts.Settings(chains=2, warmup=300, draws=600, keep_every=50),
        log=lambda *_: None,
    )
    assert np.isfinite(out["lpd"]).all() and out["lpd"].shape == (10,)
    assert out["kept"]["alpha"].shape == (2, 12)
    assert out["trace"]["divergent"].shape == (2, 600)
    assert out["noncentered"] == (["walk_step"] if config.building_walk else [])

    # Same parameterization as nuts.run (a centred walk sticks near small
    # walk scales; see test_gibbs_matches_nuts_on_same_model).
    ref_config = replace(config, noncentered=tuple(out["noncentered"]))
    ref = MCMC(
        NUTS(model.build_model(prep, ref_config)),
        num_warmup=300,
        num_samples=600,
        num_chains=2,
        chain_method="vectorized",
        progress_bar=False,
    )
    ref.run(jax.random.PRNGKey(1))
    s = {k: np.asarray(v) for k, v in ref.get_samples().items()}
    checks = {"alpha": s["alpha"], "sigma": s["sigma"]}
    if config.market_drift:
        checks["market_drift"] = s["market_drift"]
    if config.building_walk:
        checks["walk_scale"] = s["walk_scale"]
    for k, draws in checks.items():
        # Both runs have ~1,200 draws; allow 5 Monte Carlo SEs at ESS ~ 1/4.
        mcse = draws.std() * np.sqrt(2 / (0.25 * draws.size))
        assert abs(out["mean"][k] - draws.mean()) < 5 * mcse, (k, out["mean"][k])
        assert abs(out["sd"][k] - draws.std()) < 0.25 * draws.std(), (k, out["sd"][k])


@pytest.mark.parametrize("warmup, segments", [(60, 5), (61, 1)])
def test_warmup_runs_in_logged_segments(warmup, segments):
    lines = []
    nuts.run(
        synthetic(),
        model.MODELS["L0-mean"],
        nuts.Settings(chains=2, warmup=warmup, draws=10, keep_every=5),
        log=lines.append,
    )
    logged = [x for x in lines if " of warmup: " in x]
    assert len(logged) == segments and logged[-1].startswith(f"segment {segments}/")


@pytest.mark.parametrize("dense", [False, True], ids=["diagonal", "dense-globals"])
def test_svi_warm_start_runs(dense):
    """--svi-steps: chains start at draws from a fitted mean-field guide, with
    its variances as the initial metric (one block per site, and the dense
    globals' block)."""
    lines = []
    out = nuts.run(
        synthetic(),
        model.MODELS["m0q"],
        nuts.Settings(
            chains=2,
            warmup=50,
            draws=20,
            keep_every=10,
            dense_globals=dense,
            coordinates=(
                "trend_levels",
                "building_totals",
                "unit_totals",
                "unit_partial",
            ),
            svi_steps=200,
        ),
        log=lines.append,
    )
    assert out["svi"]["seconds"] > 0 and np.isfinite(out["svi"]["final_loss"])
    assert any(x.startswith("svi 200 steps") for x in lines)
    assert np.isfinite(out["lpd"]).all()


def test_building_trend_is_linear_about_the_buildings_mean_month():
    prep = synthetic()
    config = model.MODELS["m0q-btrend"]
    fixed = model.constants(prep, config)
    a = prep.train
    center = fixed["building_mean_month"]
    for b in range(3):
        rows = a.building == b
        assert float(center[b]) == pytest.approx(a.month[rows].mean())
    rate = jnp.linspace(-0.1, 0.1, len(prep.buildings))
    p = model.constants(prep, model.MODELS["m0q"]) | {
        "alpha": 0.0,
        "beta": jnp.zeros(2),
        "trend_step": jnp.zeros(fixed["trend_basis"].shape[1]),
        "season_raw": jnp.zeros(12),
        "building": jnp.zeros(len(prep.buildings)),
        "unit": jnp.zeros(len(prep.units)),
        "sigma": 0.1,
        "nu": 5.0,
        **{
            k: 0.1
            for k in ("unit_scale", "building_scale", "trend_scale", "season_scale")
        },
    }
    base = model.linear_predictor(p, a.map(jnp.asarray))
    with_trend = model.linear_predictor(
        p | {"building_trend": rate, "building_mean_month": center},
        a.map(jnp.asarray),
    )
    expected = rate[a.building] * (a.month - center[a.building]) / 12
    np.testing.assert_allclose(with_trend - base, expected, atol=1e-12)


def test_nuts_building_trend_reaches_the_scored_terms():
    """The trend is sampled, gated (its scale is a traced scalar) and part of
    the terms LOO and the variance decomposition score."""
    from rentfrontier import explain

    prep = synthetic()
    out = nuts.run(
        prep,
        model.MODELS["m0q-btrend"],
        nuts.Settings(
            chains=2,
            warmup=60,
            draws=20,
            keep_every=10,
            coordinates=("trend_levels", "building_totals", "unit_totals"),
        ),
        log=lambda *_: None,
    )
    assert np.isfinite(out["lpd"]).all()
    kept = {k: v.reshape(-1, *v.shape[2:]) for k, v in out["kept"].items()}
    assert kept["building_trend"].shape[-1] == len(prep.buildings)
    terms = explain.log_terms(
        kept, prep.train, prep.features.groups, False, False, False, 0.0
    )
    np.testing.assert_allclose(
        terms["building_drift"], model.building_trend_term(kept, prep.train)
    )


def test_gibbs_refuses_the_walk_mask_and_anchor():
    for option in ({"walk_min_rows_per_knot": 2.0}, {"walk_anchor_data": True}):
        config = replace(model.MODELS["m1-walk"], **option)
        with pytest.raises(ValueError, match="--sampler nuts"):
            gibbs.build_design(synthetic(), config)


def lined():
    """synthetic() with each building's units in three lines (2-3 units each)."""
    prep = synthetic()
    prep.unit_line = np.asarray(
        (prep.units // 100) * 3 + (prep.units % 100) % 3, dtype=np.int32
    )
    return prep


def test_line_effects_enter_through_the_rows_unit():
    prep = lined()
    config = model.MODELS["m0q-btrend-lines"]
    fixed = model.constants(prep, config)
    line = jnp.linspace(-0.2, 0.2, int(fixed["unit_line"].max()) + 1)
    a = prep.train.map(jnp.asarray)
    got = model.line_term(line, fixed["unit_line"], a)
    expected = np.asarray(line)[np.asarray(prep.unit_line)[prep.train.unit]]
    np.testing.assert_allclose(got, expected)


def test_nuts_line_effects_reach_the_scored_terms():
    from rentfrontier import explain, variance

    prep = lined()
    out = nuts.run(
        prep,
        model.MODELS["m0q-btrend-lines"],
        nuts.Settings(
            chains=2,
            warmup=60,
            draws=20,
            keep_every=10,
            coordinates=("trend_levels", "building_totals", "unit_totals"),
        ),
        log=lambda *_: None,
    )
    assert np.isfinite(out["lpd"]).all()
    kept = {k: v.reshape(-1, *v.shape[2:]) for k, v in out["kept"].items()}
    terms = explain.log_terms(
        kept,
        prep.train,
        prep.features.groups,
        0,
        False,
        False,
        0.0,
        unit_line=prep.unit_line,
    )
    line = np.asarray(prep.unit_line)[prep.train.unit]  # every unit is in a line
    np.testing.assert_allclose(terms["line"], kept["line"][:, line])
    assert "unit_line" not in kept  # constants are not saved per draw
    assert set(terms) - set(prep.features.groups) <= set(variance.FIXED)


def test_fixed_degrees_of_freedom_are_constants():
    """Designs that fix nu (m5-nu5) sample no nu site; NUTS gets it from constants."""
    prep = synthetic()
    config = model.MODELS["m5-nu5"]
    assert float(model.constants(prep, config)["nu"]) == 5.0
    assert "nu" not in sites(config, prep)


@pytest.mark.parametrize(
    "config",
    [
        model.MODELS["m0q"],
        model.ModelConfig(name="t", unit_t=True, trend_knot_months=3),
    ],
    ids=["normal-units", "t-units"],
)
def test_sampling_coordinates_are_exact_reparameterizations(config):
    """trend_levels and unit_totals are unit-Jacobian maps of the same model:
    the joint density agrees at corresponding points."""
    from numpyro.infer.util import log_density

    prep = synthetic()
    tr = handlers.trace(handlers.seed(model.build_model(prep, config), 3)).get_trace()
    p = {
        k: v["value"]
        for k, v in tr.items()
        if v["type"] == "sample" and not v["is_observed"]
    }
    moved = replace(config, coordinates=("trend_levels", "unit_totals"))
    fixed = model.constants(prep, moved)
    xbar_u = fixed["unit_xbar"]
    q = {k: v for k, v in p.items() if k not in ("trend_step", "unit")}
    q["trend_absolute"] = p["alpha"] + jnp.cumsum(p["trend_step"])
    q["unit_total"] = p["unit"] + xbar_u @ p["beta"]
    base = float(log_density(model.build_model(prep, config), (), {}, p)[0])
    new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
    assert new == pytest.approx(base, rel=1e-12, abs=1e-9)


def test_nuts_with_coordinates_returns_the_original_effects():
    out = nuts.run(
        synthetic(),
        model.MODELS["m0q"],
        nuts.Settings(
            chains=2,
            warmup=60,
            draws=20,
            keep_every=10,
            coordinates=("trend_levels", "unit_totals"),
        ),
        log=lambda *_: None,
    )
    assert np.isfinite(out["lpd"]).all()
    assert out["kept"]["unit"].shape[-1] == len(synthetic().units)
    assert np.isfinite(out["mean"]["trend"]).all()


def test_zero_sum_season_integrates_out_only_the_unseen_mean():
    """The raw-season density factors as ZeroSumNormal(centred season) x the
    unseen mean's own prior N(0, scale / sqrt(12)), up to a constant."""
    import numpyro.distributions as dist

    rng = np.random.default_rng(0)
    gaps = []
    for _ in range(4):
        scale = rng.uniform(0.01, 0.2)
        raw = rng.normal(0, scale, 12) + rng.normal()
        centred = raw - raw.mean()
        orig = dist.Normal(0.0, scale).log_prob(raw).sum()
        zsn = dist.ZeroSumNormal(scale, (12,)).log_prob(centred)
        mean = dist.Normal(0.0, scale / np.sqrt(12)).log_prob(raw.mean())
        gaps.append(float(orig - zsn - mean))
    np.testing.assert_allclose(gaps, gaps[0], atol=1e-8)


def test_building_mean_plus_zero_sum_is_the_same_model():
    """building_zerosum splits the building levels and bedroom slopes into
    mean + zero-sum deviations: the joint density matches the default one up
    to a constant (the split's Jacobian), at any point."""
    from numpyro.infer.util import log_density

    prep = synthetic()
    config = model.ModelConfig(
        name="s", building_walk=True, bedroom_slope=True, trend_knot_months=3
    )
    moved = replace(config, coordinates=("building_zerosum",))
    gaps = []
    for seed in range(3):
        tr = handlers.trace(
            handlers.seed(model.build_model(prep, config), seed)
        ).get_trace()
        p = {
            k: v["value"]
            for k, v in tr.items()
            if v["type"] == "sample" and not v["is_observed"]
        }
        q = dict(p)
        for site in ("building", "bedroom_slope"):
            values = q.pop(site)
            q[f"{site}_mean"] = values.mean()
            q[f"{site}_dev"] = values - values.mean()
        base = float(log_density(model.build_model(prep, config), (), {}, p)[0])
        new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
        gaps.append(new - base)
    np.testing.assert_allclose(gaps, gaps[0], atol=1e-8)


def test_building_totals_are_the_same_model():
    """building_totals samples each building's effect plus its mean features
    times beta, as a flat global mean plus zero-sum deviations: the joint
    density matches the default one up to a constant, at any point."""
    from numpyro.infer.util import log_density

    prep = synthetic()
    config = model.MODELS["m0q"]
    moved = replace(config, coordinates=("building_totals", "unit_totals"))
    fixed = model.constants(prep, moved)
    gaps = []
    for seed in range(3):
        tr = handlers.trace(
            handlers.seed(model.build_model(prep, config), seed)
        ).get_trace()
        p = {
            k: v["value"]
            for k, v in tr.items()
            if v["type"] == "sample" and not v["is_observed"]
        }
        q = {k: v for k, v in p.items() if k not in ("building", "unit")}
        total = p["building"] + fixed["building_xbar"] @ p["beta"]
        q["building_total_mean"] = total.mean()
        q["building_total_dev"] = total - total.mean()
        ub = fixed["unit_building"]
        within = fixed["unit_xbar"] - fixed["building_xbar"][ub]
        q["unit_total"] = p["unit"] + within @ p["beta"]
        base = float(log_density(model.build_model(prep, config), (), {}, p)[0])
        new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
        gaps.append(new - base)
    np.testing.assert_allclose(gaps, gaps[0], atol=1e-7)


def windowed(width=18):
    """synthetic() over 60 months with each building's rows moved into its own
    window of `width` months, so walks have knots before and after the data."""
    prep = synthetic(months=60)
    a = prep.train
    start = (np.arange(len(prep.buildings)) * 7) % (len(prep.periods) - width)
    m = start[a.building] + a.month % width
    train = replace(
        a,
        month=m.astype(np.int32),
        calendar=(m % 12).astype(np.int32),
        knot=(m // model.KNOT_MONTHS).astype(np.int32),
        knot_frac=(m % model.KNOT_MONTHS) / model.KNOT_MONTHS,
    )
    return replace(prep, train=train)


WALK = model.ModelConfig(name="w", building_walk=True, trend_knot_months=3)
M5 = replace(WALK, name="m5", bedroom_slope=True)
WALK12 = replace(WALK, name="w12", walk_knot_months=12, building_trend=True)
TWALK12 = replace(WALK, name="tw12", walk_knot_months=12, walk_t=True)
# Walks only for buildings with at least 6 training rows per knot in range
# (5 of the 15 windowed buildings have fewer).
MASKED12 = replace(TWALK12, name="tw12min", walk_min_rows_per_knot=6.0)
ANCHORED12 = replace(TWALK12, name="tw12anchored", walk_anchor_data=True)


def test_walk_position_matches_the_stored_half_year_knots():
    a = synthetic(months=60).train
    knot, frac = model.walk_position(a, model.KNOT_MONTHS)
    assert knot is a.knot and frac is a.knot_frac
    k12, f12 = model.walk_position(a, 12)
    np.testing.assert_array_equal(k12, a.month // 12)
    np.testing.assert_allclose(k12 + f12, a.month / 12)
    # Knots every 12 months are every other half-year knot.
    w6 = np.random.default_rng(0).normal(size=(15, model.n_knots(60)))
    w12 = w6[:, ::2]
    np.testing.assert_allclose(
        model.walk_term(w12, a, 12)[a.month % 12 == 0],
        model.walk_term(w6, a, 6)[a.month % 12 == 0],
    )


@pytest.mark.parametrize(
    "config, coordinates",
    [
        (WALK, ("building_totals", "walk_levels")),
        (M5, ("building_totals", "unit_totals", "walk_levels", "slope_totals")),
        (WALK12, ("building_totals", "walk_levels")),
        (TWALK12, ("building_totals", "walk_levels")),
        (MASKED12, ("building_totals", "walk_levels")),
        (ANCHORED12, ("building_totals", "walk_levels")),
    ],
    ids=["walk", "walk-slopes", "walk12-trend", "twalk12", "masked12", "anchored12"],
)
def test_walk_and_slope_totals_are_the_same_model(config, coordinates):
    """walk_levels samples each walk as levels inside the building's data
    range (less its anchor's) and standard normal steps outside it;
    slope_totals centres building and unit totals on their mean bedrooms.
    The joint density matches the default one at corresponding points, up to
    a constant and the non-centred steps' Jacobian (walk_scale per step)."""
    from numpyro.infer.util import log_density

    prep = windowed()
    moved = replace(config, coordinates=coordinates)
    fixed = model.constants(prep, moved)
    before, after = np.asarray(fixed["walk_before"]), np.asarray(fixed["walk_after"])
    inside = (~(before | after)).sum(1)
    walks = np.asarray(fixed.get("walk_mask", np.ones(len(inside)))) > 0
    assert before.any() and after.any() and inside[walks].min() >= 2
    assert (inside[~walks] == 1).all()  # a building without a walk: its anchor
    index = np.asarray(fixed["walk_free_index"])
    n_knot = before.shape[1]
    anchor = np.array([np.setdiff1d(np.arange(n_knot), i)[0] for i in index])
    rows = np.arange(len(anchor))
    gaps = []
    for seed in range(3):
        tr = handlers.trace(
            handlers.seed(model.build_model(prep, config), seed)
        ).get_trace()
        p = {
            k: v["value"]
            for k, v in tr.items()
            if v["type"] == "sample" and not v["is_observed"]
        }
        s, steps = p["walk_scale"], np.asarray(p["walk_step"])
        walk = np.concatenate([np.zeros((len(anchor), 1)), steps.cumsum(1)], axis=1)
        full = walk - walk[rows, anchor][:, None]
        full[:, :-1] = np.where(before[:, :-1], steps / s, full[:, :-1])
        full[:, 1:] = np.where(after[:, 1:], steps / s, full[:, 1:])
        q = {k: v for k, v in p.items() if k not in ("building", "walk_step", "unit")}
        q["walk_free"] = full[rows[:, None], index]
        mask = np.asarray(fixed.get("walk_mask", np.ones(len(anchor))))
        if config.walk_min_rows_per_knot:
            assert 0 < mask.sum() < len(mask)
        # The building total is its level at its anchor knot, where an anchored
        # walk is 0 by definition.
        at_anchor = 0.0 if config.walk_anchor_data else mask * walk[rows, anchor]
        total = p["building"] + fixed["building_xbar"] @ p["beta"] + at_anchor
        unit = p["unit"]
        if "slope_totals" in coordinates:
            ub = fixed["unit_building"]
            total = total + p["bedroom_slope"] * fixed["building_beds"]
            within = fixed["unit_xbar"] - fixed["building_xbar"][ub]
            beds = fixed["unit_beds"] - fixed["building_beds"][ub]
            q["unit_total"] = unit + within @ p["beta"] + p["bedroom_slope"][ub] * beds
        else:
            q["unit"] = unit
        q["building_total_mean"] = total.mean()
        q["building_total_dev"] = total - total.mean()
        base = float(log_density(model.build_model(prep, config), (), {}, p)[0])
        new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
        gaps.append(new - base - (before | after).sum() * float(np.log(s)))
    np.testing.assert_allclose(gaps, gaps[0], atol=1e-7)


@pytest.mark.parametrize("coordinate", ["walk_levels", "slope_totals"])
def test_walk_and_slope_totals_need_building_totals(coordinate):
    with pytest.raises(ValueError, match="building_totals"):
        model.constants(windowed(), replace(M5, coordinates=(coordinate,)))


@pytest.mark.parametrize(
    "config, coordinates",
    [
        (WALK, ("building_totals", "walk_levels")),
        (M5, ("building_totals", "unit_totals", "walk_levels", "slope_totals")),
        (WALK12, ("building_totals", "walk_levels")),
        (TWALK12, ("building_totals", "walk_levels")),
        (MASKED12, ("building_totals", "walk_levels")),
        (ANCHORED12, ("building_totals", "walk_levels")),
    ],
    ids=["walk", "walk-slopes", "walk12-trend", "twalk12", "masked12", "anchored12"],
)
def test_nuts_with_walk_and_slope_totals_returns_the_effects(config, coordinates):
    prep = windowed()
    out = nuts.run(
        prep,
        config,
        nuts.Settings(
            chains=2, warmup=60, draws=20, keep_every=10, coordinates=coordinates
        ),
        log=lambda *_: None,
    )
    assert out["noncentered"] == []
    assert np.isfinite(out["lpd"]).all()
    walk = out["mean"]["walk"]
    assert walk.shape == (
        len(prep.buildings),
        model.n_knots(60, config.walk_knot_months),
    )
    zero_at = (
        np.asarray(
            model.constants(prep, replace(config, coordinates=coordinates))[
                "walk_anchor"
            ]
        )
        if config.walk_anchor_data
        else np.zeros(len(prep.buildings), dtype=int)
    )
    np.testing.assert_allclose(walk[np.arange(len(zero_at)), zero_at], 0.0)
    if config.walk_min_rows_per_knot:
        mask = model.walk_mask(prep, config)
        assert 0 < mask.sum() < len(mask)
        np.testing.assert_array_equal(walk[mask == 0], 0.0)
    if config.building_trend:
        from rentfrontier import explain

        kept = {k: v.reshape(-1, *v.shape[2:]) for k, v in out["kept"].items()}
        terms = explain.log_terms(
            kept,
            prep.train,
            prep.features.groups,
            model.walk_spacing(config),
            False,
            False,
            0.0,
        )
        np.testing.assert_allclose(
            terms["building_drift"],
            model.walk_term(kept["walk"], prep.train, 12)
            + model.building_trend_term(kept, prep.train),
        )
    if config.bedroom_slope:
        assert np.isfinite(out["mean"]["bedroom_slope"]).all()


@pytest.mark.parametrize("unit_t", [False, True], ids=["normal", "t"])
@pytest.mark.parametrize("totals", [False, True], ids=["units", "unit-totals"])
def test_partially_centred_units_are_the_same_model(unit_t, totals):
    """unit_partial (LocScaleReparam, centring c per unit) is a change of
    variables: the density gains its Jacobian, sum (1 - c) log unit_scale."""
    from numpyro.infer.util import log_density

    prep = synthetic()
    config = model.ModelConfig(name="p", unit_t=unit_t, trend_knot_months=3)
    plain = replace(config, coordinates=("unit_totals",) if totals else ())
    moved = replace(config, coordinates=plain.coordinates + ("unit_partial",))
    fixed = model.constants(prep, moved)
    c = np.asarray(fixed["unit_centering"])
    site = "unit_total" if totals else "unit"
    gaps = []
    for seed in range(3):
        tr = handlers.trace(
            handlers.seed(model.build_model(prep, plain), seed)
        ).get_trace()
        p = {
            k: v["value"]
            for k, v in tr.items()
            if v["type"] == "sample" and not v["is_observed"]
        }
        loc = (fixed["unit_xbar"] @ p["beta"]) if totals else 0.0
        scale = p["unit_scale"]
        q = {k: v for k, v in p.items() if k != site}
        q[f"{site}_decentered"] = c * loc + (p[site] - loc) / scale ** (1 - c)
        base = float(log_density(model.build_model(prep, plain), (), {}, p)[0])
        new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
        gaps.append(new - base - float(np.sum(1 - c) * np.log(scale)))
    np.testing.assert_allclose(gaps, 0.0, atol=1e-7)


def test_fixed_walk_df_is_a_constant():
    config = model.MODELS["m1-t3walk24"]
    prep = windowed()
    assert float(model.constants(prep, config)["walk_nu"]) == 3.0
    assert "walk_nu" not in sites(config, prep)


def test_student_t_walk_steps_run_non_centred():
    """Without walk_levels, Student-t walk steps are non-centred with their df
    as a shape parameter (LocScaleReparam)."""
    out = nuts.run(
        windowed(),
        TWALK12,
        nuts.Settings(chains=2, warmup=40, draws=10, keep_every=5),
        log=lambda *_: None,
    )
    assert out["noncentered"] == ["walk_step"]
    assert np.isfinite(out["lpd"]).all() and out["mean"]["walk_nu"] > 0


@pytest.mark.parametrize("unit_t", [False, True], ids=["normal", "t"])
def test_partially_centred_units_run_and_return_unit_effects(unit_t):
    """unit_partial (NumPyro LocScaleReparam with per-unit weights) samples
    and gives back the original unit effects."""
    prep = synthetic()
    config = model.ModelConfig(name="p", unit_t=unit_t, trend_knot_months=3)
    c = model.constants(prep, replace(config, coordinates=("unit_partial",)))[
        "unit_centering"
    ]
    assert float(c.min()) > 0.5 and float(c.max()) < 1.0
    out = nuts.run(
        prep,
        config,
        nuts.Settings(
            chains=2,
            warmup=60,
            draws=20,
            keep_every=10,
            coordinates=("building_totals", "unit_totals", "unit_partial"),
        ),
        log=lambda *_: None,
    )
    assert np.isfinite(out["lpd"]).all()
    assert out["kept"]["unit"].shape[-1] == len(prep.units)

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


@pytest.mark.parametrize("name", ["L0-mean", "L5-building"])
def test_gibbs_needs_every_base_term(name):
    with pytest.raises(ValueError, match="--sampler nuts"):
        gibbs.build_design(synthetic(), model.MODELS[name])


@pytest.mark.parametrize(
    "coordinates", [(), ("trend_levels", "season_zerosum", "unit_totals")]
)
def test_dense_globals_covers_the_global_sites_only(coordinates):
    out = nuts.run(
        synthetic(),
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
    for local in ("unit", "unit_total", "building"):
        assert local not in out["dense_sites"]
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


def test_walk_levels_are_the_same_model():
    """walk_levels samples each walk as levels inside the building's data
    range (less its anchor's) and standard normal steps outside it: the joint
    density matches the default one at corresponding points, up to a
    constant and the non-centred steps' Jacobian (walk_scale per step)."""
    from numpyro.infer.util import log_density

    prep = windowed()
    moved = replace(WALK, coordinates=("building_totals", "walk_levels"))
    fixed = model.constants(prep, moved)
    before, after = np.asarray(fixed["walk_before"]), np.asarray(fixed["walk_after"])
    assert before.any() and after.any() and (~(before | after)).sum(1).min() >= 2
    index = np.asarray(fixed["walk_free_index"])
    n_knot = before.shape[1]
    anchor = np.array([np.setdiff1d(np.arange(n_knot), i)[0] for i in index])
    rows = np.arange(len(anchor))
    gaps = []
    for seed in range(3):
        tr = handlers.trace(
            handlers.seed(model.build_model(prep, WALK), seed)
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
        q = {k: v for k, v in p.items() if k not in ("building", "walk_step")}
        q["walk_free"] = full[rows[:, None], index]
        total = p["building"] + fixed["building_xbar"] @ p["beta"] + walk[rows, anchor]
        q["building_total_mean"] = total.mean()
        q["building_total_dev"] = total - total.mean()
        base = float(log_density(model.build_model(prep, WALK), (), {}, p)[0])
        new = float(log_density(model.build_model(prep, moved), (), {}, q)[0])
        gaps.append(new - base - (before | after).sum() * float(np.log(s)))
    np.testing.assert_allclose(gaps, gaps[0], atol=1e-7)


def test_walk_levels_need_building_totals():
    with pytest.raises(ValueError, match="building_totals"):
        model.constants(windowed(), replace(WALK, coordinates=("walk_levels",)))


def test_nuts_with_walk_levels_returns_the_walks():
    prep = windowed()
    out = nuts.run(
        prep,
        WALK,
        nuts.Settings(
            chains=2,
            warmup=60,
            draws=20,
            keep_every=10,
            coordinates=("building_totals", "walk_levels"),
        ),
        log=lambda *_: None,
    )
    assert out["noncentered"] == []
    assert np.isfinite(out["lpd"]).all()
    walk = out["mean"]["walk"]
    assert walk.shape == (len(prep.buildings), model.n_knots(60))
    np.testing.assert_allclose(walk[:, 0], 0.0)


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

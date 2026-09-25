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


def test_each_ladder_step_adds_to_the_one_below():
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


def test_dense_globals_covers_the_small_sites_only():
    out = nuts.run(
        synthetic(),
        model.MODELS["m1q"],
        nuts.Settings(chains=2, warmup=50, draws=20, keep_every=10, dense_globals=True),
        log=lambda *_: None,
    )
    assert "beta" in out["dense_sites"] and "trend_step" in out["dense_sites"]
    assert "unit" not in out["dense_sites"] and "building" not in out["dense_sites"]
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

"""The ladder's two implementations are the same model, and its scoring terms
are that model's mean: on a small synthetic data set, for every rung, the
NumPyro and PyMC joint log densities agree at random parameter values, and
the Student-t log likelihood of `terms_for` matches NumPyro's."""

from types import SimpleNamespace

import jax
import numpy as np
import pytest
from rentfrontier import ladder, model

jax.config.update("jax_enable_x64", True)

N_BUILDINGS, N_UNITS, N_MONTHS = 3, 5, 13


def synthetic(seed=0, n=40, n_x=2):
    rng = np.random.default_rng(seed)
    month = rng.integers(0, N_MONTHS - 1, n)
    a = SimpleNamespace(
        y=rng.normal(size=n),
        x=rng.normal(size=(n, n_x)),
        month=month,
        calendar=month % 12,
        building=rng.integers(0, N_BUILDINGS, n),
        unit=rng.integers(0, N_UNITS, n),
        knot=month // model.KNOT_MONTHS,
        knot_frac=(month % model.KNOT_MONTHS) / model.KNOT_MONTHS,
        beds_centered=rng.integers(0, 4, n) - 1.0,
        unit_time=rng.normal(scale=0.5, size=n),
    )
    prep = SimpleNamespace(
        buildings=np.arange(N_BUILDINGS),
        units=np.arange(N_UNITS),
        periods=np.arange(N_MONTHS),
    )
    inp = {
        "prep": prep,
        "basis": model.knot_basis(N_MONTHS, ladder.TREND_KNOT_MONTHS),
        "beta_sd": np.linspace(0.5, 0.25, n_x),
        "mean_month": float(month.mean()),
        "fslope_index": np.array([0, 1]),
    }
    return a, inp


def random_params(terms, inp, seed=1, a=None):
    """Constrained values for every sampled site of the rung."""
    from numpyro import handlers

    if a is None:
        a, _ = synthetic()
    tr = handlers.trace(
        handlers.seed(ladder.numpyro_model(terms, a, inp), seed)
    ).get_trace()
    return {
        k: np.asarray(v["value"])
        for k, v in tr.items()
        if v["type"] == "sample" and not v["is_observed"]
    }


@pytest.mark.parametrize("rung", sorted(ladder.RUNGS))
def test_pymc_and_numpyro_agree(rung):
    pytest.importorskip("pymc")
    from numpyro.infer.util import log_density

    terms = ladder.RUNGS[rung]
    a, inp = synthetic()
    p = random_params(terms, inp)
    np_lp = float(log_density(ladder.numpyro_model(terms, a, inp), (), {}, p)[0])

    m = ladder.pymc_model(terms, a, inp)
    point = {}
    for rv in m.free_RVs:
        value = m.rvs_to_values[rv]
        x = p[rv.name]
        point[value.name] = np.log(x) if value.name.endswith("_log__") else x
    pm_lp = float(m.compile_logp(jacobian=False)(point))
    assert pm_lp == pytest.approx(np_lp, rel=1e-9, abs=1e-8)


@pytest.mark.parametrize("rung", sorted(ladder.RUNGS))
def test_terms_are_the_model_mean(rung):
    from numpyro import handlers

    terms = ladder.RUNGS[rung]
    a, inp = synthetic()
    p = random_params(terms, inp)
    tr = handlers.trace(
        handlers.substitute(ladder.numpyro_model(terms, a, inp), p)
    ).get_trace()
    expected = float(tr["y"]["fn"].log_prob(tr["y"]["value"]).sum())

    e = ladder.effects({k: v[None, None] for k, v in p.items()}, terms, inp)
    mu = sum(ladder.terms_for(e, a, inp).values())[0]
    got = ladder.t_logpdf(a.y - mu, e["nu"][0], e["sigma"][0]).sum()
    assert got == pytest.approx(expected, rel=1e-10)


def gibbs_prep(a, inp, feature_names):
    """A `model.Prepared` stand-in over the synthetic rows, for build_model."""
    n = len(a.y)
    train = model.Arrays(
        y=a.y,
        x=a.x,
        month=a.month.astype(np.int32),
        calendar=a.calendar.astype(np.int32),
        building=a.building.astype(np.int32),
        unit=a.unit.astype(np.int32),
        knot=a.knot.astype(np.int32),
        knot_frac=a.knot_frac,
        bed_group=np.zeros(n, dtype=np.int32),
        beds_centered=a.beds_centered,
        unit_time=a.unit_time,
    )
    features = SimpleNamespace(
        names=list(feature_names), prior_scale=inp["beta_sd"] / 0.5
    )
    return SimpleNamespace(
        train=train,
        periods=inp["prep"].periods,
        buildings=inp["prep"].buildings,
        units=inp["prep"].units,
        features=features,
    )


@pytest.mark.parametrize("rung", sorted(ladder.SAME_AS))
def test_rung_is_its_gibbs_design(rung):
    """Same joint density as `model.build_model` of the named design, up to
    the Jacobian of the non-centred sites (step = scale * z)."""
    from numpyro.infer.util import log_density

    config = model.MODELS[ladder.SAME_AS[rung]]
    assert config.trend_knot_months == ladder.TREND_KNOT_MONTHS
    assert config.walk_scale_sd == ladder.WALK_SCALE_SD
    terms = ladder.RUNGS[rung]
    a, inp = synthetic(n_x=3)
    names = [*ladder.FSLOPE_FEATURES]  # the slope columns are the features here
    inp["fslope_index"] = np.arange(3)
    prep = gibbs_prep(a, inp, names)
    p = random_params(terms, inp, a=a)

    q, log_jac = {}, 0.0
    for k, v in p.items():
        if k in ladder.NONCENTRED:
            site, scale = ladder.NONCENTRED[k]
            q[site] = p[scale] * v
            log_jac += v.size * np.log(p[scale])
        else:
            q[k] = v
    lp_ladder = float(log_density(ladder.numpyro_model(terms, a, inp), (), {}, p)[0])
    lp_model = float(log_density(model.build_model(prep, config), (), {}, q)[0])
    # p(step) = p(z) / scale per element.
    assert lp_model == pytest.approx(lp_ladder - log_jac, rel=1e-10, abs=1e-8)

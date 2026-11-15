"""L2 on the unitkn base with a slowly reverting lasting level
(`rentfrontier.drift_building_phase_unitkn_level_slow`, `drift.make_sampler`'s
`unit_slow`)."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp
import test_drift_building_unitt as tu

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building_phase_unitkn_level,
    drift_pool,
    run,
)
from rentfrontier import drift_building_phase_unitkn_level_slow as m

DOF = m.UNIT_DOF
# A time constant short enough for the tests' few years of ads to tell it from infinity.
TAU_S = 4.0

# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitkn-level-slow was added. A deliberate change to the model's
# draws changes it.
SLOW_RUN_SHA256 = "e8c3ec804232406857ead0e6609969fc29d2b954c1c244b222d524940f25f625"


def _sampler(train, slow=True):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=4.0)
    return drift.make_sampler(
        train,
        building_zones.Priors(),
        settings,
        unit_t=True,
        unit_dof_fixed=DOF,
        unit_kap_collapsed=True,
        unit_slow=slow,
    )


def _setup(seed=5):
    """A phased design's training rows, its sampler's parts, a state and the rows'
    remainders."""
    train, _, _ = td._split(tp._phased(per_unit=9))
    _, init, _, parts = _sampler(train)
    _, jnp = b0._jax()
    st = tu._state(init, parts, unit_dof=DOF) | {"unit_tau": jnp.asarray(TAU_S)}
    rng = np.random.default_rng(seed)
    e = jnp.asarray(0.1 * rng.standard_normal(len(train.y)))
    return train, parts, st, e


def _dense_loglik(parts, hyp, c, e, ukap):
    """`unit_loglik` from each unit's dense covariance K + C^-1, with K from `kernel`:
    the sum over units of -(log |C (K + C^-1)| + e' (K + C^-1)^-1 e) / 2."""
    D = parts["data"]
    unit, t = np.asarray(D["unit"]), np.asarray(D["t"])
    c, e = np.asarray(c), np.asarray(e)
    v = np.exp(2 * float(hyp[0])) / np.asarray(ukap)
    out = 0.0
    for k in np.unique(unit):
        r = np.flatnonzero(unit == k)
        K = np.asarray(parts["kernel"](hyp, t[r][:, None], t[r][None, :], v[k]))
        S = K + np.diag(1 / c[r])
        _, logdet = np.linalg.slogdet(S)
        out -= 0.5 * (logdet + np.sum(np.log(c[r])) + e[r] @ np.linalg.solve(S, e[r]))
    return out


def test_the_kernel_reverts_the_lasting_level():
    _, parts, st, _ = _setup()
    hyp = parts["unit_hyp"](st)
    ss, sd, tau = np.exp(np.asarray(hyp[:3]))
    got = float(parts["kernel"](hyp, 0.0, 3.0, 0.01))
    want = 0.01 * np.exp(-3 / TAU_S) + sd**2 * np.exp(-3 / tau)
    np.testing.assert_allclose(got, want, rtol=1e-12)


def test_unit_loglik_matches_the_dense_density():
    _, parts, st, e = _setup()
    D = parts["data"]
    c = parts["weights"](D, st)
    hyp = parts["unit_hyp"](st)
    got = float(parts["unit_loglik"](D, hyp, c, e, st["ukap"]))
    want = _dense_loglik(parts, hyp, c, e, st["ukap"])
    np.testing.assert_allclose(got, want, rtol=1e-9)


def test_kap_logp_matches_the_units_marginal_likelihood():
    train, parts, st, e = _setup()
    _, jnp = b0._jax()
    D = parts["data"]
    c = parts["weights"](D, st)
    hyp = parts["unit_hyp"](st)
    w1, Wb = parts["unit_W"](D, hyp, c, st["ukap"])
    logp = parts["kap_logp"](D, hyp, DOF, st["ukap"], w1, Wb, e, c)
    kap0 = np.asarray(st["ukap"])
    rows = np.bincount(train.unit, minlength=len(kap0))
    picks = [int(np.flatnonzero(rows == 1)[0]), *np.flatnonzero(rows > 2)[:3].tolist()]
    assert len(picks) == 4

    def lik(kap):
        return float(parts["unit_loglik"](D, hyp, c, e, jnp.asarray(kap)))

    base_lik = lik(kap0)
    base = np.asarray(logp(jnp.log(jnp.asarray(kap0))))
    for k in picks:
        for f in (0.05, 0.4, 3.0, 20.0):
            kap = kap0.copy()
            kap[k] *= f
            got = float(np.asarray(logp(jnp.log(jnp.asarray(kap))))[k] - base[k])
            prior = DOF / 2 * np.log(f) - DOF / 2 * (kap[k] - kap0[k])
            want = lik(kap) - base_lik + prior
            np.testing.assert_allclose(got, want, rtol=1e-8, atol=1e-10)
            assert abs(want) > 1e-3


def test_a_long_time_constant_gives_l2s_unit_density_and_predictions():
    """At unit_tau of a million years the lasting level is constant over the ads, so the
    unit density and the predictions match the sampler without the option."""
    train, _, _ = td._split(tp._phased(per_unit=9))
    _, init, _, parts = _sampler(train)
    _, init0, _, parts0 = _sampler(train, slow=False)
    _, jnp = b0._jax()
    st0 = tu._state(init0, parts0, unit_dof=DOF)
    st = st0 | {"unit_tau": jnp.asarray(1e6)}
    D = parts["data"]
    e = jnp.asarray(0.1 * np.random.default_rng(1).standard_normal(len(train.y)))
    c = parts["weights"](D, st)
    a = float(parts["unit_loglik"](D, parts["unit_hyp"](st), c, e, st["ukap"]))
    b = float(parts0["unit_loglik"](D, st0["hyp"], c, e, st0["ukap"]))
    np.testing.assert_allclose(a, b, rtol=1e-6)
    got = parts["predict"](parts["data"], st)
    want = parts0["predict"](parts0["data"], st0)
    for x, y in zip(got, want):
        np.testing.assert_allclose(np.asarray(x), np.asarray(y), rtol=1e-4, atol=1e-5)


def test_the_option_needs_the_collapsed_kap():
    train, _, _ = td._split(tp._phased(n=300, per_unit=9))
    try:
        drift.make_sampler(
            train,
            building_zones.Priors(),
            drift.Settings(chains=2),
            unit_t=True,
            unit_dof_fixed=DOF,
            unit_slow=True,
        )
    except AssertionError as err:
        assert "needs unit_kap_collapsed" in str(err)
    else:
        raise AssertionError("unit_slow without unit_kap_collapsed was accepted")


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(m.phase_levels(tp._phased(n=400, per_unit=9)))
    out = m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda s: None,
    )
    tau = np.asarray(out["trace"]["unit_tau"])
    assert tau.shape == (2, 8) and np.isfinite(tau).all() and np.ptp(tau) > 0
    rows = m.diagnostics(out["trace"], list(train.names))["per_quantity"]
    assert {"unit_sd", "drift_tau", "unit_tau"} <= set(rows)
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == SLOW_RUN_SHA256, h.hexdigest()


def test_the_model_is_l2_with_the_slow_level():
    base = drift_building_phase_unitkn_level
    assert m.NAME == "drift-building-phase-unitkn-level-slow"
    assert m.design is base.design and m.UNIT_DOF == base.UNIT_DOF
    assert m.ROW_DOF == base.ROW_DOF and m.GROUPS == base.GROUPS
    assert m.diagnostics is base.diagnostics
    assert '"drift-building-phase-unitkn-level-slow",' in open(run.__file__).read()
    assert (
        drift_pool.model_diagnostics({"model": {"name": m.NAME}}) is drift.diagnostics
    )
    d = m.phase_levels(tp._phased(n=300))
    rec = m.run_record(d)
    assert rec["phase"] == base.run_record(d)["phase"]
    assert rec["unit_slow"]["unit_tau_log_prior"].startswith("Normal(3.6889")

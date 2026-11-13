"""L1T sampled with each unit's mixing scale drawn with u and its lasting level integrated
out (`rentfrontier.drift_building_phase_unitk`, `drift.make_sampler`'s
`unit_kap_collapsed`)."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp
import test_drift_building_unitt as tu

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building_phase_unitk,
    drift_building_phase_unitt,
    run,
)

P = drift_building_phase_unitt.PHASES
DOF = drift_building_phase_unitt.UNIT_DOF


def _sampler(train):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=4.0)
    return drift.make_sampler(
        train,
        building_zones.Priors(),
        settings,
        unit_t=True,
        unit_dof_fixed=DOF,
        unit_kap_collapsed=True,
    )


def _setup(seed=5):
    """A phased design's training rows, its sampler's parts, a state and the rows'
    remainders."""
    train, _, _ = td._split(tp._phased(per_unit=9))
    _, init, _, parts = _sampler(train)
    _, jnp = b0._jax()
    st = tu._state(init, parts, unit_dof=DOF)
    rng = np.random.default_rng(seed)
    e = jnp.asarray(0.1 * rng.standard_normal(len(train.y)))
    return train, parts, st, e


def test_kap_logp_matches_the_units_marginal_likelihood():
    train, parts, st, e = _setup()
    _, jnp = b0._jax()
    D = parts["data"]
    c = parts["weights"](D, st)
    w1, Wb = parts["unit_W"](D, st["hyp"], c, st["ukap"])
    logp = parts["kap_logp"](D, st["hyp"], DOF, st["ukap"], w1, Wb, e)
    kap0 = np.asarray(st["ukap"])
    U = len(kap0)
    # Units with one row and with several, each moved alone.
    rows = np.bincount(train.unit, minlength=U)
    picks = [int(np.flatnonzero(rows == 1)[0]), *np.flatnonzero(rows > 2)[:3].tolist()]
    assert len(picks) == 4

    def lik(kap):
        return float(parts["unit_loglik"](D, st["hyp"], c, e, jnp.asarray(kap)))

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


def test_collapsed_kap_draws_from_the_conditional():
    """A unit's draws of log kap over many chains of the step, each started at the last,
    match its density on a grid."""
    train, parts, st, e = _setup()
    jax, jnp = b0._jax()
    D = parts["data"]
    c = parts["weights"](D, st)

    def step(lk, key):
        kap = jnp.exp(lk)
        w1, Wb = parts["unit_W"](D, st["hyp"], c, kap)
        new = parts["collapsed_kap"](D, key, st["hyp"], DOF, kap, w1, Wb, e)
        return jnp.log(new), jnp.log(new)

    keys = jax.random.split(jax.random.PRNGKey(3), 4000)
    _, draws = jax.lax.scan(jax.jit(step), jnp.log(st["ukap"]), keys)
    draws = np.asarray(draws)[500:]
    w1, Wb = parts["unit_W"](D, st["hyp"], c, st["ukap"])
    logp = parts["kap_logp"](D, st["hyp"], DOF, st["ukap"], w1, Wb, e)
    grid = np.linspace(-8, 4, 3001)
    U = draws.shape[1]
    dens = np.stack(
        [np.asarray(logp(jnp.full(U, g))) for g in grid], axis=1
    )  # (U, grid)
    dens = np.exp(dens - dens.max(axis=1, keepdims=True))
    dens /= dens.sum(axis=1, keepdims=True)
    for k in range(min(U, 6)):
        mean = float((grid * dens[k]).sum())
        sd = float(np.sqrt(((grid - mean) ** 2 * dens[k]).sum()))
        assert abs(draws[:, k].mean() - mean) < 0.08 * sd + 0.02
        assert abs(draws[:, k].std() / sd - 1) < 0.08


def test_without_the_option_the_sweep_is_l1ts():
    # The pins of L1T, L1 and U2 cover the draws; here the option's absence keeps L1T's
    # parts and its presence adds the step.
    train, _, _ = td._split(tp._phased(n=300, per_unit=9))
    _, _, _, parts = _sampler(train)
    assert parts["unit_t"] and not parts["dof_free"]
    try:
        drift.make_sampler(
            train,
            building_zones.Priors(),
            drift.Settings(chains=2),
            unit_kap_collapsed=True,
        )
    except AssertionError as err:
        assert "needs unit_t" in str(err)
    else:
        raise AssertionError("unit_kap_collapsed without unit_t was accepted")


def test_sweeps_move_the_kap_and_keep_the_dof():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    sweep, init, _, _ = _sampler(train)
    jax, _ = b0._jax()
    st = init(jax.random.split(jax.random.PRNGKey(0), 2))
    first = np.asarray(st["ukap"])
    key = jax.random.PRNGKey(1)
    for _ in range(5):
        key, sub = jax.random.split(key)
        st, out = sweep(jax.random.split(sub, 2), st)
        assert (np.asarray(st["unit_dof"]) == DOF).all()
        assert np.isfinite(np.asarray(st["ukap"])).all()
    assert np.abs(np.asarray(st["ukap"]) - first).min() > 0


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitk was added. A deliberate change to the model's draws changes it.
PHASE_UNITK_RUN_SHA256 = (
    "2a4b49e7370632daf9dd72ed9b3941699bf246dab5b1cff2d9a8442cd0d432b5"
)


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    out = drift_building_phase_unitk.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    assert "unit_dof" not in out["trace"] and "unit_dof" not in out["kept"]
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == PHASE_UNITK_RUN_SHA256, h.hexdigest()


def test_the_model_is_l1t_with_the_collapsed_kap_step():
    m = drift_building_phase_unitk
    t = drift_building_phase_unitt
    assert m.NAME == "drift-building-phase-unitk"
    assert m.UNIT_DOF == t.UNIT_DOF and m.LEVEL_DOF == t.LEVEL_DOF
    assert m.GROUPS == t.GROUPS and m.design is t.design and m.Priors is t.Priors
    assert (
        '("drift-building-phase-unitk", "drift_building_phase_unitk")'
        in open(run.__file__).read()
    )
    rec = m.run_record(tp._phased(n=300))
    assert rec["unit_t"]["unit_dof_fixed"] == 3.0
    assert rec["unit_t"]["kap_step"] == "collapsed over u and s"

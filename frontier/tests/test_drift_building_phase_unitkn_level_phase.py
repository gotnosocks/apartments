"""L2 on the unitkn base with the phases' factors drawn in the noise step
(`rentfrontier.drift_building_phase_unitkn_level_phase`, `drift.make_sampler`'s
`phase_collapsed`)."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp
import test_drift_building_unitt as tu
from scipy import stats

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building_phase_unitkn_level,
    drift_pool,
    run,
)
from rentfrontier import drift_building_phase_unitkn_level_phase as m

DOF = m.UNIT_DOF
NU = m.ROW_DOF

# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitkn-level-phase was added. A deliberate change to the model's
# draws changes it.
PHASE_RUN_SHA256 = "f1bd74527fca3630082673c9fb18e8df237de1bcbb026db5ad798c5655fbe537"


def _sampler(train, collapsed=True):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=4.0)
    return drift.make_sampler(
        train,
        building_zones.Priors(),
        settings,
        unit_t=True,
        unit_dof_fixed=DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=NU,
        phase_collapsed=collapsed,
    )


def _setup(collapsed=True):
    """A phased design's training rows, its sampler's parts, a state and remainders for
    the rows."""
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    _, init, _, parts = _sampler(train, collapsed)
    _, jnp = b0._jax()
    st = tu._state(init, parts, unit_dof=DOF)
    rng = np.random.default_rng(8)
    r = jnp.asarray(0.1 * rng.standard_t(NU, len(train.y)))
    return train, parts, st, r


def test_the_noise_step_moves_the_factors_and_draws_lam_at_them():
    _, parts, st, r = _setup()
    jax, jnp = b0._jax()
    key = jax.random.PRNGKey(2)
    nu, sigma, lam, factor = parts["update_noise"](key, st, r, parts["data"])
    assert float(jnp.abs(factor - st["phase_scale"]).min()) > 0
    # lam's Gamma draw reads the new factors: the same key at the old ones gives another.
    _, parts0, st0, _ = _setup(collapsed=False)
    nu0, sigma0, lam0, factor0 = parts0["update_noise"](key, st0, r, parts0["data"])
    np.testing.assert_array_equal(np.asarray(factor0), np.asarray(st0["phase_scale"]))
    np.testing.assert_array_equal(np.asarray(sigma0), np.asarray(sigma))
    D = parts["data"]
    sd = np.asarray(sigma)[np.asarray(D["group"])]
    f = np.concatenate([[1.0], np.asarray(factor)])[np.asarray(D["phase"])]
    f0 = np.concatenate([[1.0], np.asarray(factor0)])[np.asarray(D["phase"])]
    z2, z20 = (np.asarray(r) / (sd * f)) ** 2, (np.asarray(r) / (sd * f0)) ** 2
    np.testing.assert_allclose(
        np.asarray(lam) * (NU + z2), np.asarray(lam0) * (NU + z20), rtol=1e-9
    )


def test_repeated_noise_steps_sample_sigma_and_the_factors_given_the_remainders():
    """Many noise steps in a row, each from the last one's sigma and factors, against a
    random-walk Metropolis chain on the same density written out here: the rows'
    Student-t density at scale sigma[group] factor[phase], sigma's half-Normal prior and
    the Normal prior on each free log factor."""
    train, parts, st, r = _setup()
    jax, jnp = b0._jax()
    D = parts["data"]
    steps = 6000

    def step(carry, key):
        sigma, factor = carry
        _, sigma, _, factor = parts["update_noise"](
            key, st | {"sigma": sigma, "phase_scale": factor}, r, D
        )
        return (sigma, factor), jnp.concatenate([jnp.log(sigma), jnp.log(factor)])

    keys = jax.random.split(jax.random.PRNGKey(4), steps)
    _, got = jax.lax.scan(step, (st["sigma"], st["phase_scale"]), keys)
    got = np.asarray(got)[500:]

    group, phase = np.asarray(D["group"]), np.asarray(D["phase"])
    free = got.shape[1] - 4
    prior_sd = building_zones.Priors().sigma
    rn = np.asarray(r)

    def logp(x):
        sig = np.exp(x[:4])
        lf = np.concatenate([[0.0], x[4:]])
        scale = sig[group] * np.exp(lf[phase])
        return (
            stats.t.logpdf(rn, NU, scale=scale).sum()
            - np.sum(sig**2) / (2 * prior_sd**2)
            + np.sum(x[:4])
            - np.sum(x[4:] ** 2) / (2 * drift.PHASE_PRIOR**2)
        )

    rng = np.random.default_rng(0)
    x = got.mean(axis=0)
    lp = logp(x)
    want = np.empty((40000, 4 + free))
    for i in range(len(want)):
        y = x + 0.06 * rng.standard_normal(len(x))
        ly = logp(y)
        if np.log(rng.uniform()) < ly - lp:
            x, lp = y, ly
        want[i] = x
    want = want[2000:]
    np.testing.assert_allclose(got.mean(axis=0), want.mean(axis=0), atol=0.03)
    np.testing.assert_allclose(got.std(axis=0), want.std(axis=0), rtol=0.2)
    # A group's sigma and a factor trade off, and the noise step now moves along that too.
    assert got[:, 4:].std(axis=0).min() > 0.03


def test_the_option_needs_phases():
    train, _, _ = td._split(td._design(n=300))
    try:
        drift.make_sampler(
            train,
            building_zones.Priors(),
            drift.Settings(chains=2),
            phase_collapsed=True,
        )
    except AssertionError as err:
        assert "needs phases" in str(err)
    else:
        raise AssertionError("phase_collapsed without phases was accepted")


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(m.phase_levels(tp._phased(n=400, per_unit=9)))
    out = m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda s: None,
    )
    f = np.asarray(out["trace"]["phase_scale"])
    assert np.isfinite(f).all() and np.ptp(f[..., 1:], axis=1).min() > 0
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == PHASE_RUN_SHA256, h.hexdigest()


def test_the_model_is_l2_with_the_option():
    base = drift_building_phase_unitkn_level
    assert m.NAME == "drift-building-phase-unitkn-level-phase"
    assert m.design is base.design and m.UNIT_DOF == base.UNIT_DOF
    assert m.ROW_DOF == base.ROW_DOF and m.GROUPS == base.GROUPS
    assert m.diagnostics is base.diagnostics
    assert '"drift-building-phase-unitkn-level-phase",' in open(run.__file__).read()
    assert (
        drift_pool.model_diagnostics({"model": {"name": m.NAME}}) is drift.diagnostics
    )
    d = m.phase_levels(tp._phased(n=300))
    rec = m.run_record(d)
    assert rec["phase"] == base.run_record(d)["phase"]
    assert rec["phase_collapsed"] is True

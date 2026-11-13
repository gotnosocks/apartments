"""L1TK with the rows' degrees of freedom held at 2
(`rentfrontier.drift_building_phase_unitkn`, `drift.make_sampler`'s `row_dof_fixed`)."""

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
    drift_building_phase_unitkn,
    run,
)

P = drift_building_phase_unitk.PHASES
DOF = drift_building_phase_unitk.UNIT_DOF
NU = drift_building_phase_unitkn.ROW_DOF


def _sampler(train, row_dof):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=4.0)
    return drift.make_sampler(
        train,
        building_zones.Priors(),
        settings,
        unit_t=True,
        unit_dof_fixed=DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=row_dof,
    )


def _setup(row_dof, seed=5):
    """A phased design's training rows, its sampler's parts, a state with nu at `NU`, the
    targets and the buildings' means."""
    train, _, _ = td._split(tp._phased(per_unit=9))
    _, init, _, parts = _sampler(train, row_dof)
    _, jnp = b0._jax()
    st = tu._state(init, parts, unit_dof=DOF) | {"nu": jnp.asarray(NU)}
    rng = np.random.default_rng(seed)
    F = 0.1 * rng.standard_normal(len(parts["zone"]))
    tgt = F[train.site[parts["order"]]] + 0.2 * rng.standard_normal(len(train.y))
    return train, parts, st, jnp.asarray(tgt), jnp.asarray(F)


def _unit_eta(parts, st):
    """The units' standardized log mixing scales at nu_u = `DOF`."""
    _, jnp = b0._jax()
    m, s = parts["lam_moments"](jnp.log(jnp.asarray(DOF)))
    return (jnp.log(st["ukap"]) - m) / s


def test_scales_logp_with_nu_fixed_is_the_free_density_at_that_nu():
    _, free, st, tgt, F = _setup(None)
    _, fixed, _, _, _ = _setup(NU)
    _, jnp = b0._jax()
    m, s = free["lam_moments"](jnp.log(st["nu"]))
    eta = (jnp.log(st["lam"]) - m) / s
    keta = _unit_eta(free, st)
    rng = np.random.default_rng(7)
    for _ in range(4):
        hyp = np.log([0.08, 0.1, 0.2]) + 0.3 * rng.standard_normal(3)
        ls = np.log(np.asarray(st["sigma"])) + 0.2 * rng.standard_normal(4)
        lf = 0.2 * rng.standard_normal(len(P) - 1)
        x_free = np.concatenate([hyp, ls, [np.log(NU)], lf])
        x_fixed = np.concatenate([hyp, ls, lf])

        def at(parts, x):
            return float(
                parts["scales_logp"](
                    parts["data"],
                    jnp.asarray(x),
                    eta,
                    tgt,
                    st["bld_sd"],
                    None,
                    F,
                    st["kap"],
                    keta,
                )
            )

        np.testing.assert_allclose(at(fixed, x_fixed), at(free, x_free), rtol=1e-12)


def test_the_scale_step_holds_nu_and_the_rows_mixing_scales():
    _, parts, st, tgt, F = _setup(NU)
    jax, jnp = b0._jax()
    assert not parts["nu_free"]
    assert st["hyp_dirs"].shape == (7 + len(P) - 1,) * 2
    new = parts["update_scales"](parts["data"], jax.random.PRNGKey(4), st, tgt, F)
    assert float(new["nu"]) == NU
    np.testing.assert_allclose(np.asarray(new["lam"]), np.asarray(st["lam"]), rtol=1e-6)
    assert float(jnp.abs(new["hyp"] - st["hyp"]).min()) > 0
    assert float(jnp.abs(new["sigma"] - st["sigma"]).min()) > 0
    np.testing.assert_allclose(
        parts["scales_x"](st | new)[7:], np.log(np.asarray(new["phase_scale"]))
    )


def test_the_noise_step_holds_nu_and_draws_sigma_and_lam():
    train, parts, st, _, _ = _setup(NU)
    jax, jnp = b0._jax()
    r = jnp.asarray(0.1 * np.random.default_rng(8).standard_normal(len(train.y)))
    nu, sigma, lam = parts["update_noise"](jax.random.PRNGKey(2), st, r, parts["data"])
    assert float(nu) == NU
    assert float(jnp.abs(sigma - st["sigma"]).min()) > 0
    assert float(jnp.abs(lam - st["lam"]).min()) > 0


def test_sweeps_keep_nu_at_its_value():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    sweep, init, _, _ = _sampler(train, NU)
    jax, _ = b0._jax()
    st = init(jax.random.split(jax.random.PRNGKey(0), 2))
    first = np.asarray(st["sigma"])
    key = jax.random.PRNGKey(1)
    for _ in range(5):
        key, sub = jax.random.split(key)
        st, _ = sweep(jax.random.split(sub, 2), st)
        assert (np.asarray(st["nu"]) == NU).all()
        assert np.isfinite(np.asarray(st["lam"])).all()
    assert np.abs(np.asarray(st["sigma"]) - first).min() > 0


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitkn was added. A deliberate change to the model's draws changes
# it.
PHASE_UNITKN_RUN_SHA256 = (
    "b5bf611050258d4a3df9ae9fae182d15080f783fc2d3694e19be80e47a65988c"
)


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    out = drift_building_phase_unitkn.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    assert (np.asarray(out["trace"]["nu"]) == NU).all()
    assert (np.asarray(out["kept"]["nu"]) == NU).all()
    # The gate skips the constant nu and still reads every scale that moves.
    names = train.names
    rows = drift_building_phase_unitkn.diagnostics(out["trace"], names)["per_quantity"]
    assert "nu" not in rows and {"unit_sd", "drift_sd", "sigma[1]"} <= set(rows)
    assert "coefficients" in drift_building_phase_unitkn.summarize(out["kept"], names)
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == PHASE_UNITKN_RUN_SHA256, h.hexdigest()


def test_the_model_is_l1tk_with_the_rows_nu_fixed():
    m = drift_building_phase_unitkn
    k = drift_building_phase_unitk
    assert m.NAME == "drift-building-phase-unitkn" and m.ROW_DOF == 2.0
    assert m.UNIT_DOF == k.UNIT_DOF and m.LEVEL_DOF == k.LEVEL_DOF
    assert m.GROUPS == k.GROUPS and m.design is k.design and m.Priors is k.Priors
    assert (
        '("drift-building-phase-unitkn", "drift_building_phase_unitkn")'
        in open(run.__file__).read()
    )
    rec = m.run_record(tp._phased(n=300))
    assert rec["unit_t"]["kap_step"] == "collapsed over u and s"
    assert rec["row_dof_fixed"] == 2.0

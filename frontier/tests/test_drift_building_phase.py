"""The building model with a noise scale for each lease phase
(`rentfrontier.drift_building_phase`), and the drift model's phases in general."""

import dataclasses
import hashlib

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building,
    drift_building_phase,
    drift_pool,
    drift_score,
    run,
)

P = drift_building_phase.PHASES


def test_phases_count_the_months_from_the_units_previous_ad():
    day = pd.Timestamp("2024-01-01", tz="UTC")
    month = pd.Timedelta(days=365.25 / 12)
    rows = [
        # building, unit_id, months from `day`, audit_id, the phase
        ("a", "1", 43.0, "5", "26+"),
        ("a", "1", 0.0, "1", "none"),
        ("a", "1", 2.9, "2", "0-2"),
        ("a", "1", 6.0, "3", "3-9"),
        ("a", "1", 16.2, "4", "10-13"),
        # The same unit_id in another building is another unit.
        ("b", "1", 31.0, "6", "none"),
        # Two ads at one time are ordered by audit_id.
        ("c", "7", 0.0, "9", "0-2"),
        ("c", "7", 0.0, "8", "none"),
        ("c", None, 1.0, "10", "none"),
        ("c", "7", 13.9, "11", "10-13"),
        ("c", "7", 28.0, "12", "14-21"),
        ("c", "7", 50.1, "13", "22-25"),
        ("c", "7", 76.2, "14", "26+"),
    ]
    frame = pd.DataFrame(
        {
            "building": [r[0] for r in rows],
            "unit_id": [r[1] for r in rows],
            "price_at": [day + r[2] * month for r in rows],
            "audit_id": [r[3] for r in rows],
        }
    )
    want = [r[4] for r in rows]
    got = [P[i] for i in drift_building_phase.phase_index(frame)]
    assert got == want
    months = drift_building_phase.months_since_previous(frame)
    np.testing.assert_allclose(months[[2, 6]], [2.9, 0.0], atol=1e-9)
    assert np.isnan(months[[1, 5, 7, 8]]).all()


def _phased(seed=4, **kw):
    """`td._design` with random noise phases."""
    full = td._design(**kw)
    rng = np.random.default_rng(seed)
    return dataclasses.replace(
        full, phase=rng.integers(0, len(P), len(full.y)), phases=P
    )


def test_scales_logp_matches_the_dense_density_as_the_factors_move():
    train, _, _ = td._split(_phased(per_unit=9))
    _, init, _, parts = td._sampler(train, dof=4.0)
    assert parts["phased"]
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(5)
    st = td._state(init, parts)
    S = len(parts["zone"])
    F = 0.1 * rng.standard_normal(S)
    tgt = F[train.site[parts["order"]]] + 0.2 * rng.standard_normal(len(train.y))
    m, s = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (np.log(np.asarray(st["lam"])) - float(m)) / float(s)
    head = np.log([0.08, 0.1, 0.2, 0.05, 0.06, 0.07, 0.08, 4.0])

    def both(lf):
        x = np.concatenate([head, lf])
        got = parts["scales_logp"](
            D,
            jnp.asarray(x),
            jnp.asarray(eta),
            jnp.asarray(tgt),
            st["bld_sd"],
            None,
            jnp.asarray(F),
            st.get("kap"),
        )
        return float(got), td._scales_want(train, parts, st, eta, tgt, F, x)

    base = both(np.zeros(len(P) - 1))
    for lf in (
        [0.3, 0, 0, 0, 0, 0],
        [0, -0.4, 0, 0, 0.2, 0],
        0.25 * rng.standard_normal(len(P) - 1),
    ):
        got, want = both(np.asarray(lf, float))
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_update_scales_moves_the_factors_with_the_other_scales():
    train, _, _ = td._split(_phased(per_unit=9))
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    st = td._state(init, parts)
    assert st["hyp_dirs"].shape == (8 + len(P) - 1,) * 2
    rng = np.random.default_rng(6)
    F = jnp.asarray(0.1 * rng.standard_normal(len(parts["zone"])))
    tgt = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    new = parts["update_scales"](parts["data"], jax.random.PRNGKey(4), st, tgt, F)
    assert float(jnp.abs(new["phase_scale"] - st["phase_scale"]).min()) > 0
    np.testing.assert_allclose(
        parts["scales_x"](st | new)[8:], np.log(np.asarray(new["phase_scale"]))
    )


@pytest.fixture(scope="module")
def phase_run():
    full = _phased(n=400, per_unit=9)
    train, _, held = td._split(full)
    out = drift_building.run(
        train,
        building_zones.Priors(),
        drift.Settings(
            chains=2, warmup=60, draws=8, keep_every=2, level_dof=4.0, seed=3
        ),
        log=lambda m: None,
    )
    return full, held, out


def test_a_run_traces_and_keeps_every_phases_factor(phase_run):
    full, held, out = phase_run
    trace, kept = out["trace"], out["kept"]
    assert trace["phase_scale"].shape == (2, 8, len(P))
    assert (trace["phase_scale"][..., 0] == 1).all()
    assert np.ptp(trace["phase_scale"][..., 1:], axis=1).min() > 0
    assert kept["phase_scale"].shape == (2, 4, len(P))
    np.testing.assert_array_equal(kept["pred_phase"], full.phase[held])
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 8 + len(P) - 1
    rows = drift.diagnostics(trace, full.names)["per_quantity"]
    assert "phase_scale[0]" not in rows
    assert {f"phase_scale[{j}]" for j in range(1, len(P))} <= set(rows)
    assert len(drift.summarize(kept, full.names)["phase_scale"]) == len(P)


def _save(tmp_path, name, out, held):
    d = tmp_path / name
    d.mkdir()
    np.savez(
        d / "posterior.npz",
        **{f"trace/{k}": v for k, v in out["trace"].items()},
        **{f"kept/{k}": v for k, v in out["kept"].items()},
        names=np.array(["a"]),
        heldout=held,
    )
    return d


def test_scores_scale_each_rows_sigma_by_its_phases_factor(phase_run, tmp_path):
    _, held, out = phase_run
    got = drift_score.score_run(_save(tmp_path, "r", out, held))
    kept = out["kept"]
    flat = lambda k: kept[k].reshape(-1, *kept[k].shape[2:])  # noqa: E731
    group, phase = kept["pred_group"], kept["pred_phase"]
    want = drift_score.score_rows(
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma")[:, group] * flat("phase_scale")[:, phase],
        flat("nu"),
        kept["pred_y"],
        0,
    )
    np.testing.assert_allclose(got["elpd"], want["elpd"])
    plain = drift_score.score_rows(
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma")[:, group],
        flat("nu"),
        kept["pred_y"],
        0,
    )
    assert np.abs(got["elpd"] - plain["elpd"]).max() > 1e-3


def test_pooled_parts_keep_the_rows_phases(phase_run, tmp_path):
    _, held, out = phase_run
    a = dict(np.load(_save(tmp_path, "a", out, held) / "posterior.npz"))
    pooled = drift_pool.pool([a, a])
    np.testing.assert_array_equal(pooled["kept/pred_phase"], a["kept/pred_phase"])
    assert pooled["kept/phase_scale"].shape[0] == 4
    other = a | {"kept/pred_phase": a["kept/pred_phase"][::-1]}
    with pytest.raises(SystemExit, match="pred_phase"):
        drift_pool.pool([a, other])


# The sha256 of every traced and kept array of the run below on drift.py as of a98b0a35,
# before the noise phases, on the CPU. A deliberate change to the building model's draws
# changes it.
BUILDING_RUN_SHA256 = "56935545df671796e76b433453175d1074a3ecba773559a60a1f92db4267d48b"


def test_a_design_with_no_phases_draws_what_it_drew_before_the_phases():
    full = td._design(n=400, per_unit=9)
    train, _, _ = td._split(full)
    assert train.phase is None
    out = drift_building.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == BUILDING_RUN_SHA256


# The sha256 of every traced and kept array of the run below on the CPU, as drawn at
# 9a7830fb, the commit of L1's fits. A deliberate change to the phased model's draws
# changes it.
PHASE_RUN_SHA256 = "c35722d48b214279d47475b7b3beb2dab56d8b1fd865801c6dccde51b2d4b959"


def test_a_phased_design_draws_what_it_drew_at_l1s_commit():
    train, _, _ = td._split(_phased(n=400, per_unit=9))
    assert train.phase is not None
    out = drift_building.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == PHASE_RUN_SHA256


def test_the_model_is_the_building_model_with_its_phases():
    assert drift_building_phase.LEVEL_DOF == drift_building.LEVEL_DOF
    assert drift_building_phase.GROUPS == ("building",)
    assert drift_building_phase.NAME == "drift-building-phase"
    assert P[0] == "10-13" and len(set(P)) == 7
    assert set(drift_building_phase.BINNED) | {"none"} == set(P)
    assert (
        '("drift-building-phase", "drift_building_phase")' in open(run.__file__).read()
    )
    d = _phased(n=300)
    rec = drift_building_phase.run_record(d)["phase"]
    assert rec["reference"] == "10-13" and sum(rec["rows"].values()) == len(d.y)

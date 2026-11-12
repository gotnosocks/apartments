"""The building model with noise factors for lease phase and calendar year
(`rentfrontier.drift_building_phase_year`), and the drift model's `Design.phase_map`."""

import dataclasses

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building,
    drift_building_phase_year,
    drift_score,
    run,
)

M = drift_building_phase_year
P, Y = len(M.PHASES), len(M.YEARS)
FREE = P - 1 + Y - 1


def test_years_take_the_price_at_year_with_the_ends_clipped():
    frame = pd.DataFrame(
        {
            "price_at": pd.to_datetime(
                [
                    "2012-06-01 00:00:00",
                    "2014-03-01 00:00:00",
                    "2021-01-01 04:00:00",
                    "2024-07-01 00:00:00",
                    "2026-10-01 00:00:00",
                    "2027-02-01 00:00:00",
                ],
                utc=True,
            )
        }
    )
    got = [M.YEARS[i] for i in M.year_index(frame)]
    assert got == [2014, 2014, 2021, 2024, 2026, 2026]
    assert M.YEARS[0] == M.REFERENCE_YEAR and sorted(M.YEARS) == list(range(2014, 2027))


def test_a_cells_factor_is_its_phases_times_its_years():
    names, A = M.cells(), M.cell_map()
    assert names[0] == f"{M.PHASES[0]}|{M.REFERENCE_YEAR}" and len(names) == P * Y
    assert A.shape == (P * Y, FREE) and not A[0].any()
    rng = np.random.default_rng(1)
    lf = 0.3 * rng.standard_normal(FREE)
    cell = np.exp(A @ lf)
    phase, year = M.factors(cell)
    np.testing.assert_allclose(phase, np.exp(np.r_[0, lf[: P - 1]]))
    np.testing.assert_allclose(year, np.exp(np.r_[0, lf[P - 1 :]]))
    np.testing.assert_allclose(cell.reshape(P, Y), np.outer(phase, year))


def _crossed(seed=4, **kw):
    """`td._design` with random cells of phase and year and their map."""
    full = td._design(**kw)
    rng = np.random.default_rng(seed)
    return dataclasses.replace(
        full,
        phase=rng.integers(0, P * Y, len(full.y)),
        phases=M.cells(),
        phase_map=M.cell_map(),
    )


def test_scales_logp_matches_the_dense_density_as_the_factors_move():
    train, _, _ = td._split(_crossed(per_unit=9))
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

    base = both(np.zeros(FREE))
    one_year = np.zeros(FREE)
    one_year[P - 1 + 5] = 0.4
    for lf in (
        one_year,
        np.r_[[0.3, 0, 0, 0, 0, 0], [0, -0.4] + [0] * (Y - 3)],
        0.25 * rng.standard_normal(FREE),
    ):
        got, want = both(np.asarray(lf, float))
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_update_scales_moves_every_free_factor():
    train, _, _ = td._split(_crossed(per_unit=9))
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    st = td._state(init, parts)
    assert st["phase_scale"].shape[-1] == FREE
    assert st["hyp_dirs"].shape == (8 + FREE,) * 2
    rng = np.random.default_rng(6)
    F = jnp.asarray(0.1 * rng.standard_normal(len(parts["zone"])))
    tgt = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    new = parts["update_scales"](parts["data"], jax.random.PRNGKey(4), st, tgt, F)
    assert float(jnp.abs(new["phase_scale"] - st["phase_scale"]).min()) > 0
    # Each row's scale is its group's sigma times its phase's and its year's factors.
    sd = np.asarray(parts["row_sd"](parts["data"], new["sigma"], new["phase_scale"]))
    cell = train.phase[parts["order"]]
    f = np.r_[1.0, np.asarray(new["phase_scale"])]
    g = np.r_[1.0, f[P:]]
    want = (
        np.asarray(new["sigma"])[train.group[parts["order"]]]
        * f[:P][cell // Y]
        * g[cell % Y]
    )
    np.testing.assert_allclose(sd, want, rtol=1e-6)


@pytest.fixture(scope="module")
def crossed_run():
    full = _crossed(n=400, per_unit=9)
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


def test_a_run_keeps_every_cells_factor_as_a_product(crossed_run):
    full, held, out = crossed_run
    trace, kept = out["trace"], out["kept"]
    assert trace["phase_scale"].shape == (2, 8, P * Y)
    assert kept["phase_scale"].shape == (2, 4, P * Y)
    phase, year = M.factors(trace["phase_scale"])
    np.testing.assert_allclose(
        trace["phase_scale"],
        (phase[..., :, None] * year[..., None, :]).reshape(2, 8, -1),
        rtol=1e-6,
    )
    assert (phase[..., 0] == 1).all() and (year[..., 0] == 1).all()
    np.testing.assert_array_equal(kept["pred_phase"], full.phase[held])
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 8 + FREE
    rows = drift.diagnostics(trace, full.names)["per_quantity"]
    # Every free factor is a cell's own: phase p in the reference year, year y in the
    # reference phase.
    assert {f"phase_scale[{p * Y}]" for p in range(1, P)} <= set(rows)
    assert {f"phase_scale[{y}]" for y in range(1, Y)} <= set(rows)
    assert "phase_scale[0]" not in rows


def test_scores_scale_each_rows_sigma_by_its_cells_factor(crossed_run, tmp_path):
    _, held, out = crossed_run
    d = tmp_path / "r"
    d.mkdir()
    np.savez(
        d / "posterior.npz",
        **{f"trace/{k}": v for k, v in out["trace"].items()},
        **{f"kept/{k}": v for k, v in out["kept"].items()},
        names=np.array(["a"]),
        heldout=held,
    )
    got = drift_score.score_run(d)
    kept = out["kept"]
    flat = lambda k: kept[k].reshape(-1, *kept[k].shape[2:])  # noqa: E731
    cell, group = kept["pred_phase"], kept["pred_group"]
    phase, year = M.factors(flat("phase_scale"))
    want = drift_score.score_rows(
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma")[:, group] * phase[:, cell // Y] * year[:, cell % Y],
        flat("nu"),
        kept["pred_y"],
        0,
    )
    np.testing.assert_allclose(got["elpd"], want["elpd"], rtol=1e-6)


def test_the_model_is_the_phase_model_with_its_years():
    assert M.LEVEL_DOF == drift_building.LEVEL_DOF
    assert M.GROUPS == ("building",)
    assert M.NAME == "drift-building-phase-year"
    assert (
        '("drift-building-phase-year", "drift_building_phase_year")'
        in open(run.__file__).read()
    )
    d = _crossed(n=300)
    rec = M.run_record(d)["phase"]
    assert rec["reference"] == "10-13" and rec["reference_year"] == 2024
    assert sum(rec["rows"].values()) == sum(rec["year_rows"].values()) == len(d.y)

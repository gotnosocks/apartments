import json

import numpy as np
import pytest

from rentfrontier import b0, b0_2, b0_3
from test_b0 import frame_of

pytest.importorskip("numpyro")


def cells_of(frame):
    known = ~np.isnan(frame.full_baths.to_numpy())
    beds = np.minimum(frame.bedrooms.to_numpy().astype(int), b0_3.BEDS)
    full = np.clip(np.nan_to_num(frame.full_baths.to_numpy(), nan=1), 1, b0_3.BATHS)
    return known, beds, full.astype(int)


def test_columns_step_from_each_levels_modal_bath():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    d = b0_3.design(frame)
    assert not any(n.startswith("full>=") for n in d.names)
    known, beds, full = cells_of(frame)
    x = dict(zip(d.names, d.x.T))
    # 2 beds: the modal count is 1, so a second full bath is a step up.
    assert set(np.unique(x["bed=2:full>=2"])) <= {0.0, 1.0}
    assert x["bed=2:full>=2"].sum() == (known & (beds == 2) & (full >= 2)).sum()
    # 4 beds: the modal count is 2, so one full bath sits a step below it.
    if "bed=4:full>=2" in x:
        assert set(np.unique(x["bed=4:full>=2"])) <= {0.0, -1.0}
        assert -x["bed=4:full>=2"].sum() == (known & (beds == 4) & (full < 2)).sum()
    assert [
        b0_3.pool(n) for n in ("bed=0:full>=2", "bed=3:full>=4", "bed=4:full>=2")
    ] == [
        "bath+1",
        "bath+3",
        "bath-1",
    ]
    assert b0_3.pool("bed=5:full>=4") == "bath+2"


def test_ladder_sums_the_spine_and_bath_steps_of_each_cell():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    d = b0_3.design(frame)
    ladder = [j for j, n in enumerate(d.names) if n.startswith(("bed>=", "bed="))]
    rng = np.random.default_rng(0)
    beta = np.zeros(len(d.names))
    beta[ladder] = rng.normal(0, 0.3, len(ladder))
    cells = b0_3.cell_log_premiums(beta, d.names)
    assert cells[(0, 1)] == 0.0
    known, beds, full = cells_of(frame)
    want = np.array([cells[(b, f)] for b, f in zip(beds, full)])
    assert np.allclose((d.x @ beta)[known], want[known])


def test_modal_contrasts_read_the_modal_path():
    cells = {
        (b, f): 10.0 * b + f + (5.0 if b >= 4 else 0.0)
        for b in range(6)
        for f in range(1, 5)
    }
    c = b0_3.modal_contrasts(cells)
    assert c["bed 0->1 on modal path"] == 10.0
    assert c["bed 3->4 on modal path"] == 10.0 + 5.0 + 1.0
    assert c["2 bed: +1 full bath over 1"] == 1.0
    assert c["4 bed: -1 full bath from 2"] == -1.0
    assert "1 bed: -1 full bath from 1" not in c
    # B0.2's cells go through the same contrasts.
    frame, _ = frame_of(n=2000, weeks=20, seed=4)
    d = b0_2.design(frame)
    beta = np.random.default_rng(1).normal(0, 0.2, (7, len(d.names)))
    c2 = b0_3.modal_contrasts(b0_2.cell_log_premiums(beta, d.names))
    assert c2["bed 4->5 on modal path"].shape == (7,)


def test_model_log_density_matches_b0_3_written_out():
    """The NumPyro model's joint density at a point equals B0.3 written out by hand, up to
    the constant of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = b0_3.design(frame)
    priors = b0_3.Priors()
    fixed, steps, pools = b0_3.split_index(d.names)
    rng = np.random.default_rng(0)
    main = rng.normal(0, 0.1, len(fixed))
    main[0] = np.log(2500)
    phi = np.array([0.2, 0.3, 0.5, 0.6])
    u = rng.normal(0, 1, len(steps))
    z = rng.standard_t(2, d.weeks)
    point = {
        "main": main,
        "phi": phi,
        "s_bath": 0.07,
        "bath_z": u,
        "g": 0.0005,
        "tau": 0.002,
        "nu_t": 1.5,
        "nu": 5.0,
        "sigma": truth["sigma"],
        "z": z,
    }
    got, _ = log_density(b0_3.model(d, priors), (), {}, point)

    m_fix, s_fix = b0_3.prior_arrays(priors, d.names)
    beta = np.zeros(len(d.names))
    beta[fixed], beta[steps] = main, phi[pools] + 0.07 * u
    L = np.concatenate([[0.0], np.cumsum(0.0005 + 0.002 * z)])
    mu = d.x @ beta + (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    want = (
        stats.norm.logpdf(main, m_fix, s_fix).sum()
        + stats.norm.logpdf(phi, *priors.bath).sum()
        + np.log(2) + stats.norm.logpdf(0.07, 0, priors.s_bath)
        + stats.norm.logpdf(u, 0, 1).sum()
        + stats.norm.logpdf(0.0005, *priors.g)
        + np.log(tau_rate) - tau_rate * 0.002
        + stats.gamma.logpdf(1.5, priors.nu_t[0], scale=1 / priors.nu_t[1])
        + stats.gamma.logpdf(5.0, priors.nu[0], scale=1 / priors.nu[1])
        + (np.log(2) + stats.norm.logpdf(truth["sigma"], 0, priors.sigma)).sum()
        + stats.t.logpdf(z, 1.5).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )  # fmt: skip
    assert float(got) == pytest.approx(float(want), rel=1e-9)


def test_run_and_score(tmp_path, monkeypatch):
    from rentfrontier import loo
    from rentfrontier import run as runmod

    frame, _ = frame_of(n=1500, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(loo, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "b0.3", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "b03-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "b03-test" / "result.json").read_text())
    assert result["sampler"] == "b0.3" and result["line"] == "baseline-blackjax"
    per = result["diagnostics"]["per_quantity"]
    assert "s_bath" in per and "phi[bath+1]" in per
    assert result["model"]["priors"]["s_bath"] == b0_3.Priors.s_bath
    record, pointwise = b0.score("b03-test", "b0.3", b0_3)
    assert record["model"] == "b0.3"
    assert np.isfinite(record["elpd_loo"])
    s = record["summary"]
    assert s["cells"]["0bed_1bath"]["median"] == 0.0
    assert "4 bed: -1 full bath from 2" in s["modal_contrasts"]
    assert set(s["shared_bath_steps"]) == set(b0_3.POOLS)
    assert [r["n"] for r in record["scorecard"]] == list(range(1, 9))
    assert pointwise["heldout_quantiles"].shape == (result["sizes"]["heldout"], 5)

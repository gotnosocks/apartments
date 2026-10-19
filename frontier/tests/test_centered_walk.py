import json

import numpy as np
import pytest

from rentfrontier import b0, b0_3, centered_walk
from test_b0 import frame_of

pytest.importorskip("numpyro")


def a_point(d, truth, rng):
    fixed, steps, _ = b0_3.split_index(d.names)
    main = rng.normal(0, 0.1, len(fixed))
    main[0] = np.log(2500)
    return {
        "main": main,
        "phi": np.array([0.2, 0.3, 0.5, 0.6]),
        "s_bath": 0.07,
        "bath_z": rng.normal(0, 1, len(steps)),
        "g": 0.0005,
        "tau": 0.002,
        "nu_t": 1.5,
        "nu": 5.0,
        "sigma": truth["sigma"],
    }


def test_log_density_matches_the_centered_walk_written_out():
    """The joint density at a point equals the model written out by hand, up to the constant
    of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = centered_walk.design(frame)
    priors = centered_walk.Priors()
    fixed, steps, pools = b0_3.split_index(d.names)
    rng = np.random.default_rng(0)
    point = a_point(d, truth, rng)
    level = np.cumsum(rng.normal(0.001, 0.01, d.weeks))
    point["level"] = level
    got, _ = log_density(centered_walk.model(d, priors), (), {}, point)

    m_fix, s_fix = b0_3.prior_arrays(priors, d.names)
    main, phi, u = point["main"], point["phi"], point["bath_z"]
    beta = np.zeros(len(d.names))
    beta[fixed], beta[steps] = main, phi[pools] + 0.07 * u
    L = np.concatenate([[0.0], level])
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
        + stats.t.logpdf(np.diff(L), 1.5, 0.0005, 0.002).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )  # fmt: skip
    assert float(got) == pytest.approx(float(want), rel=1e-9)


def test_same_posterior_as_b0_3_up_to_the_jacobian():
    """At the levels B0.3 builds from z, the two densities differ by W log tau, the Jacobian
    of z -> L, and the trend and shocks they report agree."""
    import jax
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=600, weeks=25, seed=4)
    d = centered_walk.design(frame)
    priors = centered_walk.Priors()
    rng = np.random.default_rng(1)
    point = a_point(d, truth, rng)
    z = rng.standard_t(3, d.weeks)
    nc, nc_trace = log_density(b0_3.model(d, priors), (), {}, point | {"z": z})
    level = np.cumsum(point["g"] + point["tau"] * z)
    c, c_trace = log_density(
        centered_walk.model(d, priors), (), {}, point | {"level": level}
    )
    assert float(c) == pytest.approx(
        float(nc) - d.weeks * np.log(point["tau"]), rel=1e-9
    )
    for k in ("L", "eta", "beta"):
        np.testing.assert_allclose(
            c_trace[k]["value"], nc_trace[k]["value"], atol=1e-12
        )


def test_starting_trend_follows_the_weekly_means():
    frame, truth = frame_of(n=3000, weeks=40, seed=7)
    d = centered_walk.design(frame)
    L = centered_walk.starting_trend(d)
    assert L.shape == (d.weeks + 1,) and L[0] == 0.0
    init = centered_walk.initial_values(d, centered_walk.Priors(), chains=4, seed=0)
    assert "z" not in init and init["level"].shape == (4, d.weeks)
    assert np.all(np.isfinite(init["tau"])) and np.all(np.exp(init["tau"]) > 0)
    # The intercept absorbs the starting trend's average over the rows.
    trend = (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    assert init["main"][:, 0].mean() == pytest.approx(
        np.mean(d.y) - np.mean(trend), abs=0.01
    )


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
            "--split", "latest", "--model", "centered-walk", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "cw-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "cw-test" / "result.json").read_text())
    assert result["sampler"] == "centered-walk"
    assert result["line"] == "baseline-blackjax"
    assert "tau" in result["diagnostics"]["per_quantity"]
    record, _ = b0.score("cw-test", "centered-walk", centered_walk)
    assert record["model"] == "centered-walk"
    assert np.isfinite(record["elpd_loo"])

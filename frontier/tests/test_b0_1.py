import json

import numpy as np
import pytest

from rentfrontier import b0, b0_1
from test_b0 import frame_of

pytest.importorskip("numpyro")


def test_model_log_density_matches_b0_written_out():
    """The NumPyro model's joint density at a point equals B0's model written out by hand,
    up to the constant of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = b0.design(frame)
    priors = b0.Priors()
    rng = np.random.default_rng(0)
    beta = truth["beta"] + 0.01 * rng.standard_normal(len(d.names))
    L = truth["L"][: d.weeks + 1]
    point = {
        "beta": beta,
        "g": 0.0005,
        "h": 30.0,
        "tau": 0.0004,
        "nu_t": 3.0,
        "nu": 5.0,
        "sigma": truth["sigma"],
        "level": beta[0] + L[1:],
    }
    got, _ = log_density(b0_1.model(d, priors), (), {}, point)

    m_beta, s_beta = b0.prior_arrays(priors, d.names)
    rho = 0.5 ** (1 / 30.0)
    z = np.diff(L) - 0.0005
    eta = z[1:] - rho * z[:-1]
    trend = (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    mu = d.x @ beta + trend
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    want = (
        stats.norm.logpdf(beta, m_beta, s_beta).sum()
        + stats.norm.logpdf(0.0005, *priors.g)
        + stats.norm.logpdf(np.log(30.0), *priors.log_h)
        - np.log(30.0)
        + np.log(tau_rate)
        - tau_rate * 0.0004
        + stats.gamma.logpdf(3.0, priors.nu_t[0], scale=1 / priors.nu_t[1])
        + stats.gamma.logpdf(5.0, priors.nu[0], scale=1 / priors.nu[1])
        + (np.log(2) + stats.norm.logpdf(truth["sigma"], 0, priors.sigma)).sum()
        + stats.norm.logpdf(z[0], 0, 0.0004 / np.sqrt(1 - rho**2))
        + stats.t.logpdf(eta, 3.0, 0, 0.0004).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )
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
            "--split", "latest", "--model", "b0.1", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "b01-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "b01-test" / "result.json").read_text())
    assert result["sampler"] == "b0.1" and result["line"] == "baseline-blackjax"
    assert result["sampler_settings"]["max_leapfrog_steps"] == 20
    assert 0 < result["chees"]["gradients"] <= 100 * 20
    record, pointwise = b0.score("b01-test", "b0.1")
    assert record["model"] == "b0.1"
    assert np.isfinite(record["elpd_loo"])
    assert pointwise["heldout_quantiles"].shape == (result["sizes"]["heldout"], 5)

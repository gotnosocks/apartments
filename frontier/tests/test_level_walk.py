import json

import numpy as np
import pytest

from rentfrontier import b0, centered_walk, level_walk
from test_b0 import frame_of
from test_centered_walk import a_point

pytest.importorskip("numpyro")


def test_same_posterior_as_the_centered_walk():
    """At M = intercept + (0, L_1..L_W) the two densities agree exactly, since the map has
    Jacobian 1, and so do the trend, shocks and coefficients they report."""
    import jax
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=600, weeks=25, seed=4)
    d = level_walk.design(frame)
    priors = level_walk.Priors()
    rng = np.random.default_rng(1)
    point = a_point(d, truth, rng)
    level = np.cumsum(rng.normal(0.001, 0.01, d.weeks))
    c, c_trace = log_density(
        centered_walk.model(d, priors), (), {}, point | {"level": level}
    )
    alpha = point["main"][0]
    moved = point | {
        "main": point["main"][1:],
        "level": np.concatenate([[alpha], alpha + level]),
    }
    m, m_trace = log_density(level_walk.model(d, priors), (), {}, moved)
    assert float(m) == pytest.approx(float(c), rel=1e-12)
    for k in ("L", "eta", "beta"):
        np.testing.assert_allclose(m_trace[k]["value"], c_trace[k]["value"], atol=1e-12)


def test_starting_levels_carry_the_intercept():
    frame, _ = frame_of(n=3000, weeks=40, seed=7)
    d = level_walk.design(frame)
    priors = level_walk.Priors()
    c = centered_walk.initial_values(d, priors, chains=4, seed=0)
    init = level_walk.initial_values(d, priors, chains=4, seed=0)
    assert init["main"].shape == (4, c["main"].shape[1] - 1)
    assert init["level"].shape == (4, d.weeks + 1)
    np.testing.assert_allclose(init["level"][:, 0], c["main"][:, 0])
    np.testing.assert_allclose(
        init["level"][:, 1:] - init["level"][:, :1], c["level"], atol=1e-12
    )
    np.testing.assert_allclose(init["main"], c["main"][:, 1:])


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
            "--split", "latest", "--model", "level-walk", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "lw-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "lw-test" / "result.json").read_text())
    assert result["sampler"] == "level-walk"
    assert result["line"] == "baseline-blackjax"
    assert "beta[alpha]" in result["diagnostics"]["per_quantity"]
    record, _ = b0.score("lw-test", "level-walk", level_walk)
    assert record["model"] == "level-walk"
    assert np.isfinite(record["elpd_loo"])

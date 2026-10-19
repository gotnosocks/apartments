import json

import numpy as np
import pytest

from rentfrontier import b0, level_walk, total_walk
from test_b0 import frame_of
from test_centered_walk import a_point

pytest.importorskip("numpyro")


def test_grid_season_matches_the_design_on_grid_days():
    """An ad posted on a grid week's Monday gets the same season terms as that grid week."""
    frame, _ = frame_of(n=800, weeks=60, seed=3)
    d = total_walk.design(frame)
    B = total_walk.grid_season(d)
    cols = [d.names.index(n) for n in total_walk.SEASON]
    on = d.frac == 0
    assert on.any()
    np.testing.assert_allclose(d.x[on][:, cols], B[d.week[on]], atol=1e-12)


def test_same_posterior_as_the_level_walk():
    """At D = M + B s the two densities agree exactly, since the map has Jacobian 1, and so do
    the trend, shocks and coefficients they report."""
    import jax
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=600, weeks=25, seed=4)
    d = total_walk.design(frame)
    priors = total_walk.Priors()
    rng = np.random.default_rng(1)
    point = a_point(d, truth, rng)
    point["main"] = point["main"][1:]
    M = np.log(2500) + np.concatenate([[0.0], np.cumsum(rng.normal(0, 0.01, d.weeks))])
    lw, lw_trace = log_density(
        level_walk.model(d, priors), (), {}, point | {"level": M}
    )
    fixed, _, _ = total_walk.split_index(d.names)
    rest = list(fixed[fixed != d.names.index("alpha")])
    s = point["main"][[rest.index(d.names.index(n)) for n in total_walk.SEASON]]
    assert np.abs(s).max() > 0.01
    D = M + total_walk.grid_season(d) @ s
    tw, tw_trace = log_density(
        total_walk.model(d, priors), (), {}, point | {"total": D}
    )
    assert float(tw) == pytest.approx(float(lw), rel=1e-12)
    for k in ("L", "eta", "beta"):
        np.testing.assert_allclose(
            tw_trace[k]["value"], lw_trace[k]["value"], atol=1e-12
        )


def test_starting_totals_carry_the_season():
    frame, _ = frame_of(n=3000, weeks=40, seed=7)
    d = total_walk.design(frame)
    priors = total_walk.Priors()
    lw = level_walk.initial_values(d, priors, chains=4, seed=0)
    init = total_walk.initial_values(d, priors, chains=4, seed=0)
    assert "level" not in init and init["total"].shape == (4, d.weeks + 1)
    np.testing.assert_allclose(init["main"], lw["main"])
    fixed, _, _ = total_walk.split_index(d.names)
    rest = list(fixed[fixed != d.names.index("alpha")])
    s = init["main"][:, [rest.index(d.names.index(n)) for n in total_walk.SEASON]]
    np.testing.assert_allclose(
        init["total"] - s @ total_walk.grid_season(d).T, lw["level"], atol=1e-12
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
            "--split", "latest", "--model", "total-walk", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "tw-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "tw-test" / "result.json").read_text())
    assert result["sampler"] == "total-walk"
    assert result["line"] == "baseline-blackjax"
    assert "beta[cos1]" in result["diagnostics"]["per_quantity"]
    record, _ = b0.score("tw-test", "total-walk", total_walk)
    assert record["model"] == "total-walk"
    assert np.isfinite(record["elpd_loo"])

import json

import numpy as np
import pytest
from scipy import stats

from rentfrontier import b0, free_bath, total_walk
from test_b0 import frame_of
from test_centered_walk import a_point

pytest.importorskip("numpyro")


def test_differs_from_the_total_walk_only_in_the_bath_prior():
    """At the same bath steps, the two densities differ by the pooled prior against the
    independent one, and the trend, shocks and coefficients agree."""
    import jax
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=600, weeks=25, seed=4)
    d = free_bath.design(frame)
    priors = free_bath.Priors()
    rng = np.random.default_rng(1)
    point = a_point(d, truth, rng)
    point["main"] = point["main"][1:]
    point["total"] = np.log(2500) + np.cumsum(rng.normal(0, 0.01, d.weeks + 1))
    t, t_trace = log_density(total_walk.model(d, priors), (), {}, point)
    _, _, pools = free_bath.split_index(d.names)
    phi, s_bath, u = point.pop("phi"), point.pop("s_bath"), point.pop("bath_z")
    theta = phi[pools] + s_bath * u
    f, f_trace = log_density(
        free_bath.model(d, priors), (), {}, point | {"bath": theta}
    )
    pooled = (
        stats.norm(*priors.bath).logpdf(phi).sum()
        + stats.halfnorm(scale=priors.s_bath).logpdf(s_bath)
        + stats.norm().logpdf(u).sum()
    )
    free = stats.norm(*priors.bath).logpdf(theta).sum()
    assert float(f) - float(t) == pytest.approx(free - pooled, rel=1e-10)
    for k in ("L", "eta", "beta"):
        np.testing.assert_allclose(f_trace[k]["value"], t_trace[k]["value"], atol=1e-12)


def test_starting_steps_match_the_pooled_start():
    frame, _ = frame_of(n=3000, weeks=40, seed=7)
    d = free_bath.design(frame)
    priors = free_bath.Priors()
    t = total_walk.initial_values(d, priors, chains=4, seed=0)
    init = free_bath.initial_values(d, priors, chains=4, seed=0)
    _, steps, pools = free_bath.split_index(d.names)
    assert not {"phi", "s_bath", "bath_z"} & init.keys()
    assert init["bath"].shape == (4, len(steps))
    np.testing.assert_allclose(
        init["bath"], t["phi"][:, pools] + np.exp(t["s_bath"])[:, None] * t["bath_z"]
    )
    np.testing.assert_allclose(init["total"], t["total"])


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
            "--split", "latest", "--model", "free-bath", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "fb-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "fb-test" / "result.json").read_text())
    assert result["sampler"] == "free-bath"
    per_quantity = result["diagnostics"]["per_quantity"]
    assert "beta[bed=2:full>=2]" in per_quantity
    assert not any(k.startswith("phi") or k == "s_bath" for k in per_quantity)
    record, _ = b0.score("fb-test", "free-bath", free_bath)
    assert record["model"] == "free-bath"
    assert np.isfinite(record["elpd_loo"])
    assert {r["n"] for r in record["scorecard"]} == {1, 2, 4, 5, 7, 8, 9}

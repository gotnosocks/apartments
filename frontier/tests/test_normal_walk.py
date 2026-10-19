import json

import numpy as np
import pytest
from scipy import stats

from rentfrontier import b0, normal_walk, total_walk
from test_b0 import frame_of
from test_centered_walk import a_point

pytest.importorskip("numpyro")


def _points(seed=4):
    """A point of the total walk and the same point in the normal walk's coordinates."""
    frame, truth = frame_of(n=600, weeks=25, seed=seed)
    d = normal_walk.design(frame)
    rng = np.random.default_rng(1)
    point = a_point(d, truth, rng)
    point["main"] = point["main"][1:]
    point["total"] = np.log(2500) + np.cumsum(rng.normal(0, 0.01, d.weeks + 1))
    _, _, pools = normal_walk.split_index(d.names)
    theta = point["phi"][pools] + point["s_bath"] * point["bath_z"]
    normal = {
        k: v for k, v in point.items() if k not in ("phi", "s_bath", "bath_z", "nu_t")
    }
    return d, point, normal | {"bath": theta}


def test_differs_from_the_total_walk_in_bath_prior_and_shocks():
    """At the same bath steps and totals, the two densities differ by the independent bath
    prior against the pooled one, Normal shocks against Student-t shocks, and nu_T's prior.
    The trend, shocks and coefficients agree."""
    import jax
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    d, point, normal = _points()
    tp = total_walk.Priors()
    t, t_trace = log_density(total_walk.model(d, tp), (), {}, point)
    priors = normal_walk.Priors()
    f, f_trace = log_density(normal_walk.model(d, priors), (), {}, normal)
    step = np.diff(np.asarray(f_trace["beta"]["value"])[0] + f_trace["L"]["value"])
    g, tau, nu_t = point["g"], point["tau"], point["nu_t"]
    old = (
        stats.norm(*tp.bath).logpdf(point["phi"]).sum()
        + stats.halfnorm(scale=tp.s_bath).logpdf(point["s_bath"])
        + stats.norm().logpdf(point["bath_z"]).sum()
        + stats.t(nu_t, g, tau).logpdf(step).sum()
        + stats.gamma(tp.nu_t[0], scale=1 / tp.nu_t[1]).logpdf(nu_t)
    )
    new = (
        stats.norm(0.0, 0.5).logpdf(normal["bath"]).sum()
        + stats.norm(g, tau).logpdf(step).sum()
    )
    assert float(f) - float(t) == pytest.approx(new - old, rel=1e-10)
    for k in ("L", "eta", "beta"):
        np.testing.assert_allclose(f_trace[k]["value"], t_trace[k]["value"], atol=1e-12)


def test_walk_density_is_normal():
    """The walk term is the Normal(g, tau) log density of the level's steps, and moving tau
    changes the joint density by that term and tau's prior alone."""
    import jax
    from numpyro import handlers
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    d, _, point = _points(seed=6)
    priors = normal_walk.Priors()
    fn = normal_walk.model(d, priors)
    trace = handlers.trace(handlers.substitute(fn, data=point)).get_trace()
    M = np.asarray(trace["beta"]["value"])[0] + np.asarray(trace["L"]["value"])
    g, tau = point["g"], point["tau"]
    walk = trace["walk"]["fn"].log_factor
    assert float(walk) == pytest.approx(
        stats.norm(g, tau).logpdf(np.diff(M)).sum(), rel=1e-12
    )
    np.testing.assert_allclose(trace["eta"]["value"], np.diff(M) - g, atol=1e-12)
    rate = -np.log(priors.tau_alpha) / priors.tau_u
    a, _ = log_density(fn, (), {}, point)
    b, _ = log_density(fn, (), {}, point | {"tau": 0.004})
    change = (
        stats.norm(g, 0.004).logpdf(np.diff(M)).sum()
        - stats.norm(g, tau).logpdf(np.diff(M)).sum()
        - rate * (0.004 - tau)
    )
    assert float(b) - float(a) == pytest.approx(change, rel=1e-10)


def test_starting_steps_match_the_pooled_start():
    frame, _ = frame_of(n=3000, weeks=40, seed=7)
    d = normal_walk.design(frame)
    priors = normal_walk.Priors()
    t = total_walk.initial_values(d, total_walk.Priors(), chains=4, seed=0)
    init = normal_walk.initial_values(d, priors, chains=4, seed=0)
    _, steps, pools = normal_walk.split_index(d.names)
    assert not {"phi", "s_bath", "bath_z", "nu_t"} & init.keys()
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
            "--split", "latest", "--model", "normal-walk", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "nw-test", "--tier", "full",
        ]
    )  # fmt: skip
    result = json.loads((tmp_path / "runs" / "nw-test" / "result.json").read_text())
    assert result["sampler"] == "normal-walk"
    per_quantity = result["diagnostics"]["per_quantity"]
    assert "beta[bed=2:full>=2]" in per_quantity
    assert not any(k.startswith("phi") or k == "s_bath" for k in per_quantity)
    record, _ = b0.score("nw-test", "normal-walk", normal_walk)
    assert record["model"] == "normal-walk"
    assert np.isfinite(record["elpd_loo"])
    assert {r["n"] for r in record["scorecard"]} == set(range(1, 11))
    assert "nu_t" not in per_quantity and "nu_t" not in record["summary"]["hyper"]

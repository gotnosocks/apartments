import json

import numpy as np
import pytest

from rentfrontier import b0_3, b0_4, b0_5
from test_b0 import frame_of
from test_b0_4 import registry_of

pytest.importorskip("numpyro")


def test_design_divides_each_basis_by_its_spectral_sd():
    frame, _ = frame_of(n=2000, weeks=20, seed=3)
    d4 = b0_4.design(frame, registry=registry_of())
    d5 = b0_5.design(frame, registry=registry_of())
    assert d5.names == d4.names
    for s4, s5 in zip(d4.surfaces, d5.surfaces):
        np.testing.assert_allclose(s5["basis"] * s5["sd"], s4["basis"], rtol=1e-12)
        assert s5["sd"].shape == (s4["basis"].shape[1],)
        assert np.all(s5["sd"] > 0)
    assert b0_5.run_record(d5) == b0_4.run_record(d4)


def test_centred_surfaces_equal_b0_4s_at_matching_coefficients():
    frame, _ = frame_of(n=1000, weeks=20, seed=6)
    d4 = b0_4.design(frame, registry=registry_of())
    d5 = b0_5.design(frame, registry=registry_of())
    rng = np.random.default_rng(0)
    amp = np.array([0.3, 0.2])
    z = rng.normal(0, 1, (5, sum(len(s["sd"]) for s in d5.surfaces)))
    scale = np.concatenate([a * s["sd"] for a, s in zip(amp, d5.surfaces)])
    got = b0_5.surface_draws(d5, {"gp_w": z * scale})
    want = b0_4.surface_draws(d4, {"amp": np.broadcast_to(amp, (5, 2)), "gp_z": z})
    np.testing.assert_allclose(got, want, atol=1e-12)


def test_model_log_density_matches_b0_5_written_out():
    """The NumPyro model's joint density at a point equals the centred model written out by
    hand, up to the constant of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = b0_5.design(frame, registry=registry_of())
    priors = b0_5.Priors()
    fixed, steps, pools = b0_3.split_index(d.names)
    rng = np.random.default_rng(0)
    main = rng.normal(0, 0.1, len(fixed))
    main[0] = np.log(2500)
    phi = np.array([0.2, 0.3, 0.5, 0.6])
    bath = phi[pools] + rng.normal(0, 0.07, len(steps))
    amp = np.array([0.2, 0.15])
    sd = np.concatenate([s["sd"] for s in d.surfaces])
    scale = np.concatenate([a * s["sd"] for a, s in zip(amp, d.surfaces)])
    w = rng.normal(0, 1, len(sd)) * scale
    level = np.cumsum(0.0005 + 0.002 * rng.standard_t(2, d.weeks))
    point = {
        "main": main,
        "phi": phi,
        "s_bath": 0.07,
        "bath": bath,
        "amp": amp,
        "gp_w": w,
        "g": 0.0005,
        "tau": 0.002,
        "nu_t": 1.5,
        "nu": 5.0,
        "sigma": truth["sigma"],
        "level": level,
    }
    got, _ = log_density(b0_5.model(d, priors), (), {}, point)

    m_fix, s_fix = b0_5.prior_arrays(priors, d.names)
    beta = np.zeros(len(d.names))
    beta[fixed], beta[steps] = main, bath
    F = b0_5.surface_draws(d, {"gp_w": w})
    L = np.concatenate([[0.0], level])
    mu = d.x @ beta + F[d.site] + (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    want = (
        stats.norm.logpdf(main, m_fix, s_fix).sum()
        + stats.norm.logpdf(phi, *priors.bath).sum()
        + np.log(2) + stats.norm.logpdf(0.07, 0, priors.s_bath)
        + stats.norm.logpdf(bath, phi[pools], 0.07).sum()
        + (np.log(2) + stats.norm.logpdf(amp, 0, priors.amp)).sum()
        + stats.norm.logpdf(w, 0, scale).sum()
        + stats.norm.logpdf(0.0005, *priors.g)
        + np.log(tau_rate) - tau_rate * 0.002
        + stats.gamma.logpdf(1.5, priors.nu_t[0], scale=1 / priors.nu_t[1])
        + stats.gamma.logpdf(5.0, priors.nu[0], scale=1 / priors.nu[1])
        + (np.log(2) + stats.norm.logpdf(truth["sigma"], 0, priors.sigma)).sum()
        + stats.t.logpdf(np.diff(L), 1.5, 0.0005, 0.002).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )  # fmt: skip
    assert float(got) == pytest.approx(float(want), rel=1e-9)


def test_run_records_the_surfaces_and_scoring_refuses(tmp_path, monkeypatch):
    from rentfrontier import loo
    from rentfrontier import run as runmod

    frame, _ = frame_of(n=1500, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    registry_of().to_parquet(tmp_path / "registry.parquet")
    monkeypatch.setattr(b0_4, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(loo, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "b0.5", "--features", "b0",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "b05-test", "--tier", "full",
        ]
    )  # fmt: skip
    rdir = tmp_path / "runs" / "b05-test"
    result = json.loads((rdir / "result.json").read_text())
    assert result["sampler"] == "b0.5" and result["line"] == "baseline-blackjax"
    assert [s["name"] for s in result["surfaces"]] == ["manhattan", "brooklyn"]
    per = result["diagnostics"]["per_quantity"]
    assert "amp[0]" in per and "tau" in per
    post = np.load(rdir / "posterior.npz")
    k = sum(s["basis"] for s in result["surfaces"])
    assert post["kept/gp_w"].shape[-1] == k and post["kept/amp"].shape[-1] == 2
    assert post["kept/eta"].shape[-1] == post["kept/L"].shape[-1] - 1
    monkeypatch.setattr(loo, "git", lambda *a: "" if a[0] == "status" else "abc1234")
    monkeypatch.setattr(loo, "LOO_ROOT", tmp_path / "loo")
    with pytest.raises(SystemExit, match="B0.5"):
        loo.main(["b05-test"])


def test_prior_predictive_matches_b0_4s_surface_spread():
    frame, _ = frame_of(n=2000, weeks=40, seed=4)
    d4 = b0_4.design(frame, registry=registry_of())
    d5 = b0_5.design(frame, registry=registry_of())
    out = b0_5.prior_predictive(d5, b0_5.Priors(), draws=400, rows=1000)
    ref = b0_4.prior_predictive(d4, b0_4.Priors(), draws=400, rows=1000)
    assert set(out["surface_sd_quantiles"]) == {"manhattan", "brooklyn"}
    assert 0 < out["share_1000_30000"] <= 1
    for name in ("manhattan", "brooklyn"):
        a, b = (
            out["surface_sd_quantiles"][name]["0.5"],
            ref["surface_sd_quantiles"][name]["0.5"],
        )
        assert a == pytest.approx(b, rel=0.25)

import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import b0, b0_3, b0_4
from test_b0 import frame_of

pytest.importorskip("numpyro")


def registry_of(seed=0):
    """Buildings 0..299 of `frame_of`: 0..149 in Manhattan, 150..279 in Brooklyn, 280..289 in
    Queens, and none of 290..299 in the registry."""
    rng = np.random.default_rng(seed)
    b = np.arange(290)
    boro = np.where(b < 150, "1", np.where(b < 280, "3", "4"))
    lat = np.where(boro == "1", 40.76, np.where(boro == "3", 40.68, 40.74))
    lon = np.where(boro == "1", -73.98, np.where(boro == "3", -73.95, -73.90))
    return pd.DataFrame(
        {
            "building": b.astype(str),
            "bbl": [f"{d}00001{i:04d}" for d, i in zip(boro, b)],
            "latitude": lat + rng.normal(0, 0.012, len(b)),
            "longitude": lon + rng.normal(0, 0.012, len(b)),
        }
    )


def test_design_adds_borough_offsets_and_places_rows_on_their_surfaces():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    d = b0_4.design(frame, registry=registry_of())
    d3 = b0_3.design(frame)
    assert d.names[: len(d3.names)] == d3.names
    assert d.names[len(d3.names) :] == [
        "boro:brooklyn",
        "boro:queens",
        "boro:unlocated",
    ]
    np.testing.assert_array_equal(d.x[:, : len(d3.names)], d3.x)
    b = frame.building.astype(int).to_numpy()
    x = dict(zip(d.names, d.x.T))
    np.testing.assert_array_equal(x["boro:brooklyn"], (b >= 150) & (b < 280))
    np.testing.assert_array_equal(x["boro:queens"], (b >= 280) & (b < 290))
    np.testing.assert_array_equal(x["boro:unlocated"], b >= 290)
    man, bk = d.surfaces
    assert (man["name"], bk["name"]) == ("manhattan", "brooklyn")
    assert (man["first"], man["sites"], bk["first"]) == (0, 150, 150)
    # Rows off both surfaces point at the zero site past the last building.
    off = d.site == man["sites"] + bk["sites"]
    np.testing.assert_array_equal(off, b >= 280)
    # Each column averages zero over its borough's rows.
    for s in d.surfaces:
        on = (d.site >= s["first"]) & (d.site < s["first"] + s["sites"])
        rows = s["basis"][d.site[on] - s["first"]]
        np.testing.assert_allclose(rows.mean(0), 0, atol=1e-12)
        assert s["basis"].shape[1] == np.prod(s["waves"])
    train = b0_4.subset(d, d.week < 10)
    assert len(train.site) == len(train.y) == (d.week < 10).sum()


def test_basis_approximates_the_squared_exponential_kernel():
    rng = np.random.default_rng(1)
    x, y = rng.uniform(-3, 3, 400), rng.uniform(-1, 1, 400)
    B, shape = b0_4.basis(x, y, 0.0)
    assert shape["waves"] == [
        int(np.ceil(1.75 * b0_4.C * s / b0_4.LENGTHSCALE))
        for s in np.array(shape["half_width_km"]) / b0_4.C
    ]
    i, j = rng.integers(0, 400, (2, 2000))
    d2 = (x[i] - x[j]) ** 2 + (y[i] - y[j]) ** 2
    want = np.exp(-d2 / (2 * b0_4.LENGTHSCALE**2))
    got = np.sum(B[i] * B[j], axis=1)
    # Points away from the box's edge, where the approximation holds.
    inner = (np.abs(x[i]) < 2) & (np.abs(x[j]) < 2) & (np.abs(y[i]) < 0.5)
    inner &= np.abs(y[j]) < 0.5
    assert np.max(np.abs(got - want)[inner]) < 0.05


def test_model_log_density_matches_b0_4_written_out():
    """The NumPyro model's joint density at a point equals B0.4 written out by hand, up to
    the constant of nu_T's truncated prior."""
    import jax
    from jax.scipy import stats
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    frame, truth = frame_of(n=800, weeks=30, seed=2)
    d = b0_4.design(frame, registry=registry_of())
    priors = b0_4.Priors()
    fixed, steps, pools = b0_3.split_index(d.names)
    rng = np.random.default_rng(0)
    main = rng.normal(0, 0.1, len(fixed))
    main[0] = np.log(2500)
    phi = np.array([0.2, 0.3, 0.5, 0.6])
    u = rng.normal(0, 1, len(steps))
    z = rng.standard_t(2, d.weeks)
    amp = np.array([0.2, 0.15])
    k = sum(s["basis"].shape[1] for s in d.surfaces)
    gz = rng.normal(0, 1, k)
    point = {
        "main": main,
        "phi": phi,
        "s_bath": 0.07,
        "bath_z": u,
        "amp": amp,
        "gp_z": gz,
        "g": 0.0005,
        "tau": 0.002,
        "nu_t": 1.5,
        "nu": 5.0,
        "sigma": truth["sigma"],
        "z": z,
    }
    got, _ = log_density(b0_4.model(d, priors), (), {}, point)

    m_fix, s_fix = b0_4.prior_arrays(priors, d.names)
    assert list(m_fix[-3:]) == [0, 0, 0] and list(s_fix[-3:]) == [0.5, 0.5, 0.5]
    beta = np.zeros(len(d.names))
    beta[fixed], beta[steps] = main, phi[pools] + 0.07 * u
    F = b0_4.surface_draws(d, {"amp": amp, "gp_z": gz})
    L = np.concatenate([[0.0], np.cumsum(0.0005 + 0.002 * z)])
    mu = d.x @ beta + F[d.site] + (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    want = (
        stats.norm.logpdf(main, m_fix, s_fix).sum()
        + stats.norm.logpdf(phi, *priors.bath).sum()
        + np.log(2) + stats.norm.logpdf(0.07, 0, priors.s_bath)
        + stats.norm.logpdf(u, 0, 1).sum()
        + (np.log(2) + stats.norm.logpdf(amp, 0, priors.amp)).sum()
        + stats.norm.logpdf(gz, 0, 1).sum()
        + stats.norm.logpdf(0.0005, *priors.g)
        + np.log(tau_rate) - tau_rate * 0.002
        + stats.gamma.logpdf(1.5, priors.nu_t[0], scale=1 / priors.nu_t[1])
        + stats.gamma.logpdf(5.0, priors.nu[0], scale=1 / priors.nu[1])
        + (np.log(2) + stats.norm.logpdf(truth["sigma"], 0, priors.sigma)).sum()
        + stats.t.logpdf(z, 1.5).sum()
        + stats.t.logpdf(d.y, 5.0, mu, truth["sigma"][d.group]).sum()
    )  # fmt: skip
    assert float(got) == pytest.approx(float(want), rel=1e-9)
    assert priors.s_bath == 0.3


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
            "--split", "latest", "--model", "b0.4", "--features", "b0",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "b04-test", "--tier", "full",
        ]
    )  # fmt: skip
    rdir = tmp_path / "runs" / "b04-test"
    result = json.loads((rdir / "result.json").read_text())
    assert result["sampler"] == "b0.4" and result["line"] == "baseline-blackjax"
    assert [s["name"] for s in result["surfaces"]] == ["manhattan", "brooklyn"]
    assert result["counts"]["boro:queens"] > 0
    per = result["diagnostics"]["per_quantity"]
    assert "amp[0]" in per and "beta[boro:brooklyn]" in per
    post = np.load(rdir / "posterior.npz")
    k = sum(s["basis"] for s in result["surfaces"])
    assert post["kept/gp_z"].shape[-1] == k and post["kept/amp"].shape[-1] == 2
    monkeypatch.setattr(loo, "git", lambda *a: "" if a[0] == "status" else "abc1234")
    monkeypatch.setattr(loo, "LOO_ROOT", tmp_path / "loo")
    with pytest.raises(SystemExit, match="B0.4"):
        loo.main(["b04-test"])


def test_prior_predictive_runs_on_the_surfaces():
    frame, _ = frame_of(n=2000, weeks=40, seed=4)
    d = b0_4.design(frame, registry=registry_of())
    out = b0_4.prior_predictive(d, b0_4.Priors(), draws=20, rows=1000)
    assert set(out["surface_sd_quantiles"]) == {"manhattan", "brooklyn"}
    assert 0 < out["share_1000_30000"] <= 1

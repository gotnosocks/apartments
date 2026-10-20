import json

import numpy as np
import pytest

from rentfrontier import building_zones, building_zones_gibbs as bzg, two_zone
from rentfrontier.building_zones import site_zone, wave_matrix
from test_b0 import frame_of
from test_building_zones import _design
from test_b0_4 import registry_of
from test_whitened_zones import nj_registry_of


def _state(d, seed=0):
    """One chain's scales, drawn away from the defaults."""
    rng = np.random.default_rng(seed)
    nz = len(d.surfaces)
    return dict(
        bld_sd=rng.uniform(0.1, 0.4, nz),
        sigma=rng.uniform(0.1, 0.3, 4),
        lam=rng.gamma(3.0, 1 / 3.0, len(d.y)),
        tau=0.01,
        amp=rng.uniform(0.2, 1.0, nz),
    )


def _dense_marginal(d, priors, st):
    """The precision and linear term of theta with the levels integrated out, by building the
    joint precision of (theta, eta) row by row and taking its Schur complement densely."""
    alpha = d.names.index("alpha")
    others = [j for j in range(len(d.names)) if j != alpha]
    pb, W1 = len(others), d.weeks + 1
    Bc, sds = wave_matrix(d)
    K = len(sds)
    G = pb + W1 + 1 + K
    zone = site_zone(d)
    S = len(zone)
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    m_b, s_b, m_a, s_a = bzg._prior_vectors(d, priors)
    m_g, s_g = priors.g
    N = G + S
    J = np.zeros((N, N))
    h = np.zeros(N)
    c = st["lam"] / st["sigma"][d.group] ** 2
    for i in range(len(d.y)):
        a = np.zeros(N)
        a[:pb] = d.x[i, others]
        a[pb + d.week[i]] += 1 - d.frac[i]
        a[pb + d.week[i] + 1] += d.frac[i]
        a[G + d.site[i]] = 1
        J += c[i] * np.outer(a, a)
        h += c[i] * d.y[i] * a
    J[:pb, :pb] += np.diag(1 / s_b**2)
    h[:pb] += m_b / s_b**2
    J[pb, pb] += 1 / s_a**2
    h[pb] += m_a / s_a**2
    for k in range(W1 - 1):
        e = np.zeros(N)
        e[pb + k], e[pb + k + 1], e[pb + W1] = -1, 1, -1
        J += np.outer(e, e) / st["tau"] ** 2
    J[pb + W1, pb + W1] += 1 / s_g**2
    h[pb + W1] += m_g / s_g**2
    sw = slice(pb + W1 + 1, G)
    J[sw, sw] += np.diag(1 / (st["amp"][which] * sds) ** 2)
    # eta_s - Bc_s w ~ Normal(0, b_z)
    D = np.zeros((S, N))
    D[:, G:] = np.eye(S)
    D[:, sw] = -Bc
    J += D.T @ (D / st["bld_sd"][zone][:, None] ** 2)
    A = J[:G, :G] - J[:G, G:] @ np.linalg.solve(J[G:, G:], J[G:, :G])
    return A, h[:G] - J[:G, G:] @ np.linalg.solve(J[G:, G:], h[G:])


def test_global_system_matches_the_dense_schur_complement():
    d = _design(n=300, weeks=12, seed=4)
    priors = building_zones.Priors()
    _, _, parts = bzg.make_sampler(d, priors, bzg.Settings(site_block=7))
    st = _state(d)
    # The sampler keeps the rows sorted by building.
    A, h, _ = parts["global_system"](st | {"lam": st["lam"][parts["order"]]})
    A0, h0 = _dense_marginal(d, priors, st)
    assert np.allclose(np.asarray(A), A0, rtol=1e-7, atol=1e-6 * np.abs(A0).max())
    assert np.allclose(np.asarray(h), h0, rtol=1e-7, atol=1e-6 * np.abs(h0).max())


def _simulated(d, priors, seed=0):
    """`d` with its rows redrawn from the model at known values, and those values."""
    rng = np.random.default_rng(seed)
    Bc, sds = wave_matrix(d)
    zone = site_zone(d)
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    nz = len(d.surfaces)
    truth = dict(
        amp=np.array([0.8, 0.4, 0.5])[:nz],
        bld_sd=np.array([0.22, 0.14, 0.15])[:nz],
        sigma=np.array([0.12, 0.15, 0.18, 0.2]),
        nu=4.0,
        tau=0.006,
        g=0.0005,
    )
    w = rng.standard_normal(len(sds)) * truth["amp"][which] * sds
    lev = Bc @ w + rng.standard_normal(len(zone)) * truth["bld_sd"][zone]
    M = 8.0 + np.concatenate(
        [[0], np.cumsum(truth["g"] + truth["tau"] * rng.standard_normal(d.weeks))]
    )
    beta = np.zeros(len(d.names))
    beta[1:] = 0.1 * rng.standard_normal(len(d.names) - 1)
    beta[0] = 0
    mean = d.x @ beta + (1 - d.frac) * M[d.week] + d.frac * M[d.week + 1] + lev[d.site]
    noise = truth["sigma"][d.group] * rng.standard_t(truth["nu"], len(d.y))
    import dataclasses

    return dataclasses.replace(d, y=mean + noise), truth


def test_recovers_simulated_scales():
    frame, _ = frame_of(n=6000, weeks=40, seed=9)
    from rentfrontier import whitened_zones

    d = whitened_zones.design(
        frame, registry=registry_of(), nj_registry=nj_registry_of()
    )
    d = whitened_zones.subset(d, np.ones(len(d.y), bool))
    priors = building_zones.Priors()
    d, truth = _simulated(d, priors)
    out = bzg.run(
        d,
        priors,
        bzg.Settings(chains=2, warmup=150, draws=300, keep_every=5),
        log=lambda m: None,
    )
    tr = out["trace"]
    for k in ("nu", "tau"):
        lo, hi = np.quantile(tr[k], [0.005, 0.995])
        assert lo < truth[k] < hi, (k, lo, hi, truth[k])
    for z in range(
        1, 3
    ):  # the toy's Manhattan zone holds too few buildings to pin its spread
        lo, hi = np.quantile(tr["bld_sd"][..., z], [0.005, 0.995])
        assert lo < truth["bld_sd"][z] < hi, (z, lo, hi)
    sig = tr["sigma"].reshape(-1, 4)
    assert np.all(np.abs(np.median(sig, 0) / truth["sigma"] - 1) < 0.15)


def test_run(tmp_path, monkeypatch):
    from rentfrontier import run as runmod, whitened_zones

    frame, _ = frame_of(n=1500, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    registry_of().to_parquet(tmp_path / "registry.parquet")
    nj_registry_of().to_parquet(tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-gibbs", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzg-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzg-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-gibbs"
    assert result["sampler_settings"]["site_block"] == 16
    assert result["gibbs"]["sweeps"] == 60
    assert "min_leapfrog_steps" not in result
    assert {"bld_sd[manhattan]", "bld_sd[nj]"} <= result["diagnostics"][
        "per_quantity"
    ].keys()
    # A checkpoint after each round but the last.
    assert (out / "partial.npz").exists()
    post = np.load(out / "posterior.npz")
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    assert set(kept) == set(building_zones.KEPT)
    assert kept["beta"].shape[:2] == (2, 10)
    assert kept["bld"].dtype == np.float32
    assert kept["bld"].shape[-1] == result["buildings"]["count"]
    names = [str(n) for n in post["names"]]
    summary = building_zones.summarize(kept, names)
    share = summary["zones"]["outer"]["bld_share"]["median"]
    assert 0 < share < 1
    # The walk's levels start at zero, and its shocks are their steps less the drift.
    assert np.allclose(kept["L"][..., 0], 0)
    assert np.allclose(
        np.diff(kept["L"], axis=-1) - kept["g"][..., None], kept["eta"], atol=1e-12
    )

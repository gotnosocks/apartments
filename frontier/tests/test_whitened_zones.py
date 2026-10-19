import json

import numpy as np
import pandas as pd
import pytest

from rentfrontier import two_zone, two_zone_1k, whitened_zones
from test_b0 import frame_of
from test_b0_4 import registry_of
from test_normal_walk import _points

pytest.importorskip("numpyro")


def nj_registry_of(seed=1):
    """Buildings 290..299 of `frame_of`, the ones `registry_of` leaves out, in Hoboken and
    Jersey City."""
    rng = np.random.default_rng(seed)
    b = np.arange(290, 300)
    return pd.DataFrame(
        {
            "building": b.astype(str),
            "latitude": 40.73 + rng.normal(0, 0.01, len(b)),
            "longitude": -74.04 + rng.normal(0, 0.008, len(b)),
        }
    )


NO_NJ = pd.DataFrame({"building": [], "latitude": [], "longitude": []})


def test_design_puts_nj_buildings_on_a_third_surface():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    d = whitened_zones.design(
        frame, registry=registry_of(), nj_registry=nj_registry_of()
    )
    assert [s["name"] for s in d.surfaces] == ["manhattan", "outer", "nj"]
    manhattan, outer, nj = d.surfaces
    b = frame.building.astype(int).to_numpy()
    on_nj = d.site >= nj["first"]
    np.testing.assert_array_equal(on_nj, b >= 290)
    np.testing.assert_array_equal(d.site < outer["first"], b < 150)
    assert nj["sites"] == len(np.unique(b[b >= 290]))
    for s in d.surfaces:
        assert s["lengthscale_km"] == 1.0
        assert s["basis"].shape == (s["sites"], s["waves"][0] * s["waves"][1])


def test_nyc_surfaces_match_two_zone_1k():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    frame = frame[frame.building.astype(int) < 290].reset_index(drop=True)
    d = whitened_zones.design(frame, registry=registry_of(), nj_registry=NO_NJ)
    d1 = two_zone_1k.design(frame, registry=registry_of())
    np.testing.assert_array_equal(d.site, d1.site)
    for s, s1 in zip(d.surfaces, d1.surfaces, strict=True):
        np.testing.assert_array_equal(s["basis"], s1["basis"])
        assert s["angle"] == s1["angle"] and s["waves"] == s1["waves"]


def test_design_refuses_a_building_in_both_registries():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    nj = nj_registry_of()
    nj.loc[0, "building"] = "12"
    with pytest.raises(ValueError, match="in both registries"):
        whitened_zones.design(frame, registry=registry_of(), nj_registry=nj)


def _design(n=600, weeks=25, seed=4):
    frame, _ = frame_of(n=n, weeks=weeks, seed=seed)
    d = whitened_zones.design(
        frame, registry=registry_of(), nj_registry=nj_registry_of()
    )
    return whitened_zones.subset(d, np.ones(len(d.y), bool))


def test_whitening_turns_the_reference_precision_into_the_identity():
    """T' H T = I, with H built row by row from the centred surface each unit coefficient
    gives every building, the zones together."""
    d = _design()
    K = sum(len(s["sd"]) for s in d.surfaces)
    Bc = whitened_zones.surface_draws(d, {"gp_w": np.eye(K)}).T
    A = Bc[d.site]
    info = (whitened_zones.NU_REF + 1) / (whitened_zones.NU_REF + 3)
    sd = np.concatenate([s["sd"] for s in d.surfaces])
    H = info / whitened_zones.SIGMA_REF**2 * A.T @ A
    H += np.diag(1 / (whitened_zones.AMP_REF * sd) ** 2)
    T = whitened_zones.whitening(d)
    np.testing.assert_allclose(T.T @ H @ T, np.eye(K), atol=1e-8)


def test_whitened_coordinates_give_two_zones_density_at_w():
    """T z is the saved gp_w, and at w = T z the log density in z equals two-zone-1k's at w,
    at two different points, so the two differ by no more than a constant."""
    import jax
    from numpyro import handlers
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    _, _, point = _points()
    frame, _ = frame_of(n=600, weeks=25, seed=4)
    frame = frame[frame.building.astype(int) < 290].reset_index(drop=True)
    keep = np.ones(len(frame), bool)
    d = whitened_zones.subset(
        whitened_zones.design(frame, registry=registry_of(), nj_registry=NO_NJ), keep
    )
    d1 = two_zone_1k.subset(two_zone_1k.design(frame, registry=registry_of()), keep)
    priors = two_zone.Priors()
    T = whitened_zones.whitening(d)
    rng = np.random.default_rng(2)
    gaps = []
    for amp in (np.array([0.2, 0.1]), np.array([0.7, 1.3])):
        z = rng.normal(0, 1, len(T))
        w = T @ z
        fn = handlers.substitute(
            whitened_zones.model(d, priors), data=point | {"amp": amp, "gp_z": z}
        )
        trace = handlers.trace(handlers.seed(fn, 0)).get_trace()
        np.testing.assert_allclose(np.asarray(trace["gp_w"]["value"]), w, rtol=1e-12)
        f, _ = log_density(
            whitened_zones.model(d, priors), (), {}, point | {"amp": amp, "gp_z": z}
        )
        g, _ = log_density(
            two_zone_1k.model(d1, priors), (), {}, point | {"amp": amp, "gp_w": w}
        )
        gaps.append(float(f) - float(g))
        base = handlers.trace(
            handlers.seed(
                handlers.substitute(
                    two_zone_1k.model(d1, priors), data=point | {"amp": amp, "gp_w": w}
                ),
                0,
            )
        ).get_trace()
        np.testing.assert_allclose(
            np.asarray(trace["y"]["fn"].loc),
            np.asarray(base["y"]["fn"].loc),
            rtol=1e-12,
        )
    assert gaps[0] == pytest.approx(gaps[1], abs=1e-8)


def test_prior_predictive_reports_the_nj_gap():
    d = _design(n=2000, weeks=30, seed=8)
    out = whitened_zones.prior_predictive(d, two_zone.Priors(), draws=20, rows=500)
    assert set(out["surface_sd_quantiles"]) == {"manhattan", "outer", "nj"}
    assert "nj_over_outer_pct_quantiles" in out


def test_run(tmp_path, monkeypatch):
    from rentfrontier import run as runmod

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
            "--split", "latest", "--model", "whitened-zones", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "wz-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "wz-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "whitened-zones"
    assert [s["name"] for s in result["surfaces"]] == ["manhattan", "outer", "nj"]
    assert result["whitening"]["sigma"] == whitened_zones.SIGMA_REF
    per_quantity = result["diagnostics"]["per_quantity"]
    assert {"amp[nj]", "zone_gap", "zone_gap[nj]"} <= per_quantity.keys()
    post = np.load(out / "posterior.npz")
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    assert kept["gp_w"].shape[-1] == sum(s["basis"] for s in result["surfaces"])
    summary = whitened_zones.summarize(kept, [str(n) for n in post["names"]])
    assert np.isfinite(summary["nj_over_outer_pct"]["median"])

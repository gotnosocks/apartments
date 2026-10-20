import json

import numpy as np
import pytest

from rentfrontier import building_zones, two_zone, whitened_zones
from test_b0 import frame_of
from test_b0_4 import registry_of
from test_normal_walk import _points
from test_whitened_zones import nj_registry_of

pytest.importorskip("numpyro")


def _design(n=600, weeks=25, seed=4):
    frame, _ = frame_of(n=n, weeks=weeks, seed=seed)
    d = whitened_zones.design(
        frame, registry=registry_of(), nj_registry=nj_registry_of()
    )
    return whitened_zones.subset(d, np.ones(len(d.y), bool))


def test_whitening_turns_the_building_precision_into_the_identity():
    """T' H T = I, with H built building by building from the centred surface at the
    reference spread."""
    d = _design()
    K = sum(len(s["sd"]) for s in d.surfaces)
    Bc = whitened_zones.surface_draws(d, {"gp_w": np.eye(K)}).T
    sd = np.concatenate([s["sd"] for s in d.surfaces])
    H = Bc.T @ Bc / building_zones.BLD_SD_REF**2
    H += np.diag(1 / (whitened_zones.AMP_REF * sd) ** 2)
    T = building_zones.whitening(d)
    np.testing.assert_allclose(T.T @ H @ T, np.eye(K), atol=1e-8)


def test_scale_and_zone_follow_the_sites():
    d = _design()
    n = building_zones.site_rows(d)
    assert n.sum() == len(d.y)
    zone = building_zones.site_zone(d)
    assert len(zone) == len(n) == len(building_zones.building_offset(d))
    for k, s in enumerate(d.surfaces):
        assert (zone[s["first"] : s["first"] + s["sites"]] == k).all()
    scale = building_zones.building_scale(d)
    assert (np.diff(scale[np.argsort(n)]) <= 1e-12).all()
    assert scale.max() <= building_zones.BLD_SD_REF


def test_centred_levels_match_plain_building_effects_up_to_a_constant():
    """At the same w and building effects b, the centred model (levels eta = F + b) and the
    plain model (b sampled directly) give the same row means, and their log densities differ
    by the same amount at two different points."""
    import jax
    from numpyro import handlers
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    _, _, point = _points()
    d = _design()
    priors = two_zone.Priors()
    T_c = building_zones.whitening(d)
    T_p = whitened_zones.whitening(d)
    eta0 = building_zones.building_offset(d)
    scale = building_zones.building_scale(d)
    rng = np.random.default_rng(2)
    gaps = []
    for amp, bsd in (
        (np.array([0.2, 0.1, 0.3]), np.array([0.1, 0.2, 0.15])),
        (np.array([0.7, 1.3, 0.5]), np.array([0.4, 0.05, 0.3])),
    ):
        w = T_p @ rng.normal(0, 1, len(T_p))
        F = whitened_zones.surface_draws(d, {"gp_w": w[None]})[0]
        b = rng.normal(0, 1, len(scale)) * bsd[building_zones.site_zone(d)]
        common = point | {"amp": amp, "bld_sd": bsd}
        centred = common | {
            "gp_z": np.linalg.solve(T_c, w),
            "bld_u": (F + b - eta0) / scale,
        }
        plain = common | {"gp_z": np.linalg.solve(T_p, w), "bld_u": b / scale}
        traces = [
            handlers.trace(
                handlers.seed(handlers.substitute(m(d, priors), data=p), 0)
            ).get_trace()
            for m, p in (
                (building_zones.model, centred),
                (building_zones.plain_model, plain),
            )
        ]
        for name in ("y", "bld"):
            got, want = (
                np.asarray(t[name]["fn"].loc if name == "y" else t[name]["value"])
                for t in traces
            )
            np.testing.assert_allclose(got, want, rtol=1e-5, atol=1e-6)
        f, _ = log_density(building_zones.model(d, priors), (), {}, centred)
        g, _ = log_density(building_zones.plain_model(d, priors), (), {}, plain)
        gaps.append(float(f) - float(g))
    assert gaps[0] == pytest.approx(gaps[1], abs=1e-6)


def test_prior_predictive_reports_the_building_spread():
    d = _design(n=2000, weeks=30, seed=8)
    out = building_zones.prior_predictive(d, two_zone.Priors(), draws=20, rows=500)
    assert "bld_sd_quantiles" in out and "bld_effect_pct_quantiles" in out


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
            "--split", "latest", "--model", "building-zones", "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "bz-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bz-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones"
    assert result["buildings"]["sd_ref"] == building_zones.BLD_SD_REF
    assert {"bld_sd[manhattan]", "bld_sd[nj]"} <= result["diagnostics"][
        "per_quantity"
    ].keys()
    post = np.load(out / "posterior.npz")
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    assert kept["bld"].dtype == np.float32
    assert kept["bld"].shape[-1] == result["buildings"]["count"]
    summary = building_zones.summarize(kept, [str(n) for n in post["names"]])
    share = summary["zones"]["outer"]["bld_share"]["median"]
    assert 0 <= share <= 1
    assert building_zones.building_quantiles(kept).shape == (
        result["buildings"]["count"],
        3,
    )

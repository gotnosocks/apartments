import json
import math

import numpy as np
import pytest
from scipy import stats

from rentfrontier import normal_walk, two_zone, two_zone_1k
from test_b0 import frame_of
from test_b0_4 import registry_of
from test_normal_walk import _points

pytest.importorskip("numpyro")


def located(n=3000, weeks=20, seed=3):
    """Rows of `frame_of` whose buildings `registry_of` places."""
    frame, truth = frame_of(n=n, weeks=weeks, seed=seed)
    frame = frame[frame.building.astype(int) < 290].reset_index(drop=True)
    return frame, truth


def test_rotation_turns_a_tilted_strip_onto_the_axes():
    rng = np.random.default_rng(0)
    t = math.radians(30)
    a, b = rng.uniform(-6, 6, 4000), rng.uniform(-1, 1, 4000)
    x, y = a * math.cos(t) - b * math.sin(t), a * math.sin(t) + b * math.cos(t)
    assert two_zone.rotation(x, y) == pytest.approx(60.0, abs=1.0)


def test_design_places_manhattan_and_the_rest_on_two_surfaces():
    frame, _ = located()
    d = two_zone.design(frame, registry=registry_of())
    d3 = normal_walk.design(frame)
    assert d.names == d3.names
    np.testing.assert_array_equal(d.x, d3.x)
    assert [s["name"] for s in d.surfaces] == ["manhattan", "outer"]
    manhattan, outer = d.surfaces
    assert outer["first"] == manhattan["sites"]
    b = frame.building.astype(int).to_numpy()
    on_manhattan = d.site < outer["first"]
    np.testing.assert_array_equal(on_manhattan, b < 150)
    # Queens buildings 280..289 share the outer surface with Brooklyn.
    assert outer["sites"] == len(np.unique(b[b >= 150]))
    for s in d.surfaces:
        assert 0 <= s["angle"] < 90
        assert s["basis"].shape == (s["sites"], s["waves"][0] * s["waves"][1])
        assert len(s["sd"]) == s["basis"].shape[1]
    assert two_zone.site_share(d).sum() == pytest.approx(1.0)


def test_design_refuses_unlocated_buildings():
    frame, _ = frame_of(n=3000, weeks=20, seed=3)
    with pytest.raises(ValueError, match="no registry point"):
        two_zone.design(frame, registry=registry_of())


def test_flat_surfaces_reduce_to_the_normal_walk():
    """With every coefficient at zero the density is the normal walk's plus the amplitudes'
    HalfNormal prior and the coefficients' Normal prior at zero; with coefficients set, each
    row's mean moves by its building's centred surface value."""
    import jax
    from numpyro import handlers
    from numpyro.infer.util import log_density

    jax.config.update("jax_enable_x64", True)
    _, _, point = _points()
    frame, _ = frame_of(n=600, weeks=25, seed=4)
    keep = frame.building.astype(int).to_numpy() < 290
    d = two_zone.subset(
        two_zone.design(frame[keep].reset_index(drop=True), registry=registry_of()),
        np.ones(keep.sum(), bool),
    )
    dn = normal_walk.design(frame[keep].reset_index(drop=True))
    priors = two_zone.Priors()
    amp = np.array([0.2, 0.1])
    k = [len(s["sd"]) for s in d.surfaces]
    zero = point | {"amp": amp, "gp_w": np.zeros(sum(k))}
    f, _ = log_density(two_zone.model(d, priors), (), {}, zero)
    n, _ = log_density(normal_walk.model(dn, normal_walk.Priors()), (), {}, point)
    sd = np.concatenate([a * s["sd"] for a, s in zip(amp, d.surfaces)])
    extra = (
        stats.halfnorm(scale=priors.amp).logpdf(amp).sum()
        + stats.norm(0, sd).logpdf(0).sum()
    )
    assert float(f) - float(n) == pytest.approx(extra, rel=1e-10)

    rng = np.random.default_rng(2)
    w = rng.normal(0, 0.05, sum(k))
    fn = handlers.substitute(two_zone.model(d, priors), data=zero | {"gp_w": w})
    trace = handlers.trace(handlers.seed(fn, 0)).get_trace()
    F = two_zone.surface_draws(d, {"gp_w": w})
    share = two_zone.site_share(d)
    assert share @ F == pytest.approx(0.0, abs=1e-12)
    levels = np.asarray(trace["zone_level"]["value"])
    first = d.surfaces[1]["first"]
    assert levels[0] == pytest.approx(
        share[:first] @ F[:first] / share[:first].sum(), rel=1e-10
    )
    plain = handlers.substitute(two_zone.model(d, priors), data=zero)
    base = handlers.trace(handlers.seed(plain, 0)).get_trace()
    np.testing.assert_allclose(
        np.asarray(trace["y"]["fn"].loc) - np.asarray(base["y"]["fn"].loc),
        F[d.site],
        atol=1e-12,
    )


def test_prior_predictive_runs():
    frame, _ = located(n=2000, weeks=30, seed=8)
    d = two_zone.design(frame, registry=registry_of())
    out = two_zone.prior_predictive(d, two_zone.Priors(), draws=20, rows=500)
    assert set(out["surface_sd_quantiles"]) == {"manhattan", "outer"}
    assert "manhattan_over_outer_pct_quantiles" in out
    assert 0 < out["share_1000_30000"] <= 1


def test_1k_halves_the_waves_and_keeps_the_boxes():
    frame, _ = located()
    d5 = two_zone.design(frame, registry=registry_of())
    d1 = two_zone_1k.design(frame, registry=registry_of())
    for s5, s1 in zip(d5.surfaces, d1.surfaces):
        assert s1["angle"] == s5["angle"]
        assert s1["half_width_km"] == s5["half_width_km"]
        for m5, m1, L in zip(s5["waves"], s1["waves"], s1["half_width_km"]):
            assert m1 == math.ceil(1.75 * L / 1.0)
            assert m1 <= (m5 + 1) // 2 + 1
        assert s1["lengthscale_km"] == 1.0 and s5["lengthscale_km"] == 0.5
        # The first wave's spectral sd at unit amplitude: sqrt(2 pi l^2 exp(-l^2 w^2 / 2)).
        L1, L2 = s1["half_width_km"]
        w2 = (math.pi / (2 * L1)) ** 2 + (math.pi / (2 * L2)) ** 2
        assert s1["sd"][0] == pytest.approx(math.sqrt(2 * math.pi * math.exp(-w2 / 2)))
    assert two_zone_1k.run_record(d1)["lengthscale_km"] == 1.0


@pytest.mark.parametrize("name", ["two-zone", "two-zone-1k"])
def test_run(tmp_path, monkeypatch, name):
    from rentfrontier import run as runmod

    frame, _ = located(n=1500, weeks=60, seed=5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    registry_of().to_parquet(tmp_path / "registry.parquet")
    monkeypatch.setattr(two_zone, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", name, "--features", "base-v1",
            "--chains", "4", "--warmup", "60", "--draws", "40", "--keep-every", "2",
            "--max-leapfrog-steps", "20", "--name", "tz-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "tz-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == name
    assert [s["name"] for s in result["surfaces"]] == ["manhattan", "outer"]
    per_quantity = result["diagnostics"]["per_quantity"]
    assert {"amp[manhattan]", "amp[outer]", "zone_gap"} <= per_quantity.keys()
    post = np.load(out / "posterior.npz")
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    summary = two_zone.summarize(kept, [str(n) for n in post["names"]])
    assert set(summary["zones"]) == {"manhattan", "outer"}
    assert np.isfinite(summary["manhattan_over_outer_pct"]["median"])

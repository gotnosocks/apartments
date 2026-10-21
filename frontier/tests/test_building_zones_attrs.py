import dataclasses
import json

import numpy as np
import pandas as pd

from rentfrontier import building_zones, building_zones_attrs as bza
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier.building_zones import site_zone, wave_matrix
from test_b0 import frame_of
from test_b0_4 import registry_of
from test_whitened_zones import NO_NJ

TRUTH = {
    "bld:log_height": 0.09,
    "bld:height_unknown": -0.04,
    "bld:elevator": 0.07,
    "bld:elevator_unknown": 0.02,
    "bld:condo": 0.05,
    "bld:doorman_full": 0.06,
    "bld:doorman_part": 0.03,
    "bld:doorman_virtual": -0.02,
}


def registry_with_bins(n=290, seed=0):
    """`registry_of`, every NYC building with a BIN, ten of them placeholders."""
    reg = registry_of(seed)
    b = reg.building.astype(int).to_numpy()
    boro = reg.bbl.str[0].to_numpy()
    reg["bin"] = [f"{d}{100000 + i:06d}" for d, i in zip(boro, b)]
    reg.loc[b % 29 == 3, "bin"] = [f"{d}000000" for d in boro[b % 29 == 3]]
    return reg


def tables_of(registry, seed=2):
    """A footprint height for most BINs and a building-attrs row for every building."""
    rng = np.random.default_rng(seed)
    bins = registry.bin[~registry.bin.str.fullmatch(r"[1-5]000000")]
    bins = bins[rng.random(len(bins)) < 0.92]
    footprints = pd.DataFrame(
        {
            "bin": bins.to_numpy(),
            "height_roof": (78 * np.exp(0.8 * rng.standard_normal(len(bins))))
            .round(1)
            .astype(str),
        }
    )
    b = registry.building.to_numpy()
    attrs = pd.DataFrame(
        {
            "building": b,
            "elevator": rng.choice(["yes", "no", "unknown"], len(b), p=[0.5, 0.4, 0.1]),
            "doorman": rng.choice(
                ["none", "full", "part", "virtual"], len(b), p=[0.4, 0.2, 0.2, 0.2]
            ),
            "tenure": rng.choice(
                ["rental", "condo", "coop"], len(b), p=[0.7, 0.2, 0.1]
            ),
        }
    )
    return footprints, attrs


def _nyc_frame(n, weeks, seed):
    frame, _ = frame_of(n=n, weeks=weeks, seed=seed)
    return frame[frame.building.astype(int) < 290].reset_index(drop=True)


def test_columns_code_heights_and_attributes():
    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    frame = _nyc_frame(2000, 20, 3)
    d = bza.design(
        frame, registry=reg, nj_registry=NO_NJ, attrs=attrs, footprints=footprints
    )
    assert d.names[-8:] == list(bza.COLUMNS)
    x = pd.DataFrame(d.x[:, -8:], columns=bza.COLUMNS)
    heights = bza.roof_heights(reg, footprints)
    h = frame.building.map(heights)
    # Placeholder BINs and BINs with no footprint have no height.
    placeholder = frame.building.map(reg.set_index("building").bin).str.endswith(
        "000000"
    )
    assert h[placeholder.to_numpy()].isna().all()
    unknown = h.isna().to_numpy()
    np.testing.assert_array_equal(x["bld:height_unknown"], unknown)
    np.testing.assert_allclose(
        x["bld:log_height"][~unknown], np.log(h[~unknown] / bza.HEIGHT_REF)
    )
    assert (x["bld:log_height"][unknown] == 0).all()
    a = attrs.set_index("building").reindex(frame.building)
    np.testing.assert_array_equal(x["bld:elevator"], a.elevator.eq("yes"))
    np.testing.assert_array_equal(x["bld:condo"], a.tenure.eq("condo"))
    np.testing.assert_array_equal(x["bld:doorman_part"], a.doorman.eq("part"))
    # Two zones without NJ.
    assert [s["name"] for s in d.surfaces] == ["manhattan", "outer"]


def _simulated(d, seed=0):
    """`d` with its rows redrawn from the model with the building coefficients at TRUTH."""
    rng = np.random.default_rng(seed)
    Bc, sds = wave_matrix(d)
    zone = site_zone(d)
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    amp, bld_sd = np.array([0.8, 0.4]), np.array([0.10, 0.08])
    sigma, nu = np.array([0.12, 0.15, 0.18, 0.2]), 4.0
    w = rng.standard_normal(len(sds)) * amp[which] * sds
    lev = Bc @ w + rng.standard_normal(len(zone)) * bld_sd[zone]
    M = 8.0 + np.concatenate(
        [[0], np.cumsum(0.0005 + 0.006 * rng.standard_normal(d.weeks))]
    )
    beta = np.zeros(len(d.names))
    beta[1:] = 0.1 * rng.standard_normal(len(d.names) - 1)
    for n, v in TRUTH.items():
        beta[d.names.index(n)] = v
    mean = d.x @ beta + (1 - d.frac) * M[d.week] + d.frac * M[d.week + 1] + lev[d.site]
    noise = sigma[d.group] * rng.standard_t(nu, len(d.y))
    return dataclasses.replace(d, y=mean + noise)


def test_recovers_simulated_building_coefficients():
    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    frame = _nyc_frame(8000, 30, 9)
    d = bza.design(
        frame, registry=reg, nj_registry=NO_NJ, attrs=attrs, footprints=footprints
    )
    d = bza.subset(d, np.ones(len(d.y), bool))
    d = _simulated(d)
    out = bza.run(
        d,
        building_zones.Priors(),
        bzg.Settings(chains=2, warmup=100, draws=300, keep_every=5),
        log=lambda m: None,
    )
    beta = out["trace"]["beta"].reshape(-1, len(d.names))
    for n, v in TRUTH.items():
        lo, hi = np.quantile(beta[:, d.names.index(n)], [0.001, 0.999])
        assert lo < v < hi, (n, lo, hi, v)
        # The toy's 290 buildings pin each coefficient to within a few hundredths.
        assert hi - lo < 0.2, (n, lo, hi)


def test_run(tmp_path, monkeypatch):
    from rentfrontier import building_attrs, run as runmod, whitened_zones

    frame = _nyc_frame(1500, 60, 5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    reg.to_parquet(tmp_path / "registry.parquet")
    NO_NJ.to_parquet(tmp_path / "registry-nj.parquet")
    footprints.to_parquet(tmp_path / "footprints.parquet")
    attrs.to_parquet(tmp_path / "attrs.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-attrs", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bza-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bza-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-attrs"
    assert result["height_ref_ft"] == bza.HEIGHT_REF
    assert "beta[bld:elevator]" in result["diagnostics"]["per_quantity"]
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert names[-8:] == list(bza.COLUMNS)
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    summary = bza.summarize(kept, names)
    assert set(summary["building"]) == set(bza.COLUMNS)
    assert "outer" in summary["zones"] and "nj" not in summary["zones"]


def test_500m_rebuilds_the_surfaces_with_the_same_buildings():
    from rentfrontier import building_zones_attrs_500m as bza500

    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    frame = _nyc_frame(2000, 20, 3)
    tables = dict(registry=reg, nj_registry=NO_NJ, attrs=attrs, footprints=footprints)
    d1 = bza.design(frame, **tables)
    d5 = bza500.design(frame, **tables)
    np.testing.assert_array_equal(d1.site, d5.site)
    np.testing.assert_array_equal(d1.x, d5.x)
    for s1, s5 in zip(d1.surfaces, d5.surfaces):
        assert (s1["first"], s1["sites"]) == (s5["first"], s5["sites"])
        assert s5["lengthscale_km"] == 0.5
        assert len(s5["sd"]) > 2 * len(s1["sd"])

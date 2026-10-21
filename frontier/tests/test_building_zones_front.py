import numpy as np
import pandas as pd

import test_building_zones_attrs as tba
from rentfrontier import building_zones, building_zones_attrs as bza
from rentfrontier import building_zones_front as bzf
from rentfrontier import building_zones_gibbs as bzg
from test_building_zones_attrs import _nyc_frame, registry_with_bins, tables_of
from test_whitened_zones import NO_NJ

TRUTH = tba.TRUTH | {
    "bld:front_41_60": -0.03,
    "bld:front_61_80": 0.04,
    "bld:front_over_80": 0.08,
    "bld:front_unknown": -0.02,
    "bld:corner": 0.03,
    "bld:corner_unknown": 0.01,
}


def frontage_of(registry, seed=4):
    """A frontage row for every building, a few with unknown width or corner."""
    rng = np.random.default_rng(seed)
    b = registry.building.drop_duplicates().to_numpy()
    return pd.DataFrame(
        {
            "building": b,
            "front_width_ft": rng.choice([30.0, 34.0, 50.0, 60.0, 70.0, 100.0, np.nan], len(b)),
            "corner": rng.choice([0.0, 1.0, np.nan], len(b), p=[0.65, 0.3, 0.05]),
        }
    )  # fmt: skip


def _design(n=2000, weeks=20, seed=3):
    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    frame = _nyc_frame(n, weeks, seed)
    tables = dict(registry=reg, nj_registry=NO_NJ, attrs=attrs, footprints=footprints)
    return frame, tables, frontage_of(reg)


def test_columns_code_bands_and_corners():
    frame, tables, front = _design()
    d = bzf.design(frame, frontage=front, **tables)
    base = bza.design(frame, **tables)
    assert d.names == base.names + list(bzf.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : base.x.shape[1]], base.x)
    x = pd.DataFrame(d.x[:, -6:], columns=bzf.COLUMNS)
    f = front.set_index("building").reindex(frame.building.astype(str))
    w, c = f.front_width_ft.to_numpy(), f.corner.to_numpy()
    np.testing.assert_array_equal(x["bld:front_41_60"], (w == 50) | (w == 60))
    np.testing.assert_array_equal(x["bld:front_61_80"], w == 70)
    np.testing.assert_array_equal(x["bld:front_over_80"], w == 100)
    np.testing.assert_array_equal(x["bld:front_unknown"], np.isnan(w))
    np.testing.assert_array_equal(x["bld:corner"], c == 1)
    np.testing.assert_array_equal(x["bld:corner_unknown"], np.isnan(c))
    assert all(d.count[n] == x[n].sum() for n in bzf.COLUMNS)


def test_recovers_simulated_frontage_coefficients(monkeypatch):
    frame, tables, front = _design(8000, 30, 9)
    d = bzf.design(frame, frontage=front, **tables)
    d = bzf.subset(d, np.ones(len(d.y), bool))
    monkeypatch.setattr(tba, "TRUTH", TRUTH)
    d = tba._simulated(d)
    out = bzf.run(
        d,
        building_zones.Priors(),
        bzg.Settings(chains=2, warmup=100, draws=300, keep_every=5),
        log=lambda m: None,
    )
    beta = out["trace"]["beta"].reshape(-1, len(d.names))
    for n, v in TRUTH.items():
        lo, hi = np.quantile(beta[:, d.names.index(n)], [0.001, 0.999])
        assert lo < v < hi, (n, lo, hi, v)


def test_run(tmp_path, monkeypatch):
    import json

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
    frontage_of(reg).to_parquet(tmp_path / "frontage.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setattr(bzf, "FRONTAGE", tmp_path / "frontage.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-front", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzf-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzf-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-front"
    assert result["frontage"] == str(tmp_path / "frontage.parquet")
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert names[-6:] == list(bzf.COLUMNS)
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    assert set(bzf.COLUMNS) <= set(bzf.summarize(kept, names)["building"])

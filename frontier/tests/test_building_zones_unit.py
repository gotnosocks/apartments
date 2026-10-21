import numpy as np
import pandas as pd

import test_building_zones_attrs as tba
from rentfrontier import building_zones, building_zones_attrs as bza
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier import building_zones_unit as bzu
from test_building_zones_attrs import _nyc_frame, registry_with_bins, tables_of
from test_whitened_zones import NO_NJ

TRUTH = tba.TRUTH | {
    "unit:log_size_rel": 0.45,
    "unit:size_imputed": -0.02,
    "unit:size_unknown": -0.05,
    "unit:laundry_in_unit": 0.08,
    "unit:laundry_in_building": -0.03,
    "unit:dishwasher": 0.04,
    "bld:truck_through": -0.03,
}


def tables_for(frame, seed=4):
    """A unit-features row for most listings and a truck row for every building."""
    rng = np.random.default_rng(seed)
    ids = frame.listing_id.astype(str).drop_duplicates().to_numpy()
    ids = ids[rng.random(len(ids)) < 0.9]
    source = rng.choice(
        ["stated", "unit", "line", "none"], len(ids), p=[0.3, 0.15, 0.1, 0.45]
    )
    units = pd.DataFrame(
        {
            "listing_id": ids,
            "size_source": source,
            "log_size_rel": np.where(source == "none", 0.0, rng.normal(0, 0.25, len(ids))),
            "laundry": rng.choice(["in_unit", "in_building", "unstated"], len(ids)),
            "dishwasher": (rng.random(len(ids)) < 0.5).astype(float),
        }
    )  # fmt: skip
    b = frame.building.astype(str).drop_duplicates().to_numpy()
    trucks = pd.DataFrame(
        {"building": b, "truck_through": (rng.random(len(b)) < 0.2).astype(float)}
    )
    return units, trucks


def _design(n=2000, weeks=20, seed=3):
    reg = registry_with_bins()
    footprints, attrs = tables_of(reg)
    frame = _nyc_frame(n, weeks, seed)
    units, trucks = tables_for(frame)
    tables = dict(registry=reg, nj_registry=NO_NJ, attrs=attrs, footprints=footprints)
    return frame, tables, units, trucks


def test_columns_code_size_laundry_dishwasher_and_trucks():
    frame, tables, units, trucks = _design()
    d = bzu.design(frame, units=units, trucks=trucks, **tables)
    base = bza.design(frame, **tables)
    assert d.names == base.names + list(bzu.COLUMNS)
    assert not any(n.startswith("bld:front") or "corner" in n for n in d.names)
    np.testing.assert_array_equal(d.x[:, : base.x.shape[1]], base.x)
    x = pd.DataFrame(d.x[:, -7:], columns=bzu.COLUMNS)
    u = units.set_index("listing_id").reindex(frame.listing_id.astype(str))
    src = u.size_source.fillna("none").to_numpy()
    lau = u.laundry.fillna("unstated").to_numpy()
    np.testing.assert_allclose(
        x["unit:log_size_rel"], np.where(src == "none", 0, u.log_size_rel.fillna(0))
    )
    np.testing.assert_array_equal(
        x["unit:size_imputed"], np.isin(src, ["unit", "line"])
    )
    np.testing.assert_array_equal(x["unit:size_unknown"], src == "none")
    np.testing.assert_array_equal(x["unit:laundry_in_unit"], lau == "in_unit")
    np.testing.assert_array_equal(x["unit:laundry_in_building"], lau == "in_building")
    np.testing.assert_array_equal(x["unit:dishwasher"], u.dishwasher.fillna(0) == 1)
    t = frame.building.astype(str).map(trucks.set_index("building").truck_through)
    np.testing.assert_array_equal(x["bld:truck_through"], t == 1)
    assert all(d.count[n] == (x[n] != 0).sum() for n in bzu.COLUMNS)


def test_recovers_simulated_unit_coefficients(monkeypatch):
    frame, tables, units, trucks = _design(8000, 30, 9)
    d = bzu.design(frame, units=units, trucks=trucks, **tables)
    d = bzu.subset(d, np.ones(len(d.y), bool))
    monkeypatch.setattr(tba, "TRUTH", TRUTH)
    d = tba._simulated(d)
    out = bzu.run(
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
    snap = tmp_path / "unit-features"
    snap.mkdir()
    units, trucks = tables_for(frame)
    units.to_parquet(snap / "unit_features.parquet")
    trucks.to_parquet(snap / "truck.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setattr(bzu, "SNAPSHOT", snap)
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-unit", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzu-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzu-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-unit"
    assert result["unit_features"] == str(snap)
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert names[-7:] == list(bzu.COLUMNS)
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    s = bzu.summarize(kept, names)
    assert "bld:truck_through" in s["building"]
    assert set(n for n in bzu.COLUMNS if n.startswith("unit:")) <= set(s["unit"])

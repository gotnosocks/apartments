import json

import numpy as np
import pandas as pd

import test_building_zones_attrs as tba
import test_building_zones_gym as tby
import test_building_zones_unit as tbu
from rentfrontier import building_age, building_zones
from rentfrontier import building_zones_age as bzs
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier import building_zones_gym as bzy
from rentfrontier import building_zones_unit as bzu

TRUTH = tbu.TRUTH | {
    "bld:gym": 0.05,
    "bld:built_pre1900": -0.03,
    "bld:built_1940_1979": -0.02,
    "bld:built_1980_1999": 0.02,
    "bld:built_2000_2009": 0.04,
    "bld:built_2010_on": 0.08,
    "bld:altered_2000_on": 0.03,
    "bld:retail": -0.02,
}


def ages_for(frame, seed=8):
    """An age row for most buildings, with a few unknown years and retail areas."""
    rng = np.random.default_rng(seed)
    b = frame.building.astype(str).drop_duplicates().to_numpy()
    b = b[rng.random(len(b)) < 0.95]
    n = len(b)
    year = rng.choice([1880, 1920, 1960, 1990, 2005, 2015, np.nan], n)
    alter = np.where(rng.random(n) < 0.3, rng.integers(1990, 2030, n), np.nan)
    unknown = rng.random(n) < 0.05
    return pd.DataFrame(
        {
            "building": b,
            "year_built": year,
            "alter1": alter,
            "alter2": np.where(rng.random(n) < 0.1, 2001.0, np.nan),
            "retail": np.where(unknown, 0.0, rng.random(n) < 0.4),
            "retail_unknown": unknown * 1.0,
        }
    )


def test_building_table_reads_years_and_retail():
    attrs = pd.DataFrame(
        {
            "building": ["a", "b", "c", "d"],
            "year_built": [1920.0, np.nan, 2012.0, 1900.0],
        }
    )
    registry = pd.DataFrame(
        {"building": ["a", "b", "c", "d"], "bbl": ["1", "2", "3", None]}
    )
    pluto = pd.DataFrame(
        {
            "bbl": ["1", "2", "3"],
            "yearalter1": ["2005", "0", "1995"],
            "yearalter2": ["0", "0", "2015"],
            "retailarea": ["1200", None, "0"],
            "comarea": ["1200", "300", "500"],
        }
    )
    t = building_age.building_table(attrs, registry, pluto).set_index("building")
    assert t.alter1["a"] == 2005 and t.alter1["c"] == 1995
    assert np.isnan(t.alter1["b"]) and np.isnan(t.alter1["d"])
    assert np.isnan(t.alter2["a"]) and t.alter2["c"] == 2015
    assert t.retail.to_dict() == {"a": 1.0, "b": 1.0, "c": 0.0, "d": 0.0}
    assert t.retail_unknown.to_dict() == {"a": 0.0, "b": 0.0, "c": 0.0, "d": 1.0}
    assert np.isnan(t.year_built["b"]) and t.year_built["c"] == 2012


def test_design_keeps_trucks_and_adds_gym_age_and_retail():
    frame, tables, units, trucks = tbu._design()
    gyms, ages = tby.gyms_for(frame), ages_for(frame)
    d = bzs.design(frame, units=units, trucks=trucks, gyms=gyms, ages=ages, **tables)
    u = bzu.design(frame, units=units, trucks=trucks, **tables)
    assert d.names == u.names + list(bzs.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : u.x.shape[1]], u.x)
    x = pd.DataFrame(d.x[:, u.x.shape[1] :], columns=bzs.COLUMNS)
    b = frame.building.astype(str)
    g = b.map(gyms.set_index("building").gym).fillna(0)
    np.testing.assert_array_equal(x["bld:gym"], g == 1)
    a = ages.set_index("building").reindex(b)
    y = a.year_built.to_numpy()
    np.testing.assert_array_equal(x["bld:built_pre1900"], y < 1900)
    np.testing.assert_array_equal(x["bld:built_1940_1979"], (y >= 1940) & (y < 1980))
    np.testing.assert_array_equal(x["bld:built_2010_on"], y >= 2010)
    np.testing.assert_array_equal(x["bld:built_unknown"], np.isnan(y))
    ad = pd.to_datetime(frame.price_at).dt.year.to_numpy()
    alt = [a[c].to_numpy() for c in ("alter1", "alter2")]
    np.testing.assert_array_equal(
        x["bld:altered_2000_on"],
        np.any([(v >= 2000) & (v <= ad) for v in alt], axis=0),
    )
    np.testing.assert_array_equal(x["bld:retail"], a.retail.fillna(0).to_numpy() == 1)
    np.testing.assert_array_equal(
        x["bld:retail_unknown"], a.retail_unknown.fillna(1).to_numpy() == 1
    )
    assert all(d.count[n] == (x[n] != 0).sum() for n in bzs.COLUMNS)


def test_recovers_simulated_age_coefficients(monkeypatch):
    frame, tables, units, trucks = tbu._design(8000, 30, 9)
    d = bzs.design(
        frame,
        units=units,
        trucks=trucks,
        gyms=tby.gyms_for(frame),
        ages=ages_for(frame),
        **tables,
    )
    d = bzs.subset(d, np.ones(len(d.y), bool))
    monkeypatch.setattr(tba, "TRUTH", TRUTH)
    d = tba._simulated(d)
    out = bzs.run(
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
    from rentfrontier import building_attrs, run as runmod, whitened_zones
    from rentfrontier import building_zones_attrs as bza

    frame = tba._nyc_frame(1500, 60, 5)
    dataset = tmp_path / "b0-data"
    dataset.mkdir()
    frame.to_parquet(dataset / "rows.parquet")
    (dataset / "manifest.json").write_text(json.dumps({"rows_sha256": "x"}))
    reg = tba.registry_with_bins()
    footprints, attrs = tba.tables_of(reg)
    reg.to_parquet(tmp_path / "registry.parquet")
    tbu.NO_NJ.to_parquet(tmp_path / "registry-nj.parquet")
    footprints.to_parquet(tmp_path / "footprints.parquet")
    attrs.to_parquet(tmp_path / "attrs.parquet")
    snap = tmp_path / "unit-features"
    snap.mkdir()
    units, trucks = tbu.tables_for(frame)
    units.to_parquet(snap / "unit_features.parquet")
    trucks.to_parquet(snap / "truck.parquet")
    gsnap = tmp_path / "building-gym"
    gsnap.mkdir()
    tby.gyms_for(frame).to_parquet(gsnap / "gym.parquet")
    asnap = tmp_path / "building-age"
    asnap.mkdir()
    ages_for(frame).to_parquet(asnap / "age.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setattr(bzu, "SNAPSHOT", snap)
    monkeypatch.setattr(bzy, "GYM_SNAPSHOT", gsnap)
    monkeypatch.setattr(bzs, "GYM_SNAPSHOT", gsnap)
    monkeypatch.setattr(bzs, "AGE_SNAPSHOT", asnap)
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-age", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzs-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzs-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-age"
    assert result["building_age"] == str(asnap)
    assert result["building_gym"] == str(gsnap)
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert names[-len(bzs.COLUMNS) :] == list(bzs.COLUMNS)
    assert "bld:truck_through" in names
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    s = bzs.summarize(kept, names)
    assert "bld:built_2010_on" in s["building"]

import json

import numpy as np
import pandas as pd

import test_building_zones_attrs as tba
import test_building_zones_unit as tbu
from rentfrontier import building_gym, building_zones
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier import building_zones_gym as bzy
from rentfrontier import building_zones_unit as bzu

TRUTH = {k: v for k, v in tbu.TRUTH.items() if k != "bld:truck_through"} | {
    "bld:gym": 0.05
}


def gyms_for(frame, seed=6):
    """A gym row for most buildings, about a third of them with a gym."""
    rng = np.random.default_rng(seed)
    b = frame.building.astype(str).drop_duplicates().to_numpy()
    b = b[rng.random(len(b)) < 0.9]
    return pd.DataFrame({"building": b, "gym": (rng.random(len(b)) < 0.35) * 1.0})


def test_building_table_takes_the_majority_of_stating_listings():
    rows = pd.DataFrame(
        {
            "listing_id": [1, 2, 3, 4, 5, 6, 7, 7],
            "building": ["a", "a", "a", "b", "b", "c", "d", "d"],
        }
    )
    listing = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5", "6"],
            "states": [True, True, False, True, True, False],
            "gym": [True, False, False, False, False, False],
        }
    )
    t = building_gym.building_table(rows, listing).set_index("building")
    assert t.listings.to_dict() == {"a": 3, "b": 2, "c": 1, "d": 1}
    assert t.stating.to_dict() == {"a": 2, "b": 2, "c": 0, "d": 0}
    assert t.gym.to_dict() == {"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0}
    assert t.gym_unknown.to_dict() == {"a": 0.0, "b": 0.0, "c": 1.0, "d": 1.0}
    assert t.gym_share["a"] == 0.5 and np.isnan(t.gym_share["c"])


def test_design_drops_trucks_and_adds_gym():
    frame, tables, units, trucks = tbu._design()
    gyms = gyms_for(frame)
    d = bzy.design(frame, units=units, trucks=trucks, gyms=gyms, **tables)
    u = bzu.design(frame, units=units, trucks=trucks, **tables)
    assert d.names == [n for n in u.names if n != "bld:truck_through"] + ["bld:gym"]
    np.testing.assert_array_equal(d.x[:, :-1], u.x[:, :-1])
    g = frame.building.astype(str).map(gyms.set_index("building").gym).fillna(0)
    np.testing.assert_array_equal(d.x[:, -1], g == 1)
    assert "bld:truck_through" not in d.count
    assert d.count["bld:gym"] == (g == 1).sum()


def test_recovers_simulated_gym_coefficient(monkeypatch):
    frame, tables, units, trucks = tbu._design(8000, 30, 9)
    d = bzy.design(frame, units=units, trucks=trucks, gyms=gyms_for(frame), **tables)
    d = bzy.subset(d, np.ones(len(d.y), bool))
    monkeypatch.setattr(tba, "TRUTH", TRUTH)
    d = tba._simulated(d)
    out = bzy.run(
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
    gyms_for(frame).to_parquet(gsnap / "gym.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setattr(bzu, "SNAPSHOT", snap)
    monkeypatch.setattr(bzy, "GYM_SNAPSHOT", gsnap)
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", "building-zones-gym", "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzy-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzy-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == "building-zones-gym"
    assert result["building_gym"] == str(gsnap)
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert names[-1] == "bld:gym" and "bld:truck_through" not in names
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    s = bzy.summarize(kept, names)
    assert "bld:gym" in s["building"]

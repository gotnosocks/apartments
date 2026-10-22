import json

import numpy as np
import pandas as pd
import pytest

import test_building_zones_age as tbs
import test_building_zones_attrs as tba
import test_building_zones_gym as tby
import test_building_zones_unit as tbu
from rentfrontier import building_zones
from rentfrontier import building_zones_age as bzs
from rentfrontier import building_zones_floor as bzf
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier import unit_floor

# A curve rising with log floor in elevator buildings and falling with each flight of stairs
# in walk-ups, and the flags.
ELEV = {f"unit:elev_f{k}": 0.04 * np.log(k) for k in range(2, bzf.ELEV_CAP + 1)}
WALKUP = {f"unit:walkup_f{k}": -0.02 * (k - 1) for k in range(2, bzf.WALKUP_CAP + 1)}
FLAGS = {
    "unit:elev_top": 0.05,
    "unit:walkup_top": -0.03,
    "unit:penthouse": 0.10,
    "unit:garden": 0.04,
    "unit:lower": -0.15,
    "unit:elev_floor_unknown": 0.02,
    "unit:walkup_floor_unknown": -0.01,
}
TRUTH = tbs.TRUTH | ELEV | WALKUP | FLAGS


def floors_for(frame, seed=11):
    """A floor row for most listings: floors up to 60 with a few unknown, and the flags."""
    rng = np.random.default_rng(seed)
    ids = frame.listing_id.astype(str).drop_duplicates().to_numpy()
    ids = ids[rng.random(len(ids)) < 0.95]
    n = len(ids)
    floor = np.minimum(1 + rng.geometric(0.12, n) - 1, 60).astype(float)
    floor[rng.random(n) < 0.15] = np.nan
    garden = (rng.random(n) < 0.05) & (floor == 1)
    lower = (rng.random(n) < 0.05) & (floor == 1) & ~garden
    return pd.DataFrame(
        {
            "listing_id": ids,
            "floor": floor,
            "garden": garden * 1.0,
            "lower": lower * 1.0,
            "penthouse": ((rng.random(n) < 0.05) & (floor > 3)) * 1.0,
            "top": ((rng.random(n) < 0.15) & (floor > 1)) * 1.0,
            "top_source": "pluto",
        }
    )


def _design(n=2000, weeks=20, seed=3):
    frame, tables, units, trucks = tbu._design(n, weeks, seed)
    floors = floors_for(frame)
    d = bzf.design(
        frame,
        units=units,
        trucks=trucks,
        gyms=tby.gyms_for(frame),
        ages=tbs.ages_for(frame),
        floors=floors,
        **tables,
    )
    return frame, tables, units, trucks, floors, d


def test_floor_table_fills_floors_and_flags():
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5", "6", "7"],
            "building": ["a", "a", "a", "b", "b", "c", "c"],
            "page": [
                "https://x/a/garden",
                "https://x/a/ph",
                "https://x/a/3f",
                "https://x/b/ll",
                "https://x/b/4a",
                "https://x/c/2b",
                "https://x/c/5a",
            ],
            "listed_floor": [np.nan, np.nan, 3.0, np.nan, 4.0, 2.0, 5.0],
        }
    )
    registry = pd.DataFrame({"building": ["a", "b", "c"], "bbl": ["1", "2", None]})
    pluto = pd.DataFrame({"bbl": ["1", "2"], "numfloors": ["4.5", "6"]})
    tops = unit_floor.top_floors(rows, registry, pluto)
    assert tops.top_floor.to_dict() == {"a": 4.0, "b": 6.0, "c": 5.0}
    assert tops.top_source.to_dict() == {"a": "pluto", "b": "pluto", "c": "ads"}
    t = unit_floor.floor_table(rows, tops).set_index("listing_id")
    assert t.floor.to_dict() == {
        "1": 1.0, "2": 4.0, "3": 3.0, "4": 1.0, "5": 4.0, "6": 2.0, "7": 5.0
    }  # fmt: skip
    assert t.index[t.garden == 1].tolist() == ["1"]
    assert t.index[t.lower == 1].tolist() == ["4"]
    assert t.index[t.penthouse == 1].tolist() == ["2"]
    assert t.index[t.top == 1].tolist() == ["2", "7"]


def test_columns_code_curves_and_flags():
    frame, tables, units, trucks, floors, d = _design()
    a = bzs.design(
        frame,
        units=units,
        trucks=trucks,
        gyms=tby.gyms_for(frame),
        ages=tbs.ages_for(frame),
        **tables,
    )
    assert d.names[: len(a.names)] == a.names
    new = d.names[len(a.names) :]
    assert new[: len(bzf.CURVE)] == list(bzf.CURVE)
    x = pd.DataFrame(d.x[:, len(a.names) :], columns=new)
    f = floors.set_index("listing_id").reindex(frame.listing_id.astype(str))
    floor = f.floor.to_numpy()
    el = a.x[:, a.names.index("bld:elevator")] == 1
    # Each row with a known floor above 1 sets its group's column at its capped floor.
    curve_e = x[[c for c in bzf.CURVE if "elev" in c]].to_numpy()
    curve_w = x[[c for c in bzf.CURVE if "walkup" in c]].to_numpy()
    above = ~np.isnan(floor) & (floor > 1)
    np.testing.assert_array_equal(curve_e.sum(1), above & el)
    np.testing.assert_array_equal(curve_w.sum(1), above & ~el)
    k = np.minimum(floor, bzf.ELEV_CAP)
    hit = above & el
    np.testing.assert_array_equal(curve_e[hit].argmax(1) + 2, k[hit])
    hit = above & ~el
    k = np.minimum(floor, bzf.WALKUP_CAP)
    np.testing.assert_array_equal(curve_w[hit].argmax(1) + 2, k[hit])
    np.testing.assert_array_equal(x["unit:elev_floor_unknown"], np.isnan(floor) & el)
    np.testing.assert_array_equal(x["unit:walkup_floor_unknown"], np.isnan(floor) & ~el)
    np.testing.assert_array_equal(x["unit:elev_top"], (f.top.fillna(0) == 1) & el)
    np.testing.assert_array_equal(x["unit:garden"], f.garden.fillna(0) == 1)
    assert all(d.count[n] == (x[n] != 0).sum() for n in new)
    spec = bzf.gp_spec(d.names)
    assert [s["name"] for s in spec] == ["elev", "walkup"]
    np.testing.assert_allclose(spec[0]["x"], np.log(np.arange(2, bzf.ELEV_CAP + 1)))


def test_gp_prior_replaces_the_normal_prior_on_the_curve():
    *_, d = _design(600, 10, 5)
    d = bzs.subset(d, np.ones(len(d.y), bool))
    priors, settings = building_zones.Priors(), bzg.Settings(chains=1, site_block=64)
    spec = bzf.gp_spec(d.names)
    _, init, plain = bzg.make_sampler(d, priors, settings)
    _, init_gp, sys_gp = bzg.make_sampler(d, priors, settings, gp=spec)
    import jax

    st = {
        k: v[0] for k, v in init_gp(jax.random.split(jax.random.PRNGKey(0), 1)).items()
    }
    A0 = np.asarray(plain["global_system"](st)[0])
    A1 = np.asarray(sys_gp["global_system"](st)[0])
    others = [n for n in d.names if n != "alpha"]
    _, s_b, _, _ = bzg._prior_vectors(d, priors)
    for k, s in enumerate(spec):
        pos = [others.index(c) for c in s["cols"]]
        Kc = np.asarray(bzg.gp_cov(np, s["x"], float(st["gp_ls"][k])))
        want = np.linalg.inv(Kc) / float(st["gp_amp"][k]) ** 2 - np.diag(
            1 / s_b[pos] ** 2
        )
        np.testing.assert_allclose(
            A1[np.ix_(pos, pos)] - A0[np.ix_(pos, pos)], want, rtol=1e-6, atol=1e-6
        )
    curve = [others.index(c) for s in spec for c in s["cols"]]
    rest = np.setdiff1d(np.arange(A0.shape[0]), curve)
    np.testing.assert_array_equal(A1[np.ix_(rest, rest)], A0[np.ix_(rest, rest)])


def test_gp_cov_is_pinned_at_zero():
    x = np.log(np.arange(1, 8.0))
    K = bzg.gp_cov(np, x, 0.7)
    assert abs(K[0, 0] - bzg.GP_NUGGET) < 1e-12 and np.allclose(K[0, 1:], 0)
    assert np.all(np.linalg.eigvalsh(K) > 0)


def test_recovers_simulated_floor_curves_and_flags(monkeypatch):
    *_, d = _design(8000, 30, 9)
    d = bzs.subset(d, np.ones(len(d.y), bool))
    monkeypatch.setattr(tba, "TRUTH", TRUTH)
    d = tba._simulated(d)
    out = bzf.run(
        d,
        building_zones.Priors(),
        bzg.Settings(chains=2, warmup=100, draws=300, keep_every=5),
        log=lambda m: None,
    )
    beta = out["trace"]["beta"].reshape(-1, len(d.names))
    check = tbs.TRUTH | FLAGS | {c: TRUTH[c] for c in WALKUP}
    check |= {f"unit:elev_f{k}": ELEV[f"unit:elev_f{k}"] for k in (2, 4, 8, 16)}
    for n, v in check.items():
        lo, hi = np.quantile(beta[:, d.names.index(n)], [0.001, 0.999])
        assert lo < v < hi, (n, lo, hi, v)
    for q in ("gp_amp", "gp_ls"):
        v = out["trace"][q]
        assert v.shape[-1] == 2 and np.all(np.isfinite(v)) and np.all(v > 0)
        assert np.ptp(v[..., 0]) > 0


@pytest.mark.parametrize(
    "model",
    [
        "building-zones-floor",
        "building-zones-mundlak",
        "building-zones-transit",
        "building-zones-parks",
        "building-zones-noise",
        "building-zones-location",
        "building-zones-avenue",
    ],
)
def test_run(tmp_path, monkeypatch, model):
    from rentfrontier import building_attrs, run as runmod, whitened_zones
    from rentfrontier import building_zones_attrs as bza
    from rentfrontier import building_zones_front as bzfront
    from rentfrontier import building_zones_gym as bzy
    from rentfrontier import building_zones_noise as bzn
    from rentfrontier import building_zones_parks as bzp
    from rentfrontier import building_zones_transit as bzt
    from rentfrontier import building_zones_unit as bzu

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
    tbs.ages_for(frame).to_parquet(asnap / "age.parquet")
    fsnap = tmp_path / "unit-floor"
    fsnap.mkdir()
    floors_for(frame).to_parquet(fsnap / "floor.parquet")
    monkeypatch.setattr(whitened_zones, "REGISTRY", tmp_path / "registry.parquet")
    monkeypatch.setattr(whitened_zones, "NJ_REGISTRY", tmp_path / "registry-nj.parquet")
    monkeypatch.setattr(bza, "FOOTPRINTS", tmp_path / "footprints.parquet")
    monkeypatch.setattr(building_attrs, "ATTRS", tmp_path / "attrs.parquet")
    monkeypatch.setattr(bzu, "SNAPSHOT", snap)
    monkeypatch.setattr(bzy, "GYM_SNAPSHOT", gsnap)
    monkeypatch.setattr(bzs, "GYM_SNAPSHOT", gsnap)
    monkeypatch.setattr(bzs, "AGE_SNAPSHOT", asnap)
    monkeypatch.setattr(bzf, "FLOOR_SNAPSHOT", fsnap)
    tsnap = tmp_path / "building-transit"
    tsnap.mkdir()
    blds = frame.building.astype(str).unique()
    pd.DataFrame(
        {
            "building": blds,
            "station_km": np.linspace(0.1, 1.2, len(blds)),
            "routes_800m": np.arange(len(blds)) % 7,
        }
    ).to_parquet(tsnap / "transit.parquet")
    monkeypatch.setattr(bzt, "TRANSIT_SNAPSHOT", tsnap)
    psnap = tmp_path / "building-parks"
    psnap.mkdir()
    pd.DataFrame(
        {
            "building": blds,
            "park_km": np.linspace(0.02, 0.9, len(blds)),
            "big_park_km": np.linspace(0.5, 3.0, len(blds)),
            "water_km": np.linspace(3.0, 0.1, len(blds)),
        }
    ).to_parquet(psnap / "parks.parquet")
    monkeypatch.setattr(bzp, "PARKS_SNAPSHOT", psnap)
    nsnap = tmp_path / "building-noise"
    nsnap.mkdir()
    pd.DataFrame(
        {"building": blds, "noise_per_year": np.linspace(0.0, 300.0, len(blds))}
    ).to_parquet(nsnap / "noise.parquet")
    monkeypatch.setattr(bzn, "NOISE_SNAPSHOT", nsnap)
    pd.DataFrame(
        {
            "building": blds,
            "front_width_ft": np.where(np.arange(len(blds)) % 3 == 0, 70.0, 30.0),
            "corner": (np.arange(len(blds)) % 2).astype(float),
        }
    ).to_parquet(tmp_path / "frontage.parquet")
    monkeypatch.setattr(bzfront, "FRONTAGE", tmp_path / "frontage.parquet")
    monkeypatch.setenv("FRONTIER_DATASET", str(dataset))
    monkeypatch.setenv("FRONTIER_COMMIT", "abc1234")
    monkeypatch.setattr(runmod, "RUNS", tmp_path / "runs")
    runmod.main(
        [
            "--split", "latest", "--model", model, "--features", "base-v1",
            "--chains", "2", "--warmup", "20", "--draws", "40", "--keep-every", "4",
            "--site-block", "16", "--name", "bzf-test", "--tier", "full",
        ]
    )  # fmt: skip
    out = tmp_path / "runs" / "bzf-test"
    result = json.loads((out / "result.json").read_text())
    assert result["sampler"] == model
    assert result["unit_floor"] == str(fsnap)
    assert result["floor_gp"]["caps"] == {
        "elev": bzf.ELEV_CAP,
        "walkup": bzf.WALKUP_CAP,
    }
    rows = result["diagnostics"]["per_quantity"]
    assert {"gp_amp[elev]", "gp_ls[walkup]"} <= set(rows)
    post = np.load(out / "posterior.npz")
    names = [str(n) for n in post["names"]]
    assert set(bzf.CURVE) <= set(names)
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    s = bzf.summarize(kept, names)
    assert {"gp_amp[elev]", "gp_ls[elev]"} <= set(s["floor_gp"])
    assert "unit:elev_top" in s["unit"]

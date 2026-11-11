import json
from datetime import date

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from scipy.stats import norm
from test_drift_deals import _run
from test_drift_estimates import _latest

from rentfrontier import drift_diagnostics, drift_estimates
from rentfrontier.b0data import sha256


def _history(rows):
    """Give `_run`'s rows a past: listing 1 came a year before listing 2 with two
    bedrooms, and listing 5 a year before listing 4 at 1,500, in the piece of unit u3
    the dataset cut off where the bedroom count changed."""
    rows.loc[0, ["latest_day", "bedrooms"]] = [date(2025, 11, 1), 2.0]
    rows.loc[4, ["latest_day", "latest_ask", "bedrooms"]] = [
        date(2025, 10, 1),
        1500.0,
        0.0,
    ]
    rows.loc[3, "unit_id"] = "u3~2"
    rows.loc[4, "unit_id"] = "u3~1"


def _features(root):
    """Snapshot folders under `root`: two of listing codes (the older one must lose),
    one of building attributes, one of lots. No other family has a folder."""
    old = root / "listing-codes" / "20261001-aaa"
    new = root / "listing-codes" / "20261110-bbb"
    for folder, photos in ((old, 99), (new, 7)):
        folder.mkdir(parents=True)
        pd.DataFrame(
            {
                "listing_id": ["2", "3", "4"],
                "photos": [photos, 8, 9],
                "feat:DISHWASHER": np.array([1, 0, 1], "int8"),
                "feat:LOFT": np.array([0, 0, 0], "int8"),
                "source_type": ["agent", "owner", ""],
            }
        ).to_parquet(folder / "listing-codes.parquet", index=False)
    attrs = root / "building-attrs" / "20261110-bbb"
    attrs.mkdir(parents=True)
    pd.DataFrame(
        {"building": ["a", "b"], "floors": [5.0, 20.0], "tenure": ["rental", "condo"]}
    ).to_parquet(attrs / "attrs.parquet", index=False)
    pluto = root / "pluto" / "20261017-ccc"
    pluto.mkdir(parents=True)
    pd.DataFrame(
        {
            "bbl": ["1000010001", "3000010001"],
            "unitsres": ["12", "40"],
            "landmark": ["THE OLD HOUSE", None],
        }
    ).to_parquet(pluto / "pluto.parquet", index=False)
    return root


def _with_lots(reg):
    """The registry at `reg` with lots: a in Manhattan, b and c in Brooklyn."""
    frame = pd.read_parquet(reg)
    frame["bbl"] = ["1000010001", "3000010001", "3000020002"]
    frame.to_parquet(reg, index=False)
    return reg


def _published(tmp_path, **kw):
    latest, reg = _latest(tmp_path / "l", change=_history)
    market, ads, _ = _run(tmp_path / "m", change=_history)
    out = tmp_path / "site" / "diagnostics"
    meta = drift_diagnostics.publish(latest, out, market, ads, _with_lots(reg), **kw)
    return out, meta, latest


def test_publish_writes_three_tables_and_then_the_meta(tmp_path):
    out, meta, latest = _published(tmp_path)
    names = ["ads.parquet", "buildings.parquet", "history.parquet", "meta.json"]
    assert sorted(p.name for p in out.iterdir()) == names
    assert meta == json.loads((out / "meta.json").read_text())
    for name in ("ads", "buildings", "history"):
        assert meta["sha256"][name] == sha256(out / f"{name}.parquet")
    assert meta["runs"] == {"latest": "r", "market": "r"}
    assert meta["scoring_day"] == "2026-11-09" and meta["model"] == "drift-building"
    assert meta["gate"]["latest"]["passes"] and meta["gate"]["market"]["passes"]
    assert meta["counts"]["ads"] == {"all": 4, "latest": 0, "market": 4}
    assert meta["counts"]["buildings"] == 3 and meta["counts"]["history"] == 6
    assert meta["sources"]["ads"]["sha256"] == sha256(tmp_path / "m" / "ads.parquet")

    ads = pd.read_parquet(out / "ads.parquet")
    core = list(drift_diagnostics.CORE)
    assert ads.columns.tolist()[: len(core)] == core and ads.columns[-1] == "flags"
    # The same ads, asks and medians as the Estimates table of the same two runs.
    est, _ = drift_estimates.estimates(latest, tmp_path / "m" / "runs" / "r")
    assert ads.listing_id.tolist() == est.listing_id.tolist()
    assert (ads.ask == est.ask).all() and (ads.model_median == est.model_median).all()
    assert np.allclose(ads.pit, est.below_share, atol=1e-4)
    assert np.allclose(ads.z, norm.ppf(ads.pit).clip(-6, 6))
    assert np.allclose(ads.gap, np.log(ads.ask / 3000), atol=0.01)
    # `miss` is the gap in units of the spread read from the model's 80% range.
    spread = np.log(ads.model_hi80 / ads.model_lo80) / 2.5631
    assert np.allclose(ads.miss, ads.gap / spread, rtol=0.02, atol=0.01)
    assert meta["model_terms"] == []
    row = ads.set_index("listing_id")
    assert row.unit.to_dict() == {"2": "2A", "3": "3B", "4": "PH1", "6": "4D"}
    assert row.address["4"] == "1 East 2nd Street" and row.latitude["4"] == 40.71
    assert row.square_feet["2"] == 700 and np.isnan(row.square_feet["3"])
    assert row.first_ask["4"] == 3600 and row.days_on_market["4"] == 40


def test_basis_and_previous_ads_come_from_the_runs_rows(tmp_path):
    out, _, _ = _published(tmp_path)
    row = pd.read_parquet(out / "ads.parquet").set_index("listing_id")
    # Training rows: listing 1 (building a, unit u1) and listing 5 (building b, u3~1).
    assert row.unit_ads.to_dict() == {"2": 1, "3": 0, "4": 0, "6": 0}
    assert row.building_ads.to_dict() == {"2": 1, "3": 1, "4": 1, "6": 0}
    assert row.basis.to_dict() == {"2": "unit", "3": "area", "4": "area", "6": "area"}
    assert row.prev_ask["2"] == 3000 and row.prev_day["2"] == "2025-11-01"
    assert row.prev_bedrooms["2"] == 2
    # The pieces u3~1 and u3~2 are one apartment, so listing 4 follows listing 5.
    assert row.prev_ask["4"] == 1500 and row.prev_day["4"] == "2025-10-01"
    assert np.isnan(row.prev_ask["3"]) and pd.isna(row.prev_day["3"])
    flags = {k: list(v) for k, v in row["flags"].items()}
    assert flags["2"] == ["beds_conflict", "beds_jump"]
    # 3,300 after 1,500 is over twice the previous ask.
    assert flags["4"] == ["beds_conflict", "beds_jump", "ask_jump"]
    assert flags["3"] == [] and flags["6"] == []


def test_building_basis_takes_five_training_ads(tmp_path):
    def more(rows):
        extra = pd.concat([rows.iloc[[4]]] * 5, ignore_index=True)
        extra["listing_id"] = [str(i) for i in range(10, 15)]
        extra["unit_id"] = [f"v{i}" for i in range(5)]
        for c in rows:
            rows.loc[rows.index, c] = rows[c]
        return extra

    latest, _ = _latest(tmp_path / "l", scored=False)
    path = tmp_path / "l" / "data" / "rows.parquet"
    rows = pd.read_parquet(path)
    rows = pd.concat([rows, more(rows)], ignore_index=True)
    rows.to_parquet(path, index=False)
    z = dict(np.load(latest / "posterior.npz"))
    z["heldout"] = np.r_[z["heldout"], np.zeros(5, bool)]
    np.savez(latest / "posterior.npz", **z)
    record = json.loads((latest / "result.json").read_text())
    manifest = json.loads((path.parent / "manifest.json").read_text())
    manifest["rows_sha256"] = record["dataset_observations_sha256"] = sha256(path)
    (path.parent / "manifest.json").write_text(json.dumps(manifest))
    (latest / "result.json").write_text(json.dumps(record))
    tables, meta = drift_diagnostics.diagnostics(latest)
    row = tables["ads"].set_index("listing_id")
    # Building b now has six training ads. Listing 4's unit u3 has one of them.
    assert row.building_ads["3"] == 6 and row.basis["3"] == "building"
    assert row.basis["4"] == "unit" and row.basis["6"] == "area"
    assert meta["counts"]["basis"] == {"unit": 2, "building": 1, "area": 1}
    assert tables["buildings"].set_index("building").train_ads.to_dict() == {
        "a": 1,
        "b": 6,
        "c": 0,
    }


def test_detectors():
    t = pd.DataFrame(
        {
            "building": ["a"] * 5 + ["b"] * 5,
            "ask": [3000.0] * 10,
            "prev_ask": [1400.0, 6100, 1500, 3000, np.nan] * 2,
            "bedrooms": [1.0] * 10,
            "prev_bedrooms": [1.0, 2, np.nan, 1, 1] * 2,
            "square_feet": [200.0, 800, 2000, np.nan, 800] * 2,
            "pit": [0.05, 0.05, 0.05, 0.05, 0.5, 0.95, 0.95, 0.95, 0.5, 0.5],
            "miss": [-4.5, 0, 0, 0, 0, 4.1, 0, 0, 0, 4.0],
            "_beds_conflict": [True] + [False] * 9,
        }
    )
    flags = drift_diagnostics.detect(t)
    assert flags[0] == ["beds_conflict", "ask_jump", "ppsf", "extreme", "building_side"]
    assert flags[1] == ["beds_jump", "ask_jump", "building_side"]
    # 3,000 a month for 2,000 square feet is 18 dollars a foot a year: under the range.
    assert flags[2] == ["ppsf", "building_side"]
    assert flags[3] == ["building_side"] and flags[4] == []
    # Three of building b's five ads are over the range: fewer than four in five.
    assert flags[5] == ["ask_jump", "ppsf", "extreme"] and flags[9] == []
    out = drift_diagnostics.ppsf_outside(
        [3000, 3000, 3000], [240, 239, 1801], [0, 0, 5]
    )
    assert out.tolist() == [False, True, True]


def test_features_come_from_the_newest_snapshots_and_missing_ones_are_noted(tmp_path):
    out, meta, _ = _published(tmp_path, features=_features(tmp_path / "external"))
    ads = pd.read_parquet(out / "ads.parquet").set_index("listing_id")
    listed = {f["name"]: f for f in meta["features"]}
    # The four core attributes are listed whether or not a snapshot exists.
    assert {"square_feet", "floor", "months_free", "days_on_market"} <= set(listed)
    assert listed["days_on_market"]["after"] and not listed["square_feet"]["after"]
    assert listed["photos"] == {
        "name": "photos",
        "label": "Photos in the ad",
        "kind": "number",
        "level": "ad",
        "in_model": True,
        "after": False,
        "source": "codes",
        "known_share": 0.75,
    }
    assert ads.photos["2"] == 7 and np.isnan(ads.photos["6"])
    assert (
        ads.dishwasher["2"] and not ads.dishwasher["3"] and pd.isna(ads.dishwasher["6"])
    )
    assert ads.source_type["3"] == "owner" and pd.isna(ads.source_type["4"])
    assert ads.building_floors["2"] == 5 and np.isnan(ads.building_floors["6"])
    assert ads.tenure["3"] == "condo"
    # Lots are joined through the registry's bbl. A landmark is a lot with a name.
    assert ads.lot_units["2"] == 12 and ads.lot_units["4"] == 40
    assert ads.landmark["2"] and not ads.landmark["3"] and pd.isna(ads.landmark["6"])
    skipped = {s["name"]: s["why"] for s in meta["skipped"]}
    assert skipped["loft"] == "true for 0.00% of the ads"
    assert skipped["station_km"] == "no transit table"
    assert skipped["year_built"] == "attrs.parquet has no column year_built"
    assert "loft" not in ads and "station_km" not in ads
    used = meta["sources"]
    assert set(used) == {"ads", "codes", "attrs", "pluto"}
    assert "20261110-bbb" in used["codes"]["path"]
    assert used["codes"]["sha256"] == sha256(used["codes"]["path"])
    # Building-level attributes are in the buildings table too, and the others are not.
    b = pd.read_parquet(out / "buildings.parquet").set_index("building")
    assert b.building_floors["b"] == 20 and b.tenure["a"] == "rental"
    assert b.landmark["a"] and "photos" not in b
    schema = pq.read_schema(out / "ads.parquet")
    assert str(schema.field("flags").type) == "list<element: string>"
    assert str(schema.field("dishwasher").type) == "bool"


def test_a_given_table_replaces_the_newest_snapshot(tmp_path):
    root = _features(tmp_path / "external")
    old = root / "listing-codes" / "20261001-aaa" / "listing-codes.parquet"
    out, meta, _ = _published(tmp_path, features=root, sources={"codes": old})
    assert pd.read_parquet(out / "ads.parquet").photos.max() == 99
    assert meta["sources"]["codes"]["path"] == str(old)


def test_buildings_and_history(tmp_path):
    out, meta, _ = _published(tmp_path)
    b = pd.read_parquet(out / "buildings.parquet").set_index("building")
    assert b.index.tolist() == ["a", "b", "c"]
    assert (
        b.address["a"] == "134 West 23rd Street" and b.neighbourhood["c"] == "Chelsea"
    )
    assert b.train_ads.to_dict() == {"a": 1, "b": 1, "c": 0}
    assert b.heldout_ads.to_dict() == {"a": 1, "b": 2, "c": 1}
    ads = pd.read_parquet(out / "ads.parquet")
    assert np.isclose(b.heldout_gap["b"], ads.gap[ads.building == "b"].mean())
    assert np.isclose(b.heldout_z["b"], ads.z[ads.building == "b"].mean())
    assert np.isclose(b.heldout_miss["b"], ads.miss[ads.building == "b"].mean())
    # The tiny run keeps no building levels, so the columns are left out with a reason.
    assert "level" not in b and meta["level"] is None and meta["level_missing"]
    h = pd.read_parquet(out / "history.parquet")
    assert h.columns.tolist() == list(drift_diagnostics.HISTORY)
    assert h.listing_id.tolist() == ["1", "2", "3", "5", "4", "6"]
    assert h.heldout.tolist() == [False, True, True, False, True, True]
    assert h.market.tolist() == h.heldout.tolist()
    assert meta["counts"]["history"] == 6
    assert h.day[0] == "2025-11-01" and h.ask[3] == 1500 and h.unit[4] == "PH1"


def test_levels_follow_the_fits_order_of_buildings(tmp_path):
    latest, reg = _latest(tmp_path / "l")
    # Building a is in Manhattan and b, c in Brooklyn, so the fit numbers them a, b, c
    # even when the rows start with a Brooklyn building. Here the rows start with a.
    _with_lots(reg)
    nj = tmp_path / "nj.parquet"
    pd.DataFrame(
        {"building": ["z"], "latitude": [40.7], "longitude": [-74.05]}
    ).to_parquet(nj)
    z = dict(np.load(latest / "posterior.npz"))
    draws = np.random.default_rng(1).normal(size=(2, 50, 3)) * 0.01
    z["kept/bld"] = draws + np.array([0.1, -0.2, 0.3])
    np.savez(latest / "posterior.npz", **z)
    record = json.loads((latest / "result.json").read_text())
    record |= {
        "registry": str(reg),
        "nj_registry": str(nj),
        "surfaces": [
            {"name": "manhattan", "first": 0, "sites": 1},
            {"name": "outer", "first": 1, "sites": 2},
        ],
    }
    (latest / "result.json").write_text(json.dumps(record))
    tables, meta = drift_diagnostics.diagnostics(latest, registry=reg)
    b = tables["buildings"].set_index("building")
    assert b.zone.to_dict() == {"a": "manhattan", "b": "outer", "c": "outer"}
    assert np.allclose(b.level, [0.1, -0.2, 0.3], atol=0.01)
    assert (b.level_sd > 0).all() and meta["level"] and meta["level_missing"] is None
    # A record with other counts than the rebuilt order gives: no levels.
    record["surfaces"][0]["sites"], record["surfaces"][1]["sites"] = 2, 1
    (latest / "result.json").write_text(json.dumps(record))
    tables, meta = drift_diagnostics.diagnostics(latest, registry=reg)
    assert (
        "level" not in tables["buildings"] and "does not match" in meta["level_missing"]
    )


def test_coverage_counts_the_central_ranges():
    pit = [0.02, 0.2, 0.3, 0.5, 0.74, 0.76, 0.9, 0.99]
    assert drift_diagnostics.coverage(pit) == {"50": 0.375, "80": 0.75, "95": 0.75}


def test_publish_refuses_wrong_splits_models_and_missed_gates(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    market, ads, _ = _run(tmp_path / "m")
    with pytest.raises(SystemExit, match="not a run on the latest split"):
        drift_diagnostics.diagnostics(market)
    other, _, _ = _run(tmp_path / "o", model="drift")
    with pytest.raises(SystemExit):
        drift_diagnostics.diagnostics(latest, other)
    record = json.loads((latest / "result.json").read_text())
    record["diagnostics"] = {"passes": False, "max_rhat": 1.2, "min_ess": 50.0}
    (latest / "result.json").write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="convergence gate"):
        drift_diagnostics.publish(latest, tmp_path / "out", market, ads)
    assert not (tmp_path / "out").exists()


def test_the_command_line_names_its_sources(tmp_path, capsys):
    latest, reg = _latest(tmp_path / "l")
    out = tmp_path / "out"
    args = ["publish", "r", "--runs", str(latest.parent), "--out", str(out)]
    drift_diagnostics.main([*args, "--registry", str(reg)])
    assert json.loads(capsys.readouterr().out)["counts"]["ads"]["all"] == 4
    with pytest.raises(SystemExit):
        drift_diagnostics.main([*args, "--source", "nothing=/x"])


def test_history_adds_the_market_datasets_ads(tmp_path):
    def rows(ids, asks, day):
        return pd.DataFrame(
            {
                "listing_id": ids,
                "building": "a",
                "unit_id": ["u1", "u1", "u2"][: len(ids)],
                "latest_day": day,
                "latest_ask": asks,
                "bedrooms": 1.0,
                "full_baths": 1.0,
            }
        )

    past = rows(["1", "2", "3"], [3000.0, 3100, 2000], date(2026, 10, 1))
    # The market dataset has ad 2 at a newer ask and on the market, ad 3 closed and held
    # out by no fit there, and the new ad 9 of unit u2.
    now = rows(["2", "3", "9"], [2900.0, 2000, 2100], date(2026, 11, 9))
    now["unit_id"] = ["u1", "u2", "u2"]
    held, on = np.array([False, True, True]), np.array([True, False, True])
    h = drift_diagnostics.history(
        past, held, None, (now[[True, False, True]], on[[0, 2]])
    )
    assert h.listing_id.tolist() == ["1", "2", "3", "9"]
    assert h.ask.tolist() == [3000, 2900, 2000, 2100]
    assert h.heldout.tolist() == [False, True, True, True]
    assert h.market.tolist() == [False, True, False, True]


def test_model_terms_puts_the_coefficient_names_in_plain_words(tmp_path):
    latest, _ = _latest(tmp_path / "l")
    z = dict(np.load(latest / "posterior.npz"))
    z["names"] = np.array(
        [
            "alpha",
            "bed>=1",
            "bed>=2",
            "unit:elev_f3",
            "bld:amen_pool",
            "umean:ad:video",
            "odd",
        ]
    )
    z["kept/bld"] = np.zeros((2, 50, 3))
    np.savez(latest / "posterior.npz", **z)
    assert drift_diagnostics.model_terms(latest) == [
        "Bedrooms",
        "Floor, apart for elevator and walk-up buildings",
        "Building amenities stated in ads",
        "Each unit's average of the ad-level attributes, beside the ad's own value",
        "odd",
        "A level for each building",
    ]

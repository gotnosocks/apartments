import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from rentfrontier import data, design, design_parts, rentmap, summary


def toy(seed=0, rows=60, buildings=6, months=30):
    rng = np.random.default_rng(seed)
    names = ["beds", "sqft", "floor", "doorman", "current_capture_ask"]
    groups = ["bedrooms", "size", "floor", "doorman", "price_basis"]
    building = rng.integers(0, buildings - 1, rows)  # the last building has no rows
    train = SimpleNamespace(
        x=rng.normal(size=(rows, len(names))),
        building=building,
        beds_centered=rng.integers(0, 5, rows) - 1.0,
        month=rng.integers(0, months, rows),
    )
    prep = SimpleNamespace(
        buildings=np.array([f"b{i}" for i in range(buildings)], dtype=object),
        units=np.array([f"u{i}" for i in range(9)], dtype=object),
        periods=pd.period_range("2024-01", periods=months, freq="M").to_timestamp(),
        offset=8.25,
        features=SimpleNamespace(names=names, groups=groups),
        train=train,
    )
    feats = SimpleNamespace(names=names, groups=groups)
    hoods = np.array(["Chelsea", "West Village"])[np.arange(buildings) % 2]
    frame = pd.DataFrame(
        {
            "building": np.concatenate([prep.buildings[building], ["b5"]]),
            "neighbourhood": np.concatenate([hoods[building], ["Chelsea"]]),
            "audit_id": [f"a{i}" for i in range(rows + 1)],
        }
    )
    heldout = np.r_[np.zeros(rows, dtype=bool), True]
    return frame, heldout, feats, prep


def old_typical_rows(prep):
    """The rent map's typical rows as computed from the whole design before
    the design parts."""
    tr = prep.train
    groups = np.asarray(prep.features.groups)
    names = prep.features.names
    building_cols = np.isin(groups, list(rentmap.BUILDING_GROUPS))
    price = np.array([n == "current_capture_ask" for n in names])
    n_b = len(prep.buildings)
    counts = np.bincount(tr.building, minlength=n_b)
    own = np.zeros((n_b, len(names)))
    np.add.at(own, tr.building, tr.x)
    own /= np.maximum(counts, 1)[:, None]
    beds = tr.beds_centered + 1
    out = {}
    for key, _, values in rentmap.BEDROOMS:
        rows = np.isin(beds, values)
        apartment = tr.x[rows].mean(0)
        x = np.where(building_cols[None], own, apartment[None])
        x[:, price] = 0.0
        out[key] = (x, float(tr.beds_centered[rows].mean()))
    return out


def registry(tmp_path, buildings):
    path = tmp_path / "registry.parquet"
    pd.DataFrame(
        {
            "building": buildings,
            "label": [f"{i} W 20th St, New York" for i in range(len(buildings))],
            "latitude": 40.74,
            "longitude": -74.0,
        }
    ).to_parquet(path)
    return path


def test_parts_give_the_rent_map_what_the_whole_design_gave(tmp_path):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    for (key, (x, beds)), (old_key, (old_x, old_beds)) in zip(
        rentmap.typical_rows(parts).items(), old_typical_rows(prep).items()
    ):
        assert key == old_key
        assert np.array_equal(x, old_x)
        assert beds == old_beds
    years = np.unique(prep.periods.year)
    table = rentmap.building_table(parts, years, registry(tmp_path, prep.buildings))
    tr = prep.train
    for i, b in enumerate(table):
        mine = prep.periods[tr.month[tr.building == i]].year
        assert b["fit_listings"] == len(mine)
        assert b["first_year"] == (mine.min() if len(mine) else years[-1])
        assert b["last_year"] == (mine.max() if len(mine) else years[0])
    assert table[-1]["fit_listings"] == 0
    assert list(parts.hood[:5]) == ["Chelsea", "West Village"] * 2 + ["Chelsea"]
    # The last building's only row is held out, so it has no neighbourhood.
    assert pd.isna(parts.hood[5])
    assert parts.area == "Chelsea and West Village"


RUN = {
    "name": "m-run",
    "dataset": "/d",
    "dataset_observations_sha256": "d",
    "split": "rows",
    "feature_set": "f",
    "data_rules": ["q"],
    "data_rule_sources": {"q": "qsha"},
}


def test_parts_read_back_as_written(tmp_path):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    path = tmp_path / design_parts.FILE
    record = design_parts.write(parts, path, RUN, "r")
    assert record == {
        "file": design_parts.FILE,
        "sha256": design_parts.file_sha256(path),
        "rows_sha256": "r",
    }
    back, meta = design_parts.load(tmp_path / design_parts.FILE)
    assert meta["run"] == {k: v for k, v in RUN.items() if k != "dataset"}
    assert meta["rows_sha256"] == "r"
    assert np.array_equal(back.buildings, prep.buildings)
    assert back.buildings.dtype == object
    assert np.array_equal(back.units, prep.units)
    assert back.periods.equals(prep.periods)
    assert back.offset == prep.offset
    assert back.features.names == feats.names
    assert back.features.groups == feats.groups
    for field in (
        "building_x",
        "building_rows",
        "building_first",
        "building_last",
        "bedroom_x",
        "bedroom_beds",
    ):
        assert np.array_equal(
            getattr(back, field), getattr(parts, field), equal_nan=True
        ), field
    # A building without listings in the fit reads back as missing, too.
    assert list(back.hood[:5]) == list(parts.hood[:5])
    assert pd.isna(back.hood[5])
    assert back.area == parts.area
    assert back.heldout_sha256 == parts.heldout_sha256


def write_run(tmp_path, frame, heldout, prep, rows_sha256="r"):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    np.savez(run_dir / "posterior.npz", units=prep.units, buildings=prep.buildings)
    np.savez(run_dir / "heldout.npz", audit_id=frame.audit_id.to_numpy()[heldout])
    return run_dir, RUN | {"rows_sha256": rows_sha256}


def test_the_bundle_parts_stand_in_only_when_they_go_with_the_run(
    tmp_path, monkeypatch
):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    design_parts.write(parts, bundle / design_parts.FILE, RUN, "r")
    run_dir, result = write_run(tmp_path, frame, heldout, prep)
    prepared, checked = [], []
    monkeypatch.setattr(data, "load", lambda path: frame)
    monkeypatch.setattr(data, "recorded_rules", lambda result: [])
    monkeypatch.setattr(
        design,
        "prepared",
        lambda *a: prepared.append(a) or (frame, heldout, feats, prep),
    )
    monkeypatch.setattr(summary, "verify_run", lambda *a: checked.append(a))

    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["design"] == "summary bundle"
    assert source["rows_sha256_matches_run"]
    assert not prepared and not checked
    assert np.array_equal(found.building_x, parts.building_x)

    # The rows hash can differ by a last bit of a log rent, so it is recorded.
    for change in ({"rows_sha256": "other"}, {"rows_sha256": None}):
        found, source = design_parts.for_run(result | change, run_dir, bundle)
        assert source["design"] == "summary bundle"
        assert not source["rows_sha256_matches_run"]

    found, source = design_parts.for_run(
        result | {"dataset_observations_sha256": "other"}, run_dir, bundle
    )
    assert source["design"] == "prepared"
    assert source["bundle_parts_unused"].startswith("dataset")
    assert len(checked) == 1

    # Another run's bundle over the same rows, buildings and units.
    for change in (
        {"name": "m-other"},
        {"feature_set": "g"},
        {"data_rules": ["q", "r"]},
        {"data_rule_sources": {"q": "other"}},
    ):
        found, source = design_parts.for_run(result | change, run_dir, bundle)
        key = next(iter(change))
        assert source["bundle_parts_unused"] == f"{key} differs from the run's"
    # The record's rules read back as a list wherever they came from.
    found, source = design_parts.for_run(
        result | {"data_rules": ("q",)}, run_dir, bundle
    )
    assert source["design"] == "summary bundle"

    np.savez(run_dir / "heldout.npz", audit_id=frame.audit_id.to_numpy()[:1])
    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["bundle_parts_unused"].startswith("held-out rows")
    np.savez(run_dir / "heldout.npz", audit_id=frame.audit_id.to_numpy()[heldout])

    other = SimpleNamespace(**vars(prep))
    other.units = prep.units[::-1]
    np.savez(run_dir / "posterior.npz", units=other.units, buildings=prep.buildings)
    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["bundle_parts_unused"].startswith("units or buildings")

    # The rent map uses the whole design unchecked, as before.
    found, source = design_parts.for_run(result, run_dir, None, verify=False)
    assert source == {
        "design": "prepared",
        "bundle_parts_unused": "no summary bundle given",
    }
    assert np.array_equal(found.building_x, parts.building_x)

    np.savez(run_dir / "posterior.npz", units=prep.units, buildings=prep.buildings)
    # Parts that differ from the bundle's record of them are passed over.
    record = design_parts.write(parts, bundle / design_parts.FILE, RUN, "r")
    (bundle / "complete.json").write_text(json.dumps({"design_parts": record}))
    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["design"] == "summary bundle"
    (bundle / "complete.json").write_text(
        json.dumps({"design_parts": record | {"sha256": "other"}})
    )
    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["bundle_parts_unused"].startswith("the file differs")
    (bundle / "complete.json").unlink()

    # Parts of another file version are passed over, too.
    monkeypatch.setattr(design_parts, "VERSION", "design-parts-v2")
    found, source = design_parts.for_run(result, run_dir, bundle)
    assert source["design"] == "prepared"
    assert "design-parts-v1, not design-parts-v2" in source["bundle_parts_unused"]
    assert len(checked) == 9


def test_another_version_is_refused(tmp_path, monkeypatch):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    path = tmp_path / design_parts.FILE
    design_parts.write(parts, path, RUN, "r")
    monkeypatch.setattr(design_parts, "VERSION", "design-parts-v0")
    with pytest.raises(ValueError, match="design-parts-v1"):
        design_parts.load(path)

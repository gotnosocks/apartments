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


def test_parts_read_back_as_written(tmp_path):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    record = design_parts.write(parts, tmp_path / design_parts.FILE, "d", "r")
    assert record == {"file": design_parts.FILE, "rows_sha256": "r"}
    back, meta = design_parts.load(tmp_path / design_parts.FILE)
    assert meta["dataset_observations_sha256"] == "d"
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
    assert back.area == parts.area


def write_run(tmp_path, prep, rows_sha256="r"):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    np.savez(run_dir / "posterior.npz", units=prep.units, buildings=prep.buildings)
    return run_dir, {
        "dataset": "/d",
        "dataset_observations_sha256": "d",
        "rows_sha256": rows_sha256,
        "split": "rows",
        "feature_set": "f",
    }


def test_the_bundle_parts_stand_in_only_when_they_go_with_the_run(
    tmp_path, monkeypatch
):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    design_parts.write(parts, bundle / design_parts.FILE, "d", "r")
    run_dir, result = write_run(tmp_path, prep)
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
    assert not prepared and not checked
    assert np.array_equal(found.building_x, parts.building_x)

    for change, reason in (
        ({"dataset_observations_sha256": "other"}, "dataset"),
        ({"rows_sha256": "other"}, "rows"),
        ({"rows_sha256": None}, "rows"),
    ):
        found, source = design_parts.for_run(result | change, run_dir, bundle)
        assert source["design"] == "prepared"
        assert source["bundle_parts_unused"].startswith(reason)
    assert len(checked) == 3

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
    assert len(checked) == 4
    assert np.array_equal(found.building_x, parts.building_x)


def test_another_version_is_refused(tmp_path):
    frame, heldout, feats, prep = toy()
    parts = design_parts.from_design(frame, heldout, feats, prep)
    path = tmp_path / design_parts.FILE
    design_parts.write(parts, path, "d", "r")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(design_parts, "VERSION", "design-parts-v0")
    with pytest.raises(ValueError, match="design-parts-v1"):
        design_parts.load(path)
    monkeypatch.undo()

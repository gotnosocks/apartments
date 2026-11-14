"""L1 reading its MapPLUTO fields from the release out when each row's ad was priced
(`rentfrontier.drift_building_phase_plutoasof`)."""

import copy
import dataclasses
import hashlib
import json

import numpy as np
import pandas as pd
import pytest
import test_drift as td
import test_drift_building_phase as tp

from rentfrontier import (
    b0coop,
    building_age,
    building_attrs,
    building_zones,
    building_zones_age,
    building_zones_attrs,
    building_zones_floor_asof,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_plutoasof,
    drift_pool,
    market,
    run,
)
from rentfrontier import building_zones_kitchen_sink as ks

M = drift_building_phase_plutoasof
F = M.FIELDS
# Each lot's fields in 26v2, in the order of FIELDS (`M.FIELDS`): units, lot front, lot type,
# built FAR, residential FAR, landmark, buildings, class, residential area, floors, year
# built, the alteration years, and the retail and commercial areas.
LOTS_26 = {
    "1000010001": "40 50.5 3 5.1 6.02 - 1 R4 40000 12 2004 0 0 1200 1500",
    "1000010002": "10 25 5 3.9 3.44 - 1 C1 9000 5 1910 2008 0 0 0",
    "1000010003": "120 100 1 9.0 10.0 UWS 2 D4 - 15 0 1990 2012 - 3000",
    "1000010004": "60 75 3 7.5 7.52 - 1 D1 52000 20 2019 0 0 2500 2500",
}
# The same lots in 20v1: the condo still a rental of class C1, the walk-up one floor lower
# and with no alteration, and the fourth lot not yet built. Blank fields are written as the
# older releases write them, as empty strings, and one class carries padding.
LOTS_20 = {
    "1000010001": "38 50.5 3 4.9 6.02 - 1 _C1 39000 11 2004 0 0 1200 1500",
    "1000010002": "10 25 5 3.9 3.44 - 1 C1 9000 4 1910 0 0 0 0",
    "1000010003": "118 100 1 9.0 10.0 UWS 2 D4 - 15 0 1990 0 - 2900",
}
# Release 22v2 carries no publication date, and no row reads its classes.
LOTS_22 = {b: v.replace(" D4 ", " Z9 ") for b, v in LOTS_26.items()}
BUILDINGS = {
    "b0": "1000010001",
    "b1": "1000010002",
    "b2": "1000010003",
    "b3": "1000010004",
    "b4": "1000010009",
    "b5": None,
}
DATES = [
    "2020-01-15",
    "2021-06-10",
    "2023-03-03",
    "2026-08-30",
    "2026-09-02",
    "2026-10-01",
]


@pytest.fixture(autouse=True)
def _record():
    """Each test starts with no record of an earlier design."""
    M.RECORD.clear()
    yield
    M.RECORD.clear()


def _lots(spec, release, published):
    """The lines of the release file for the lots `spec` (bbl: fields), with "-" for an empty
    string and "_" for a space."""
    rows = []
    for bbl, line in spec.items():
        vals = [v.replace("-", "").replace("_", " ") for v in line.split()]
        rows.append({"release": release, "bbl": bbl, "published": published})
        rows[-1] |= dict(zip(F, vals, strict=True))
    return pd.DataFrame(rows, dtype=object)


def _write(tmp_path, *parts):
    path = tmp_path / "plutoreleases.parquet"
    pd.concat(parts, ignore_index=True).astype("string").to_parquet(path)
    return path


def _today():
    """26v2's lots as `building_attrs.PLUTO` holds them."""
    t = _lots(LOTS_26, "26v2", None).drop(columns=["release", "published"])
    for f in F:
        t[f] = M.blank(t[f]).astype(object)
    return t.assign(version="26v2")


def _frame():
    """Six rows of each building, one on each of DATES, with their ads and amenities."""
    rows, ads, amen = [], [], []
    for i, (b, _) in enumerate(BUILDINGS.items()):
        for j, at in enumerate(DATES):
            lid = f"L{i}{j}"
            rows.append(
                {
                    "listing_id": lid,
                    "building": b,
                    "unit_id": f"{b}-{j % 2}",
                    "price_at": pd.Timestamp(at, tz="UTC"),
                    "bedrooms": j % 3,
                    "full_baths": 1,
                }
            )
            # The third ad of each building is a penthouse with no floor, which reads the
            # building's floor count; the second of b2 states an elevator.
            ads.append(
                {
                    "listing_id": lid,
                    "page": f"https://x/{b}/{'ph' if j == 2 else f'{j + 2}a'}",
                    "square_feet": np.nan,
                    "building_floor_count": np.nan,
                    "listed_floor": np.nan if j == 2 else float(j + 2),
                    "elevator": True if (b == "b2" and j == 1) else None,
                    "doorman_type": "full_time" if b == "b0" else None,
                }
            )
            amen.append({"listing_id": lid, "states": j % 2 == 0, "gym": i % 2 == 0})
    frame = pd.DataFrame(rows)
    registry = pd.DataFrame(
        {"building": list(BUILDINGS), "bbl": list(BUILDINGS.values())}
    )
    held = frame.price_at.eq(pd.Timestamp(DATES[-1], tz="UTC")).to_numpy()
    return frame, held, registry, pd.DataFrame(ads), pd.DataFrame(amen)


@dataclasses.dataclass
class _D:
    """The fields of a design the MapPLUTO columns read and write."""

    y: np.ndarray
    x: np.ndarray
    names: list
    site: np.ndarray
    count: dict


def _l1(frame, held, registry, pluto, ads, amenities):
    """A design of `frame` with a column of noise and the MapPLUTO columns, built by L1's own
    functions from the lots `pluto` as L1 builds them from 26v2."""
    train = ~held
    n = len(frame)
    site = np.unique(frame.building, return_inverse=True)[1]
    rows = building_zones_floor_asof.ad_rows(frame, ads)
    lots = building_attrs.nyc_lots(registry, pluto)
    attrs = building_zones_floor_asof.attrs_table(rows, train, lots)
    condo = building_zones_attrs.columns(frame, pd.Series(dtype=float), attrs)[:, 4]
    base = [*ks.BASE_COLUMNS, *ks.FLOOR_COLUMNS]
    d = ks.asof_base(
        _D(np.zeros(n), np.zeros((n, len(base))), base, site, {}),
        frame,
        train,
        ads,
        amenities,
        lots,
    )
    gyms = pd.DataFrame({"building": pd.Series([], dtype=object), "gym": []})
    ages = building_age.building_table(attrs, registry, pluto)
    age = building_zones_age.columns(frame, gyms, ages)[:, 1:]
    lot_names, lot_x = ks.lot_columns(frame, ks.lot_table(registry, pluto))
    noise = np.random.default_rng(0).normal(size=n)
    names = ["unit:noise", "bld:condo", *base, *M.AGE_COLUMNS, *lot_names]
    x = np.column_stack([noise, condo, d.x, age, lot_x])
    count = {k: int((x[:, j] != 0).sum()) for j, k in enumerate(names)}
    return _D(np.zeros(n), x, names, site, count)


def _p1(monkeypatch, l1, frame, held, registry, ads, amenities, path):
    """P1's design of `frame` from the release file `path`, over the design `l1` as L1's."""
    monkeypatch.setattr(
        drift_building_phase, "design", lambda *a, **k: copy.deepcopy(l1)
    )
    return M.design(
        frame,
        held=held,
        ads=ads,
        amenities=amenities,
        registry=registry,
        releases=path,
        today=_today(),
    )


def test_rows_read_the_latest_release_out_a_week_before_their_month(tmp_path):
    dates = {
        "09v1": "2009-07-31",
        "17v1": "2018-01-31",
        "18v1": "2018-07-31",
        "22v1": "2022-06-30",
        "22v2": None,
        "22v3": "2022-11-21",
        "26v2": "2026-08-17",
    }
    parts = [
        _lots({"1000010001": LOTS_26["1000010001"]}, r, p) for r, p in dates.items()
    ]
    path = _write(tmp_path, *parts)
    published = M.published(path)
    assert list(published.index) == [r for r, p in dates.items() if p]
    rng = np.random.default_rng(1)
    days = rng.integers(0, 19 * 365, 3000)
    at = pd.Series(pd.Timestamp("2008-01-01", tz="UTC") + pd.to_timedelta(days, "D"))
    got = M.release_of(at, published)
    # The reference is the rule `b0coop.classes` gives each row its co-op class by.
    releases = pd.read_parquet(
        path, columns=["release", "bbl", "bldgclass", "published"]
    )
    frame = pd.DataFrame({"building": "b0", "price_at": at})
    want = b0coop.classes(frame, pd.Series({"b0": "1000010001"}), releases).release
    np.testing.assert_array_equal(got, want.fillna("").to_numpy(dtype=object))
    month = b0coop.months(at)
    usable = published + pd.Timedelta(days=7)
    for r in np.unique(got):
        rows = got == r
        if r == "":
            # A row priced before the first release is out reads none.
            assert (month[rows] < usable.iloc[0].to_datetime64()).all()
            continue
        # A row reads a release out a week before its month, and no later release is.
        assert (usable[r].to_datetime64() <= month[rows]).all()
        later = usable[usable.index[list(usable.index).index(r) + 1 :]]
        if len(later):
            assert (month[rows] < later.iloc[0].to_datetime64()).all()
    assert "22v2" not in set(got)
    # The day itself: 26v2, out 2026-08-17, reaches rows from September 2026.
    edge = pd.Series(pd.to_datetime(["2026-08-31", "2026-09-01"], utc=True))
    assert list(M.release_of(edge, published)) == ["22v3", "26v2"]


def test_a_lot_missing_from_its_release_reads_blank_and_an_unrecorded_field_reads_26v2(
    tmp_path,
):
    # 12v2 recorded no residential FAR on any lot, and does not hold the fourth lot.
    old = _lots(LOTS_20, "12v2", "2013-06-30").assign(residfar="")
    path = _write(
        tmp_path,
        old,
        _lots(LOTS_22, "22v2", None),
        _lots(LOTS_26, "26v2", "2026-08-17"),
    )
    frame, _, registry, _, _ = _frame()
    rows, table, from_today = M.lot_reads(frame, registry, path, _today())
    assert from_today == {"12v2": ["residfar"]}
    status = dict(zip(zip(frame.building, frame.price_at.dt.year), rows.status))
    assert status["b0", 2021] == "read" and status["b3", 2021] == "lot not in release"
    assert status["b3", 2026] == "read" and status["b4", 2021] == "lot not in release"
    assert status["b5", 2021] == "no lot"
    assert set(rows.release) == {"12v2", "26v2"}
    assert "1000010004|12v2" not in table.index
    # The residential FAR of 12v2's lots is 26v2's, and its other fields are its own.
    assert table.loc["1000010001|12v2", "residfar"] == "6.02"
    assert table.loc["1000010001|12v2", "numfloors"] == "11"
    # An empty string reads blank, and padding is stripped.
    assert table.loc["1000010001|12v2", "landmark"] is None
    assert table.loc["1000010001|12v2", "bldgclass"] == "C1"
    assert table.loc["1000010003|26v2", "resarea"] is None
    # Before the first release is out, every row reads none.
    early = M.lot_reads(
        frame.assign(price_at=pd.Timestamp("2012-01-01", tz="UTC")),
        registry,
        path,
        _today(),
    )[0]
    assert set(early.status) == {"no release", "no lot"}


def test_with_every_row_on_26v2_the_design_is_l1s(tmp_path, monkeypatch):
    frame, held, registry, ads, amenities = _frame()
    # 26v2 here is out before every row, so every row reads it.
    path = _write(tmp_path, _lots(LOTS_26, "26v2", "2000-01-01"))
    l1 = _l1(frame, held, registry, _today(), ads, amenities)
    d = _p1(monkeypatch, l1, frame, held, registry, ads, amenities, path)
    np.testing.assert_array_equal(d.x, l1.x)
    assert d.names == l1.names and d.count == l1.count
    rec = M.RECORD
    assert rec["rows_by_release"] == {"26v2": 36}
    assert all(v == {"train": 0, "held": 0} for v in rec["changed_rows"].values())
    assert set(rec["changed_rows"]) == set(l1.names) - {"unit:noise"} - {
        "bld:doorman_full",
        "bld:doorman_part",
        "bld:doorman_virtual",
        "bld:gym",
    }


def test_a_market_datasets_inputs_set_the_release_file_before_it_is_read(
    tmp_path, monkeypatch
):
    frame, held, registry, ads, amenities = _frame()
    path = _write(tmp_path, _lots(LOTS_26, "26v2", "2000-01-01"))
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / market.INPUTS).write_text(
        json.dumps({f"{M.__name__}.RELEASES": str(path)})
    )
    frame.attrs["dataset"] = str(dataset)
    # Recorded so that teardown puts back the constant the inputs repoint.
    monkeypatch.setattr(M, "RELEASES", M.RELEASES)
    l1 = _l1(frame, held, registry, _today(), ads, amenities)
    monkeypatch.setattr(
        drift_building_phase, "design", lambda *a, **k: copy.deepcopy(l1)
    )
    d = M.design(
        frame,
        held=held,
        ads=ads,
        amenities=amenities,
        registry=registry,
        today=_today(),
    )
    assert M.RECORD["releases"] == str(path)
    np.testing.assert_array_equal(d.x, l1.x)


def test_each_row_reads_l1s_columns_of_its_own_release(tmp_path, monkeypatch):
    frame, held, registry, ads, amenities = _frame()
    path = _write(
        tmp_path,
        _lots(LOTS_20, "20v1", "2020-02-29"),
        _lots(LOTS_22, "22v2", None),
        _lots(LOTS_26, "26v2", "2026-08-17"),
    )
    l1 = _l1(frame, held, registry, _today(), ads, amenities)
    # A building with no lot keeps L1's columns, whatever they hold.
    nolot = frame.building.eq("b5").to_numpy()
    l1.x[nolot, 2:] = 7.0
    d = _p1(monkeypatch, l1, frame, held, registry, ads, amenities, path)
    rows = M.lot_reads(frame, registry, path, _today())[0]
    for r in ("", "20v1", "26v2"):
        lots = _lots(LOTS_20 if r == "20v1" else LOTS_26, r, None)
        lots = lots.iloc[:0] if r == "" else lots
        for f in F:
            lots[f] = M.blank(lots[f]).astype(object)
        want = _l1(frame, held, registry, lots.assign(version=r), ads, amenities)
        on = rows.release.eq(r).to_numpy() & ~nolot
        np.testing.assert_array_equal(d.x[on], want.x[on], err_msg=r)
    np.testing.assert_array_equal(d.x[nolot], l1.x[nolot])
    x = pd.DataFrame(d.x, columns=d.names)
    year = frame.price_at.dt.year.to_numpy()
    b = frame.building.to_numpy()
    # The condo was a rental until 26v2 reached September 2026.
    at = frame.price_at.dt.strftime("%Y-%m").to_numpy()
    np.testing.assert_array_equal(x["bld:condo"][b == "b0"], at[b == "b0"] >= "2026-09")
    # The new building has no lot before 26v2, nor does any building before 20v1.
    new = (b == "b3") & (at < "2026-09")
    assert (x["bld:lot_unknown"][new | ((year == 2020) & ~nolot)] == 1).all()
    assert (x["bld:built_unknown"][new] == 1).all()
    assert (x["bld:lot_unknown"][(b == "b3") & (at >= "2026-09")] == 0).all()
    # The walk-up's penthouse ad reads its floor count of 20v1, four floors.
    ph = (b == "b1") & (year == 2023)
    assert x["unit:walkup_f4"][ph].item() == 1 and x["unit:walkup_top"][ph].item() == 1
    # No row reads 22v2, which carries no publication date.
    assert "22v2" not in set(rows.release)
    rec = M.RECORD
    assert rec["changed_rows"]["bld:condo"] == {"train": 4, "held": 0}


# The sha256 of every traced and kept array of the run below on the CPU. A deliberate change
# to the as-of reading or to L1's draws changes it.
ASOF_RUN_SHA256 = "71da1ee3fb5150090969930244013ad3c4e7c859ea2346c1c9d181143d15184b"


def test_an_as_of_design_draws_what_it_drew_when_pinned(tmp_path):
    full = tp._phased(n=400, per_unit=9)
    building = np.array([f"s{s}" for s in full.site], dtype=object)
    at = full.start + pd.to_timedelta(full.week * 7, "D")
    frame = pd.DataFrame({"building": building, "price_at": at.tz_localize("UTC")})
    sites = np.unique(full.site)
    bbl = {f"s{s}": (f"10{s:08d}" if s % 4 != 3 else None) for s in sites}
    registry = pd.DataFrame({"building": list(bbl), "bbl": list(bbl.values())})
    line = "40 50 3 5 6 - 1 {} 40000 12 2004 0 0 0 0"
    old = {f"10{s:08d}": line.format("C1" if s % 4 == 0 else "R4") for s in sites}
    old = {k: v for k, v in old.items() if int(k[2:]) % 4 in (0, 1)}
    new = {f"10{s:08d}": line.format("R4" if s % 4 < 2 else "R9") for s in sites}
    path = _write(
        tmp_path, _lots(old, "18v2", "2019-01-31"), _lots(new, "19v1", "2019-04-20")
    )
    rows, table, _ = M.lot_reads(frame, registry, path, _today())
    assert set(rows.release) == {"", "18v2", "19v1"}
    cls = table.bldgclass.reindex(rows.key).to_numpy(dtype=object)
    held = np.zeros(len(frame), bool)
    full, changed = M.put(
        full, {"bld:condo": b0coop.tenure(cls)[0]}, rows.bbl.eq("").to_numpy(), ~held
    )
    assert changed["bld:condo"]["train"] > 0
    train, _, _ = td._split(full)
    out = M.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == ASOF_RUN_SHA256


def test_the_model_is_l1_reading_mappluto_as_of_the_month():
    assert M.NAME == "drift-building-phase-plutoasof"
    assert M.LEVEL_DOF == drift_building_phase.LEVEL_DOF
    assert M.GROUPS == ("building",) and M.PHASES == drift_building_phase.PHASES
    assert M.run is drift_building.run and M.Design is drift_building.Design
    assert M.diagnostics is drift_building_phase.diagnostics
    assert str(M.RELEASES) == str(b0coop.RELEASES)
    assert '("drift-building-phase-plutoasof", "drift_building_phase_plutoasof")' in (
        open(run.__file__).read()
    )
    assert drift_pool.model_diagnostics({"model": {"name": M.NAME}}) is (
        drift.diagnostics
    )
    # Every field the lot table reads besides the lot and its version is read as of the
    # month.
    assert set(ks.PLUTO_FIELDS) - set(F) == {"bbl", "version"}
    d = tp._phased(n=300)
    M.RECORD.update(rows_by_release={"26v2": 1})
    rec = M.run_record(d)
    assert "phase" in rec and rec["pluto_asof"]["rows_by_release"] == {"26v2": 1}

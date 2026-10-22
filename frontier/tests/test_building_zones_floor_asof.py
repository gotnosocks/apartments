import numpy as np
import pandas as pd
import pytest
import test_building_zones_age as tbs
import test_building_zones_floor as tbf
import test_building_zones_gym as tby
import test_building_zones_unit as tbu

from rentfrontier import building_attrs, building_gym, splits, unit_features, unit_floor
from rentfrontier import building_zones_floor as bzf
from rentfrontier import building_zones_floor_asof as bzfa
from rentfrontier import building_zones_mundlak as bzm
from rentfrontier import building_zones_mundlak_asof as bzma

LABELS = ("4B", "12C", "3A", "2F", "25A", "1204", "PH", "GARDEN", "LL", "7")


def ads_for(frame, seed=21):
    """A pipeline row for each listing of `frame`: the page with a unit label, a stated size
    on about half, and building fields that vary between the building's ads."""
    rng = np.random.default_rng(seed)
    units = frame.unit_id.astype(str).drop_duplicates().to_numpy()
    label = dict(zip(units, rng.choice(LABELS, len(units))))
    blds = frame.building.astype(str).drop_duplicates().to_numpy()
    count = dict(zip(blds, rng.integers(3, 40, len(blds)).astype(float)))
    elev = dict(zip(blds, rng.random(len(blds))))
    n = len(frame)
    lab = frame.unit_id.astype(str).map(label)
    b = frame.building.astype(str)
    floor = np.array([unit_features.floor_and_line(s)[0] for s in lab])
    floor[rng.random(n) < 0.1] = np.nan
    p = b.map(elev).to_numpy()
    u = rng.random(n)
    elevator = np.where(u < 0.2, None, np.where(u < 0.2 + 0.8 * p, True, False))
    return pd.DataFrame(
        {
            "listing_id": frame.listing_id.astype(str).to_numpy(),
            "page": ("https://streeteasy.com/building/" + b + "/" + lab.str.lower()),
            "square_feet": np.where(
                rng.random(n) < 0.5, rng.normal(800, 250, n).clip(50), np.nan
            ),
            "building_floor_count": b.map(count).to_numpy()
            + rng.integers(-1, 2, n) * (rng.random(n) < 0.2),
            "listed_floor": floor,
            "elevator": elevator.astype(object),
            "doorman_type": rng.choice(
                ["full_time", "part_time", "virtual", "unspecified", None],
                n,
                p=[0.2, 0.1, 0.15, 0.1, 0.45],
            ),
        }
    )


def amenities_for(ads, seed=22):
    """Amenity flags for most listings, a gym on about a third of them."""
    rng = np.random.default_rng(seed)
    ids = ads.listing_id.to_numpy()
    ids = ids[rng.random(len(ids)) < 0.95]
    states = rng.random(len(ids)) < 0.9
    return pd.DataFrame(
        {
            "listing_id": ids,
            "states": states,
            "gym": states & (rng.random(len(ids)) < 0.35),
        }
    )


def lots_for(frame, seed=23):
    """A lot row for most buildings, some with no floor count or class."""
    rng = np.random.default_rng(seed)
    b = frame.building.astype(str).drop_duplicates().to_numpy()
    b = b[rng.random(len(b)) < 0.8]
    n = len(b)
    floors = rng.integers(2, 30, n).astype(float)
    floors[rng.random(n) < 0.3] = np.nan
    return pd.DataFrame(
        {
            "numfloors": floors,
            "bldgclass": rng.choice(["D1", "C4", "R4", "R2", "A1", ""], n),
            "yearbuilt": rng.integers(1890, 2020, n).astype(float),
        },
        index=pd.Index(b, name="building"),
    )


def toy(n=1200, seed=3):
    frame = tbf.tba._nyc_frame(n, 30, seed)
    ads = ads_for(frame)
    return frame, ads, amenities_for(ads), lots_for(frame)


def features(frame, ads, amenities, lots, held):
    """Each row's size, building and floor values under the as-of rebuild."""
    rows = bzfa.ad_rows(frame, ads)
    t = bzfa.tables_for(
        frame, held, ads, amenities, lots, tbu.tables_for(frame)[0].iloc[:0]
    )
    b = rows.building
    a = t["attrs"].set_index("building").reindex(b)
    g = t["gyms"].set_index("building").reindex(b)
    f = t["floors"].set_index("listing_id").reindex(rows.listing_id)
    u = t["units"].set_index("listing_id").reindex(rows.listing_id)
    return pd.DataFrame(
        {
            "sqft": u.sqft.to_numpy(),
            "size_source": u.size_source.to_numpy(),
            "log_size_rel": u.log_size_rel.to_numpy(),
            "elevator": a.elevator.to_numpy(),
            "doorman": a.doorman.to_numpy(),
            "floors": a.floors.to_numpy(),
            "gym": g.gym.to_numpy(),
            "top": f.top.to_numpy(),
            "floor": f.floor.to_numpy(),
        }
    )


def perturb(ads, amenities, ids, seed=5):
    """`ads` and `amenities` with every source field of listings `ids` redrawn."""
    rng = np.random.default_rng(seed)
    ads, amenities = ads.copy(), amenities.copy()
    on = ads.listing_id.isin(ids).to_numpy()
    k = int(on.sum())
    ads.loc[on, "square_feet"] = rng.uniform(150, 5000, k)
    ads.loc[on, "elevator"] = pd.Series(rng.random(k) < 0.5, dtype=object).to_numpy()
    ads.loc[on, "doorman_type"] = "full_time"
    ads.loc[on, "building_floor_count"] = 99.0
    ads.loc[on, "listed_floor"] = 98.0
    on = amenities.listing_id.isin(ids)
    amenities.loc[on, "states"] = True
    amenities.loc[on, "gym"] = True
    return ads, amenities


def test_held_out_rows_ignore_other_held_out_ads():
    frame, ads, amenities, lots = toy()
    held = splits.latest_split(frame)
    assert held.sum() > 20
    base = features(frame, ads, amenities, lots, held)
    lid = frame.listing_id.astype(str).to_numpy()
    for r in np.flatnonzero(held)[:15]:
        others = set(lid[held]) - {lid[r]}
        a2, m2 = perturb(ads, amenities, others)
        got = features(frame, a2, m2, lots, held)
        pd.testing.assert_series_equal(got.iloc[r], base.iloc[r])
    # The perturbation reaches the held-out rows' own sizes, so the check has teeth.
    a2, m2 = perturb(ads, amenities, set(lid[held]))
    got = features(frame, a2, m2, lots, held)
    assert not got.sqft[held].equals(base.sqft[held])


def test_sizes_ignore_later_rows():
    frame, ads, amenities, lots = toy()
    held = splits.latest_split(frame)
    base = features(frame, ads, amenities, lots, held)
    at = pd.to_datetime(frame.price_at).dt.floor("D").to_numpy()
    lid = frame.listing_id.astype(str).to_numpy()
    for r in np.flatnonzero(held)[:15]:
        later = set(lid[at > at[r]])
        a2, m2 = perturb(ads, amenities, later)
        got = features(frame, a2, m2, lots, held)
        assert got.size_source[r] == base.size_source[r]
        np.testing.assert_allclose(got.sqft[r], base.sqft[r])


def test_all_training_rows_reproduce_the_snapshot_rules():
    frame, ads, amenities, lots = toy()
    held = np.zeros(len(frame), bool)
    rows = bzfa.ad_rows(frame, ads)
    t = bzfa.tables_for(frame, held, ads, amenities, lots, tbu.tables_for(frame)[0])
    pipe = rows[["listing_id", "building", *bzfa.AD_FIELDS]]
    want = building_attrs.attributes(building_attrs.ad_attributes(pipe), lots)
    pd.testing.assert_frame_equal(t["attrs"], want)
    want = building_gym.building_table(pipe, amenities)
    pd.testing.assert_frame_equal(t["gyms"], want)
    registry = pd.DataFrame(
        {"building": lots.index, "bbl": np.arange(len(lots)).astype(str)}
    )
    pluto = pd.DataFrame({"bbl": registry.bbl, "numfloors": lots.numfloors.to_numpy()})
    want = unit_floor.floor_table(pipe, unit_floor.top_floors(pipe, registry, pluto))
    pd.testing.assert_frame_equal(t["floors"], want)


def test_sizes_match_the_snapshot_where_dates_do_not_matter():
    """Each unit states a size on its first listing only, a day before the others, so the
    unit fill reads the same size either way."""
    frame, ads, _, _ = toy()
    # Three units a building, so most units list more than once.
    pick = np.random.default_rng(4).integers(0, 3, len(frame)).astype(str)
    frame = frame.assign(unit_id=frame.building.astype(str) + "-" + pick)
    frame = frame.sort_values(["unit_id", "price_at"]).reset_index(drop=True)
    first = ~frame.unit_id.duplicated().to_numpy()
    day = pd.to_datetime(frame.price_at).dt.floor("D")
    frame = frame[first | (day > day.groupby(frame.unit_id).transform("min"))]
    frame = frame.reset_index(drop=True)
    first = ~frame.unit_id.duplicated().to_numpy()
    ads = ads.set_index("listing_id").loc[frame.listing_id.astype(str)].reset_index()
    ads["square_feet"] = np.where(first, 400.0 + 3 * np.arange(len(ads)), np.nan)
    # A label of its own for each unit, so the snapshot's units are the frame's.
    code = pd.factorize(frame.unit_id)[0]
    ads["page"] = "https://streeteasy.com/building/b/u" + pd.Series(code).astype(str)
    rows = bzfa.ad_rows(frame, ads)
    got = bzfa.size_table(rows, np.ones(len(rows), bool))
    snap = unit_features.sizes(rows.assign(unit_id=rows.unit_id))
    stated_or_unit = np.isin(snap.size_source, ["stated", "unit"])
    assert stated_or_unit.sum() > 100 and (snap.size_source == "unit").sum() > 20
    np.testing.assert_array_equal(
        got.size_source[stated_or_unit], snap.size_source[stated_or_unit]
    )
    np.testing.assert_allclose(got.sqft[stated_or_unit], snap.sqft[stated_or_unit])
    np.testing.assert_allclose(
        got.log_size_rel[stated_or_unit], snap.log_size_rel[stated_or_unit], atol=1e-12
    )


def _designs():
    frame, tables, units, trucks = tbu._design()
    attrs = tables.pop("attrs")
    ads = ads_for(frame)
    held = splits.latest_split(frame)
    kw = dict(units=units, trucks=trucks, ages=tbs.ages_for(frame), **tables)
    asof = bzfa.design(
        frame,
        held=held,
        ads=ads,
        amenities=amenities_for(ads),
        lots=lots_for(frame),
        **kw,
    )
    floor = bzf.design(
        frame,
        attrs=attrs,
        gyms=tby.gyms_for(frame),
        floors=tbf.floors_for(frame),
        **kw,
    )
    return frame, held, ads, asof, floor


def test_design_has_the_floor_models_columns():
    """Both designs drop a column with no nonzero row, so on toy data they differ only in
    columns one of them drops."""
    _, _, _, asof, floor = _designs()
    shared = [n for n in asof.names if n in floor.names]
    assert shared == [n for n in floor.names if n in asof.names]
    assert len(shared) > 30
    for n in set(asof.names) ^ set(floor.names):
        d = floor if n in asof.names else asof
        assert d.count.get(n, 0) == 0, n
    assert asof.x.shape[0] == floor.x.shape[0]


def test_design_needs_the_held_out_rows(monkeypatch):
    frame, ads, amenities, lots = toy()
    monkeypatch.setattr(bzfa, "SPLIT", None)
    with pytest.raises(ValueError, match="held-out"):
        bzfa.design(frame, ads=ads, amenities=amenities, lots=lots)
    monkeypatch.setattr(bzfa, "SPLIT", "latest")
    np.testing.assert_array_equal(bzfa.held_out(frame), splits.latest_split(frame))


def test_mundlak_means_read_training_rows_only():
    frame, held, _, asof, _ = _designs()
    x = asof.x.copy()
    new = bzma.columns(x, list(asof.names), asof.site, ~held)
    # Changing held-out rows' unit columns leaves every mean as it was.
    j = asof.names.index("unit:log_size_rel")
    x[held, j] += 1.0
    np.testing.assert_allclose(bzma.columns(x, list(asof.names), asof.site, ~held), new)
    # With no row held out the means are the building means model's.
    np.testing.assert_allclose(
        bzma.columns(asof.x, list(asof.names), asof.site, np.ones(len(x), bool)),
        bzm.columns(asof.x, list(asof.names), asof.site),
    )

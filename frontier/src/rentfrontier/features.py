"""Named feature sets, kept separate from model designs.

A feature set maps the flat table plus a training mask to a matrix of named,
grouped columns on the log-rent scale. Anything estimated from data (reference
medians, category levels) uses training rows only. Unknown is always its own
level or indicator, never folded into "no".

Each set has an id that runs record. Change a set's behaviour by adding a new
id, so older leaderboard entries stay reproducible from their commit anyway.
"""

from __future__ import annotations

import contextvars
import functools
import itertools
import json
import math
import re
from dataclasses import dataclass
from functools import partial

import numpy as np
import pandas as pd

from . import data as data_module


@dataclass
class Features:
    id: str
    names: list[str]
    groups: list[str]  # contribution group per column, e.g. "bedrooms"
    values: np.ndarray  # (rows, columns) float64
    prior_scale: np.ndarray  # per-column normal prior sd on log scale

    def group_names(self) -> list[str]:
        return list(dict.fromkeys(self.groups))


class _Builder:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.names: list[str] = []
        self.groups: list[str] = []
        self.columns: list[np.ndarray] = []
        self.scales: list[float] = []

    def add(self, group: str, name: str, values, scale: float = 1.0):
        values = np.asarray(values, dtype=np.float64)
        if values.shape != (len(self.frame),) or not np.isfinite(values).all():
            raise ValueError(f"Bad feature column {name}")
        self.names.append(name)
        self.groups.append(group)
        self.columns.append(values)
        self.scales.append(scale)

    def categorical(self, group: str, column, reference: str, scale: float = 1.0):
        series = self.frame[column] if isinstance(column, str) else column
        for level in sorted(set(series.unique()) - {reference}):
            self.add(group, f"{group}={level}", series.eq(level), scale)

    def build(self, id: str) -> Features:
        return Features(
            id,
            self.names,
            self.groups,
            np.column_stack(self.columns),
            np.asarray(self.scales),
        )


# The unit's label is the last path element of its StreetEasy URL
# (".../building/chelsea-stratus/23c"); upper-case regexes.
UNIT_LABEL_FLAGS = {
    "penthouse": r"^PH|PENTHOUSE",
    "garden": r"GARDEN|GDN|^GF$|^GRDN|^GARD",
    "lower_level": r"BSMT|BASEMENT|^LL|LOWER|^CELLAR",
}


def label_floor_number(frame: pd.DataFrame) -> pd.Series:
    """The floor a unit label states: "23C", "APT-4B", "4TH" -> 23, 4, 4; "307" -> 3."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.upper()
    lettered = label.str.extract(r"^(?:APT-?)?(\d{1,2})[A-Z]{1,2}$")[0]
    numbered = label.str.extract(r"^(\d)\d\d$")[0]
    return lettered.fillna(numbered).astype(float)


def _bedroom_label(count):
    return count.astype(int).map(lambda b: "5+" if b >= 5 else str(b))


def unit_bedrooms(frame: pd.DataFrame) -> pd.Series:
    """Each unit's bedroom count: the lower median of its listings' counts.

    12% of units listed more than once change bedroom count between listings,
    mostly by one with the same square footage: the same apartment advertised
    as a studio or a junior one-bedroom, a one-bedroom or a flex two. Within
    those units the ask moves about 0.14 in log rent per relabelled bedroom,
    against 0.26 between a studio and a one-bedroom in the same building and
    year. Bedrooms are a feature, so the unit's other listings leak no outcome.
    """
    beds = frame.bedrooms.round().clip(0, 5)
    return np.floor(beds.groupby(frame.unit_id).transform("median"))


def base_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "base-v1",
    by_unit: bool = False,
    unit_size: bool = False,
    unit_labels: bool = False,
    label_floor: bool = False,
) -> Features:
    """Listing attributes as advertised, with explicit unknown levels.

    by_unit ("unitbeds-v1"): the bedroom levels (and the size baseline) use the
    unit's bedroom count, and `bedrooms_vs_unit` carries the listing's own
    count less the unit's.
    unit_size ("unitattrs-v1"): square feet are the unit's, the median of the
    sizes its listings state. Only 35% of rows state a size; filling from the
    unit's other listings covers 48%.
    unit_labels ("unitlabels-v1"): flags from the unit's StreetEasy label
    (UNIT_LABEL_FLAGS): penthouse, garden and lower-level units. Penthouses ask
    12% more than other units of the same building, year and bedrooms.
    label_floor ("unitfloor-v2"): the floor, when the listing states none, from
    the unit's label ("23C" -> 23, "307" -> 3). Where both exist they agree on
    all 33,270 rows. A label floor is used only if the building (MapPLUTO) has
    that many floors, give or take 2: in 121 buildings the label's number is
    not a floor ("24A" in a 4-storey building), and filling those
    (abca5b7, unchecked) gave 16 divergences.
    """
    b = _Builder(frame)
    advertised = frame.bedrooms.round().clip(0, 5)
    count = unit_bedrooms(frame) if by_unit else advertised
    beds = _bedroom_label(count)
    b.categorical("bedrooms", beds, reference="1")
    if by_unit:
        b.add("bedrooms", "bedrooms_vs_unit", advertised - count)

    full = frame.full_baths.clip(1, 4).map(lambda n: "4+" if n >= 4 else str(n))
    b.categorical("bathrooms", full.rename("full"), reference="1")
    half = frame.half_baths.map(
        lambda n: "unknown" if pd.isna(n) else ("2+" if n >= 2 else str(int(n)))
    )
    b.categorical("bathrooms", "half=" + half, reference="half=0")

    # Size: log square feet relative to the training median for the same
    # bedroom count. Unknown size gets its own indicator and zero deviation.
    sqft = frame.square_feet
    if unit_size:
        sqft = (
            sqft.where(sqft.between(150, 8000))
            .groupby(frame.unit_id)
            .transform("median")
        )
    known = sqft.between(150, 8000)
    log_sqft = np.log(sqft.where(known))
    median = log_sqft[train & known.to_numpy()].groupby(beds[train]).median()
    deviation = (log_sqft - beds.map(median)).where(known, 0.0).fillna(0.0)
    b.add("size", "log_sqft_vs_bedroom_median", deviation)
    b.add("size", "sqft_unknown", ~known)

    # Advertised floor label (a proxy, not a verified physical floor).
    floor = frame.listed_floor.astype("float")
    if label_floor:
        label = label_floor_number(frame)
        height = pd.to_numeric(building_lots(frame).numfloors, errors="coerce")
        label = label.where(label.le(height.to_numpy() + 2))
        floor = floor.where(floor.ge(1), label)
    floor_known = floor.ge(1)
    log_floor = np.log(floor.where(floor_known, 1.0))
    b.add("floor", "log_floor", log_floor)
    b.add("floor", "log_floor_above_6", np.maximum(0, log_floor - np.log(6)))
    b.add("floor", "log_floor_above_15", np.maximum(0, log_floor - np.log(15)))
    b.add("floor", "floor_unknown", ~floor_known)
    b.add("floor", "log_floor_x_no_elevator", log_floor * frame.elevator.eq("no"))

    b.categorical("elevator", "elevator", reference="yes")
    b.categorical("doorman", "doorman", reference="unknown")
    b.categorical("laundry", "laundry", reference="in_building")
    hvac = frame.hvac.where(frame.hvac.isin(["central_ac", "unknown"]), "other")
    b.categorical("hvac", hvac, reference="unknown")
    b.categorical("pets", "pets", reference="unknown")
    for name in data_module.VIEWS:
        b.add("views", f"view_{name}", frame[f"view_{name}"].eq("yes"))
    for name in data_module.WINDOWS:
        b.add("windows", f"window_{name}", frame[f"window_{name}"].eq("yes"))
    if unit_labels:
        label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.upper()
        for name, pattern in UNIT_LABEL_FLAGS.items():
            b.add(
                "unit label", f"label:{name}", label.str.contains(pattern, regex=True)
            )
    b.add(
        "price_basis",
        "current_capture_ask",
        frame.price_basis.ne("historical_initial_own_advertisement_ask"),
    )
    return b.build(id)


# Description flags: a mention in the listing's own advertisement text. "Not
# mentioned" is the reference; a missing description has its own indicator,
# so unknown is never read as "no". Patterns are lower-case regexes.
DESCRIPTION_FLAGS = {
    "renovated": r"renovat|brand[- ]new (?:kitchen|bath)",
    "dishwasher": r"dish ?washer",
    "washer_dryer_in_unit": r"washer.{0,15}dryer.{0,20}(?:in|inside).{0,10}(?:unit|apartment|residence)|in[- ]unit (?:washer|laundry|w/?d)|\bw/d\b",
    "no_fee": r"\bno (?:broker )?fee",
    "furnished": r"(?<!un)furnished",
    "concession": r"\b(?:one|two|1|2|3|\d\.?\d?) months? free|net effective|free rent|concession",
    "income_restricted": r"income restrict|affordable housing|housing lottery|\bami\b",
    "rent_stabilized": r"rent[- ]stabiliz",
    "private_outdoor": r"private (?:outdoor|terrace|balcony|roof|garden|patio|backyard)|(?:your|its) own (?:terrace|balcony|garden|patio|backyard)",
    "shared_space": r"shared (?:bath|kitchen)|\bsro\b|roommate",
    "luxury": r"\bluxury\b",
    "flex_convertible": r"\bflex\b|convertible",
    "duplex": r"\bduplex|triplex",
    "walkup_text": r"walk[- ]?up",
    "high_ceilings": r"high ceiling|soaring ceiling|(?:1[0-9]|[89])[- ]?(?:ft|foot|feet|') ceiling",
    "exposed_brick": r"exposed brick",
    "fireplace": r"fireplace",
    "outdoor_shared": r"(?:shared|common|communal) (?:roof|garden|terrace|courtyard)|roof ?deck",
    "gym": r"\bgym\b|fitness (?:center|room)",
    "short_term": r"short[- ]term|month[- ]to[- ]month|\bsublet",
}


def desc_v1(
    frame: pd.DataFrame, train: np.ndarray, id: str = "desc-v1", base: str = "base-v1"
) -> Features:
    """A base set (base-v1) plus flags from the listing's own advertisement
    description."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    text = descriptions.attach(frame)
    known = text.str.len() > 20
    b = _Builder(frame)
    b.add("description", "description_missing", ~known)
    for name, pattern in DESCRIPTION_FLAGS.items():
        b.add(
            "description",
            f"text:{name}",
            known & text.str.contains(pattern, regex=True),
        )
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# External snapshots read by feature sets (rentfrontier.registry, .external).
REGISTRY_SNAPSHOT = "/data1/apartments/external/registry/20260925-6b67137"
PLUTO_SNAPSHOT = "/data1/apartments/external/pluto/20260925-3096a62"
REGISTRY_FILE = f"{REGISTRY_SNAPSHOT}/buildings.parquet"
PLUTO_FILE = f"{PLUTO_SNAPSHOT}/pluto.parquet"
# The registry with 11 pages re-geocoded from their ads' addresses
# (config/reviews/registry-overrides-20260930.json), and MapPLUTO for its lots.
REGISTRY_V2_FILE = (
    "/data1/apartments/external/registry/20260930-4d41f8b/buildings.parquet"
)
PLUTO_V2_FILE = "/data1/apartments/external/pluto/20260930-4d41f8b/pluto.parquet"
# That registry with Avalon West Chelsea also re-geocoded from its ads
# (config/reviews/registry-overrides-20260930-avalon.json), and MapPLUTO for its lots.
REGISTRY_V3_FILE = (
    "/data1/apartments/external/registry/20260930-676c382/buildings.parquet"
)
PLUTO_V3_FILE = "/data1/apartments/external/pluto/20260930-676c382/pluto.parquet"
# Which registry and MapPLUTO snapshots building_lots reads while a feature set
# is built (`build`); feature sets not listed in LOT_SNAPSHOTS read the first.
_LOTS: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "lots", default=None
)
SUBWAY_SNAPSHOT = "/data1/apartments/external/subway/20260929-8e7c364"
SUBWAY_FILE = f"{SUBWAY_SNAPSHOT}/subway.parquet"
# Street centerlines, parks and shoreline (`rentfrontier.external basemap`).
BASEMAP_SNAPSHOT = "/data1/apartments/external/basemap/20260929-da7e40d"
BASEMAP_FILE = f"{BASEMAP_SNAPSHOT}/basemap.parquet"
# Building outlines, the registry's and their neighbours' (`rentfrontier.external footprints`).
FOOTPRINTS_SNAPSHOT = "/data1/apartments/external/footprints/20260930-6634906"
FOOTPRINTS_FILE = f"{FOOTPRINTS_SNAPSHOT}/footprints.parquet"
# HPD housing-code violations of the registry's buildings (`rentfrontier.external hpd`).
HPD_SNAPSHOT = "/data1/apartments/external/hpd/20260930-cb289ad"
HPD_FILE = f"{HPD_SNAPSHOT}/hpd.parquet"
ERAS = (
    (0, 1900, "pre-1900"),
    (1900, 1930, "1900-1929"),
    (1930, 1960, "1930-1959"),
    (1960, 1990, "1960-1989"),
    (1990, 2010, "1990-2009"),
    (2010, 3000, "2010+"),
)


def building_lots(frame: pd.DataFrame) -> pd.DataFrame:
    """MapPLUTO attributes of each row's building (one row per listing row)."""
    registry_file, pluto_file = _LOTS.get() or (REGISTRY_FILE, PLUTO_FILE)
    registry = pd.read_parquet(registry_file)
    pluto = pd.read_parquet(pluto_file).set_index("bbl")
    lot = registry.set_index("building").bbl.reindex(frame.building.to_numpy())
    return pluto.reindex(lot.to_numpy()).reset_index(drop=True)


def pluto_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "pluto-v1",
    base: str = "base-v1",
    flood_zone: bool = True,
    latest_alteration: bool = False,
) -> Features:
    """A base set (base-v1) plus the building's MapPLUTO attributes
    (building-level). `flood_zone=False` leaves out the 2015 flood-zone flag,
    which in Chelsea marks the western blocks (location), not flood risk.
    `latest_alteration=True` dates "altered since 2000" by the later of the
    lot's two recorded alterations; yearalter1 alone misses an alteration in
    2000 or later recorded only in yearalter2."""
    base = FEATURE_SETS[base](frame, train)
    lot = building_lots(frame)
    num = {
        c: pd.to_numeric(lot[c], errors="coerce")
        for c in (
            "yearbuilt",
            "yearalter1",
            "yearalter2",
            "numfloors",
            "unitsres",
            "resarea",
            "builtfar",
            "lotfront",
        )
    }
    b = _Builder(frame)
    year = num["yearbuilt"]
    era = pd.Series("unknown", index=lot.index)
    for lo, hi, name in ERAS:
        era[(year >= lo) & (year < hi) & (year > 0)] = name
    b.categorical("building era", era, reference="1900-1929")

    def centred_log(v, known):
        """log of the known values minus their training mean; 0 when unknown."""
        logs = np.log(v.where(known))
        return (logs - float(np.nanmean(logs[train]))).fillna(0.0)

    for col in ("numfloors", "unitsres"):
        v = num[col]
        known = v > 0
        b.add("building size", f"log_{col}", centred_log(v, known))
        b.add("building size", f"{col}_unknown", ~known)
    per_unit = num["resarea"] / num["unitsres"]
    known = (per_unit > 100) & (per_unit < 10000)
    log_per_unit = np.log(per_unit.where(known))
    centre = float(np.nanmedian(log_per_unit[train]))
    b.add("building size", "log_res_area_per_unit", (log_per_unit - centre).fillna(0.0))
    b.add("building size", "res_area_per_unit_unknown", ~known)
    far = num["builtfar"]
    b.add("building size", "log_built_far", centred_log(far, far > 0))
    b.add("building size", "built_far_unknown", ~(far > 0))
    family = (
        lot.bldgclass.fillna("?")
        .str[0]
        .map(lambda c: c if c in ("C", "D", "R", "S") else "other")
    )
    b.categorical("building class", family, reference="D")
    b.add("building status", "landmark", lot.landmark.notna())
    b.add("building status", "historic_district", lot.histdist.notna())
    if flood_zone:
        b.add("building status", "flood_zone_2015", lot.pfirm15_flag.notna())
    altered = num["yearalter1"]
    if latest_alteration:
        altered = pd.concat([altered, num["yearalter2"]], axis=1).max(axis=1)
    b.add("building status", "altered_since_2000", altered >= 2000)
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# The location surface: Gaussian bumps LOCATION_SPACING_M apart (and as wide)
# over the buildings' registry coordinates, scaled so the surface's prior sd is
# about beta_sd * LOCATION_SCALE (0.15 in log rent) on average over the buildings
# (lower at the map's edges).
LOCATION_SPACING_M = 250.0
LOCATION_SCALE = 0.3


def building_xy(buildings) -> np.ndarray:
    """(n, 2) east and north metres of buildings (registry coordinates) from
    the registry's centre."""
    registry = pd.read_parquet(REGISTRY_FILE).set_index("building")
    lat0, lon0 = registry.latitude.mean(), registry.longitude.mean()
    lat = registry.latitude.reindex(buildings).to_numpy()
    lon = registry.longitude.reindex(buildings).to_numpy()
    metres = 111_320.0
    return np.column_stack(
        [(lon - lon0) * metres * np.cos(np.radians(lat0)), (lat - lat0) * metres]
    )


def location_bumps(xy: np.ndarray, sites: np.ndarray) -> np.ndarray:
    """(len(xy), k) bump values at points xy for bumps on a square grid that
    covers `sites` (each kept bump centre is within one spacing of a site),
    normalised so the mean over sites of the sum of squared bumps is 1."""
    h = LOCATION_SPACING_M
    lo, hi = sites.min(0) - h, sites.max(0) + h
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + h, h), np.arange(lo[1], hi[1] + h, h))
    centres = np.column_stack([gx.ravel(), gy.ravel()])
    near = ((sites[:, None, :] - centres[None]) ** 2).sum(-1).min(0) <= h**2
    centres = centres[near]

    def bumps(points):
        d2 = ((points[:, None, :] - centres[None]) ** 2).sum(-1)
        return np.exp(-d2 / (2 * h**2))

    norm = np.sqrt((bumps(sites) ** 2).sum(1).mean())
    return bumps(xy) / norm


def location_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "location-v1",
    base: str = "base-v1",
) -> Features:
    """A base set plus a smooth location surface over the map: what buildings
    nearby rent for (building-level)."""
    base = FEATURE_SETS[base](frame, train)
    registry = pd.read_parquet(REGISTRY_FILE)
    sites = building_xy(registry.building)
    sites = sites[np.isfinite(sites).all(1)]
    xy = building_xy(frame.building.to_numpy())
    known = np.isfinite(xy).all(1)
    values = np.zeros((len(frame), 0))
    if known.any():
        values = np.where(known[:, None], location_bumps(np.nan_to_num(xy), sites), 0.0)
    b = _Builder(frame)
    for k in range(values.shape[1]):
        b.add("location", f"location_{k:02d}", values[:, k], scale=LOCATION_SCALE)
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


WALK_M_PER_MIN = 80.0
TRANSIT_WALK_M = 800.0  # a 10-minute walk
# Station stops that opened after the data begin (2010) and are close enough to a
# registry building to change a value, by GTFS stop id. A listing counts a stop
# only if it opened before the listing's month began (no future information).
# 726: 34 St-Hudson Yards (7), opened 2015-09-13. Later openings farther away
# (72, 86 and 96 St on the Q, 2017; WTC Cortlandt, reopened 2018) are beyond
# 800 m of every registry building and never the nearest stop, so they are left out.
STOP_OPENED = {"726": "2015-09-13"}


def stops_not_open(month) -> frozenset:
    """GTFS ids of the stops that had not opened when `month` began."""
    start = pd.Timestamp(month).replace(day=1)
    return frozenset(s for s, day in STOP_OPENED.items() if pd.Timestamp(day) >= start)


def building_transit(buildings, exclude=frozenset()) -> pd.DataFrame:
    """Per building (registry coordinates): metres to the nearest subway
    station stop and the distinct daytime routes stopping within
    TRANSIT_WALK_M (straight-line distances), without the stops in `exclude`
    (GTFS ids)."""
    registry = pd.read_parquet(REGISTRY_FILE).set_index("building")
    stops = pd.read_parquet(SUBWAY_FILE)
    stops = stops[~stops.gtfs_stop_id.isin(exclude)].reset_index(drop=True)
    lat0 = registry.latitude.mean()
    metres, cos = 111_320.0, np.cos(np.radians(lat0))

    def xy(lat, lon):
        return np.column_stack(
            [np.asarray(lon) * metres * cos, np.asarray(lat) * metres]
        )

    b = xy(registry.latitude, registry.longitude)
    s = xy(stops.gtfs_latitude, stops.gtfs_longitude)
    d = np.sqrt(((b[:, None, :] - s[None]) ** 2).sum(-1))
    routes = stops.daytime_routes.fillna("").str.split()
    n_routes = [len(set().union(*routes[row <= TRANSIT_WALK_M])) for row in d]
    table = pd.DataFrame(
        {"subway_m": d.min(1), "routes_10min": n_routes}, index=registry.index
    )
    return table.reindex(buildings).reset_index(drop=True)


def transit_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "transit-v2",
    base: str = "base-v1",
) -> Features:
    """A base set plus transit access as of each listing's month: the walk to
    the nearest subway station and the subway routes within a 10-minute walk
    (building-level, changing when a station opens)."""
    base = FEATURE_SETS[base](frame, train)
    closed = frame.period.map(stops_not_open)
    t = pd.DataFrame(index=range(len(frame)), columns=["subway_m", "routes_10min"])
    for exclude in closed.unique():
        rows = (closed == exclude).to_numpy()
        part = building_transit(frame.building.to_numpy()[rows], exclude)
        t.loc[rows] = part.to_numpy()
    known = t.subway_m.notna().to_numpy()
    walk = np.log(np.maximum(t.subway_m.to_numpy(dtype=float) / WALK_M_PER_MIN, 1.0))
    routes = np.log1p(t.routes_10min.to_numpy(dtype=float))
    b = _Builder(frame)
    for name, v in (("log_walk_min_to_subway", walk), ("log1p_routes_10min", routes)):
        centre = float(np.mean(v[train & known]))
        # A building without coordinates (none in the registry today) sits at the mean.
        b.add("transit", name, np.where(known, v - centre, 0.0))
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Which way an apartment faces: the building's frontage (the street of its
# address, and which side of it the building stands on) against the apartment's
# window exposures, front/rear unit labels and ad text, pooled over the unit's
# listings. Manhattan's grid runs FRONTAGE_BEARING_DEG east of true north; a
# front on the grid's north or south lands on the same compass point either way.
FRONTAGE_BEARING_DEG = 29.0
WIDE_STREETS = frozenset({14, 23, 34})  # Chelsea's wide two-way crosstown streets
_SIDE_ADDRESS = re.compile(r"^\d+[A-Z]?(?:-\d+)?\s+WEST\s+(\d+)\s+STREET")
ORDINAL_AVENUES = {
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
    "EIGHTH": 8,
    "NINTH": 9,
    "TENTH": 10,
    "ELEVENTH": 11,
    "TWELFTH": 12,
}
_AVENUE_ADDRESS = re.compile(
    r"^\d+[A-Z]?(?:-\d+)?\s+(\d+|" + "|".join(ORDINAL_AVENUES) + r")\s+AVENUE"
)
_AMERICAS = re.compile(r"AVENUE OF (THE )?AMERICAS|AMERICAS AVENUE")
FRONT_TEXT = (
    r"street[- ]facing|facing the street|faces the street|front[- ]facing"
    r"|avenue[- ]facing|facing (?:the )?avenue"
    r"|overlook(?:s|ing) (?:the )?(?:avenue|street|\d+(?:st|nd|rd|th) street)"
)
REAR_TEXT = (
    r"rear[- ]facing|back of the building|courtyard[- ]facing|faces the courtyard"
    r"|facing the courtyard|quiet (?:rear|back)|garden[- ]facing|facing the garden"
    r"|back[- ]facing|faces the back"
)
THROUGH_TEXT = r"floor[- ]?through"  # windows at the front and the back
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def frontage_street(label: str):
    """(centerline name, street type, axis) of an address label, or Nones."""
    address = str(label).upper().split(",")[0]
    if m := _SIDE_ADDRESS.match(address):
        n = int(m.group(1))
        kind = "wide street" if n in WIDE_STREETS else "side street"
        return f"W  {n} ST", kind, "crosstown"
    if _AMERICAS.search(address):
        return "AVE OF THE AMERICAS", "avenue", "avenue"
    if m := _AVENUE_ADDRESS.match(address):
        n = ORDINAL_AVENUES.get(m.group(1)) or int(m.group(1))
        # Sixth Avenue's centerlines are named Avenue of the Americas.
        name = "AVE OF THE AMERICAS" if n == 6 else f"{n} AVE"
        return name, "avenue", "avenue"
    return None, None, None


@functools.lru_cache(maxsize=1)
def building_frontage() -> pd.DataFrame:
    """Per registry building: its frontage street type (avenue, wide street,
    side street) and the grid direction its front faces (the side of its
    address street it stands on, from the street's centerline)."""
    registry = pd.read_parquet(REGISTRY_FILE).set_index("building")
    lat0, lon0 = registry.latitude.mean(), registry.longitude.mean()
    phi, metres = math.radians(FRONTAGE_BEARING_DEG), 111_320.0
    cos0 = math.cos(math.radians(lat0))

    def grid(lon, lat):
        east, north = (lon - lon0) * metres * cos0, (lat - lat0) * metres
        return np.array(
            [
                east * math.cos(phi) - north * math.sin(phi),
                east * math.sin(phi) + north * math.cos(phi),
            ]
        )

    streets = pd.read_parquet(BASEMAP_FILE).query("layer == 'street'")
    segments = {}
    for row in streets.itertuples():
        geometry = json.loads(row.geometry)
        lines = geometry["coordinates"]
        lines = lines if geometry["type"] == "MultiLineString" else [lines]
        for line in lines:
            points = np.array([grid(*p) for p in line])
            segments.setdefault(row.name, []).append((points[:-1], points[1:]))
    out = []
    for building, r in registry.iterrows():
        name, kind, axis = frontage_street(r.label)
        if name not in segments or pd.isna(r.latitude):
            out.append((building, None, None))
            continue
        p = grid(r.longitude, r.latitude)
        best, offset = np.inf, None
        for a, b in segments[name]:
            ab = b - a
            t = np.clip(
                ((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1
            )
            q = a + t[:, None] * ab
            d = np.hypot(*(p - q).T)
            i = int(d.argmin())
            if d[i] < best:
                best, offset = d[i], p - q[i]
        if axis == "crosstown":
            front = "south" if offset[1] > 0 else "north"
        else:
            front = "west" if offset[0] > 0 else "east"
        out.append((building, kind, front))
    return pd.DataFrame(out, columns=["building", "street_type", "front"]).set_index(
        "building"
    )


def unit_orientation(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row: which way its unit faces (front, rear, front and rear, side,
    unknown) and the building's frontage street type, from all of the unit's
    listings."""
    from . import descriptions

    frontage = building_frontage().reindex(frame.building.to_numpy())
    front_dir = frontage.front.to_numpy()
    windows = {d: frame[f"window_{d}"].eq("yes").to_numpy() for d in OPPOSITE}
    known = pd.notna(front_dir)
    at = lambda d: np.array(
        [windows[x][i] if isinstance(x, str) else False for i, x in enumerate(d)]
    )
    front_window = at(front_dir)
    back_window = at([OPPOSITE[x] if isinstance(x, str) else None for x in front_dir])
    any_window = np.column_stack(list(windows.values())).any(1)
    # "2F" / "2R": front and rear, only in buildings whose lettered labels are all F or R.
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.upper().fillna("")
    letter = label.str.extract(r"^\d{1,2}([A-Z]+)$")[0]
    letters = letter.groupby(frame.building.to_numpy()).agg(lambda s: set(s.dropna()))
    fr_building = frame.building.map(
        lambda b: (
            letters.get(b, set()) <= {"F", "R"} and len(letters.get(b, set())) == 2
        )
    )
    label_front = (fr_building & letter.eq("F")).to_numpy()
    label_rear = (fr_building & letter.eq("R")).to_numpy()
    text = descriptions.attach(frame).fillna("").str.lower()
    through = text.str.contains(THROUGH_TEXT, regex=True).to_numpy()
    text_front = text.str.contains(FRONT_TEXT, regex=True).to_numpy() | through
    text_rear = text.str.contains(REAR_TEXT, regex=True).to_numpy() | through
    rows = pd.DataFrame(
        {
            "front": (known & front_window)
            | label_front
            | text_front
            | frame.view_street.eq("yes").to_numpy(),
            "rear": (known & back_window)
            | label_rear
            | text_rear
            | frame.view_courtyard.eq("yes").to_numpy(),
            # Side windows need a known frontage to be told from front or back ones.
            "window": any_window & known,
        },
        index=frame.index,
    )
    unit = rows.groupby(frame.unit_id.to_numpy()).transform("any")
    facing = np.select(
        [
            unit.front & unit.rear,
            unit.front,
            unit.rear,
            unit.window,
        ],
        ["front and rear", "front", "rear", "side"],
        "unknown",
    )
    return pd.DataFrame(
        {"facing": facing, "street_type": frontage.street_type.to_numpy()},
        index=frame.index,
    )


def facing_v2(
    frame: pd.DataFrame, train: np.ndarray, id: str = "facing-v2", base: str = "base-v1"
) -> Features:
    """A base set plus which way the apartment faces (unit-level): its
    building's front on an avenue, a wide street or a side street, its rear,
    both (floor-through), or only the sides; against no evidence."""
    base = FEATURE_SETS[base](frame, train)
    o = unit_orientation(frame)
    b = _Builder(frame)
    for kind in ("avenue", "wide street", "side street"):
        b.add(
            "facing",
            f"faces front: {kind}",
            (o.facing == "front") & (o.street_type == kind),
        )
    b.add("facing", "faces rear only", o.facing == "rear")
    b.add("facing", "faces front and rear", o.facing == "front and rear")
    b.add("facing", "faces the sides only", o.facing == "side")
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Every side of a building: the street it looks onto, from its footprint. Each
# facade edge (grouped by the grid direction its outward normal is nearest) is
# sampled every SIDE_SPACING_M, or once at its middle if shorter. A sample
# looks straight out, along the edge's normal, for up to SIDE_REACH_M: it sees
# the first street centerline its sight line crosses, unless another
# building's outline crosses it first (a party wall, or a rear yard with
# buildings behind it). A side looks onto the street most of its clear samples
# see, if two samples see one or one edge sees it along its whole length (a
# narrow front between recessed walls); otherwise it faces no street.
SIDE_REACH_M = 45.0
SIDE_SPACING_M = 5.0
SIDE_MIN_EDGE_M = 1.0
GRID_DIRECTIONS = {
    "north": (0.0, 1.0),
    "south": (0.0, -1.0),
    "east": (1.0, 0.0),
    "west": (-1.0, 0.0),
}
LOUD_ROADS = frozenset({"WEST ST", "12 AVE"})  # the West Side Highway, with the avenues


def street_kind(name: str, roadway: str | None) -> str | None:
    """Street type of a centerline: avenue (and the highway), wide crosstown
    street, side street, or None for other ways."""
    if roadway == "2" or name in LOUD_ROADS:
        return "avenue"
    if name.endswith(" AVE") or name in ("AVE OF THE AMERICAS", "BROADWAY"):
        return "avenue"
    if m := re.fullmatch(r"W\s+(\d+) ST", name):
        return "wide street" if int(m.group(1)) in WIDE_STREETS else "side street"
    return None


def _hits(p, q, e0, e1) -> np.ndarray:
    """Where segment p-q crosses each edge e0[i]-e1[i], as a fraction of p-q
    (inf where it does not)."""
    if not len(e0):
        return np.zeros(0)
    d, e, ap = q - p, e1 - e0, e0 - p
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    ok = np.abs(den) > 1e-9
    den = np.where(ok, den, 1.0)
    t = (ap[:, 0] * e[:, 1] - ap[:, 1] * e[:, 0]) / den
    u = (ap[:, 0] * d[1] - ap[:, 1] * d[0]) / den
    return np.where(ok & (t > 1e-6) & (t <= 1) & (u >= 0) & (u <= 1), t, np.inf)


def facade_sides(ring, streets, occluders) -> dict:
    """For one counter-clockwise outline (grid metres): per grid direction the
    type of street that side looks onto, "none", or "no facade". streets is
    (starts, ends, kinds) of centerline segments; occluders is (starts, ends)
    of the other buildings' outline edges."""
    a, b, kinds = streets
    # The outline's own walls block too (an inner courtyard wall does not see
    # through the building's other wing).
    e0 = np.concatenate([occluders[0], ring[:-1]])
    e1 = np.concatenate([occluders[1], ring[1:]])
    votes = {d: {} for d in GRID_DIRECTIONS}
    whole = {d: set() for d in GRID_DIRECTIONS}  # kinds an edge sees end to end
    for p, q in itertools.pairwise(ring):
        edge = q - p
        length = float(np.hypot(*edge))
        if length < SIDE_MIN_EDGE_M:
            continue
        normal = np.array([edge[1], -edge[0]]) / length
        side = max(GRID_DIRECTIONS, key=lambda d: normal @ np.array(GRID_DIRECTIONS[d]))
        spots = np.arange(SIDE_SPACING_M / 2, length, SIDE_SPACING_M)
        seen = []
        for s in spots if len(spots) else [length / 2]:
            start = p + edge * (s / length) + 0.3 * normal
            end = start + SIDE_REACH_M * normal
            street = _hits(start, end, a, b)
            i = int(street.argmin()) if len(street) else -1
            hit = "none"
            if i >= 0 and np.isfinite(street[i]):
                wall = _hits(start, end, e0, e1)
                if not (len(wall) and wall.min() < street[i]):
                    hit = kinds[i]
            votes[side][hit] = votes[side].get(hit, 0) + 1
            seen.append(hit)
        if seen[0] != "none" and len(set(seen)) == 1:
            whole[side].add(seen[0])
    sides = {}
    for d, v in votes.items():
        clear = {k: n for k, n in v.items() if k != "none"}
        if not v:
            sides[d] = "no facade"
        elif clear and (sum(clear.values()) >= 2 or whole[d]):
            sides[d] = max(clear, key=clear.get)
        else:
            sides[d] = "none"
    return sides


@functools.lru_cache(maxsize=1)
def building_sides() -> pd.DataFrame:
    """Per registry building with a footprint: for each grid direction the type
    of street that side looks onto, or "none" (no street), or "no facade"."""
    registry = pd.read_parquet(REGISTRY_FILE).set_index("building")
    lat0, lon0 = registry.latitude.mean(), registry.longitude.mean()
    phi, metres = math.radians(FRONTAGE_BEARING_DEG), 111_320.0
    cos0 = math.cos(math.radians(lat0))

    def grid(lon, lat):
        east = (np.asarray(lon, float) - lon0) * metres * cos0
        north = (np.asarray(lat, float) - lat0) * metres
        return np.stack(
            [
                east * math.cos(phi) - north * math.sin(phi),
                east * math.sin(phi) + north * math.cos(phi),
            ],
            -1,
        )

    def rings_of(geometry):
        geometry = json.loads(geometry)
        polygons = geometry["coordinates"]
        polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
        return [grid([q[0] for q in pg[0]], [q[1] for q in pg[0]]) for pg in polygons]

    starts, ends, kinds = [], [], []
    for row in pd.read_parquet(BASEMAP_FILE).query("layer == 'street'").itertuples():
        roadway = json.loads(row.attributes).get("rw_type")
        kind = street_kind(row.name, roadway)
        if kind is None or roadway not in ("1", "2", "3", "9"):
            continue
        geometry = json.loads(row.geometry)
        lines = geometry["coordinates"]
        for line in lines if geometry["type"] == "MultiLineString" else [lines]:
            pts = grid([p[0] for p in line], [p[1] for p in line])
            starts.append(pts[:-1])
            ends.append(pts[1:])
            kinds += [kind] * (len(pts) - 1)
    streets = (np.concatenate(starts), np.concatenate(ends), np.array(kinds))

    footprints = pd.read_parquet(FOOTPRINTS_FILE)
    e0, e1, owner = [], [], []
    for r in footprints.itertuples():
        for ring in rings_of(r.geometry):
            e0.append(ring[:-1])
            e1.append(ring[1:])
            owner += [str(r.bin)] * (len(ring) - 1)
    e0, e1 = np.concatenate(e0), np.concatenate(e1)
    owner = np.array(owner)
    by_bin = footprints.groupby(footprints.bin.astype(str))
    by_lot = footprints.groupby(footprints.base_bbl.astype(str))
    out = {}
    for building, r in registry.iterrows():
        key_bin, key_lot = str(r.bin), str(r.bbl)
        if not re.fullmatch(r"[1-5]000000", key_bin) and key_bin in by_bin.groups:
            rows = by_bin.get_group(key_bin)
        elif key_lot in by_lot.groups:
            rows = by_lot.get_group(key_lot)
        else:
            continue
        rings = [
            (str(fp_bin), ring)
            for fp_bin, g in zip(rows.bin, rows.geometry)
            for ring in rings_of(g)
        ]
        # The outline nearest the registry point (a lot can hold several buildings).
        here = grid(r.longitude, r.latitude)
        ring_bin, ring = min(
            rings, key=lambda q: float(np.hypot(*(q[1].mean(0) - here)))
        )
        if 0.5 * np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1]) < 0:
            ring = ring[::-1]  # counter-clockwise, so the outward normal is (dy, -dx)
        # Every other building nearby blocks the view, on the same lot too;
        # outlines of the building itself (its BIN) are left to facade_sides,
        # which lets the outline's own walls block.
        own = (owner == ring_bin) & (not re.fullmatch(r"[1-5]000000", ring_bin))
        centre = ring.mean(0)
        radius = float(np.hypot(*(ring - centre).T).max()) + SIDE_REACH_M + 10.0
        # A lower bound on each edge's distance from the centre.
        reach = np.minimum(np.hypot(*(e0 - centre).T), np.hypot(*(e1 - centre).T))
        near = (reach - np.hypot(*(e1 - e0).T) < radius) & ~own
        out[building] = facade_sides(ring, streets, (e0[near], e1[near]))
    return pd.DataFrame.from_dict(out, orient="index")


def unit_sides(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row: whether its unit looks onto an avenue, a wide street, a side
    street, or no street (rear, courtyard), pooled over the unit's listings,
    from window directions against its building's sides, front/rear labels,
    ad text and views (text, labels and views place the front on the address
    street)."""
    from . import descriptions

    sides = building_sides().reindex(frame.building.to_numpy())
    address_kind = (
        building_frontage().street_type.reindex(frame.building.to_numpy()).to_numpy()
    )
    has_sides = sides.notna().all(axis=1).to_numpy()
    looks = {
        k: np.zeros(len(frame), bool)
        for k in ("avenue", "wide street", "side street", "none")
    }
    for d in GRID_DIRECTIONS:
        window = frame[f"window_{d}"].eq("yes").to_numpy() & has_sides
        side = sides[d].to_numpy()
        for kind in looks:
            looks[kind] |= window & (side == kind)
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.upper().fillna("")
    letter = label.str.extract(r"^\d{1,2}([A-Z]+)$")[0]
    letters = letter.groupby(frame.building.to_numpy()).agg(lambda s: set(s.dropna()))
    fr_building = frame.building.map(
        lambda b: letters.get(b, set()) == {"F", "R"}
    ).to_numpy()
    text = descriptions.attach(frame).fillna("").str.lower()
    through = text.str.contains(THROUGH_TEXT, regex=True).to_numpy()
    front = (
        (fr_building & letter.eq("F").to_numpy())
        | text.str.contains(FRONT_TEXT, regex=True).to_numpy()
        | through
        | frame.view_street.eq("yes").to_numpy()
    )
    rear = (
        (fr_building & letter.eq("R").to_numpy())
        | text.str.contains(REAR_TEXT, regex=True).to_numpy()
        | through
        | frame.view_courtyard.eq("yes").to_numpy()
    )
    for kind in ("avenue", "wide street", "side street"):
        looks[kind] |= front & (address_kind == kind)
    looks["none"] |= rear
    rows = pd.DataFrame(looks, index=frame.index)
    return rows.groupby(frame.unit_id.to_numpy()).transform("any")


def facing_v3(
    frame: pd.DataFrame, train: np.ndarray, id: str = "facing-v3", base: str = "base-v1"
) -> Features:
    """A base set plus which streets the apartment looks onto (unit-level): an
    avenue, a wide street, a side street, and whether it also looks onto the
    rear or a courtyard; each from every side of its building (footprints), not
    only the address street. No evidence is the reference."""
    base = FEATURE_SETS[base](frame, train)
    looks = unit_sides(frame)
    b = _Builder(frame)
    for kind, name in (
        ("avenue", "looks onto an avenue"),
        ("wide street", "looks onto a wide street"),
        ("side street", "looks onto a side street"),
        ("none", "looks onto the rear or a courtyard"),
    ):
        b.add("facing", name, looks[kind])
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Building condition: hazardous (class B) and immediately hazardous (class C)
# housing-code violations HPD found in the building in the years before the
# listing's month, per apartment and year. The window trails the listing, so
# no later information enters.


def building_violations(frame: pd.DataFrame, days: int = 365) -> np.ndarray:
    """Per row: class B and C violations found in its building (registry BIN,
    or its lot for placeholder BINs) in the `days` before the row's month."""
    registry = pd.read_parquet(REGISTRY_FILE).set_index("building")
    hpd = pd.read_parquet(HPD_FILE)
    hpd = hpd[hpd["class"].isin(["B", "C"])]
    found = pd.to_datetime(hpd.inspectiondate, errors="coerce")
    hpd = hpd.assign(found=found)[found.notna()]
    by_bin = {
        k: np.sort(g.found.to_numpy()) for k, g in hpd.groupby(hpd.bin.astype(str))
    }
    by_lot = {
        k: np.sort(g.found.to_numpy()) for k, g in hpd.groupby(hpd.bbl.astype(str))
    }
    period = frame.period.to_numpy().astype("datetime64[ns]")
    start = period - np.timedelta64(days, "D")
    out = np.zeros(len(frame))
    for building, idx in frame.groupby("building").indices.items():
        if building not in registry.index:
            continue
        r = registry.loc[building]
        key_bin = str(r.bin)
        if not re.fullmatch(r"[1-5]000000", key_bin) and key_bin in by_bin:
            times = by_bin[key_bin]
        else:
            times = by_lot.get(str(r.bbl), np.array([], dtype="datetime64[ns]"))
        out[idx] = np.searchsorted(times, period[idx]) - np.searchsorted(
            times, start[idx]
        )
    return out


def hpd_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "hpd-v1",
    base: str = "base-v1",
    years: int = 1,
    many: float = 0.25,
) -> Features:
    """A base set plus the building's condition as of the listing: hazardous
    housing-code violations HPD found in the `years` before, per apartment and
    year (none, a few, or `many` or more). Apartments are MapPLUTO's
    residential units, or the units listed in the building where the lot
    records none (condominium lots)."""
    base = FEATURE_SETS[base](frame, train)
    lot = building_lots(frame)
    units = pd.to_numeric(lot.unitsres, errors="coerce").to_numpy()
    listed = frame.groupby("building").unit_id.transform("nunique").to_numpy()
    units = np.where(units > 0, units, listed).clip(min=1)
    rate = building_violations(frame, days=365 * years) / units / years
    past = "the past year" if years == 1 else f"the past {years} years"
    b = _Builder(frame)
    b.add(
        "building condition",
        f"a few housing-code violations in {past}",
        (rate > 0) & (rate < many),
    )
    b.add("building condition", f"many housing-code violations in {past}", rate >= many)
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Street noise is worst low down: the floors counted as low for facing_v4.
LOW_FLOORS = 4


def row_floor(frame: pd.DataFrame) -> pd.Series:
    """Each row's floor as the base features read it: the listed floor, or the
    unit label's floor where the label is plausible for the building's height;
    NaN when neither is known."""
    floor = frame.listed_floor.astype("float")
    label = label_floor_number(frame)
    height = pd.to_numeric(building_lots(frame).numfloors, errors="coerce")
    label = label.where(label.le(height.to_numpy() + 2))
    floor = floor.where(floor.ge(1), label)
    return floor.where(floor.ge(1))


def facing_v4(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "facing-v4",
    base: str = "unitfacing-v3",
) -> Features:
    """The streets an apartment looks onto (a facing-v3 set), plus whether a
    unit that looks onto an avenue or a wide street is on a low floor
    (LOW_FLOORS or below), where traffic noise is worst."""
    base = FEATURE_SETS[base](frame, train)
    looks = unit_sides(frame)
    low = row_floor(frame).le(LOW_FLOORS).to_numpy()
    b = _Builder(frame)
    b.add(
        "facing",
        f"looks onto an avenue, floors 1-{LOW_FLOORS}",
        looks["avenue"].to_numpy() & low,
    )
    b.add(
        "facing",
        f"looks onto a wide street, floors 1-{LOW_FLOORS}",
        looks["wide street"].to_numpy() & low,
    )
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Feature sets that read the external snapshots (run records list them).
EXTERNAL = {
    "pluto-v1",
    "unitfloor-v2",
    "unitdesc-v1",
    "unitdescpluto-v1",
    "unitdescplutoloc-v1",
    "unitdescplutotransit-v2",
    "unitdescpluto-v2",
    "unitdescpluto-v3",
    "unitfacing-v2",
    "unitfacing-v3",
    "unitfacing-v4",
    "unitdescpluto-v4",
    "unitdescpluto-v5",
    "unitdescplutohpd-v1",
    "unitdescplutohpd-v2",
}
# Feature sets that read the subway stations snapshot.
SUBWAY = {"unitdescplutotransit-v2"}
# Feature sets that read the basemap snapshot (street centerlines).
BASEMAP = {"unitfacing-v2", "unitfacing-v3", "unitfacing-v4"}
# Feature sets that read the building footprints snapshot.
FOOTPRINTS = {"unitfacing-v3", "unitfacing-v4"}
# Feature sets that read the HPD violations snapshot.
HPD = {"unitdescplutohpd-v1", "unitdescplutohpd-v2"}
# Feature sets that read the advertisement descriptions (`descriptions.SOURCE`),
# directly or through their base set.
DESCRIPTIONS = {
    "desc-v1",
    "unitdesc-v1",
    "unitdescpluto-v1",
    "unitdescplutoloc-v1",
    "unitdescplutotransit-v2",
    "unitdescpluto-v2",
    "unitdescpluto-v3",
    "unitfacing-v2",
    "unitfacing-v3",
    "unitfacing-v4",
    "unitdescpluto-v4",
    "unitdescpluto-v5",
    "unitdescplutohpd-v1",
    "unitdescplutohpd-v2",
}

FEATURE_SETS = {
    "base-v1": base_v1,
    "unitbeds-v1": partial(base_v1, id="unitbeds-v1", by_unit=True),
    "unitattrs-v1": partial(base_v1, id="unitattrs-v1", by_unit=True, unit_size=True),
    "unitlabels-v1": partial(
        base_v1, id="unitlabels-v1", by_unit=True, unit_size=True, unit_labels=True
    ),
    "unitfloor-v2": partial(
        base_v1,
        id="unitfloor-v2",
        by_unit=True,
        unit_size=True,
        unit_labels=True,
        label_floor=True,
    ),
    "desc-v1": desc_v1,
    # The description flags on the unit-consistent features.
    "unitdesc-v1": partial(desc_v1, id="unitdesc-v1", base="unitfloor-v2"),
    "pluto-v1": pluto_v1,
    "unitdescpluto-v1": partial(pluto_v1, id="unitdescpluto-v1", base="unitdesc-v1"),
    # The building facts without the flood-zone flag (a location proxy here).
    "unitdescpluto-v2": partial(
        pluto_v1, id="unitdescpluto-v2", base="unitdesc-v1", flood_zone=False
    ),
    # Which way the apartment faces, on the app's building facts (v3).
    "unitfacing-v2": partial(facing_v2, id="unitfacing-v2", base="unitdescpluto-v3"),
    # Which streets the apartment looks onto, from every side of its building.
    "unitfacing-v3": partial(facing_v3, id="unitfacing-v3", base="unitdescpluto-v3"),
    # v3 plus avenue and wide-street views on low floors (traffic noise).
    "unitfacing-v4": partial(facing_v4, id="unitfacing-v4", base="unitfacing-v3"),
    # v2 with "altered since 2000" from the latest recorded alteration.
    "unitdescpluto-v3": partial(
        pluto_v1,
        id="unitdescpluto-v3",
        base="unitdesc-v1",
        flood_zone=False,
        latest_alteration=True,
    ),
    # The location surface on the building facts.
    "unitdescplutoloc-v1": partial(
        location_v1, id="unitdescplutoloc-v1", base="unitdescpluto-v1"
    ),
    # v3 on the corrected registry (LOT_SNAPSHOTS): building facts and heights
    # from the right lots for 11 pages the registry had matched to a neighbour.
    "unitdescpluto-v4": partial(
        pluto_v1,
        id="unitdescpluto-v4",
        base="unitdesc-v1",
        flood_zone=False,
        latest_alteration=True,
    ),
    # v4 with Avalon West Chelsea on its own lot (282 Eleventh Avenue).
    "unitdescpluto-v5": partial(
        pluto_v1,
        id="unitdescpluto-v5",
        base="unitdesc-v1",
        flood_zone=False,
        latest_alteration=True,
    ),
    # Building condition (HPD violations, as of each listing) on the app's facts.
    "unitdescplutohpd-v1": partial(
        hpd_v1, id="unitdescplutohpd-v1", base="unitdescpluto-v3"
    ),
    # The same over the past five years: chronic condition (0.05 or more a year
    # per apartment is "many", about the top 15% of listings).
    "unitdescplutohpd-v2": partial(
        hpd_v1, id="unitdescplutohpd-v2", base="unitdescpluto-v3", years=5, many=0.05
    ),
    # Transit access (as of each listing's month) on the building facts.
    "unitdescplutotransit-v2": partial(
        transit_v2, id="unitdescplutotransit-v2", base="unitdescpluto-v1"
    ),
}


# Feature sets that read other registry and MapPLUTO snapshots than the first.
LOT_SNAPSHOTS = {
    "unitdescpluto-v4": {"registry": REGISTRY_V2_FILE, "pluto": PLUTO_V2_FILE},
    "unitdescpluto-v5": {"registry": REGISTRY_V3_FILE, "pluto": PLUTO_V3_FILE},
}


def lot_files(name: str) -> dict:
    """The registry and MapPLUTO files a feature set's building lots read."""
    return LOT_SNAPSHOTS.get(name, {"registry": REGISTRY_FILE, "pluto": PLUTO_FILE})


def build(name: str, frame: pd.DataFrame, train: np.ndarray) -> Features:
    files = lot_files(name)
    token = _LOTS.set((files["registry"], files["pluto"]))
    try:
        return FEATURE_SETS[name](frame, np.asarray(train, dtype=bool))
    finally:
        _LOTS.reset(token)

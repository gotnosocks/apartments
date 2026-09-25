"""Named feature sets, kept separate from model designs.

A feature set maps the flat table plus a training mask to a matrix of named,
grouped columns on the log-rent scale. Anything estimated from data (reference
medians, category levels) uses training rows only. Unknown is always its own
level or indicator, never folded into "no".

Each set has an id that runs record. Change a set's behaviour by adding a new
id, so older leaderboard entries stay reproducible from their commit anyway.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def _bedrooms(frame):
    beds = frame.bedrooms.round().clip(0, 5).astype(int)
    return beds.map(lambda b: "5+" if b >= 5 else str(b))


def base_v1(frame: pd.DataFrame, train: np.ndarray) -> Features:
    """Listing attributes as advertised, with explicit unknown levels."""
    b = _Builder(frame)
    beds = _bedrooms(frame)
    b.categorical("bedrooms", beds, reference="1")

    full = frame.full_baths.clip(1, 4).map(lambda n: "4+" if n >= 4 else str(n))
    b.categorical("bathrooms", full.rename("full"), reference="1")
    half = frame.half_baths.map(
        lambda n: "unknown" if pd.isna(n) else ("2+" if n >= 2 else str(int(n)))
    )
    b.categorical("bathrooms", "half=" + half, reference="half=0")

    # Size: log square feet relative to the training median for the same
    # bedroom count. Unknown size gets its own indicator and zero deviation.
    sqft = frame.square_feet
    known = sqft.between(150, 8000)
    log_sqft = np.log(sqft.where(known))
    median = log_sqft[train & known.to_numpy()].groupby(beds[train]).median()
    deviation = (log_sqft - beds.map(median)).where(known, 0.0).fillna(0.0)
    b.add("size", "log_sqft_vs_bedroom_median", deviation)
    b.add("size", "sqft_unknown", ~known)

    # Advertised floor label (a proxy, not a verified physical floor).
    floor = frame.listed_floor.astype("float")
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
    b.add(
        "price_basis",
        "current_capture_ask",
        frame.price_basis.ne("historical_initial_own_advertisement_ask"),
    )
    return b.build("base-v1")


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


def desc_v1(frame: pd.DataFrame, train: np.ndarray) -> Features:
    """base-v1 plus flags from the listing's own advertisement description."""
    from . import descriptions

    base = base_v1(frame, train)
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
    extra = b.build("desc-v1")
    return Features(
        "desc-v1",
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# External snapshots read by feature sets (rentfrontier.registry, .external).
REGISTRY_SNAPSHOT = "/data1/apartments/external/registry/20260925-6b67137"
PLUTO_SNAPSHOT = "/data1/apartments/external/pluto/20260925-3096a62"
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
    registry = pd.read_parquet(f"{REGISTRY_SNAPSHOT}/buildings.parquet")
    pluto = pd.read_parquet(f"{PLUTO_SNAPSHOT}/pluto.parquet").set_index("bbl")
    lot = registry.set_index("building").bbl.reindex(frame.building.to_numpy())
    return pluto.reindex(lot.to_numpy()).reset_index(drop=True)


def pluto_v1(frame: pd.DataFrame, train: np.ndarray) -> Features:
    """base-v1 plus the building's MapPLUTO attributes (building-level)."""
    base = base_v1(frame, train)
    lot = building_lots(frame)
    num = {
        c: pd.to_numeric(lot[c], errors="coerce")
        for c in (
            "yearbuilt",
            "yearalter1",
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
    b.add("building status", "flood_zone_2015", lot.pfirm15_flag.notna())
    b.add("building status", "altered_since_2000", num["yearalter1"] >= 2000)
    extra = b.build("pluto-v1")
    return Features(
        "pluto-v1",
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


FEATURE_SETS = {"base-v1": base_v1, "desc-v1": desc_v1, "pluto-v1": pluto_v1}


def build(name: str, frame: pd.DataFrame, train: np.ndarray) -> Features:
    return FEATURE_SETS[name](frame, np.asarray(train, dtype=bool))

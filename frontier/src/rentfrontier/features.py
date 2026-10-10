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
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as data_module
from . import descriptions as descriptions_module
from . import lister as lister_module


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
    floor = row_floor(frame) if label_floor else frame.listed_floor.astype("float")
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


# The bedroom count an ad's first sentence states ("Sunny 2-bedroom ...",
# "One bed with ...", "Studio ..."): its first match, else none. A half count
# ("1.5 bedroom") states none.
_STATED_BEDROOMS = re.compile(
    r"(?<![\d.])\b(?:(one|two|three|four|five|[1-5])[- ]?"
    r"(?:bed(?:room)?s?|bdrms?|br|bd)\b|(studio)\b)"
)
# A sentence ends at . ! or ? before a space, or at a line break.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s|\n|<br\s*/?>")
_BEDROOM_WORDS = {"studio": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def stated_bedrooms(text: str) -> float:
    """The bedroom count the first sentence of an ad states, or NaN."""
    first = _SENTENCE_END.split(text.strip(), maxsplit=1)[0][:200].lower()
    m = _STATED_BEDROOMS.search(first)
    if not m:
        return np.nan
    word = m.group(1) or m.group(2)
    return float(_BEDROOM_WORDS.get(word, word))


def bedtext_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "bedtext-v1",
    base: str = "desc-v1",
) -> Features:
    """A base set that reads the ads plus whether the ad's first sentence
    states fewer or more bedrooms than the record (0 where it states none or
    the ad is unknown). The record's count prices the apartment; a smaller
    count in the ad marks a converted or flex room, a larger one a count the
    record missed."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    text = descriptions.attach(frame).fillna("")
    stated = text.map(stated_bedrooms).to_numpy()
    recorded = pd.to_numeric(frame.bedrooms, errors="coerce").to_numpy()
    with np.errstate(invalid="ignore"):
        diff = stated - recorded
    b = _Builder(frame)
    b.add("description", "text:states_fewer_bedrooms", diff < 0)
    b.add("description", "text:states_more_bedrooms", diff > 0)
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def relist_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "relist-v1",
    base: str = "nb-bedtext-v2",
) -> Features:
    """A base set plus how long the apartment was off the market: the log of
    the months since the unit's previous listing (its latest earlier ask), and
    a flag for its first listing. Only earlier listings count, so a row sees no
    later one. A quick relist hints at a problem unit, a long gap at a
    renovation."""
    base = FEATURE_SETS[base](frame, train)
    at = pd.to_datetime(frame.price_at, utc=True)
    order = np.lexsort((at.to_numpy(), frame.unit_id.to_numpy()))
    units = frame.unit_id.to_numpy()[order]
    times = at.to_numpy()[order]
    gap = np.full(len(frame), np.nan)
    same = np.r_[False, units[1:] == units[:-1]]
    days = np.r_[np.nan, (times[1:] - times[:-1]) / np.timedelta64(1, "D")]
    gap[order] = np.where(same, days, np.nan)
    first = np.isnan(gap)
    months = np.log1p(np.where(first, 0.0, gap) / 30.4)
    centre = float(np.mean(months[train & ~first])) if (train & ~first).any() else 0.0
    b = _Builder(frame)
    b.add(
        "relisting",
        "log_months_since_last_listing",
        np.where(first, 0.0, months - centre),
    )
    b.add("relisting", "first_listing_of_unit", first)
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


# Coded fields of each listing's own record (rentfrontier.listing_extras).
LISTING_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261004-14e27e9/listing-extras.parquet"
)
# Which listing-extras snapshot coded_v1 and prevprice_v1 read while a set is
# built (`EXTRAS_SNAPSHOTS`); unlisted sets read the files above and below.
_EXTRAS: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "extras", default=None
)
# StreetEasy's private outdoor space types, grouped.
OUTDOOR_TYPES = {
    "terrace": ("TERRACE",),
    "roof_deck": ("PRIVATE_ROOF_DECK", "ROOF_RIGHTS"),
    "garden": ("GARDEN",),
    "balcony": ("BALCONY",),
    "patio": ("PATIO",),
}


def coded_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "coded-v1",
    base: str = "nb-relist-v1",
) -> Features:
    """A base set plus coded fields of the listing's own StreetEasy record that the
    dataset lacks: its private outdoor space types (terrace, private roof deck,
    garden, balcony, patio) and its rooms beyond the bedrooms (room count less
    bedrooms: 0-1, 2, 3 or 4+, against 2; unknown where the record has none or
    states more than ten extra rooms)."""
    base = FEATURE_SETS[base](frame, train)
    extras = pd.read_parquet(_EXTRAS.get() or LISTING_EXTRAS_FILE)
    extras = extras.set_index("listing_id")
    ids = frame.source_listing_id.astype(str)
    types = ids.map(extras.outdoor_types).fillna("").str.split("|")
    rooms = pd.to_numeric(ids.map(extras.room_count), errors="coerce")
    extra = rooms - pd.to_numeric(frame.bedrooms, errors="coerce")
    # A room count more than ten above the bedrooms is a recording error.
    known = rooms.gt(0) & extra.ge(0) & extra.le(10)
    level = pd.Series("unknown", index=frame.index)
    level[known & extra.le(1)] = "0-1"
    level[known & extra.eq(2)] = "2"
    level[known & extra.eq(3)] = "3"
    level[known & extra.ge(4)] = "4+"
    b = _Builder(frame)
    for name, codes in OUTDOOR_TYPES.items():
        b.add(
            "outdoor space",
            f"outdoor:{name}",
            types.map(lambda t, c=codes: any(x in c for x in t)),
        )
    b.categorical("rooms beyond bedrooms", level, reference="2")
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# Each listing's price changes (rentfrontier.listing_extras, price_changes).
PRICE_HISTORY_FILE = (
    "/data1/apartments/external/listing-extras/20261005-ae25150/listing-extras.parquet"
)
# The previous listing's price change is clipped to +-30% (larger ones are typos).
PRICE_CHANGE_CLIP = 0.3


def prevprice_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "prevprice-v1",
    base: str = "nb-coded-v1",
    change: bool = True,
) -> Features:
    """A base set plus how the unit's previous listing was repriced before this one
    was listed: the log of its last price before this listing's date over its
    first price (clipped to +-30%), and the log of one plus the number of its price
    changes by then. A cut says the last ask was above what the unit let for; a
    rise, below. Only changes dated before this listing's own date count, so a row
    sees nothing later. The previous listing is the unit's latest earlier row of
    another advertisement (a current capture of an ad never reads its own ad's
    history). 0 for a unit's first listing. Both terms read only the price-change
    record, never the frame's rents.

    The price change holds the previous listing's own ask, so leave-one-out scores
    of that row see its target through this row's covariate. `change=False` keeps
    only the count of price changes, which reads no ask."""
    base = FEATURE_SETS[base](frame, train)
    history = pd.read_parquet(_EXTRAS.get() or PRICE_HISTORY_FILE)
    history = history.set_index("listing_id").price_changes
    at = pd.to_datetime(frame.price_at, utc=True)
    order = np.lexsort((at.to_numpy(), frame.unit_id.to_numpy()))
    units = frame.unit_id.to_numpy()
    ids = frame.source_listing_id.astype(str).to_numpy()
    prev = np.full(len(frame), -1)
    for k in range(1, len(order)):
        i = order[k]
        for back in range(k - 1, -1, -1):
            j = order[back]
            if units[j] != units[i]:
                break
            if ids[j] != ids[i]:
                prev[i] = j
                break
    change_values = np.zeros(len(frame))
    count = np.zeros(len(frame))
    seen = np.zeros(len(frame), bool)
    for i in np.flatnonzero(prev >= 0):
        record = history.get(ids[prev[i]])
        if not isinstance(record, str):
            continue
        steps = sorted((pd.Timestamp(t), p) for t, p in json.loads(record) if p and t)
        before = [p for t, p in steps if t < at.iloc[i]]
        if not before:
            continue
        change_values[i] = np.clip(
            np.log(before[-1] / before[0]), -PRICE_CHANGE_CLIP, PRICE_CHANGE_CLIP
        )
        count[i] = np.log1p(len(before) - 1)
        seen[i] = True
    centre = float(np.mean(count[train & seen])) if (train & seen).any() else 0.0
    b = _Builder(frame)
    if change:
        b.add("previous listing", "previous_listing_price_change", change_values)
    b.add(
        "previous listing",
        "log_previous_listing_repricings",
        np.where(seen, count - centre, 0.0),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# Share of a line's labelled units that must agree for the line to label a unit.
LINE_AGREEMENT = 0.75


def line_orientation(frame: pd.DataFrame) -> pd.Series:
    """Per row: "rear", "street" or "both" as its line's other units show it from
    listings dated before this row (as `unit_sides` reads each listing: windows
    against the building's sides, F/R labels, ad text and views), when at least
    LINE_AGREEMENT of those units agree; "" otherwise. A line is the units of one
    building that share a label letter or number (`data.unit_line_key`): one
    facade. Leave-one-unit-out on units with their own evidence, the line agrees
    89% of the time (2026-10-05)."""
    rows = unit_sides(frame.assign(unit_id=frame.audit_id.to_numpy()))
    street = rows[["avenue", "wide street", "side street"]].any(axis=1).to_numpy()
    rear = rows["none"].to_numpy()
    line = data_module.unit_line_key(frame)
    has_line = line.map(lambda k: isinstance(k, str)).to_numpy()
    line = line.where(has_line, "").astype(str).to_numpy()
    at = pd.to_datetime(frame.price_at, utc=True).to_numpy()
    units = frame.unit_id.to_numpy()
    out = np.full(len(frame), "", dtype=object)
    order = np.flatnonzero(has_line)
    order = order[np.lexsort((at[order], line[order]))]
    labels = {(True, False): "street", (False, True): "rear", (True, True): "both"}
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and line[order[stop]] == line[order[start]]:
            stop += 1
        seen = {}  # unit -> (street, rear) from its listings so far
        votes = {"street": 0, "rear": 0, "both": 0}
        k = start
        while k < stop:
            same = k + 1
            while same < stop and at[order[same]] == at[order[k]]:
                same += 1
            for i in order[k:same]:
                tally = dict(votes)
                own = labels.get(seen.get(units[i], (False, False)))
                if own:
                    tally[own] -= 1
                total = sum(tally.values())
                if total:
                    top = max(tally, key=tally.get)
                    if tally[top] >= LINE_AGREEMENT * total:
                        out[i] = top
            for i in order[k:same]:
                old = seen.get(units[i], (False, False))
                new = (old[0] or bool(street[i]), old[1] or bool(rear[i]))
                if new != old:
                    if labels.get(old):
                        votes[labels[old]] -= 1
                    votes[labels[new]] += 1
                    seen[units[i]] = new
            k = same
        start = stop
    return pd.Series(out, index=frame.index)


def lineface_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "lineface-v1",
    base: str = "nb-coded-v1",
) -> Features:
    """A base set plus which way an apartment with no orientation evidence of its
    own faces, read from the other apartments of its line (same building, same
    label letter or number) in listings dated before it: the rear or a courtyard,
    the street, or both (`line_orientation`). Apartments whose own listings
    already show a side keep the base set's facing terms only."""
    base = FEATURE_SETS[base](frame, train)
    own = unit_sides(frame).any(axis=1).to_numpy()
    inferred = line_orientation(frame).to_numpy()
    b = _Builder(frame)
    for lab, name in (
        ("rear", "line looks onto the rear or a courtyard"),
        ("street", "line looks onto a street"),
        ("both", "line looks onto a street and the rear"),
    ):
        b.add("line facing", name, ~own & (inferred == lab))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def garden_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-garden-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus what an apartment's rear windows look across
    (`garden.rear_open`): the open middle of the block (gardens, rear yards),
    or a wall or shaft within `garden.SHUT_OPEN_M`. Reads no rents. Like the
    building sides of the base, it reads today's footprints (neighbours built
    after a listing touch ~50 rows' facing, 2026-10-05)."""
    from . import garden

    base = FEATURE_SETS[base](frame, train)
    seen = garden.rear_open(frame)
    b = _Builder(frame)
    b.add("rear view", "rear looks over the open block", seen >= garden.SHUT_OPEN_M)
    b.add("rear view", "rear looks onto a wall or shaft", seen < garden.SHUT_OPEN_M)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def quiet_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-quiet-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus how quiet the building's address street is (`quiet`):
    on a busy road (an avenue or a roadway of `quiet.BUSY_WIDTH_FT` or more,
    the Village's named streets included); off one, a narrow roadway or a
    mid-block spot; and the listing's ad calling the street quiet or
    tree-lined. Reads no rents; the street map is today's."""
    from . import descriptions, quiet

    base = FEATURE_SETS[base](frame, train)
    terms = quiet.street_terms(frame)
    text = descriptions.attach(frame).fillna("").str.lower()
    b = _Builder(frame)
    b.add("street", "on a busy road", terms["busy"])
    b.add(
        "street",
        f"narrow street (roadway {quiet.NARROW_FT:.0f} ft or less)",
        terms["narrow"],
    )
    b.add(
        "street",
        f"mid-block ({quiet.MID_BLOCK_M:.0f} m or more from a busy road)",
        terms["mid_block"],
    )
    b.add(
        "street",
        "ad says quiet street",
        text.str.contains(quiet.QUIET_TEXT, regex=True).to_numpy(),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def loud_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-loud-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus loud frontage (`loud`): the apartment looks onto a busy
    road (an avenue or a roadway of `quiet.BUSY_WIDTH_FT` or more, the Village's
    named streets included), from its own listings; and, for one that shows no
    side, the chance one of its facades is busy (its building's busy facades,
    narrowed by its line's earlier listings). Reads no rents; the street map
    and footprints are today's."""
    from . import loud

    base = FEATURE_SETS[base](frame, train)
    terms = loud.unit_terms(frame)
    b = _Builder(frame)
    b.add("loud street", "looks onto a busy road", terms["looks"])
    b.add("loud street", "no side shown: share of busy facades", terms["chance"])
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def transit_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-transit-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus the weekday-morning subway time to midtown
    (`transit.midtown_minutes`: walk, wait and ride to the nearest of Times Sq,
    Grand Central and Herald Sq), in tens of minutes, as of the listing's month.
    The base already has the walk to the nearest station. Reads no rents; the
    timetable is today's."""
    from . import transit

    base = FEATURE_SETS[base](frame, train)
    minutes = transit.midtown_minutes(frame)
    b = _Builder(frame)
    b.add(
        "transit",
        "subway to midtown (10 min)",
        np.nan_to_num(minutes / 10, nan=np.nanmedian(minutes) / 10),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def access_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-access-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus the log of the jobs within 30 minutes by walking and
    the subway (`access.jobs_within`: LODES workplace counts of the year
    published by the listing's month, stations open by then), centred on the
    training rows. Reads no rents; the timetable is today's."""
    from . import access

    base = FEATURE_SETS[base](frame, train)
    jobs = np.log(np.maximum(access.jobs_within(frame), 1.0))
    known = np.isfinite(jobs)
    centre = float(np.mean(jobs[train & known]))
    b = _Builder(frame)
    # A building without a position (none in the registry today) sits at the mean.
    b.add("transit", "log jobs within 30 min", np.where(known, jobs - centre, 0.0))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def parks_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-parks-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus the log of the walk to the nearest park of at least an
    acre, centred on the training rows, and whether an open High Line section
    is within 5 minutes (`parks.park_terms`: parks acquired, and High Line
    sections opened, before the listing's month). Reads no rents."""
    from . import parks

    base = FEATURE_SETS[base](frame, train)
    terms = parks.park_terms(frame)
    walk = np.log(np.maximum(terms.park_min.to_numpy(), 1.0))
    known = np.isfinite(walk)
    centre = float(np.mean(walk[train & known]))
    b = _Builder(frame)
    # A building without a position (none in the registry today) sits at the mean.
    b.add("parks", "log walk min to a park", np.where(known, walk - centre, 0.0))
    b.add(
        "parks",
        f"High Line within {parks.HIGH_LINE_MIN:.0f} min",
        np.nan_to_num(terms.high_line.to_numpy()),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def lines_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-lines-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus, for each subway line group near enough buildings to
    price (`lines.priced_lines`), whether one of its stations is within
    `lines.NEAR_MIN` minutes' walk as of the listing's month (`lines.near_lines`).
    Reads no rents; the timetable is today's."""
    from . import lines

    base = FEATURE_SETS[base](frame, train)
    near = lines.near_lines(frame)
    b = _Builder(frame)
    for g in near.columns:
        b.add("transit", f"{g} within {lines.NEAR_MIN:.0f} min", near[g].to_numpy())
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def trees_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5-trees-v1",
    base: str = "nb5-plutoasof-v3",
    file: str | None = None,
) -> Features:
    """A base set plus the log of one plus the live street trees within
    `trees.RADIUS_M` metres of the building in the latest street tree census
    published a week before the listing (`trees.live_trees_near`), centred on
    the training rows. Reads no rents."""
    from . import trees

    base = FEATURE_SETS[base](frame, train)
    registry = pd.read_parquet(lot_registry()).set_index("building")
    count = trees.live_trees_near(
        registry.latitude.reindex(frame.building.to_numpy()),
        registry.longitude.reindex(frame.building.to_numpy()),
        frame.price_at.pipe(pd.to_datetime, utc=True).dt.tz_localize(None),
        pd.read_csv(file or TREES_FILE),
    )
    value = np.log1p(count)
    known = np.isfinite(value)
    centre = float(np.mean(value[train & known]))
    b = _Builder(frame)
    # A building without a position sits at the mean.
    b.add(
        "greenery",
        f"log(1 + street trees within {trees.RADIUS_M:.0f} m)",
        np.where(known, value - centre, 0.0),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def crime_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5-crime-v1",
    base: str = "nb5-plutoasof-v3",
    file: str | None = None,
) -> Features:
    """A base set plus the log of one plus the felonies reported within
    `crime.RADIUS_M` metres of the building in the year before the listing
    (`crime.felonies_near`), centred on the training rows. Reads no rents."""
    from . import crime

    base = FEATURE_SETS[base](frame, train)
    registry = pd.read_parquet(lot_registry()).set_index("building")
    count = crime.felonies_near(
        registry.latitude.reindex(frame.building.to_numpy()),
        registry.longitude.reindex(frame.building.to_numpy()),
        # The listing day in New York, where NYPD dates its reports.
        frame.price_at.pipe(pd.to_datetime, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None),
        pd.read_csv(file or CRIME_FILE),
    )
    value = np.log1p(count)
    known = np.isfinite(value)
    centre = float(np.mean(value[train & known]))
    b = _Builder(frame)
    # A building without a position, or a listing past the table, sits at the mean.
    b.add(
        "safety",
        f"log(1 + felonies within {crime.RADIUS_M:.0f} m in the year before)",
        np.where(known, value - centre, 0.0),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# The year StreetEasy began coding concessions (pricing.monthsFree and
# netEffectiveRent, from 2020); the cohort leaves those listings out, so an ad
# mentioning one from then on is one the coded field missed.
CONCESSION_CODED_FROM = 2020


def concession_era_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5-concera-v1",
    base: str = "nb5-plutoasof-v3",
) -> Features:
    """A base set plus the ad-text concession flag (`DESCRIPTION_FLAGS`) for
    listings from `CONCESSION_CODED_FROM` on. The base's text:concession then
    carries the earlier ads, and this term is how the later ones differ:
    before 2020 the ad text is the only record of a concession, after it the
    coded ones are out of the cohort. Reads no rents."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    if "text:concession" not in base.names:
        raise ValueError(f"{base.id} has no text:concession to split")
    text = descriptions.attach(frame).fillna("").str.lower()
    known = text.str.len().to_numpy() > 20
    flag = known & text.str.contains(DESCRIPTION_FLAGS["concession"]).to_numpy()
    year = (
        frame.price_at.pipe(pd.to_datetime, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.year.to_numpy()
    )
    b = _Builder(frame)
    b.add(
        "description",
        f"text:concession, {CONCESSION_CODED_FROM} on",
        flag & (year >= CONCESSION_CODED_FROM),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def unical_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5-unical-v1",
    base: str = "nb5-plutoasof-v3",
    calendar: str | None = None,
) -> Features:
    """A base set plus whether the listing day falls in each of the NYU
    calendar windows (`unical.WINDOWS`: the 6 weeks before move-in, move-in
    to the first day of classes, and 2 weeks either side of spring finals),
    and each window again for buildings within `unical.NEAR_M` metres of the
    NYU or New School main campus. The calendars are published months ahead,
    so a listing reads its own year's. Reads no rents."""
    from . import unical

    base = FEATURE_SETS[base](frame, train)
    cal = pd.read_csv(calendar or UNICAL_FILE)
    inside = unical.windows(
        frame.price_at.pipe(pd.to_datetime, utc=True).dt.tz_localize(None), cal
    )
    registry = pd.read_parquet(lot_registry()).set_index("building")
    near = unical.near_campus(
        registry.latitude.reindex(frame.building.to_numpy()),
        registry.longitude.reindex(frame.building.to_numpy()),
    )
    b = _Builder(frame)
    for name in unical.WINDOWS:
        b.add("calendar", name, inside[name].to_numpy())
    for name in unical.WINDOWS:
        b.add(
            "calendar",
            f"{name}, within {unical.NEAR_M:.0f} m of NYU or New School",
            inside[name].to_numpy() & near,
        )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def bedsize_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-bedsize-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus the largest bed the listing's own ad says its bedroom
    takes (`bedsize.stated_size`: full, with twin and double, queen or king;
    an ad stating none is the reference). Reads no rents."""
    from . import bedsize

    base = FEATURE_SETS[base](frame, train)
    size = bedsize.stated_sizes(frame).to_numpy()
    b = _Builder(frame)
    for s in bedsize.SIZES:
        b.add("description", f"ad states a {s} bed", size == s)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def nearby_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-nearby-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus what is nearby (`nearby`): log walk metres to the
    nearest dog run, hospital, ambulance station, homeless drop-in center,
    NYCHA lot and Madison Square Garden. Reads no rents; the places are
    today's."""
    from . import nearby

    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    for kind, values in nearby.terms(frame).items():
        fill = np.nanmedian(values)
        b.add(
            "nearby", f"log m to {nearby.KINDS[kind]}", np.nan_to_num(values, nan=fill)
        )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def nearby_one_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
    kind: str,
) -> Features:
    """A base set plus one `nearby_v1` term: log walk metres to the nearest
    place of `kind` (`nearby.KINDS`). Reads no rents."""
    from . import nearby

    base = FEATURE_SETS[base](frame, train)
    values = nearby.terms(frame)[kind]
    b = _Builder(frame)
    b.add(
        "nearby",
        f"log m to {nearby.KINDS[kind]}",
        np.nan_to_num(values, nan=np.nanmedian(values)),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def retail_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-retail-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus street retail (`retail`): log1p of the storefronts, and
    of the restaurants, cafes and bars, within `retail.RADIUS_M` in the
    Storefront Registry's first year. Reads no rents."""
    from . import retail

    base = FEATURE_SETS[base](frame, train)
    t = retail.terms(frame)
    b = _Builder(frame)
    for key, name in (
        ("storefronts", "log1p storefronts nearby"),
        ("food", "log1p food places nearby"),
    ):
        b.add("retail", name, np.nan_to_num(t[key], nan=np.nanmedian(t[key])))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def through_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-through-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus how likely a floor-through layout is
    (`floorthrough`): a building with room for one apartment per floor
    (`floorthrough.whole_floor`), two per floor, and the listing's ad saying floor-through.
    Reads no rents; MapPLUTO counts are today's (~1% of rows see a material
    change, 2026-10-06)."""
    from . import descriptions, floorthrough

    base = FEATURE_SETS[base](frame, train)
    upf = floorthrough.units_per_floor(frame)
    whole = floorthrough.whole_floor(frame)
    text = descriptions.attach(frame).fillna("").str.lower()
    b = _Builder(frame)
    b.add("layout", "one apartment per floor", whole)
    b.add("layout", "two apartments per floor", ~whole & (upf <= 2.0))
    b.add(
        "layout",
        "ad says floor-through",
        text.str.contains(floorthrough.THROUGH_TEXT, regex=True).to_numpy(),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def walkup_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-walkup-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus a walk-up penalty past the third floor: log(floor / 3),
    floored at zero, in buildings with no elevator. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    log_floor = base.values[:, base.names.index("log_floor")]
    walkup = frame.elevator.eq("no").to_numpy()
    b = _Builder(frame)
    b.add(
        "floor",
        "log_floor_above_3_x_no_elevator",
        np.maximum(0.0, log_floor - np.log(3)) * walkup,
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def location_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-loc-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus a smooth location surface over the map of the set's own
    registry (`lot_registry`): the Gaussian bumps of `location_v1`, 250 m apart,
    so neighbouring buildings share a premium (a fixed-scale basis-function
    approximation of a spatial Gaussian process over building coordinates)."""
    base = FEATURE_SETS[base](frame, train)
    registry = pd.read_parquet(lot_registry()).set_index("building")
    lat0, lon0 = registry.latitude.mean(), registry.longitude.mean()

    def xy(buildings):
        lat = registry.latitude.reindex(buildings).to_numpy()
        lon = registry.longitude.reindex(buildings).to_numpy()
        metres = 111_320.0
        return np.column_stack(
            [(lon - lon0) * metres * np.cos(np.radians(lat0)), (lat - lat0) * metres]
        )

    sites = xy(registry.index.to_numpy())
    sites = sites[np.isfinite(sites).all(1)]
    points = xy(frame.building.to_numpy())
    known = np.isfinite(points).all(1)
    values = np.where(known[:, None], location_bumps(np.nan_to_num(points), sites), 0.0)
    b = _Builder(frame)
    for k in range(values.shape[1]):
        b.add("location", f"location_{k:02d}", values[:, k], scale=LOCATION_SCALE)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def location_nolabel(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5p3-locnolabel-v1",
    base: str = "nb5-plutoasof-v3",
) -> Features:
    """`location_v2` without the base's neighbourhood labels: the smooth
    location surface alone carries where a building is. Against the matching
    loc set, which keeps the labels, it tests whether the label has a price
    effect beyond location (Ben, 2026-10-08: a Chelsea building beside the
    West Village may gain from proximity and, separately, from its label)."""
    full = location_v2(frame, train, id=id, base=base)
    keep = np.array([g != "neighbourhood" for g in full.groups])
    return Features(
        id,
        [n for n, k in zip(full.names, keep) if k],
        [g for g, k in zip(full.groups, keep) if k],
        full.values[:, keep],
        full.prior_scale[keep],
    )


# Areas an ad may say it is in: pattern of the name and its usual spellings.
CLAIM_AREAS = {
    "Chelsea": r"chelsea",
    "West Village": r"west village",
    "Greenwich Village": r"greenwich village",
    "Gramercy Park": r"gramercy(?: park)?",
    "Flatiron": r"flat ?iron(?: district)?",
    "East Village": r"east village",
    "Union Square": r"union square",
    "Meatpacking": r"meat ?packing(?: district)?",
    "SoHo": r"soho",
    "NoHo": r"noho",
    "NoMad": r"nomad",
    "Murray Hill": r"murray hill",
    "Kips Bay": r"kips bay",
    "Hudson Yards": r"hudson yards",
    "Hell's Kitchen": r"hell'?s kitchen|clinton(?! hill)",
    "Hudson Square": r"hudson square",
    "Tribeca": r"tribeca",
    "Stuy Town": r"stuy(?:vesant)? town|peter cooper",
    "Midtown": r"midtown",
    "Nolita": r"nolita",
    "Lower East Side": r"lower east side",
}
# A claim is the name after "in", "located in", "heart of" and the like, not
# followed by a street word or a landmark (Chelsea Market, Chelsea Piers, the
# Flatiron Building, Union Square Park). "In Gramercy Park" counts: the
# area's pattern takes the "park".
CLAIM_LEAD = (
    r"\b(?:in|located in|located on|heart of|nestled in|situated in|prime|"
    r"living in|live in|life in) (?:the )?(?:beautiful |historic |prime |trendy |"
    r"charming |vibrant |lovely |coveted |desirable )?"
)
CLAIM_TRAIL = (
    r"\b(?! ?(?:ave|avenue|st|street|sq|square|pl|place|market|piers?|park(?! area)|"
    r"building|hotel|post office|station|mews|houses|plaza|landing|lofts|"
    r"condominium|towers?)\b)"
)
# Names that count as a label's own: West Village is part of Greenwich Village.
CLAIM_OWN = {"West Village": ("West Village", "Greenwich Village")}
# Other areas with a column of their own; the rest share "another area".
CLAIM_OTHERS = (
    "Chelsea",
    "West Village",
    "Greenwich Village",
    "Gramercy Park",
    "Flatiron",
    "East Village",
    "Union Square",
    "Meatpacking",
)


def claimed_areas(text: pd.Series, label: pd.Series) -> pd.DataFrame:
    """Per ad (lower-case text) and its listing's neighbourhood label: whether
    the ad says the apartment is in its own neighbourhood, in each of
    `CLAIM_OTHERS` that is not its own, or in another area of `CLAIM_AREAS`."""
    text = text.str.replace(r"\s+", " ", regex=True)
    said = pd.DataFrame(
        {
            area: text.str.contains(CLAIM_LEAD + "(?:" + rx + ")" + CLAIM_TRAIL)
            for area, rx in CLAIM_AREAS.items()
        },
        index=text.index,
    )
    label = label.to_numpy()
    own_of = {a: CLAIM_OWN.get(a, (a,)) for a in set(label)}
    own = np.zeros(len(text), bool)
    other = {a: np.zeros(len(text), bool) for a in CLAIM_OTHERS}
    another = np.zeros(len(text), bool)
    for area in CLAIM_AREAS:
        hit = said[area].to_numpy()
        mine = np.array([area in own_of[x] for x in label])
        own |= hit & mine
        if area in other:
            other[area] |= hit & ~mine
        else:
            another |= hit & ~mine
    return pd.DataFrame(
        {
            "names its own neighbourhood": own,
            **{f"names {a}": v for a, v in other.items()},
            "names another area": another,
        },
        index=text.index,
    )


def claims_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb5p3-claim-v1",
    base: str = "nb5p3-loc-v1",
) -> Features:
    """A base set plus the areas the listing's own ad says it is in
    (`claimed_areas`), per ad, so a building's listings can differ: naming
    none is the reference, and an ad without text has none (the base's
    description indicator carries it). On
    the location surface with and without the neighbourhood labels it tests
    whether the name an ad uses carries a price beyond where the building is
    (Ben, 2026-10-08). Reads no rents."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    text = descriptions.attach(frame).fillna("").str.lower()
    known = text.str.len().to_numpy() > 20
    claims = claimed_areas(text, frame.neighbourhood)
    b = _Builder(frame)
    for name in claims:
        b.add("claimed area", f"ad {name}", claims[name].to_numpy() & known)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


@functools.lru_cache(maxsize=2)
def _waterfront_minutes(registry_file: str, basemap_file: str) -> pd.Series:
    """Per registry building: the walk (facing-grid metres over
    `WALK_M_PER_MIN`) to the nearest point of the basemap's Manhattan
    shoreline, which Hudson River Park follows on the West Side."""
    from . import parks

    basemap = pd.read_parquet(basemap_file)
    shore = parks.outline(json.loads(basemap[basemap.layer == "land"].geometry.iloc[0]))
    grid = facing_grid()
    at = grid(shore[:, 0], shore[:, 1])
    registry = pd.read_parquet(registry_file).set_index("building")
    registry = registry[registry.latitude.notna()]
    homes = grid(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    walk = np.concatenate(
        [
            np.abs(homes[i : i + 256, None, :] - at[None]).sum(-1).min(1)
            for i in range(0, len(homes), 256)
        ]
    )
    return pd.Series(walk / WALK_M_PER_MIN, index=registry.index)


def waterfront_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-water-v1",
    base: str = "nb3-parks-v1",
) -> Features:
    """A base set plus the log of the walk to the waterfront, centred on the
    training rows: the one term of the pre-GV open-space set (nb-openspace-v1)
    that nb3-parks-v1 does not already carry. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    minutes = _waterfront_minutes(lot_registry(), area_snapshot()[0])
    walk = np.log(
        np.maximum(minutes.reindex(frame.building.to_numpy()).to_numpy(), 1.0)
    )
    known = np.isfinite(walk)
    centre = float(np.mean(walk[train & known]))
    b = _Builder(frame)
    b.add(
        "parks", "log walk min to the waterfront", np.where(known, walk - centre, 0.0)
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# Pre-GV null text sets, retested on the GV data (2026-10-06).
# More of what an ad says about the apartment (nb-text-v1, 2026-10-02):
# physical attributes beyond DESCRIPTION_FLAGS; market cues are left out.
TEXT_FLAGS = {
    "whole_house": r"(?:entire|whole|single[- ]family) (?:town ?house|house|home)|single[- ]family",
    "penthouse_text": r"penthouse",
    "garden_level": r"garden (?:level|apartment|floor)",
    "terrace": r"\bterrace\b",
    "loft": r"\bloft\b",
    "gut_renovated": r"gut[- ]renovat",
    "chefs_kitchen": r"chef'?s kitchen|viking|sub[- ]?zero|miele|wolf range",
    "home_office": r"home office",
    "walk_in_closet": r"walk[- ]?in closet",
    "central_air": r"central (?:air|a/?c)\b",
    "river_view": r"(?:river|water|hudson) views?",
    "skyline_view": r"(?:skyline|city|empire state|panoramic) views?",
    "large_words": r"\bhuge\b|massive|enormous|oversized|sprawling",
    "small_words": r"\bcozy\b|\bpetite\b|\btiny\b",
}
# The six DESCRIPTION_FLAGS read worst, rewritten against a Sonnet reading of
# 1,000 ads (nb-flagfix-v1, 2026-10-04; precision / recall before -> after):
# washer/dryer in unit 0.99/0.42 -> 0.99/0.92, walk-up 0.93/0.73 -> 0.90/0.97,
# shared outdoor 0.92/0.48 -> 0.86/0.82, furnished 0.24/0.91 -> 0.90/0.82,
# private outdoor 0.94/0.64 -> 0.91/0.71, high ceilings 1.00/0.81 -> 1.00/0.83.
REWRITTEN_FLAGS = {
    "washer_dryer_in_unit": r"(?:washer|w)\s*(?:/|&|and)\s*(?:dryer|d)\b(?![^.]{0,25}(?:in|on|each) (?:the )?(?:building|basement|floor))|in[- ]unit (?:washer|laundry|w/?d)|laundry in (?:the )?(?:unit|apartment|residence)",
    "outdoor_shared": r"roof ?(?:deck|top|terrace|garden)|rooftop|(?:shared|common|communal|landscaped|private) (?:roof|garden|courtyard)|courtyard garden|(?:common|shared) (?:outdoor|terrace)",
    "private_outdoor": r"private (?:outdoor|terrace|balcony|roof|garden|patio|backyard|deck)|(?:your|its|their|own) (?:own )?(?:private )?(?:terrace|balcony|garden|patio|backyard|deck)|(?:with|w/|features|has|and) (?:a |an )?(?:large |huge |sunny |spacious |)?(?:balcony|terrace|patio|backyard)",
    "high_ceilings": r"high ceiling|soaring ceiling|tall ceiling|(?:1[0-9]|[89])[- ]?(?:ft|foot|feet|'|’)[- ]?(?:high )?ceiling|ceilings? (?:of|over|up to) (?:1[0-9]|[89])",
    "walkup_text": r"walk[- ]?up|flights? up|no elevator",
    "furnished": r"(?<!un)(?<!not )(?<!information )(?<!come )\bfurnished\b(?! (?:and landscaped|common|roof|rooftop|terrace|deck|garden|lounge|sky|pictures|herein))(?! and (?:landscaped|planted))",
}
# Attributes the same Sonnet reading found stated often and not in the feature
# list (nb-attrs-v1, 2026-10-04), each with a regex its labels support.
ATTRIBUTE_FLAGS = {
    "walk_in_closet": r"walk[- ]?in closet",
    "live_in_super": r"live[- ]in super|on[- ]site super|super on[- ]site|resident super|live[- ]in (?:building )?(?:superintendent|manager)",
    "utilities_included": r"(?:heat|hot water|gas|electric(?:ity)?|utilities|water)(?: and | & |, |/)?(?:hot water|gas|cold water|water|electric)?[^.\n]{0,20}\bincluded|includes? (?:heat|hot water|gas|electric|utilities)",
    "windowed_kitchen": r"windowed (?:eat[- ]in )?kitchen|kitchen (?:has|with) (?:a )?window",
    "windowed_bath": r"windowed (?:marble )?bath|bath(?:room)? (?:has|with) (?:a |its own )?window",
    "tree_lined": r"tree[- ]lined",
    "skylight": r"sky ?lights?|sky ?lites?",
    "video_intercom": r"video intercom|virtual doorman",
    "corner_unit": r"corner (?:unit|apartment|residence|home|loft|studio|one|two|1|2|3|bedroom)",
    "separate_kitchen": r"separate (?:eat[- ]in |windowed )?kitchen",
    "floor_to_ceiling_windows": r"floor[- ]to[- ]ceiling (?:windows|glass)",
    "marble_bath": r"marble (?:bath|bathroom)",
    "hardwood": r"hard ?wood|wood floor|wide[- ]plank|oak floor|parquet",
    "stainless": r"stainless",
    "prewar_text": r"pre[- ]?war",
}


def loft_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-loft-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set plus a loft-building flag (`loft.loft_flags`: MapPLUTO D5, or
    at least half the building's earlier ads say loft), and the flag times the
    bedroom count less one (one bedroom is the bedroom reference) and times
    `log_sqft_vs_bedroom_median`, so lofts get their own bedroom and size
    gradients. Reads no rents."""
    from . import loft

    base = FEATURE_SETS[base](frame, train)
    flag = loft.loft_flags(frame, building_lots(frame).bldgclass).loft.to_numpy()
    beds = frame.bedrooms.round().clip(0, 5).fillna(1.0).to_numpy() - 1.0
    size = base.values[:, base.names.index("log_sqft_vs_bedroom_median")]
    b = _Builder(frame)
    b.add("loft", "loft", flag)
    b.add("loft", "loft_x_bedrooms_vs_1", flag * beds)
    b.add("loft", "loft_x_log_sqft_vs_bedroom_median", flag * size)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def text_flags_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-text-v1",
    base: str = "nb3-coded-v2",
    flags: dict = TEXT_FLAGS,
) -> Features:
    """A base set that reads the ads plus `flags`, each a mention in the ad, 0
    where the ad is unknown. Reads no rents."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    text = descriptions.attach(frame)
    known = text.str.len() > 20
    b = _Builder(frame)
    for name, pattern in flags.items():
        b.add(
            "description",
            f"text:{name}",
            known & text.str.contains(pattern, regex=True),
        )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def flagfix_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb3-flagfix-v1",
    base: str = "nb3-coded-v2",
) -> Features:
    """A base set that reads the ads, with its REWRITTEN_FLAGS columns read by
    the rewritten patterns. Reads no rents."""
    from . import descriptions

    base = FEATURE_SETS[base](frame, train)
    text = descriptions.attach(frame)
    known = (text.str.len() > 20).to_numpy()
    values = base.values.copy()
    for name, pattern in REWRITTEN_FLAGS.items():
        k = base.names.index(f"text:{name}")
        values[:, k] = known & text.str.contains(pattern, regex=True).to_numpy()
    return Features(id, base.names, base.groups, values, base.prior_scale)


# External snapshots read by feature sets (rentfrontier.registry, .external).
# University calendars (rentfrontier.unical).
UNICAL_FILE = "/data1/apartments/external/unical/20261008-571dd02/calendar.csv"
# Feature sets that read UNICAL_FILE.
UNICAL = {"nb5-unical-v1"}
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
# West Village (cohort west-village-analysis-20261001-6b3ad1a): its own registry,
# geocoded from the transform's building coordinates, and MapPLUTO for its lots.
WV_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261001-3709acc/buildings.parquet"
)
WV_PLUTO_FILE = "/data1/apartments/external/pluto/20261001-3709acc/pluto.parquet"
# Which registry and MapPLUTO snapshots building_lots reads while a feature set
# is built (`build`); feature sets not listed in LOT_SNAPSHOTS read the first.
_LOTS: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "lots", default=None
)
SUBWAY_SNAPSHOT = "/data1/apartments/external/subway/20260929-8e7c364"
SUBWAY_FILE = f"{SUBWAY_SNAPSHOT}/subway.parquet"
GTFS_SNAPSHOT = "/data1/apartments/external/gtfs/20261006-6158e22"
GTFS_FILE = f"{GTFS_SNAPSHOT}/gtfs_subway.zip"
LODES_SNAPSHOT = "/data1/apartments/external/lodes/20261006-e587e60"
LODES_FILE = f"{LODES_SNAPSHOT}/lodes.parquet"
PLACES_SNAPSHOT = "/data1/apartments/external/places/20261006-7c4c408"
PLACES_FILE = f"{PLACES_SNAPSHOT}/places.parquet"
STOREFRONTS_SNAPSHOT = "/data1/apartments/external/storefronts/20261006-5fd0c26"
STOREFRONTS_FILE = f"{STOREFRONTS_SNAPSHOT}/storefronts.parquet"
PARKS_SNAPSHOT = "/data1/apartments/external/parks/20261006-d208294"
PARKS_FILE = f"{PARKS_SNAPSHOT}/parks.parquet"
# Street centerlines, parks and shoreline (`rentfrontier.external basemap`).
BASEMAP_SNAPSHOT = "/data1/apartments/external/basemap/20260929-da7e40d"
BASEMAP_FILE = f"{BASEMAP_SNAPSHOT}/basemap.parquet"
# Building outlines, the registry's and their neighbours' (`rentfrontier.external footprints`).
FOOTPRINTS_SNAPSHOT = "/data1/apartments/external/footprints/20260930-6634906"
FOOTPRINTS_FILE = f"{FOOTPRINTS_SNAPSHOT}/footprints.parquet"
# Chelsea + West Village (cohort chelsea-west-village-analysis-20261001-eea4f66):
# the two registries merged, and the neighbourhoods' MapPLUTO, footprints and
# basemap snapshots merged (`rentfrontier.external merge`).
NB_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261001-eea4f66/buildings.parquet"
)
NB_PLUTO_FILE = "/data1/apartments/external/pluto/20261001-9b54648/pluto.parquet"
NB_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261001-9b54648/footprints.parquet"
)
NB_BASEMAP_FILE = "/data1/apartments/external/basemap/20261001-9b54648/basemap.parquet"
# Chelsea, West Village and Greenwich Village (cohort
# chelsea-wv-gv-analysis-20261005-2d5b3b6): Greenwich Village's registry and
# snapshots merged into the two above, and the three crawls' listing extras.
NB3_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261005-2d5b3b6/buildings.parquet"
)
NB3_PLUTO_FILE = "/data1/apartments/external/pluto/20261005-2d5b3b6/pluto.parquet"
NB3_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261005-2d5b3b6/footprints.parquet"
)
NB3_BASEMAP_FILE = "/data1/apartments/external/basemap/20261005-2d5b3b6/basemap.parquet"
NB3_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261005-77068ea/listing-extras.parquet"
)
# LPC designations of the three neighbourhoods' lots (`rentfrontier.external lpc`).
NB3_LPC_FILE = "/data1/apartments/external/lpc/20261005-8946d6f/lpc.parquet"
# Chelsea, West Village, Greenwich Village and Flatiron + Gramercy Park:
# Flatiron + Gramercy Park's registry (20261008-34b958d) merged into nb3's, its
# MapPLUTO, footprints and basemap merged into nb3's (nb3's rows unchanged), the
# four crawls' listing extras (also the price history), and the sources keyed
# by lot, building or box fetched on the merged registry.
NB4_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261008-bda2959/buildings.parquet"
)
NB4_PLUTO_FILE = "/data1/apartments/external/pluto/20261008-e78c6fd/pluto.parquet"
NB4_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261008-e78c6fd/footprints.parquet"
)
NB4_BASEMAP_FILE = "/data1/apartments/external/basemap/20261008-e78c6fd/basemap.parquet"
NB4_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261008-e78c6fd/listing-extras.parquet"
)
NB4_LPC_FILE = "/data1/apartments/external/lpc/20261008-bda2959/lpc.parquet"
NB4_HPD_FILE = "/data1/apartments/external/hpd/20261008-bda2959/hpd.parquet"
NB4_NOISE_FILE = "/data1/apartments/external/noise311/20261008-bda2959/noise311.parquet"
NB4_PLACES_FILE = "/data1/apartments/external/places/20261008-bda2959/places.parquet"
NB4_STOREFRONTS_FILE = (
    "/data1/apartments/external/storefronts/20261008-e78c6fd/storefronts.parquet"
)
NB4_PARKS_FILE = "/data1/apartments/external/parks/20261008-bda2959/parks.parquet"
# The LPC snapshot of the set being built (`LPC_SNAPSHOTS`): when set, a lot is a
# landmark or in a historic district only from its designation date.
_LPC: contextvars.ContextVar[str | None] = contextvars.ContextVar("lpc", default=None)
# NYC Parks properties in the four crawls' box, Manhattan's only (`external
# parks --borough M`): the box reaches across the East River, to parks no walk
# from the buildings reaches and that `parks.SECTIONS` has no opening dates for.
NB5_PARKS_FILE = "/data1/apartments/external/parks/20261008-f63bf6c/parks.parquet"
# The parks file of the set being built (`PARKS_SNAPSHOTS`), else `PARKS_FILE`.
_PARKS: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "parks", default=None
)
# Parks files by feature set, where a set reads other than `PARKS_FILE`.
PARKS_SNAPSHOTS = {"nb5-parks-v1": NB5_PARKS_FILE, "nb5-water-v1": NB5_PARKS_FILE}


def parks_file() -> str:
    """The NYC Parks properties file the set being built reads."""
    return _PARKS.get() or PARKS_FILE


# The places file of the set being built (`PLACES_SNAPSHOTS`), else `PLACES_FILE`.
_PLACES: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "places", default=None
)
# Places files by feature set, where a set reads other than `PLACES_FILE`
# (the nb5 single-place sets, `NB5_SINGLES`, add theirs).
PLACES_SNAPSHOTS: dict[str, str] = {}


def places_file() -> str:
    """The places file (`nearby`) the set being built reads."""
    return _PLACES.get() or PLACES_FILE


# Whether the set being built dates the building's MapPLUTO alterations as of
# each listing (`AS_OF_SETS`): an alteration counts only from the year after it,
# so a listing never sees a later one (no future information).
_AS_OF: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pluto_as_of", default=False
)
# Which basemap and footprints snapshots facing reads while a set is built.
_AREA: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "area", default=None
)


def area_snapshot() -> tuple[str, str]:
    """(basemap, footprints) files of the set being built (AREA_SNAPSHOTS)."""
    return _AREA.get() or (BASEMAP_FILE, FOOTPRINTS_FILE)


# HPD housing-code violations of the registry's buildings (`rentfrontier.external hpd`).
HPD_SNAPSHOT = "/data1/apartments/external/hpd/20260930-cb289ad"
HPD_FILE = f"{HPD_SNAPSHOT}/hpd.parquet"

# Rent-stabilized units per lot and tax-bill year (`rentfrontier.external rentstab`).
RENTSTAB_SNAPSHOT = "/data1/apartments/external/rentstab/20261008-b487c8a"
RENTSTAB_FILE = f"{RENTSTAB_SNAPSHOT}/rentstab.parquet"
# MapPLUTO for every lot on the eight neighbourhoods' tax blocks (external.py
# blocklots): which lots a footprint spans (`lot_open_share_v2`).
BLOCKLOTS_SNAPSHOT = "/data1/apartments/external/blocklots/20261010-c90ddbd"
BLOCKLOTS_FILE = f"{BLOCKLOTS_SNAPSHOT}/blocklots.parquet"
# 2020 Neighborhood Tabulation Areas by building (`python -m rentfrontier.nta`).
NTA_FILE = "/data1/apartments/external/nta/20261010-c90ddbd/nta.parquet"
NTA_FOLDED = "Stuyvesant Town-Peter Cooper Village"
# Years a lot's last stabilized-units bill counts for (the 2019 bill reaches 2022).
STAB_CARRY_YEARS = 3

# MapPLUTO's yearly releases (2009 on) of the five neighbourhoods' registry lots
# (NB4_REGISTRY_FILE), the fields of today's MapPLUTO plus `release`.
ALTERATIONS_FILE = (
    "/data1/apartments/external/plutohistory/20261008-4fe46d6/plutohistory.parquet"
)
# Every MapPLUTO release City Planning archives (09v1-26v2) of the five
# neighbourhoods' registry lots, with each release's publication date
# (`rentfrontier.external plutoreleases`).
PLUTO_RELEASES_FILE = (
    "/data1/apartments/external/plutoreleases/20261008-bdb9e67/plutoreleases.parquet"
)
PLUTO_RELEASE_BUFFER_DAYS = 7
"""Days after a MapPLUTO release is published before a listing reads it: the
lag between the data being available and a new scrape and model fit using it.
Ben, 2026-10-08: "Don't do 60 days for the lag - do like a week! We just want to
allow a realistic lag between when the data would have been available and we
could have done a new scrape and model fit." """
# The releases file when the set being built reads each lot as the latest
# MapPLUTO release published before the listing (`PLUTO_RELEASED_SETS`).
_RELEASED: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "released", default=None
)
# Whether the set being built dates the lot's alteration years (`ALTERATION_DATED_SETS`).
_ALTER_DATED: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "alter_dated", default=None
)
ERAS = (
    (0, 1900, "pre-1900"),
    (1900, 1930, "1900-1929"),
    (1930, 1960, "1930-1959"),
    (1960, 1990, "1960-1989"),
    (1990, 2010, "1990-2009"),
    (2010, 3000, "2010+"),
)


def lot_registry() -> str:
    """The registry file the current build reads (`LOT_SNAPSHOTS`), else the first."""
    return (_LOTS.get() or (REGISTRY_FILE, PLUTO_FILE))[0]


def _grid_origin() -> tuple[float, float]:
    """The facing grid's origin: the first registry's mean position, whichever
    registry a set reads, so buildings a correction leaves alone keep their sides."""
    first = pd.read_parquet(REGISTRY_FILE)
    return first.latitude.mean(), first.longitude.mean()


def building_lots(frame: pd.DataFrame) -> pd.DataFrame:
    """MapPLUTO attributes of each row's building (one row per listing row)."""
    registry_file, pluto_file = _LOTS.get() or (REGISTRY_FILE, PLUTO_FILE)
    registry = pd.read_parquet(registry_file)
    pluto = pd.read_parquet(pluto_file).set_index("bbl")
    lot = registry.set_index("building").bbl.reindex(frame.building.to_numpy())
    lots = pluto.reindex(lot.to_numpy()).reset_index(drop=True)
    if _ALTER_DATED.get():
        lots = dated_alterations(frame, lot.to_numpy(), lots, _ALTER_DATED.get())
    if _RELEASED.get():
        lots = released_lots(frame, lot.to_numpy(), lots, _RELEASED.get())
    return lots


# Fields every release keeps as today's: the lot's identity and position, and
# the year built, a fact that does not change which older releases often
# estimate (round years).
RELEASE_KEEPS_TODAY = (
    "bbl",
    "address",
    "version",
    "yearbuilt",
    "latitude",
    "longitude",
)


def released_lots(
    frame: pd.DataFrame, bbl: np.ndarray, lots: pd.DataFrame, path: str
) -> pd.DataFrame:
    """`lots` (today's MapPLUTO per row) with each row's lot as the latest
    MapPLUTO release published at least PLUTO_RELEASE_BUFFER_DAYS before the
    listing's period had it, or the earliest release for a listing before
    that. A release with no publication date is never read. A lot missing from
    the release (numbered later), a field the release does not carry (the
    flood-zone flags before 2017), the fields in RELEASE_KEEPS_TODAY, and a
    release published before today's year built (it describes the lot before
    the building) keep today's values. Codes are written as today's file
    writes them (landuse "04" as "4", irrlotcode "Y" as True), so a code
    changes only when the release's code does (decimals may be written with
    other trailing zeros; every reader parses them as numbers). A listing
    before the earliest release reads it anyway (none in the data, which
    starts in 2010). No rents are read."""
    history = pd.read_parquet(path)
    history = history[history.published.notna()]
    published = pd.to_datetime(
        history.drop_duplicates("release").set_index("release").published
    ).sort_values()
    usable = (published + pd.Timedelta(days=PLUTO_RELEASE_BUFFER_DAYS)).to_numpy()
    listed = pd.DatetimeIndex(frame.period).to_numpy()
    order = np.clip(np.searchsorted(usable, listed, side="right") - 1, 0, None)
    release = published.index.to_numpy()[order]
    keys = pd.MultiIndex.from_arrays([release, pd.Series(bbl).astype(str).to_numpy()])
    indexed = history.set_index(["release", "bbl"])
    then = indexed.reindex(keys).reset_index(drop=True)
    built = pd.to_numeric(lots.yearbuilt, errors="coerce").to_numpy()
    use = keys.isin(indexed.index) & ~(built > published.dt.year.to_numpy()[order])
    out = lots.copy()
    for column in out.columns.intersection(then.columns).difference(
        RELEASE_KEEPS_TODAY
    ):
        value = then[column].astype("string").str.strip().replace("", pd.NA)
        carried = indexed[column].notna().groupby(level="release").any()
        take = use & carried.reindex(release).fillna(False).astype(bool).to_numpy()
        today = out[column]
        if pd.api.types.is_bool_dtype(today):
            flag = value.str.upper().map({"Y": True, "N": False, "TRUE": True})
            take &= flag.notna().to_numpy()
            out[column] = np.where(take, flag.to_numpy(), today.to_numpy()).astype(bool)
            continue
        if today.dropna().astype(str).str.fullmatch(r"0|[1-9]\d*").all():
            value = value.str.replace(r"^0+(?=\d)", "", regex=True)
        out[column] = today.astype(object).where(~take, value.to_numpy(dtype=object))
        out[column] = out[column].astype(today.dtype)
    return out


def dated_alterations(
    frame: pd.DataFrame, bbl: np.ndarray, lots: pd.DataFrame, path: str
) -> pd.DataFrame:
    """`lots` (today's MapPLUTO per row) with the two alteration years as
    MapPLUTO's release of the year before the listing's year had them (a year's
    first release comes out in its spring, so a listing never sees a later
    alteration), or the earliest release before that. Every other field keeps
    today's value: across releases they are mostly revised estimates of the same
    building, not changes to it. A lot missing from that release, and a release
    older than today's year built (it describes the lot before the building),
    keep today's values too. No rents are read."""
    history = pd.read_parquet(
        path, columns=["release", "bbl", "yearalter1", "yearalter2"]
    )
    history["bbl"] = history.bbl.astype(str).str.strip()
    releases = np.sort(history.release.unique())
    year = pd.DatetimeIndex(frame.period).year.to_numpy() - 1
    release = releases[
        np.clip(np.searchsorted(releases, year, side="right") - 1, 0, None)
    ]
    keys = pd.MultiIndex.from_arrays([release, pd.Series(bbl).astype(str).to_numpy()])
    indexed = history.set_index(["release", "bbl"])
    then = indexed.reindex(keys).reset_index(drop=True)
    built = pd.to_numeric(lots.yearbuilt, errors="coerce").to_numpy()
    use = keys.isin(indexed.index) & ~(built > release)
    out = lots.copy()
    for column in ("yearalter1", "yearalter2"):
        dated = pd.to_numeric(then[column], errors="coerce").to_numpy()
        out[column] = np.where(
            use, dated, pd.to_numeric(out[column], errors="coerce").to_numpy()
        )
    return out


def lpc_as_of(frame: pd.DataFrame, path: str) -> tuple[np.ndarray, np.ndarray]:
    """Per row: whether the Landmarks Preservation Commission had designated
    its building's lot an individual or interior landmark, and whether it had
    designated it part of a historic district, by the day of the listing (no
    future information: MapPLUTO's fields are today's status). A lot the LPC
    has no record of is neither."""
    lpc = pd.read_parquet(path)
    lpc["desdate"] = pd.to_datetime(lpc.desdate, format="%m/%d/%Y")
    lpc = lpc[lpc.status.eq("DESIGNATED")]
    registry = pd.read_parquet(lot_registry()).set_index("building").bbl
    bbl = registry.reindex(frame.building.to_numpy()).astype(str).to_numpy()
    listed = pd.to_datetime(frame.price_at, utc=True).dt.tz_localize(None).to_numpy()
    out = []
    for district in (False, True):
        kind = lpc[lpc.lm_type.eq("Historic District") == district]
        since = kind.groupby("bbl").desdate.min().reindex(bbl).to_numpy()
        out.append(~pd.isna(since) & (since <= listed))
    return out[0], out[1]


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
    if _LPC.get():
        landmark, district = lpc_as_of(frame, _LPC.get())
    else:
        landmark, district = lot.landmark.notna(), lot.histdist.notna()
    b.add("building status", "landmark", landmark)
    b.add("building status", "historic_district", district)
    if flood_zone:
        b.add("building status", "flood_zone_2015", lot.pfirm15_flag.notna())
    altered = num["yearalter1"]
    if latest_alteration:
        altered = pd.concat([altered, num["yearalter2"]], axis=1).max(axis=1)
    if _AS_OF.get():
        # The later alteration if it was done before the listing's year, else
        # the earlier one if that was (a year's own alterations may postdate
        # its listings, so they wait for the next year).
        assert latest_alteration, "as-of alterations read both recorded years"
        listed = pd.to_datetime(frame.period).dt.year.to_numpy()
        a1, a2 = num["yearalter1"].to_numpy(), num["yearalter2"].to_numpy()
        done = [np.where(a < listed, a, np.nan) for a in (a1, a2)]
        altered = pd.Series(np.fmax(*done), index=lot.index)
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


def building_frontage() -> pd.DataFrame:
    """Per registry building: its frontage street type (avenue, wide street,
    side street) and the grid direction its front faces (the side of its
    address street it stands on, from the street's centerline)."""
    return _building_frontage(lot_registry(), area_snapshot()[0])


@functools.lru_cache(maxsize=2)
def _building_frontage(
    registry_file: str, basemap_file: str = BASEMAP_FILE
) -> pd.DataFrame:
    registry = pd.read_parquet(registry_file).set_index("building")
    lat0, lon0 = _grid_origin()
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

    streets = pd.read_parquet(basemap_file).query("layer == 'street'")
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


def building_sides() -> pd.DataFrame:
    """Per registry building with a footprint: for each grid direction the type
    of street that side looks onto, or "none" (no street), or "no facade"."""
    return _building_sides(lot_registry(), *area_snapshot())


def facing_grid():
    """Lon/lat to the facing grid (metres; x across the avenues, y along them)."""
    lat0, lon0 = _grid_origin()
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

    return grid


def building_outlines(registry_file: str, footprints_file: str, reach: float):
    """Per registry building with a footprint: (building, its counter-clockwise
    outline in grid metres, (starts, ends) of the other buildings' outline edges
    within `reach` of it)."""
    registry = pd.read_parquet(registry_file).set_index("building")
    grid = facing_grid()

    def rings_of(geometry):
        geometry = json.loads(geometry)
        polygons = geometry["coordinates"]
        polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
        return [grid([q[0] for q in pg[0]], [q[1] for q in pg[0]]) for pg in polygons]

    footprints = pd.read_parquet(footprints_file)
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
        # outlines of the building itself (its BIN) are left to the caller,
        # which lets the outline's own walls block.
        own = (owner == ring_bin) & (not re.fullmatch(r"[1-5]000000", ring_bin))
        centre = ring.mean(0)
        radius = float(np.hypot(*(ring - centre).T).max()) + reach + 10.0
        # A lower bound on each edge's distance from the centre.
        dist = np.minimum(np.hypot(*(e0 - centre).T), np.hypot(*(e1 - centre).T))
        near = (dist - np.hypot(*(e1 - e0).T) < radius) & ~own
        yield building, ring, (e0[near], e1[near])


def street_lines(basemap_file: str, kind_of) -> tuple:
    """(starts, ends, kinds) of the basemap's street centerline segments in grid
    metres, kind_of(name, attributes) naming each street's kind (None skips it)."""
    grid = facing_grid()
    starts, ends, kinds = [], [], []
    for row in pd.read_parquet(basemap_file).query("layer == 'street'").itertuples():
        kind = kind_of(row.name, json.loads(row.attributes))
        if kind is None:
            continue
        geometry = json.loads(row.geometry)
        lines = geometry["coordinates"]
        for line in lines if geometry["type"] == "MultiLineString" else [lines]:
            pts = grid([p[0] for p in line], [p[1] for p in line])
            starts.append(pts[:-1])
            ends.append(pts[1:])
            kinds += [kind] * (len(pts) - 1)
    return np.concatenate(starts), np.concatenate(ends), np.array(kinds)


def _side_kind(name: str, attributes: dict) -> str | None:
    roadway = attributes.get("rw_type")
    if roadway not in ("1", "2", "3", "9"):
        return None
    return street_kind(name, roadway)


@functools.lru_cache(maxsize=2)
def _building_sides(
    registry_file: str,
    basemap_file: str = BASEMAP_FILE,
    footprints_file: str = FOOTPRINTS_FILE,
) -> pd.DataFrame:
    streets = street_lines(basemap_file, _side_kind)
    out = {
        building: facade_sides(ring, streets, occluders)
        for building, ring, occluders in building_outlines(
            registry_file, footprints_file, SIDE_REACH_M
        )
    }
    return pd.DataFrame.from_dict(out, orient="index")


def front_rear(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per row: whether the listing puts the apartment at its building's front
    (on the address street) and at its rear, from F/R labels, ad text
    (floor-throughs both) and views."""
    from . import descriptions

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
    return front, rear


def unit_sides(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row: whether its unit looks onto an avenue, a wide street, a side
    street, or no street (rear, courtyard), pooled over the unit's listings,
    from window directions against its building's sides, front/rear labels,
    ad text and views (text, labels and views place the front on the address
    street)."""
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
    front, rear = front_rear(frame)
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


def building_violations(
    frame: pd.DataFrame,
    days: int = 365,
    hpd_file: str | None = None,
    registry_file: str | None = None,
) -> np.ndarray:
    """Per row: class B and C violations found in its building (registry BIN,
    or its lot for placeholder BINs) in the `days` before the row's month."""
    registry = pd.read_parquet(registry_file or REGISTRY_FILE).set_index("building")
    hpd = pd.read_parquet(hpd_file or HPD_FILE)
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
    file: str | None = None,
) -> Features:
    """A base set plus the building's condition as of the listing: hazardous
    housing-code violations HPD found in the `years` before, per apartment and
    year (none, a few, or `many` or more). Apartments are MapPLUTO's
    residential units, or the units listed in the building where the lot
    records none (condominium lots). With `file`, the violations are that
    snapshot's, matched through the set's own registry (`lot_registry`)."""
    base = FEATURE_SETS[base](frame, train)
    lot = building_lots(frame)
    units = pd.to_numeric(lot.unitsres, errors="coerce").to_numpy()
    listed = frame.groupby("building").unit_id.transform("nunique").to_numpy()
    units = np.where(units > 0, units, listed).clip(min=1)
    found = building_violations(
        frame,
        days=365 * years,
        hpd_file=file,
        registry_file=lot_registry() if file else None,
    )
    rate = found / units / years
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
    """Each row's floor as the base features read it (`base_v1` with
    label_floor, and the low-floor flags): the listed floor, or the unit label's
    floor where the label is plausible for the building's height; NaN when
    neither is known."""
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


# NYC 311 noise complaints (rentfrontier.external noise311).
NOISE_SNAPSHOT = "/data1/apartments/external/noise311/20260930-1549d7a"
NOISE_FILE = f"{NOISE_SNAPSHOT}/noise311.parquet"
# The same complaints over the GV registry's box (2026-10-06), for nb3 sets.
NB3_NOISE_FILE = "/data1/apartments/external/noise311/20261006-c095e36/noise311.parquet"
NOISE_RADIUS_M = 100.0  # about a block
NOISE_STREET = (
    "Noise - Street/Sidewalk",
    "Noise - Vehicle",
    "Noise - Commercial",
    "Noise - Park",
)


def noise_kind(t: pd.DataFrame) -> pd.Series:
    """Street and nightlife (people, music, traffic, bars) or construction
    (after-hours work, equipment, jackhammers); other noise complaints (a
    neighbour's apartment, helicopters) are left out."""
    kind = pd.Series(None, index=t.index, dtype=object)
    kind[t.complaint_type.isin(NOISE_STREET)] = "street and nightlife"
    construction = t.complaint_type.eq("Noise") & t.descriptor.fillna("").str.contains(
        r"Construction|Jack Hammering"
    )
    kind[construction] = "construction"
    return kind


@functools.lru_cache(maxsize=2)
def _noise_times(registry_file: str, noise_file: str = NOISE_FILE) -> dict:
    """{kind: {building: sorted times of complaints within NOISE_RADIUS_M}}."""
    from scipy.spatial import cKDTree

    registry = (
        pd.read_parquet(registry_file)
        .dropna(subset=["latitude", "longitude"])
        .set_index("building")
    )
    t = pd.read_parquet(noise_file).dropna(subset=["latitude", "longitude"])
    t = t.assign(kind=noise_kind(t), when=pd.to_datetime(t.created_date))
    t = t[t.kind.notna()]
    lat0, lon0 = _grid_origin()
    cos0, metres = math.cos(math.radians(lat0)), 111_320.0

    def xy(lon, lat):
        return np.c_[(lon - lon0) * metres * cos0, (lat - lat0) * metres]

    here = xy(registry.longitude.to_numpy(), registry.latitude.to_numpy())
    out = {}
    for kind, g in t.groupby("kind"):
        tree = cKDTree(xy(g.longitude.to_numpy(), g.latitude.to_numpy()))
        times = g.when.to_numpy().astype("datetime64[ns]")
        hits = tree.query_ball_point(here, r=NOISE_RADIUS_M)
        out[kind] = {
            b: np.sort(times[np.asarray(h, dtype=int)])
            for b, h in zip(registry.index, hits)
        }
    return out


def nearby_noise(
    frame: pd.DataFrame, days: int = 365, noise_file: str = NOISE_FILE
) -> dict:
    """Per kind and row: log2 of 1 + the 311 noise complaints within
    NOISE_RADIUS_M of its building in the `days` before the row's month, less
    the same over every registry building that month (Chelsea's average: 311
    use grew over the years). Rows of buildings without coordinates get 0."""
    times = _noise_times(lot_registry(), noise_file)
    period = frame.period.to_numpy().astype("datetime64[ns]")
    months = np.unique(period)
    back = np.timedelta64(days, "D")

    def log_count(ts, at):
        return np.log2(1 + np.searchsorted(ts, at) - np.searchsorted(ts, at - back))

    out = {}
    for kind, by_building in times.items():
        chelsea = np.mean(
            [log_count(ts, months) for ts in by_building.values()], axis=0
        )
        ref = chelsea[np.searchsorted(months, period)]
        v = np.zeros(len(frame))
        for building, idx in frame.groupby("building").indices.items():
            ts = by_building.get(building)
            if ts is not None:
                v[idx] = log_count(ts, period[idx]) - ref[idx]
        out[kind] = v
    return out


def noise_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "noise-v1",
    base: str = "unitfacing-v5",
    noise_file: str = NOISE_FILE,
) -> Features:
    """A base set plus the noise around the building as of the listing: 311
    complaints within about a block in the year before, street and nightlife,
    and construction, each in doublings against Chelsea's average that month."""
    base = FEATURE_SETS[base](frame, train)
    noise = nearby_noise(frame, noise_file=noise_file)
    b = _Builder(frame)
    for kind in ("street and nightlife", "construction"):
        b.add("noise", f"{kind} noise complaints nearby (doublings)", noise[kind])
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def neighbourhood_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "neighbourhood-v1",
    base: str = "unitfloor-v2",
) -> Features:
    """A base set plus the neighbourhood: West Village against Chelsea (the
    shift of every building's level there, before its own building effect)."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    b.add("neighbourhood", "West Village", frame.neighbourhood.eq("West Village"))
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def greenwich_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "greenwich-v1",
    base: str = "nb-coded-v1",
) -> Features:
    """A base set plus Greenwich Village against Chelsea, beside the base set's
    West Village term (`neighbourhood_v1`)."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    b.add(
        "neighbourhood",
        "Greenwich Village",
        frame.neighbourhood.eq("Greenwich Village"),
    )
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def hood_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
    hood: str,
) -> Features:
    """A base set plus one more neighbourhood against Chelsea (`hood`), beside
    the base set's neighbourhood terms (`greenwich_v1`)."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    b.add("neighbourhood", hood, frame.neighbourhood.eq(hood))
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def hoods_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
    hoods: tuple[str, ...],
) -> Features:
    """A base set plus one column per neighbourhood in `hoods` against Chelsea,
    beside the base set's neighbourhood terms (`hood_v1` for several)."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    for hood in hoods:
        b.add("neighbourhood", hood, frame.neighbourhood.eq(hood))
    extra = b.build(id)
    return Features(
        id,
        base.names + extra.names,
        base.groups + extra.groups,
        np.column_stack([base.values, extra.values]),
        np.concatenate([base.prior_scale, extra.prior_scale]),
    )


def stabilized_units(frame: pd.DataFrame) -> np.ndarray:
    """Per row: the rent-stabilized units on its lot's tax bill of the year
    before the listing's year, or of the latest earlier bill year (the
    2020-2022 bills are missing for some lots). Bills come out in June, so a
    year's gap keeps any later bill out. A bill counts for at most
    `STAB_CARRY_YEARS` after its year (enough to bridge 2020-2022), so a lot
    that left the bills counts 0 afterwards. A lot with no bill by then counts
    0, as does a lot whose earlier bills sit under an old lot number."""
    registry = pd.read_parquet(lot_registry()).set_index("building")
    stab = pd.read_parquet(RENTSTAB_FILE)
    by_lot = {
        lot: (g.year.to_numpy(), g.units.to_numpy())
        for lot, g in stab.sort_values("year").groupby("bbl")
    }
    cutoff = pd.DatetimeIndex(frame.period).year.to_numpy() - 1
    out = np.zeros(len(frame))
    for building, idx in frame.groupby("building").indices.items():
        if building not in registry.index:
            continue
        years, units = by_lot.get(str(registry.loc[building].bbl), (None, None))
        if years is None:
            continue
        at = np.searchsorted(years, cutoff[idx], side="right") - 1
        last = np.maximum(at, 0)
        fresh = (at >= 0) & (cutoff[idx] - years[last] <= STAB_CARRY_YEARS)
        out[idx] = np.where(fresh, units[last], 0)
    return out


def stabilized_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set plus the share of the building's apartments that were rent
    stabilized as of the listing (`stabilized_units` over MapPLUTO's
    residential units, or the units listed where the lot records none; at most
    1), centred on the training rows. It changes within a building as units
    leave stabilization, which the building level cannot follow. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    units = pd.to_numeric(building_lots(frame).unitsres, errors="coerce").to_numpy()
    listed = frame.groupby("building").unit_id.transform("nunique").to_numpy()
    units = np.where(units > 0, units, listed).clip(min=1)
    share = np.clip(stabilized_units(frame) / units, 0.0, 1.0)
    b = _Builder(frame)
    b.add("regulation", "stabilized share", share - float(np.mean(share[train])))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def footprint_area(geometry: str) -> float:
    """Square feet inside a footprint's GeoJSON polygon or polygons (holes
    taken out)."""
    grid = facing_grid()
    geometry = json.loads(geometry)
    polygons = geometry["coordinates"]
    polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
    total = 0.0
    for polygon in polygons:
        for k, ring in enumerate(polygon):
            r = grid([q[0] for q in ring], [q[1] for q in ring])
            a = abs(0.5 * np.sum(r[:-1, 0] * r[1:, 1] - r[1:, 0] * r[:-1, 1]))
            total += a if k == 0 else -a
    return total * 10.7639


def lot_open_share(frame: pd.DataFrame) -> np.ndarray:
    """Per row: the share of its building's lot no building stands on, from
    the footprints on the lot built by the listing's year (a footprint with no
    year counts throughout) over MapPLUTO's lot area, in [0, 1]. The lot is the
    one the building's own footprint sits on (the base lot of a condominium),
    else its registry lot. NaN where the lot has no footprint or no area."""
    registry = pd.read_parquet(lot_registry()).set_index("building")
    footprints = pd.read_parquet(area_snapshot()[1])
    footprints["area"] = footprints.geometry.map(footprint_area)
    footprints["built"] = pd.to_numeric(footprints.construction_year, errors="coerce")
    base_of = dict(zip(footprints.bin.astype(str), footprints.base_bbl.astype(str)))
    by_lot = {
        lot: (g.built.fillna(0).to_numpy(), g.area.to_numpy())
        for lot, g in footprints.groupby(footprints.base_bbl.astype(str))
    }
    lotarea = pd.to_numeric(building_lots(frame).lotarea, errors="coerce").to_numpy()
    year = pd.DatetimeIndex(frame.period).year.to_numpy()
    out = np.full(len(frame), np.nan)
    for building, idx in frame.groupby("building").indices.items():
        if building not in registry.index:
            continue
        r = registry.loc[building]
        lot = base_of.get(str(r.bin), str(r.bbl))
        if lot not in by_lot:
            continue
        built, area = by_lot[lot]
        covered = np.array([area[built <= y].sum() for y in year[idx]])
        with np.errstate(divide="ignore", invalid="ignore"):
            out[idx] = 1.0 - covered / lotarea[idx]
    out[~(np.isfinite(out) & (lotarea > 0))] = np.nan
    return np.clip(out, 0.0, 1.0)


def open_space_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set plus the share of the building's lot left open
    (`lot_open_share`: courtyards, gardens, a campus's grounds), centred on the
    training rows, 0 with an indicator where unknown. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    share = lot_open_share(frame)
    known = np.isfinite(share)
    b = _Builder(frame)
    b.add(
        "building size",
        "open lot share",
        np.where(known, share - float(np.mean(share[train & known])), 0.0),
    )
    b.add("building size", "open_lot_share_unknown", ~known)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# A footprint may cover its lot by up to this share more than MapPLUTO's lot
# area and still count as the whole lot built on: roof outlines take in
# cornices and overhangs, and lot areas are rounded. About 290 of the six
# neighbourhoods' 3,700 buildings are over by 0 to 10%, most of them row
# houses that fill their lots; above 10% the lot area does not describe the
# footprint, and the share is left unknown.
OPEN_SHARE_OVERHANG = 0.10


def _footprint_rings(geometry: str, grid) -> list[tuple[int, np.ndarray]]:
    """Every ring of a footprint's GeoJSON polygon or polygons, in grid metres,
    as (its index in its polygon, so 0 is the outer ring; the ring)."""
    geometry = json.loads(geometry)
    polygons = geometry["coordinates"]
    polygons = polygons if geometry["type"] == "MultiPolygon" else [polygons]
    return [
        (k, grid([q[0] for q in ring], [q[1] for q in ring]))
        for polygon in polygons
        for k, ring in enumerate(polygon)
    ]


def _rings_area(rings) -> float:
    """Square feet inside `_footprint_rings` (holes taken out)."""
    total = 0.0
    for k, r in rings:
        a = abs(0.5 * np.sum(r[:-1, 0] * r[1:, 1] - r[1:, 0] * r[:-1, 1]))
        total += a if k == 0 else -a
    return total * 10.7639


def _rings_contain(rings, points: np.ndarray) -> np.ndarray:
    """Which points (grid metres, n x 2) lie inside the rings (even-odd, so
    holes are out)."""
    x, y = points[:, :1], points[:, 1:]
    inside = np.zeros(len(points), bool)
    for _, r in rings:
        x1, y1, x2, y2 = r[:-1, 0], r[:-1, 1], r[1:, 0], r[1:, 1]
        spans = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x1 + (x2 - x1) * (y - y1) / (y2 - y1)
        inside ^= (spans & (x < at)).sum(1) % 2 == 1
    return inside


def lot_open_share_v2(frame: pd.DataFrame) -> np.ndarray:
    """Per row: the share of its building's lot no building stands on, as
    `lot_open_share`, over the union of the lots its footprints span. A lot
    joins the union when its MapPLUTO point (`BLOCKLOTS_FILE`, the lots of the
    registry's blocks; not a condominium's billing lots) lies inside a
    footprint built by the listing's year on another lot of the block, and
    lots chained this way form one union: covered is every footprint on them
    built by that year, over their summed lot areas (the building's own lot's
    from its MapPLUTO release, the others' from today's). Covered up to
    OPEN_SHARE_OVERHANG over the union's area is 0 open; more than that, no
    footprint, or no lot area is NaN. Reads no rents."""
    grid = facing_grid()
    registry = pd.read_parquet(lot_registry()).set_index("building")
    footprints = pd.read_parquet(area_snapshot()[1])
    footprints["base_bbl"] = footprints.base_bbl.astype(str)
    rings = [_footprint_rings(g, grid) for g in footprints.geometry]
    footprints["area"] = [_rings_area(r) for r in rings]
    built = pd.to_numeric(footprints.construction_year, errors="coerce").fillna(0)
    footprints["built"] = built
    lots = pd.read_parquet(BLOCKLOTS_FILE)
    lots = lots[pd.to_numeric(lots.lot, errors="coerce") < 7501]
    lots_area = dict(zip(lots.bbl, pd.to_numeric(lots.lotarea, errors="coerce")))
    points = grid(
        pd.to_numeric(lots.longitude, errors="coerce").to_numpy(),
        pd.to_numeric(lots.latitude, errors="coerce").to_numpy(),
    )
    block = lots.bbl.str[:6].to_numpy()
    # (footprint's lot, a lot whose point it covers, the year it was built)
    joins = [
        (lot, other, year)
        for lot, r, year in zip(footprints.base_bbl, rings, footprints.built)
        for other in lots.bbl[block == lot[:6]][
            _rings_contain(r, points[block == lot[:6]])
        ]
        if other != lot
    ]
    by_lot = {
        lot: (g.built.to_numpy(), g.area.to_numpy())
        for lot, g in footprints.groupby("base_bbl")
    }

    def unions(year: int) -> dict[str, list[str]]:
        """Each lot's union as of `year`: its lots."""
        parent: dict[str, str] = {}

        def find(lot: str) -> str:
            while parent.get(lot, lot) != lot:
                lot = parent[lot]
            return lot

        for lot, other, built_in in joins:
            if built_in <= year and find(other) != find(lot):
                parent[find(other)] = find(lot)
        members: dict[str, list[str]] = {}
        for lot in {x for j in joins for x in j[:2]}:
            members.setdefault(find(lot), []).append(lot)
        return {lot: m for m in members.values() for lot in m}

    base_of = dict(zip(footprints.bin.astype(str), footprints.base_bbl))
    lotarea = pd.to_numeric(building_lots(frame).lotarea, errors="coerce").to_numpy()
    year = pd.DatetimeIndex(frame.period).year.to_numpy()
    by_year = {y: unions(y) for y in np.unique(year)}
    out = np.full(len(frame), np.nan)
    for building, idx in frame.groupby("building").indices.items():
        if building not in registry.index:
            continue
        r = registry.loc[building]
        lot = base_of.get(str(r.bin), str(r.bbl))
        for i in idx:
            union = by_year[year[i]].get(lot, [lot])
            if not any(m in by_lot for m in union):
                continue
            # The building's own lot is its registry lot's MapPLUTO area; its
            # footprint's lot, where that differs, is the same ground.
            others = sum(
                lots_area.get(m, np.nan) for m in union if m not in (lot, str(r.bbl))
            )
            covered = sum(
                area[built_in <= year[i]].sum()
                for built_in, area in (by_lot[m] for m in union if m in by_lot)
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                out[i] = 1.0 - covered / (lotarea[i] + others)
    out[~(np.isfinite(out) & (lotarea > 0) & (out >= -OPEN_SHARE_OVERHANG))] = np.nan
    return np.clip(out, 0.0, 1.0)


def open_space_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """`open_space_v1` with `lot_open_share_v2`: a footprint spanning lots is
    measured over their union, and a lot area that cannot hold its footprint
    is unknown rather than 0 open. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    share = lot_open_share_v2(frame)
    known = np.isfinite(share)
    b = _Builder(frame)
    b.add(
        "building size",
        "open lot share",
        np.where(known, share - float(np.mean(share[train & known])), 0.0),
    )
    b.add("building size", "open_lot_share_unknown", ~known)
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# A large single-owner complex: one Department of Finance owner name (MapPLUTO
# `ownername`, `BLOCKLOTS_FILE`) holding at least this many buildings and
# residential units on one tax block. Owner names that stand for no one
# (unavailable, not on file) hold nothing.
COMPLEX_MIN_BUILDINGS = 3
COMPLEX_MIN_UNITS = 300
_NO_OWNER = {"", "UNAVAILABLE OWNER", "NAME NOT ON FILE"}


def single_owner_complex(frame: pd.DataFrame) -> np.ndarray:
    """Per row: whether its building's registry lot belongs to a large
    single-owner complex (COMPLEX_MIN_BUILDINGS, COMPLEX_MIN_UNITS): the lots
    of its block with the same owner name hold that many buildings and
    residential units between them. The owner is today's, read for every
    year: a complex is sold whole, not split. A condominium's billing lots
    (7501 on) hold nothing. A campus held by differently named companies is
    missed. Reads no rents."""
    lots = pd.read_parquet(BLOCKLOTS_FILE)
    lots["owner"] = (
        lots.ownername.fillna("")
        .str.upper()
        .str.replace(r"[^A-Z0-9 ]", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    billing = pd.to_numeric(lots.lot, errors="coerce") >= 7501
    lots = lots[~lots.owner.isin(_NO_OWNER) & ~billing].copy()
    lots["block"] = lots.bbl.str[:6]
    for column in ("numbldgs", "unitsres"):
        lots[column] = pd.to_numeric(lots[column], errors="coerce").fillna(0)
    held = lots.groupby(["owner", "block"])[["numbldgs", "unitsres"]].transform("sum")
    complex_lots = set(
        lots.bbl[
            (held.numbldgs >= COMPLEX_MIN_BUILDINGS)
            & (held.unitsres >= COMPLEX_MIN_UNITS)
        ]
    )
    registry = pd.read_parquet(lot_registry()).set_index("building")
    in_complex = {
        building: str(bbl) in complex_lots for building, bbl in registry.bbl.items()
    }
    return frame.building.map(in_complex).fillna(False).to_numpy(bool)


def sizefill_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set with its size read as of the row's day (`sizefill.asof_size`):
    the stated size, else the unit's, its line's or its building's from earlier
    days, in place of the unit median over all of the unit's listings. The
    deviation from the bedroom median (training rows that state a size) and
    `sqft_unknown` are replaced, and indicators mark sizes filled from the line
    and from the building. Reads no rents."""
    from . import sizefill

    base = FEATURE_SETS[base](frame, train)
    size = sizefill.asof_size(frame)
    beds = _bedroom_label(unit_bedrooms(frame))
    log_sqft = np.log(size.sqft)
    stated = size.source.eq("own").to_numpy()
    median = log_sqft[train & stated].groupby(beds[train & stated]).median()
    deviation = (log_sqft - beds.map(median)).fillna(0.0)
    values = base.values.copy()
    values[:, base.names.index("log_sqft_vs_bedroom_median")] = deviation
    values[:, base.names.index("sqft_unknown")] = size.source.eq("none")
    b = _Builder(frame)
    b.add("size", "size from the line", size.source.eq("line"))
    b.add("size", "size from the building", size.source.eq("building"))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def nta_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set plus the building's 2020 Neighborhood Tabulation Area
    (`rentfrontier.nta`, `NTA_FILE`), against Chelsea-Hudson Yards. The areas
    cut across StreetEasy's: Chelsea's east side is in Midtown South-Flatiron-
    Union Square, part of Flatiron in Gramercy, part of Greenwich Village in
    West Village. A building in no area is "unknown". Stuyvesant Town-Peter
    Cooper Village takes the reference level: its own level would be the
    Stuyvesant Town/PCV indicator the nostuy base leaves out for explanatory
    terms. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    areas = pd.read_parquet(NTA_FILE).set_index("building").ntaname
    name = frame.building.map(areas).fillna("unknown")
    name = name.replace(NTA_FOLDED, "Chelsea-Hudson Yards")
    b = _Builder(frame)
    b.categorical("nta", name, reference="Chelsea-Hudson Yards")
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# NTAs that take the reference level in nb8's NTA set (`nta_v2`), besides
# Stuyvesant Town-Peter Cooper Village. East Village's NTA holds exactly
# StreetEasy's East Village rows, so its level would equal nb8-nostuy-v1's East
# Village indicator. The West Village and Greenwich Village NTAs together hold
# exactly those two neighbourhoods' rows, so with both levels the four columns
# sum to zero in one direction; Greenwich Village's level adds nothing the
# other three don't hold.
NB8_NTA_FOLDED = (NTA_FOLDED, "East Village", "Greenwich Village")


def nta_names(frame: pd.DataFrame, folded: tuple[str, ...]) -> pd.Series:
    """Each row's building's 2020 NTA (`NTA_FILE`), "unknown" for a building in
    none, and each NTA in `folded` as the reference, Chelsea-Hudson Yards."""
    areas = pd.read_parquet(NTA_FILE).set_index("building").ntaname
    name = frame.building.map(areas).fillna("unknown")
    return name.replace(dict.fromkeys(folded, "Chelsea-Hudson Yards"))


def nta_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
    folded: tuple[str, ...] = NB8_NTA_FOLDED,
) -> Features:
    """`nta_v1` with each NTA in `folded` taking the reference level: an NTA
    whose rows are one neighbourhood's would only repeat that neighbourhood's
    indicator. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    b.categorical("nta", nta_names(frame, folded), reference="Chelsea-Hudson Yards")
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


def owner_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set plus an indicator of a large single-owner complex
    (`single_owner_complex`): one landlord's campus, as Stuyvesant Town, Peter
    Cooper Village, London Terrace or Penn South. Reads no rents."""
    base = FEATURE_SETS[base](frame, train)
    b = _Builder(frame)
    b.add("building size", "single-owner complex", single_owner_complex(frame))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# Each listing's lister (`rentfrontier.lister`): name kind and how many of the
# building's earlier listings the same lister listed.
LISTER_FILE = "/data1/apartments/external/lister/20261010-b5c71cf/lister.parquet"


def lister_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """A base set plus who listed the advertisement, from its own record: the
    lister's kind by name (management, owner or other, against brokerage) and
    whether the lister is the building's own agent, having listed at least half
    of at least five of the building's earlier captured listings (own or
    fewer than five earlier, against outside). Reads no rents; a listing
    missing from the snapshot is other and has fewer than five earlier."""
    base = FEATURE_SETS[base](frame, train)
    snap = pd.read_parquet(
        LISTER_FILE, columns=["listing_id", "kind", "earlier", "earlier_same"]
    ).set_index("listing_id")
    ids = frame.source_listing_id.astype(str)
    kinds = ids.map(snap.kind).fillna("other")
    earlier = pd.to_numeric(ids.map(snap.earlier), errors="coerce").fillna(0)
    same = pd.to_numeric(ids.map(snap.earlier_same), errors="coerce").fillna(0)
    b = _Builder(frame)
    b.categorical("lister", kinds, reference="brokerage")
    b.categorical(
        "building agent", lister_module.own_agent(earlier, same), reference="outside"
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# Feature sets that read the external snapshots (run records list them).
EXTERNAL = {
    "nb-pluto-base",
    "nb-unitpluto-v1",
    "nb-facing-v1",
    "nb-facing-v2",
    "nb-bedtext-v1",
    "nb-facing-v3",
    "nb-bedtext-v2",
    "nb-relist-v1",
    "nb-coded-v1",
    "nb-lineface-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
    "wv-unitpluto-v1",
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
    "unitfacing-v5",
    "unitnoise-v1",
    "unitdescpluto-v4",
    "unitdescpluto-v5",
    "unitdescplutohpd-v1",
    "unitdescplutohpd-v2",
}
# Feature sets that read the subway stations snapshot.
SUBWAY = {"unitdescplutotransit-v2"}
# Feature sets that read the basemap snapshot (street centerlines).
BASEMAP = {
    "unitfacing-v2",
    "unitfacing-v3",
    "unitfacing-v4",
    "unitfacing-v5",
    "unitnoise-v1",
    "nb-facing-v1",
    "nb-facing-v2",
    "nb-bedtext-v1",
    "nb-facing-v3",
    "nb-bedtext-v2",
    "nb-relist-v1",
    "nb-coded-v1",
    "nb-lineface-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
}
# Feature sets that read the building footprints snapshot.
FOOTPRINTS = {
    "unitfacing-v3",
    "unitfacing-v4",
    "unitfacing-v5",
    "unitnoise-v1",
    "nb-facing-v1",
    "nb-facing-v2",
    "nb-bedtext-v1",
    "nb-facing-v3",
    "nb-bedtext-v2",
    "nb-relist-v1",
    "nb-coded-v1",
    "nb-lineface-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
}
# Feature sets that read the 311 noise complaints snapshot.
NOISE = {"unitnoise-v1", "nb3-noise-v1", "nb5-noise-v1"}
# The 311 file each NOISE set reads (else NOISE_FILE).
NOISE_FILES = {"nb3-noise-v1": NB3_NOISE_FILE, "nb5-noise-v1": NB4_NOISE_FILE}
# Feature sets that read the subway GTFS (transit.network).
TRANSIT = {"nb3-transit-v1", "nb3-lines-v1", "nb3-access-v1", "nb5-lines-v1"}
# Feature sets that read the LODES jobs snapshot (access).
LODES = {"nb3-access-v1"}
# Feature sets that read the places snapshot (nearby).
PLACES = {"nb3-nearby-v1"}
# Feature sets that read the Storefront Registry snapshot (retail).
STOREFRONTS = {"nb3-retail-v1"}
# Feature sets that read the NYC Parks properties snapshot (parks).
PARKS = {"nb3-parks-v1", "nb3-water-v1", "nb5-parks-v1", "nb5-water-v1"}
# Feature sets that read the HPD violations snapshot.
HPD = {"unitdescplutohpd-v1", "unitdescplutohpd-v2"}
# Feature sets that read the rent-stabilized units snapshot (`RENTSTAB_FILE`).
RENTSTAB = {
    "nb6-stab-v1",
    "nb6-nostuy-stab-v1",
    "nb6-nostuy-stabopen-v1",
    "nb6-nostuy-stabopen-v2",
    "nb6-nostuy-explain-v1",
}
# Feature sets that read the NTA snapshot (`NTA_FILE`).
NTA = {"nb6-nostuy-nta-v1"}
# Feature sets that read the block lots snapshot (`BLOCKLOTS_FILE`).
BLOCKLOTS = {
    "nb6-nostuy-open-v2",
    "nb6-nostuy-stabopen-v2",
    "nb6-nostuy-owner-v1",
    "nb6-nostuy-explain-v1",
}
# Feature sets that read the lister snapshot (`LISTER_FILE`).
LISTER = {"nb6-nostuy-lister-v1"}
# Feature sets that read the advertisement descriptions (`descriptions.SOURCE`),
# directly or through their base set.
DESCRIPTIONS = {
    "nb-facing-v1",
    "nb-facing-v2",
    "nb-bedtext-v1",
    "nb-facing-v3",
    "nb-bedtext-v2",
    "nb-relist-v1",
    "nb-coded-v1",
    "nb-lineface-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
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
    "unitfacing-v5",
    "unitnoise-v1",
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
    # Chelsea + West Village: building facts on the unit and floor features,
    # plus the neighbourhood.
    "nb-unitpluto-v1": partial(
        neighbourhood_v1, id="nb-unitpluto-v1", base="nb-pluto-base"
    ),
    "nb-pluto-base": partial(
        pluto_v1,
        id="nb-pluto-base",
        base="unitfloor-v2",
        flood_zone=False,
        latest_alteration=True,
    ),
    # Chelsea + West Village: the served design's terms (descriptions where a
    # description source has the ad, building facts, facing, the low-floor
    # flags) plus the neighbourhood.
    "nb-facing-v1": partial(neighbourhood_v1, id="nb-facing-v1", base="unitfacing-v4"),
    # nb-facing-v1 with West Village's ads too (`DESCRIPTION_SOURCES`).
    "nb-facing-v2": partial(neighbourhood_v1, id="nb-facing-v2", base="unitfacing-v4"),
    # nb-facing-v2 plus an ad that states fewer or more bedrooms than the record.
    "nb-bedtext-v1": partial(bedtext_v1, id="nb-bedtext-v1", base="nb-facing-v2"),
    # nb-facing-v2 and nb-bedtext-v1 with the building's alterations dated as of
    # each listing (`AS_OF_SETS`): no alteration from after the listing.
    "nb-facing-v3": partial(neighbourhood_v1, id="nb-facing-v3", base="unitfacing-v4"),
    "nb-bedtext-v2": partial(bedtext_v1, id="nb-bedtext-v2", base="nb-facing-v3"),
    # nb-bedtext-v2 plus the months since the apartment's previous listing.
    "nb-relist-v1": partial(relist_v1, id="nb-relist-v1", base="nb-bedtext-v2"),
    # nb-relist-v1 plus the listing record's outdoor space types and extra rooms.
    "nb-coded-v1": partial(coded_v1, id="nb-coded-v1", base="nb-relist-v1"),
    # nb-coded-v1 plus how the unit's previous listing was repriced before this one.
    "nb-prevprice-v1": partial(prevprice_v1, id="nb-prevprice-v1", base="nb-coded-v1"),
    # nb-coded-v1 plus orientation read from the apartment's line, as of each listing.
    "nb-lineface-v1": partial(lineface_v1, id="nb-lineface-v1", base="nb-coded-v1"),
    # nb-coded-v1 plus only how many times the previous listing was repriced (no ask).
    "nb-prevprice-v2": partial(
        prevprice_v1, id="nb-prevprice-v2", base="nb-coded-v1", change=False
    ),
    # Chelsea, West Village and Greenwich Village: nb-coded-v1 plus Greenwich
    # Village (`greenwich_v1`), on the three neighbourhoods' snapshots (NB3_*).
    "nb3-coded-v1": partial(greenwich_v1, id="nb3-coded-v1", base="nb-coded-v1"),
    # nb3-coded-v1 plus nb-prevprice-v1's and nb-lineface-v1's terms.
    "nb3-prevprice-v1": partial(
        prevprice_v1, id="nb3-prevprice-v1", base="nb3-coded-v1"
    ),
    "nb3-lineface-v1": partial(lineface_v1, id="nb3-lineface-v1", base="nb3-coded-v1"),
    # nb3-coded-v1 and nb3-prevprice-v1 with landmark and historic district
    # dated as of each listing from the LPC's designations (`LPC_SNAPSHOTS`).
    # (nb3-prevprice-v2 has nb-prevprice-v1's terms, not nb-prevprice-v2's.)
    "nb3-coded-v2": partial(greenwich_v1, id="nb3-coded-v2", base="nb-coded-v1"),
    # Chelsea, the West Village, Greenwich Village and Flatiron + Gramercy Park:
    # nb3-coded-v2 plus Flatiron + Gramercy Park (`hood_v1`), every term on the
    # four neighbourhoods' snapshots (NB4_*, `NB4_SETS`).
    "nb4-coded-v2": partial(
        hood_v1, id="nb4-coded-v2", base="nb3-coded-v2", hood="Flatiron + Gramercy Park"
    ),
    # The five neighbourhoods: nb3-coded-v2 plus Flatiron and Gramercy Park
    # (`hoods_v1`; DATASET_NB5 labels each Flatiron + Gramercy Park row with its
    # building's StreetEasy area), on the four crawls' snapshots (`NB4_SETS`).
    "nb5-coded-v2": partial(
        hoods_v1,
        id="nb5-coded-v2",
        base="nb3-coded-v2",
        hoods=("Flatiron", "Gramercy Park"),
    ),
    # nb5-coded-v2 with each building as the latest MapPLUTO release published
    # a week before the listing had it (PLUTO_RELEASED_SETS): the base for sets
    # after it (Ben, 2026-10-08).
    "nb5-plutoasof-v3": partial(
        hoods_v1,
        id="nb5-plutoasof-v3",
        base="nb3-coded-v2",
        hoods=("Flatiron", "Gramercy Park"),
    ),
    # nb5-plutoasof-v3 plus street trees near the building (`trees_v1`): an
    # explanatory term for greenery (Ben, 2026-10-08: explanatory features
    # over neighbourhood premiums).
    "nb5-trees-v1": partial(trees_v1, id="nb5-trees-v1", base="nb5-plutoasof-v3"),
    # nb5-plutoasof-v3 plus felonies reported near the building in the year
    # before the listing (`crime_v1`; coordinator relay 2026-10-08).
    "nb5-crime-v1": partial(crime_v1, id="nb5-crime-v1", base="nb5-plutoasof-v3"),
    # nb5-plutoasof-v3 plus building condition (`hpd_v1`, the past year) from
    # the five-neighbourhood HPD snapshot: retests the Chelsea and West Village
    # null of unitdescplutohpd-v1 as an explanatory term (Ben, 2026-10-08).
    "nb5-hpd-v1": partial(
        hpd_v1, id="nb5-hpd-v1", base="nb5-plutoasof-v3", file=NB4_HPD_FILE
    ),
    # nb5-plutoasof-v3 with the ad-text concession flag split at 2020, when
    # StreetEasy began coding concessions (`concession_era_v1`; Modeling's
    # proposal for the coordinator relay's concessions item, 2026-10-08).
    "nb5-concera-v1": partial(
        concession_era_v1, id="nb5-concera-v1", base="nb5-plutoasof-v3"
    ),
    # nb5-plutoasof-v3 plus NYU calendar windows, near campus and not (Ben,
    # 2026-10-08).
    "nb5-unical-v1": partial(unical_v1, id="nb5-unical-v1", base="nb5-plutoasof-v3"),
    # nb5-coded-v2 with the lot's alteration years as MapPLUTO had them before
    # the listing (ALTERATION_DATED_SETS); size and class stay today's.
    "nb5-plutoasof-v2": partial(
        hoods_v1,
        id="nb5-plutoasof-v2",
        base="nb3-coded-v2",
        hoods=("Flatiron", "Gramercy Park"),
    ),
    "nb3-prevprice-v2": partial(
        prevprice_v1, id="nb3-prevprice-v2", base="nb3-coded-v2"
    ),
    "nb3-garden-v1": partial(garden_v1, id="nb3-garden-v1", base="nb3-coded-v2"),
    "nb3-through-v1": partial(through_v1, id="nb3-through-v1", base="nb3-coded-v2"),
    "nb3-quiet-v1": partial(quiet_v1, id="nb3-quiet-v1", base="nb3-coded-v2"),
    "nb3-loud-v1": partial(loud_v1, id="nb3-loud-v1", base="nb3-coded-v2"),
    "nb3-transit-v1": partial(transit_v1, id="nb3-transit-v1", base="nb3-coded-v2"),
    "nb3-access-v1": partial(access_v1, id="nb3-access-v1", base="nb3-coded-v2"),
    "nb3-lines-v1": partial(lines_v1, id="nb3-lines-v1", base="nb3-coded-v2"),
    "nb3-bedsize-v1": partial(bedsize_v1, id="nb3-bedsize-v1", base="nb3-coded-v2"),
    "nb3-parks-v1": partial(parks_v1, id="nb3-parks-v1", base="nb3-coded-v2"),
    "nb3-nearby-v1": partial(nearby_v1, id="nb3-nearby-v1", base="nb3-coded-v2"),
    "nb3-retail-v1": partial(retail_v1, id="nb3-retail-v1", base="nb3-coded-v2"),
    # Pre-GV null sets, retested on the GV data (2026-10-06).
    "nb3-walkup-v1": partial(walkup_v1, id="nb3-walkup-v1", base="nb3-coded-v2"),
    "nb3-loc-v1": partial(location_v2, id="nb3-loc-v1", base="nb3-coded-v2"),
    "nb3-water-v1": partial(waterfront_v1, id="nb3-water-v1", base="nb3-parks-v1"),
    "nb3-text-v1": partial(text_flags_v1, id="nb3-text-v1", base="nb3-coded-v2"),
    "nb3-loft-v1": partial(loft_v1, id="nb3-loft-v1", base="nb3-coded-v2"),
    "nb3-flagfix-v1": partial(flagfix_v1, id="nb3-flagfix-v1", base="nb3-coded-v2"),
    "nb3-noise-v1": partial(
        noise_v1, id="nb3-noise-v1", base="nb3-coded-v2", noise_file=NB3_NOISE_FILE
    ),
    # Retests on the five neighbourhoods (DATASET_NB5): the nb3 sets on
    # nb5-coded-v2, reading the four crawls' snapshots.
    "nb5-lines-v1": partial(lines_v1, id="nb5-lines-v1", base="nb5-coded-v2"),
    "nb5-loc-v1": partial(location_v2, id="nb5-loc-v1", base="nb5-coded-v2"),
    "nb5-walkup-v1": partial(walkup_v1, id="nb5-walkup-v1", base="nb5-coded-v2"),
    "nb5-parks-v1": partial(parks_v1, id="nb5-parks-v1", base="nb5-coded-v2"),
    "nb5-water-v1": partial(waterfront_v1, id="nb5-water-v1", base="nb5-parks-v1"),
    "nb5-noise-v1": partial(
        noise_v1, id="nb5-noise-v1", base="nb5-coded-v2", noise_file=NB4_NOISE_FILE
    ),
    "nb3-attrs-v1": partial(
        text_flags_v1, id="nb3-attrs-v1", base="nb3-flagfix-v1", flags=ATTRIBUTE_FLAGS
    ),
    # West Village: the app design's building facts (as unitdescpluto-v3) on the
    # unit and floor features (no West Village ads: see nb-facing-v2).
    "wv-unitpluto-v1": partial(
        pluto_v1,
        id="wv-unitpluto-v1",
        base="unitfloor-v2",
        flood_zone=False,
        latest_alteration=True,
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
    # v4 on the corrected registry (LOT_SNAPSHOTS): building facts, fronts and
    # sides from the right buildings for the 12 re-geocoded pages.
    "unitfacing-v5": partial(facing_v4, id="unitfacing-v5", base="unitfacing-v3"),
    # The served design plus the noise around the building as of each listing.
    "unitnoise-v1": partial(noise_v1, id="unitnoise-v1", base="unitfacing-v5"),
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
    "unitfacing-v5": {"registry": REGISTRY_V3_FILE, "pluto": PLUTO_V3_FILE},
    "wv-unitpluto-v1": {"registry": WV_REGISTRY_FILE, "pluto": WV_PLUTO_FILE},
    "nb-pluto-base": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-unitpluto-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-facing-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-facing-v2": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-bedtext-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-facing-v3": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-bedtext-v2": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-relist-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-coded-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-lineface-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-prevprice-v1": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb-prevprice-v2": {"registry": NB_REGISTRY_FILE, "pluto": NB_PLUTO_FILE},
    "nb3-coded-v1": {"registry": NB3_REGISTRY_FILE, "pluto": NB3_PLUTO_FILE},
    "nb3-prevprice-v1": {"registry": NB3_REGISTRY_FILE, "pluto": NB3_PLUTO_FILE},
    "nb3-lineface-v1": {"registry": NB3_REGISTRY_FILE, "pluto": NB3_PLUTO_FILE},
    "unitnoise-v1": {"registry": REGISTRY_V3_FILE, "pluto": PLUTO_V3_FILE},
}


# Feature sets that read more description evidence than Chelsea's
# (`descriptions.SOURCE`), by run-record key.
_NB_DESCRIPTIONS = {
    "descriptions": str(descriptions_module.SOURCE),
    "descriptions_wv": str(descriptions_module.WV_SOURCE),
}
_NB3_DESCRIPTIONS = {
    **_NB_DESCRIPTIONS,
    "descriptions_gv": str(descriptions_module.GV_SOURCE),
}
_NB4_DESCRIPTIONS = {
    **_NB3_DESCRIPTIONS,
    "descriptions_fgp": str(descriptions_module.FGP_SOURCE),
}
DESCRIPTION_SOURCES = {
    "nb-facing-v2": _NB_DESCRIPTIONS,
    "nb-bedtext-v1": _NB_DESCRIPTIONS,
    "nb-facing-v3": _NB_DESCRIPTIONS,
    "nb-bedtext-v2": _NB_DESCRIPTIONS,
    "nb-relist-v1": _NB_DESCRIPTIONS,
    "nb-coded-v1": _NB_DESCRIPTIONS,
    "nb-lineface-v1": _NB_DESCRIPTIONS,
    "nb-prevprice-v1": _NB_DESCRIPTIONS,
    "nb-prevprice-v2": _NB_DESCRIPTIONS,
    "nb3-coded-v1": _NB3_DESCRIPTIONS,
    "nb3-prevprice-v1": _NB3_DESCRIPTIONS,
    "nb3-lineface-v1": _NB3_DESCRIPTIONS,
}


# Feature sets whose building alterations are dated as of each listing.
AS_OF_SETS = {
    "nb-facing-v3",
    "nb-bedtext-v2",
    "nb-relist-v1",
    "nb-coded-v1",
    "nb-lineface-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
}
# Feature sets that read the listing-extras snapshot.
LISTING_EXTRAS = {
    "nb-coded-v1",
    "nb-prevprice-v1",
    "nb-prevprice-v2",
    "nb-lineface-v1",
    "nb3-coded-v1",
    "nb3-prevprice-v1",
    "nb3-lineface-v1",
}
# Feature sets that read the price-history snapshot.
PRICE_HISTORY = {"nb-prevprice-v1", "nb-prevprice-v2", "nb3-prevprice-v1"}
# Feature sets that read another listing-extras snapshot (outdoor space, rooms
# and price changes alike) than LISTING_EXTRAS_FILE and PRICE_HISTORY_FILE.
EXTRAS_SNAPSHOTS = {
    n: NB3_EXTRAS_FILE for n in ("nb3-coded-v1", "nb3-prevprice-v1", "nb3-lineface-v1")
}
# Feature sets that read the rents of a unit's earlier listings. Their PSIS-LOO is
# not leak-free (a left-out row's rent reaches the fit through its unit's next
# row), so they are judged on the latest split, never ranked on PSIS-LOO
# (docs/leak-free-scoring.md). nb-prevprice-v2 reads only counts, not rents.
READS_EARLIER_RENTS = {"nb-prevprice-v1", "nb3-prevprice-v1"}


# Feature sets that read other basemap and footprints snapshots than the first.
AREA_SNAPSHOTS = {
    "nb-facing-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-facing-v2": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-bedtext-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-facing-v3": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-bedtext-v2": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-relist-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-coded-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-lineface-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-prevprice-v1": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb-prevprice-v2": {"basemap": NB_BASEMAP_FILE, "footprints": NB_FOOTPRINTS_FILE},
    "nb3-coded-v1": {"basemap": NB3_BASEMAP_FILE, "footprints": NB3_FOOTPRINTS_FILE},
    "nb3-prevprice-v1": {
        "basemap": NB3_BASEMAP_FILE,
        "footprints": NB3_FOOTPRINTS_FILE,
    },
    "nb3-lineface-v1": {"basemap": NB3_BASEMAP_FILE, "footprints": NB3_FOOTPRINTS_FILE},
}


def area_files(name: str) -> dict:
    """The basemap and footprints files a feature set's facing terms read."""
    return AREA_SNAPSHOTS.get(
        name, {"basemap": BASEMAP_FILE, "footprints": FOOTPRINTS_FILE}
    )


# Sets that read the LPC's designation dates, and the snapshot each reads.
LPC_SNAPSHOTS = {"nb3-coded-v2": NB3_LPC_FILE, "nb3-prevprice-v2": NB3_LPC_FILE}
# Otherwise the LPC sets read what their v1 reads.
for _new, _old in (
    ("nb3-coded-v2", "nb3-coded-v1"),
    ("nb3-prevprice-v2", "nb3-prevprice-v1"),
):
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
        PRICE_HISTORY,
        READS_EARLIER_RENTS,
    ):
        if _old in _group:
            _group.add(_new)
    for _table in (
        LOT_SNAPSHOTS,
        DESCRIPTION_SOURCES,
        EXTRAS_SNAPSHOTS,
        AREA_SNAPSHOTS,
    ):
        if _old in _table:
            _table[_new] = _table[_old]


# The wish sets read what nb3-coded-v2 (their base) reads.
for _wish in (
    "nb3-garden-v1",
    "nb3-through-v1",
    "nb3-quiet-v1",
    "nb3-loud-v1",
    "nb3-transit-v1",
    "nb3-access-v1",
    "nb3-lines-v1",
    "nb3-bedsize-v1",
    "nb3-parks-v1",
    "nb3-nearby-v1",
    "nb3-retail-v1",
    "nb3-walkup-v1",
    "nb3-loc-v1",
    "nb3-water-v1",
    "nb3-text-v1",
    "nb3-flagfix-v1",
    "nb3-attrs-v1",
    "nb3-noise-v1",
    "nb3-loft-v1",
):
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
    ):
        if "nb3-coded-v2" in _group:
            _group.add(_wish)
    for _table in (
        LOT_SNAPSHOTS,
        DESCRIPTION_SOURCES,
        EXTRAS_SNAPSHOTS,
        AREA_SNAPSHOTS,
        LPC_SNAPSHOTS,
    ):
        if "nb3-coded-v2" in _table:
            _table[_wish] = _table["nb3-coded-v2"]


# The nb4 sets read what their nb3 counterpart reads, from the four
# neighbourhoods' snapshots (#451) in place of the three's.
NB4_SETS = {
    "nb4-coded-v2": "nb3-coded-v2",
    "nb5-coded-v2": "nb3-coded-v2",
    "nb5-lines-v1": "nb3-lines-v1",
    "nb5-loc-v1": "nb3-loc-v1",
    "nb5-walkup-v1": "nb3-walkup-v1",
    "nb5-parks-v1": "nb3-parks-v1",
    "nb5-water-v1": "nb3-water-v1",
    "nb5-noise-v1": "nb3-noise-v1",
    "nb5-plutoasof-v2": "nb3-coded-v2",
    "nb5-plutoasof-v3": "nb3-coded-v2",
    "nb5-unical-v1": "nb5-plutoasof-v3",
}
# Sets that date the lot's alteration years (`dated_alterations`).
ALTERATION_DATED_SETS = {"nb5-plutoasof-v2"}
# Sets that read each lot as the latest MapPLUTO release published before the
# listing (`released_lots`). A set built on nb5-plutoasof-v3 joins it through
# NB4_SETS (`NB4_SETS[name] = "nb5-plutoasof-v3"`), like the other groups.
PLUTO_RELEASED_SETS = {"nb5-plutoasof-v3"}
# The street tree table (`trees.main`) and the sets that read it.
TREES_FILE = "/data1/apartments/external/trees/20261008-e8ae3db/trees.csv"
TREES = {"nb5-trees-v1"}
NB4_SETS["nb5-trees-v1"] = "nb5-plutoasof-v3"
# The NYPD felony table (`crime.main`) and the sets that read it.
CRIME_FILE = "/data1/apartments/external/crime/20261008-c17e0ae/felonies.csv"
CRIME = {"nb5-crime-v1"}
NB4_SETS["nb5-crime-v1"] = "nb5-plutoasof-v3"
# The HPD snapshot each set reads where it is not HPD_FILE.
HPD_SNAPSHOTS = {"nb5-hpd-v1": NB4_HPD_FILE}
HPD.add("nb5-hpd-v1")
NB4_SETS["nb5-hpd-v1"] = "nb5-plutoasof-v3"
NB4_SETS["nb5-concera-v1"] = "nb5-plutoasof-v3"
# One set per ad attribute (`ATTRIBUTE_FLAGS`) and per place kind
# (`nearby.KINDS`): nb5-coded-v2 plus that one column, each its own full fit.
NB5_SINGLES = {
    **{
        f"nb5-attr-{name.replace('_', '-')}-v1": ("attr", name)
        for name in ATTRIBUTE_FLAGS
    },
    **{
        f"nb5-near-{kind.replace(' ', '-')}-v1": ("near", kind)
        for kind in (
            "dog run",
            "hospital",
            "ambulance station",
            "drop-in center",
            "nycha",
            "arena",
        )
    },
}
for _name, (_what, _item) in NB5_SINGLES.items():
    if _what == "attr":
        FEATURE_SETS[_name] = partial(
            text_flags_v1,
            id=_name,
            base="nb5-coded-v2",
            flags={_item: ATTRIBUTE_FLAGS[_item]},
        )
    else:
        FEATURE_SETS[_name] = partial(
            nearby_one_v1, id=_name, base="nb5-coded-v2", kind=_item
        )
        PLACES.add(_name)
        PLACES_SNAPSHOTS[_name] = NB4_PLACES_FILE
    NB4_SETS[_name] = "nb5-coded-v2"
# The queued nb5 tests again on nb5-plutoasof-v3 (point-in-time MapPLUTO) in
# place of nb5-coded-v2: the same builder and arguments, the new base, and the
# same snapshots as the nb5 set (`P3_TESTS[new] = (nb5 set, base)`).
P3_TESTS = {
    "nb5p3-lines-v1": ("nb5-lines-v1", "nb5-plutoasof-v3"),
    "nb5p3-loc-v1": ("nb5-loc-v1", "nb5-plutoasof-v3"),
    "nb5p3-walkup-v1": ("nb5-walkup-v1", "nb5-plutoasof-v3"),
    "nb5p3-noise-v1": ("nb5-noise-v1", "nb5-plutoasof-v3"),
    "nb5p3-parks-v1": ("nb5-parks-v1", "nb5-plutoasof-v3"),
    "nb5p3-water-v1": ("nb5-water-v1", "nb5p3-parks-v1"),
}
for _name, (_like, _base) in P3_TESTS.items():
    _builder = FEATURE_SETS[_like]
    FEATURE_SETS[_name] = partial(
        _builder.func, **{**_builder.keywords, "id": _name, "base": _base}
    )
    NB4_SETS[_name] = "nb5-plutoasof-v3"
    for _group in (TRANSIT, PARKS, NOISE, LODES, PLACES, STOREFRONTS, HPD):
        if _like in _group:
            _group.add(_name)
    for _table in (NOISE_FILES, PARKS_SNAPSHOTS, PLACES_SNAPSHOTS):
        if _like in _table:
            _table[_name] = _table[_like]

# The label against location split (`location_nolabel`), on the same base as
# nb5p3-loc-v1.
FEATURE_SETS["nb5p3-locnolabel-v1"] = partial(
    location_nolabel, id="nb5p3-locnolabel-v1", base="nb5-plutoasof-v3"
)
NB4_SETS["nb5p3-locnolabel-v1"] = "nb5-plutoasof-v3"
# The names an ad uses (`claims_v1`) on both sides of that split (Ben,
# 2026-10-08: a label effect apart from location).
for _name, _base in (
    ("nb5p3-claim-v1", "nb5p3-loc-v1"),
    ("nb5p3-claimnolabel-v1", "nb5p3-locnolabel-v1"),
):
    FEATURE_SETS[_name] = partial(claims_v1, id=_name, base=_base)
    NB4_SETS[_name] = "nb5-plutoasof-v3"

for _new, _old in NB4_SETS.items():
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
        PRICE_HISTORY,
        READS_EARLIER_RENTS,
        PLUTO_RELEASED_SETS,
    ):
        if _old in _group:
            _group.add(_new)
    LOT_SNAPSHOTS[_new] = {"registry": NB4_REGISTRY_FILE, "pluto": NB4_PLUTO_FILE}
    AREA_SNAPSHOTS[_new] = {
        "basemap": NB4_BASEMAP_FILE,
        "footprints": NB4_FOOTPRINTS_FILE,
    }
    DESCRIPTION_SOURCES[_new] = _NB4_DESCRIPTIONS
    EXTRAS_SNAPSHOTS[_new] = NB4_EXTRAS_FILE
    LPC_SNAPSHOTS[_new] = NB4_LPC_FILE

# The six neighbourhoods (data.DATASET_NB6): the five plus Stuyvesant Town/PCV
# (stuyvesant-town-pcv-analysis-20261008-966f0a0). Its registry
# (20261008-330937b, each page geocoded from its own address,
# config/reviews/registry-overrides-20261008-stuy.json) merged into nb4's, its
# MapPLUTO, footprints and basemap merged into nb4's (nb4's rows unchanged), the
# five crawls' listing extras, and the sources keyed by lot fetched on the
# merged registry.
NB6_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261008-d405de4/buildings.parquet"
)
NB6_PLUTO_FILE = "/data1/apartments/external/pluto/20261008-d2a8364/pluto.parquet"
NB6_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261008-d2a8364/footprints.parquet"
)
NB6_BASEMAP_FILE = "/data1/apartments/external/basemap/20261008-d2a8364/basemap.parquet"
NB6_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261008-0076126/listing-extras.parquet"
)
NB6_LPC_FILE = "/data1/apartments/external/lpc/20261008-d2a8364/lpc.parquet"
NB6_HPD_FILE = "/data1/apartments/external/hpd/20261008-d2a8364/hpd.parquet"
NB6_STOREFRONTS_FILE = (
    "/data1/apartments/external/storefronts/20261008-d2a8364/storefronts.parquet"
)
NB6_PARKS_FILE = "/data1/apartments/external/parks/20261008-d2a8364/parks.parquet"
NB6_PLUTO_RELEASES_FILE = (
    "/data1/apartments/external/plutoreleases/20261008-d2a8364/plutoreleases.parquet"
)
_NB6_DESCRIPTIONS = {
    **_NB4_DESCRIPTIONS,
    "descriptions_stuy": str(descriptions_module.STUY_SOURCE),
}
# The MapPLUTO releases file by feature set, where a set in
# PLUTO_RELEASED_SETS reads other than `PLUTO_RELEASES_FILE`.
PLUTO_RELEASES_SNAPSHOTS: dict[str, str] = {}
# The nb6 sets read what their nb5 counterpart reads, from the six
# neighbourhoods' snapshots in place of the five's.
NB6_SETS = {
    "nb6-plutoasof-v3": "nb5-plutoasof-v3",
    "nb6-nostuy-v1": "nb5-plutoasof-v3",
    "nb6-stab-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-stab-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-open-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-stabopen-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-open-v2": "nb5-plutoasof-v3",
    "nb6-nostuy-stabopen-v2": "nb5-plutoasof-v3",
    "nb6-nostuy-owner-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-explain-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-riverparks-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-sizefill-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-nta-v1": "nb5-plutoasof-v3",
    "nb6-nostuy-lister-v1": "nb5-plutoasof-v3",
}
# nb5-plutoasof-v3 plus Stuyvesant Town/PCV (`hoods_v1`): the six
# neighbourhoods' base. Not fitted until runs resume (Ben, 2026-10-08: pause).
# The Stuyvesant Town/PCV indicator is a placeholder, a descriptive premium: a
# later test replaces it with what explains it (one landlord, the share of
# rent-stabilized units, campus open space, building age and type), per Ben's
# preference for explanatory features over neighbourhood premiums.
FEATURE_SETS["nb6-plutoasof-v3"] = partial(
    hoods_v1,
    id="nb6-plutoasof-v3",
    base="nb3-coded-v2",
    hoods=("Flatiron", "Gramercy Park", "Stuyvesant Town/PCV"),
)
# Tests of what explains the Stuyvesant Town/PCV indicator: nb6-nostuy-v1
# leaves it out (Stuyvesant Town/PCV rows take Chelsea's level);
# nb6-stab-v1 adds the rent-stabilized share beside it, and
# nb6-nostuy-stab-v1 has the share in its place. Both lots are close to
# fully stabilized on the tax bills since 2011.
FEATURE_SETS["nb6-nostuy-v1"] = partial(
    hoods_v1,
    id="nb6-nostuy-v1",
    base="nb3-coded-v2",
    hoods=("Flatiron", "Gramercy Park"),
)
FEATURE_SETS["nb6-stab-v1"] = partial(
    stabilized_v1, id="nb6-stab-v1", base="nb6-plutoasof-v3"
)
FEATURE_SETS["nb6-nostuy-stab-v1"] = partial(
    stabilized_v1, id="nb6-nostuy-stab-v1", base="nb6-nostuy-v1"
)
# The lot's open share (`open_space_v1`) in place of the indicator, alone and
# with the stabilized share: Stuyvesant Town and Peter Cooper Village leave
# about three quarters of their lots open, a typical lot here about a quarter.
FEATURE_SETS["nb6-nostuy-open-v1"] = partial(
    open_space_v1, id="nb6-nostuy-open-v1", base="nb6-nostuy-v1"
)
FEATURE_SETS["nb6-nostuy-stabopen-v1"] = partial(
    open_space_v1, id="nb6-nostuy-stabopen-v1", base="nb6-nostuy-stab-v1"
)
# v1's open share clips to 0 the 350 buildings whose footprints cover more than
# their lot's area. v2 (`open_space_v2`) measures a footprint over the union of
# the lots it spans and leaves a lot area that cannot hold it unknown: the v1
# sets are not to be fitted. Building age and type are in the base (era,
# class, units); a single owner is not (`owner_v1` below).
FEATURE_SETS["nb6-nostuy-open-v2"] = partial(
    open_space_v2, id="nb6-nostuy-open-v2", base="nb6-nostuy-v1"
)
FEATURE_SETS["nb6-nostuy-stabopen-v2"] = partial(
    open_space_v2, id="nb6-nostuy-stabopen-v2", base="nb6-nostuy-stab-v1"
)
# One landlord's campus (`owner_v1`) in place of the indicator, alone and with
# the stabilized and open shares (nb6-nostuy-explain-v1): every explanation of
# the Stuyvesant Town/PCV premium at once.
FEATURE_SETS["nb6-nostuy-owner-v1"] = partial(
    owner_v1, id="nb6-nostuy-owner-v1", base="nb6-nostuy-v1"
)
FEATURE_SETS["nb6-nostuy-explain-v1"] = partial(
    owner_v1, id="nb6-nostuy-explain-v1", base="nb6-nostuy-stabopen-v2"
)


# Hudson River Park and its new piers (`riverparks`), dated, beside the NYC
# Parks properties: Little Island 2021, Pier 57's roof 2022, Gansevoort
# Peninsula 2023. Built with `python -m rentfrontier.riverparks`.
RIVERPARKS_FILE = (
    "/data1/apartments/external/riverparks/20261009-6f20a5f/riverparks.parquet"
)
RIVERPARKS = {"nb6-nostuy-riverparks-v1"}


def riverparks_v1(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str = "nb6-nostuy-riverparks-v1",
    base: str = "nb6-nostuy-v1",
) -> Features:
    """A base set plus `parks_v1`'s two terms with Hudson River Park among the
    parks, and whether one of its new piers (Little Island, Pier 57's roof,
    Gansevoort Peninsula) is within 10 minutes (`riverparks.terms`: places
    open before the listing's month). Reads no rents."""
    from . import parks, riverparks

    base = FEATURE_SETS[base](frame, train)
    terms = riverparks.terms(frame, parks_file(), RIVERPARKS_FILE)
    walk = np.log(np.maximum(terms.park_min.to_numpy(), 1.0))
    known = np.isfinite(walk)
    centre = float(np.mean(walk[train & known]))
    b = _Builder(frame)
    b.add("parks", "log walk min to a park", np.where(known, walk - centre, 0.0))
    b.add(
        "parks",
        f"High Line within {parks.HIGH_LINE_MIN:.0f} min",
        np.nan_to_num(terms.high_line.to_numpy()),
    )
    b.add(
        "parks",
        f"river pier park within {riverparks.PIER_MIN:.0f} min",
        np.nan_to_num(terms.pier.to_numpy()),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


FEATURE_SETS["nb6-nostuy-riverparks-v1"] = partial(
    riverparks_v1, id="nb6-nostuy-riverparks-v1", base="nb6-nostuy-v1"
)
PARKS.add("nb6-nostuy-riverparks-v1")
PARKS_SNAPSHOTS["nb6-nostuy-riverparks-v1"] = NB6_PARKS_FILE
# Size as of the row's day (`sizefill_v1`) in place of the unit median over
# all of the unit's listings, which reads later listings (2026-10-09).
FEATURE_SETS["nb6-nostuy-sizefill-v1"] = partial(
    sizefill_v1, id="nb6-nostuy-sizefill-v1", base="nb6-nostuy-v1"
)
# The 2020 NTAs (`nta_v1`): City Planning's areas, which cut across StreetEasy's.
FEATURE_SETS["nb6-nostuy-nta-v1"] = partial(
    nta_v1, id="nb6-nostuy-nta-v1", base="nb6-nostuy-v1"
)
# Who listed the advertisement (`lister_v1`), on the six neighbourhoods' base
# without the Stuyvesant Town/PCV indicator.
FEATURE_SETS["nb6-nostuy-lister-v1"] = partial(
    lister_v1, id="nb6-nostuy-lister-v1", base="nb6-nostuy-v1"
)
for _new, _old in NB6_SETS.items():
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
        PRICE_HISTORY,
        READS_EARLIER_RENTS,
        PLUTO_RELEASED_SETS,
    ):
        if _old in _group:
            _group.add(_new)
    LOT_SNAPSHOTS[_new] = {"registry": NB6_REGISTRY_FILE, "pluto": NB6_PLUTO_FILE}
    AREA_SNAPSHOTS[_new] = {
        "basemap": NB6_BASEMAP_FILE,
        "footprints": NB6_FOOTPRINTS_FILE,
    }
    DESCRIPTION_SOURCES[_new] = _NB6_DESCRIPTIONS
    EXTRAS_SNAPSHOTS[_new] = NB6_EXTRAS_FILE
    LPC_SNAPSHOTS[_new] = NB6_LPC_FILE
    PLUTO_RELEASES_SNAPSHOTS[_new] = NB6_PLUTO_RELEASES_FILE


# The seven neighbourhoods (data.DATASET_NB7): the six plus NoMad
# (nomad-analysis-20261009-d3b4050), StreetEasy's child area of Flatiron north
# of 25th Street, which the Flatiron crawl left out. Its registry
# (20261009-d3b4050, each page geocoded from its own address, no overrides)
# merged into nb6's, its MapPLUTO, footprints and basemap merged into nb6's
# (nb6's rows unchanged), the seven crawls' listing extras, and the sources
# keyed by lot fetched on the merged registry.
NB7_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261009-dcee63b/buildings.parquet"
)
NB7_PLUTO_FILE = "/data1/apartments/external/pluto/20261009-dcee63b/pluto.parquet"
NB7_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261009-dcee63b/footprints.parquet"
)
NB7_BASEMAP_FILE = "/data1/apartments/external/basemap/20261009-dcee63b/basemap.parquet"
NB7_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261009-dcee63b/listing-extras.parquet"
)
NB7_LPC_FILE = "/data1/apartments/external/lpc/20261009-dcee63b/lpc.parquet"
NB7_HPD_FILE = "/data1/apartments/external/hpd/20261009-dcee63b/hpd.parquet"
NB7_STOREFRONTS_FILE = (
    "/data1/apartments/external/storefronts/20261009-dcee63b/storefronts.parquet"
)
NB7_PARKS_FILE = "/data1/apartments/external/parks/20261009-dcee63b/parks.parquet"
NB7_PLUTO_RELEASES_FILE = (
    "/data1/apartments/external/plutoreleases/20261009-dcee63b/plutoreleases.parquet"
)
_NB7_DESCRIPTIONS = {
    **_NB6_DESCRIPTIONS,
    "descriptions_nomad": str(descriptions_module.NOMAD_SOURCE),
}
# The nb7 sets read what their nb5 counterpart reads, from the seven
# neighbourhoods' snapshots in place of the six's.
NB7_SETS = {
    "nb7-nostuy-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-stab-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-stabopen-v2": "nb5-plutoasof-v3",
    "nb7-nostuy-explain-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-riverparks-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-sizefill-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-nta-v1": "nb5-plutoasof-v3",
    "nb7-nostuy-lister-v1": "nb5-plutoasof-v3",
}
# nb6-nostuy-v1 plus a NoMad indicator beside Flatiron's: the seven
# neighbourhoods' base. Not fitted until runs resume (Ben, 2026-10-08: pause).
# The NoMad indicator is a descriptive premium like the others; the nb7 tests
# below carry nb6's explanations (parks, size as of the day, NTAs, lister,
# stabilized and open shares, one landlord) to NoMad's buildings.
FEATURE_SETS["nb7-nostuy-v1"] = partial(
    hoods_v1,
    id="nb7-nostuy-v1",
    base="nb3-coded-v2",
    hoods=("Flatiron", "Gramercy Park", "NoMad"),
)
FEATURE_SETS["nb7-nostuy-stab-v1"] = partial(
    stabilized_v1, id="nb7-nostuy-stab-v1", base="nb7-nostuy-v1"
)
FEATURE_SETS["nb7-nostuy-stabopen-v2"] = partial(
    open_space_v2, id="nb7-nostuy-stabopen-v2", base="nb7-nostuy-stab-v1"
)
FEATURE_SETS["nb7-nostuy-explain-v1"] = partial(
    owner_v1, id="nb7-nostuy-explain-v1", base="nb7-nostuy-stabopen-v2"
)
FEATURE_SETS["nb7-nostuy-riverparks-v1"] = partial(
    riverparks_v1, id="nb7-nostuy-riverparks-v1", base="nb7-nostuy-v1"
)
FEATURE_SETS["nb7-nostuy-sizefill-v1"] = partial(
    sizefill_v1, id="nb7-nostuy-sizefill-v1", base="nb7-nostuy-v1"
)
FEATURE_SETS["nb7-nostuy-nta-v1"] = partial(
    nta_v1, id="nb7-nostuy-nta-v1", base="nb7-nostuy-v1"
)
FEATURE_SETS["nb7-nostuy-lister-v1"] = partial(
    lister_v1, id="nb7-nostuy-lister-v1", base="nb7-nostuy-v1"
)
RENTSTAB |= {"nb7-nostuy-stab-v1", "nb7-nostuy-stabopen-v2", "nb7-nostuy-explain-v1"}
BLOCKLOTS |= {"nb7-nostuy-stabopen-v2", "nb7-nostuy-explain-v1"}
RIVERPARKS.add("nb7-nostuy-riverparks-v1")
NTA.add("nb7-nostuy-nta-v1")
LISTER.add("nb7-nostuy-lister-v1")
PARKS.add("nb7-nostuy-riverparks-v1")
PARKS_SNAPSHOTS["nb7-nostuy-riverparks-v1"] = NB7_PARKS_FILE
for _new, _old in NB7_SETS.items():
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
        PRICE_HISTORY,
        READS_EARLIER_RENTS,
        PLUTO_RELEASED_SETS,
    ):
        if _old in _group:
            _group.add(_new)
    LOT_SNAPSHOTS[_new] = {"registry": NB7_REGISTRY_FILE, "pluto": NB7_PLUTO_FILE}
    AREA_SNAPSHOTS[_new] = {
        "basemap": NB7_BASEMAP_FILE,
        "footprints": NB7_FOOTPRINTS_FILE,
    }
    DESCRIPTION_SOURCES[_new] = _NB7_DESCRIPTIONS
    EXTRAS_SNAPSHOTS[_new] = NB7_EXTRAS_FILE
    LPC_SNAPSHOTS[_new] = NB7_LPC_FILE
    PLUTO_RELEASES_SNAPSHOTS[_new] = NB7_PLUTO_RELEASES_FILE


# The eight neighbourhoods (data.DATASET_NB8): the seven plus East Village
# (east-village-analysis-20261010-3ebfea04), crawled building first. Its
# registry (20261010-3ebfea0, each page geocoded from its own address, no
# overrides) merged into nb7's, its MapPLUTO, footprints and basemap merged
# into nb7's (nb7's rows unchanged), the eight crawls' listing extras, and the
# sources keyed by lot fetched on the merged registry.
NB8_REGISTRY_FILE = (
    "/data1/apartments/external/registry/20261010-b5c71cf/buildings.parquet"
)
NB8_PLUTO_FILE = "/data1/apartments/external/pluto/20261010-b5c71cf/pluto.parquet"
NB8_FOOTPRINTS_FILE = (
    "/data1/apartments/external/footprints/20261010-b5c71cf/footprints.parquet"
)
NB8_BASEMAP_FILE = "/data1/apartments/external/basemap/20261010-b5c71cf/basemap.parquet"
NB8_EXTRAS_FILE = (
    "/data1/apartments/external/listing-extras/20261010-b5c71cf/listing-extras.parquet"
)
NB8_LPC_FILE = "/data1/apartments/external/lpc/20261010-b5c71cf/lpc.parquet"
NB8_HPD_FILE = "/data1/apartments/external/hpd/20261010-b5c71cf/hpd.parquet"
NB8_STOREFRONTS_FILE = (
    "/data1/apartments/external/storefronts/20261010-b5c71cf/storefronts.parquet"
)
NB8_PARKS_FILE = "/data1/apartments/external/parks/20261010-b5c71cf/parks.parquet"
NB8_PLUTO_RELEASES_FILE = (
    "/data1/apartments/external/plutoreleases/20261010-b5c71cf/plutoreleases.parquet"
)
_NB8_DESCRIPTIONS = {
    **_NB7_DESCRIPTIONS,
    "descriptions_ev": str(descriptions_module.EV_SOURCE),
}
# The nb8 sets read what their nb5 counterpart reads, from the eight
# neighbourhoods' snapshots in place of the seven's.
NB8_SETS = {
    "nb8-nostuy-v1": "nb5-plutoasof-v3",
    "nb8-nostuy-sizefill-v1": "nb5-plutoasof-v3",
    "nb8-nostuy-nta-v1": "nb5-plutoasof-v3",
    "nb8-nostuy-lister-v1": "nb5-plutoasof-v3",
}
# nb7-nostuy-v1 plus an East Village indicator: the eight neighbourhoods'
# base, and the base the tests below sit on (size as of the day, NTAs,
# lister, river parks). Not fitted while model runs are paused.
FEATURE_SETS["nb8-nostuy-v1"] = partial(
    hoods_v1,
    id="nb8-nostuy-v1",
    base="nb3-coded-v2",
    hoods=("Flatiron", "Gramercy Park", "NoMad", "East Village"),
)
FEATURE_SETS["nb8-nostuy-sizefill-v1"] = partial(
    sizefill_v1, id="nb8-nostuy-sizefill-v1", base="nb8-nostuy-v1"
)
FEATURE_SETS["nb8-nostuy-nta-v1"] = partial(
    nta_v2, id="nb8-nostuy-nta-v1", base="nb8-nostuy-v1"
)
FEATURE_SETS["nb8-nostuy-lister-v1"] = partial(
    lister_v1, id="nb8-nostuy-lister-v1", base="nb8-nostuy-v1"
)
NTA.add("nb8-nostuy-nta-v1")
LISTER.add("nb8-nostuy-lister-v1")


def riverparks_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """`riverparks_v1` with Pier 42 dated (`eastparks.terms`): the eight
    neighbourhoods' parks file adds it, and `riverparks` has no day for it.
    Reads no rents."""
    from . import eastparks, parks, riverparks

    base = FEATURE_SETS[base](frame, train)
    terms = eastparks.terms(frame, parks_file(), RIVERPARKS_FILE)
    walk = np.log(np.maximum(terms.park_min.to_numpy(), 1.0))
    known = np.isfinite(walk)
    centre = float(np.mean(walk[train & known]))
    b = _Builder(frame)
    b.add("parks", "log walk min to a park", np.where(known, walk - centre, 0.0))
    b.add(
        "parks",
        f"High Line within {parks.HIGH_LINE_MIN:.0f} min",
        np.nan_to_num(terms.high_line.to_numpy()),
    )
    b.add(
        "parks",
        f"river pier park within {riverparks.PIER_MIN:.0f} min",
        np.nan_to_num(terms.pier.to_numpy()),
    )
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


NB8_SETS["nb8-nostuy-riverparks-v1"] = "nb5-plutoasof-v3"
FEATURE_SETS["nb8-nostuy-riverparks-v1"] = partial(
    riverparks_v2, id="nb8-nostuy-riverparks-v1", base="nb8-nostuy-v1"
)
RIVERPARKS.add("nb8-nostuy-riverparks-v1")
PARKS.add("nb8-nostuy-riverparks-v1")
PARKS_SNAPSHOTS["nb8-nostuy-riverparks-v1"] = NB8_PARKS_FILE
# nb8-nostuy-v1 plus each subway line group within an 8-minute walk
# (`lines_v1`): an explanation of the neighbourhood premiums (Ben, 2026-10-08).
# A quarter of East Village's rows have no line that near, against a ninth of
# Chelsea's, and the eight neighbourhoods' registry prices the J/Z.
NB8_SETS["nb8-nostuy-lines-v1"] = "nb5-plutoasof-v3"
FEATURE_SETS["nb8-nostuy-lines-v1"] = partial(
    lines_v1, id="nb8-nostuy-lines-v1", base="nb8-nostuy-v1"
)
TRANSIT.add("nb8-nostuy-lines-v1")


def retail_v2(
    frame: pd.DataFrame,
    train: np.ndarray,
    id: str,
    base: str,
) -> Features:
    """`retail_v1` reading the set's storefronts snapshot
    (`STOREFRONTS_SNAPSHOTS`) in place of `STOREFRONTS_FILE`, which holds
    storefronts near the first crawls' buildings only. Reads no rents."""
    from . import retail

    base = FEATURE_SETS[base](frame, train)
    table = retail._building_retail(lot_registry(), STOREFRONTS_SNAPSHOTS[id])
    table = table.reindex(frame.building.to_numpy())
    b = _Builder(frame)
    for key, name in (
        ("storefronts", "log1p storefronts nearby"),
        ("food", "log1p food places nearby"),
    ):
        t = np.log1p(table[key].to_numpy())
        b.add("retail", name, np.nan_to_num(t, nan=np.nanmedian(t)))
    out = b.build(id)
    return Features(
        id,
        base.names + out.names,
        base.groups + out.groups,
        np.column_stack([base.values, out.values]),
        np.concatenate([base.prior_scale, out.prior_scale]),
    )


# nb8-nostuy-v1 plus street retail (`retail_v2`): an explanation of the
# neighbourhood premiums (Ben, 2026-10-08). STOREFRONTS_FILE gives East
# Village's buildings a median of 5 storefronts within 150 m (NoMad 3, Gramercy
# Park 0) where the nb8 snapshot gives 39 (44, 23), so the set reads the nb8
# snapshot. No base set reads retail terms.
STOREFRONTS_SNAPSHOTS = {"nb8-nostuy-retail-v1": NB8_STOREFRONTS_FILE}
NB8_SETS["nb8-nostuy-retail-v1"] = "nb5-plutoasof-v3"
FEATURE_SETS["nb8-nostuy-retail-v1"] = partial(
    retail_v2, id="nb8-nostuy-retail-v1", base="nb8-nostuy-v1"
)
STOREFRONTS.add("nb8-nostuy-retail-v1")
# nb8-nostuy-v1 plus the noise around the building as of the listing
# (`noise_v1`): street and nightlife, and construction. NB4_NOISE_FILE stops at
# latitude 40.723 and misses the southern East Village, so the set reads a 311
# snapshot boxed on the nb8 registry. No base set reads noise terms.
NB8_NOISE_FILE = "/data1/apartments/external/noise311/20261010-90f03f5/noise311.parquet"
NB8_SETS["nb8-nostuy-noise-v1"] = "nb5-plutoasof-v3"
FEATURE_SETS["nb8-nostuy-noise-v1"] = partial(
    noise_v1, id="nb8-nostuy-noise-v1", base="nb8-nostuy-v1", noise_file=NB8_NOISE_FILE
)
NOISE.add("nb8-nostuy-noise-v1")
NOISE_FILES["nb8-nostuy-noise-v1"] = NB8_NOISE_FILE
for _new, _old in NB8_SETS.items():
    for _group in (
        EXTERNAL,
        BASEMAP,
        FOOTPRINTS,
        DESCRIPTIONS,
        AS_OF_SETS,
        LISTING_EXTRAS,
        PRICE_HISTORY,
        READS_EARLIER_RENTS,
        PLUTO_RELEASED_SETS,
    ):
        if _old in _group:
            _group.add(_new)
    LOT_SNAPSHOTS[_new] = {"registry": NB8_REGISTRY_FILE, "pluto": NB8_PLUTO_FILE}
    AREA_SNAPSHOTS[_new] = {
        "basemap": NB8_BASEMAP_FILE,
        "footprints": NB8_FOOTPRINTS_FILE,
    }
    DESCRIPTION_SOURCES[_new] = _NB8_DESCRIPTIONS
    EXTRAS_SNAPSHOTS[_new] = NB8_EXTRAS_FILE
    LPC_SNAPSHOTS[_new] = NB8_LPC_FILE
    PLUTO_RELEASES_SNAPSHOTS[_new] = NB8_PLUTO_RELEASES_FILE


def lot_files(name: str) -> dict:
    """The registry and MapPLUTO files a feature set's building lots read."""
    return LOT_SNAPSHOTS.get(name, {"registry": REGISTRY_FILE, "pluto": PLUTO_FILE})


def description_files(name: str) -> dict:
    """The description evidence files a feature set reads, by record key."""
    return DESCRIPTION_SOURCES.get(
        name, {"descriptions": str(descriptions_module.SOURCE)}
    )


def build(name: str, frame: pd.DataFrame, train: np.ndarray) -> Features:
    files = lot_files(name)
    area = area_files(name)
    token = _LOTS.set((files["registry"], files["pluto"]))
    as_of_token = _AS_OF.set(name in AS_OF_SETS)
    area_token = _AREA.set((area["basemap"], area["footprints"]))
    extras_token = _EXTRAS.set(EXTRAS_SNAPSHOTS.get(name))
    lpc_token = _LPC.set(LPC_SNAPSHOTS.get(name))
    alter_token = _ALTER_DATED.set(
        ALTERATIONS_FILE if name in ALTERATION_DATED_SETS else None
    )
    released_token = _RELEASED.set(
        PLUTO_RELEASES_SNAPSHOTS.get(name, PLUTO_RELEASES_FILE)
        if name in PLUTO_RELEASED_SETS
        else None
    )
    parks_token = _PARKS.set(PARKS_SNAPSHOTS.get(name))
    places_token = _PLACES.set(PLACES_SNAPSHOTS.get(name))
    text_token = descriptions_module.SOURCES.set(
        tuple(Path(p) for p in description_files(name).values())
    )
    try:
        return FEATURE_SETS[name](frame, np.asarray(train, dtype=bool))
    finally:
        _LOTS.reset(token)
        _AS_OF.reset(as_of_token)
        _AREA.reset(area_token)
        _EXTRAS.reset(extras_token)
        _LPC.reset(lpc_token)
        _ALTER_DATED.reset(alter_token)
        _RELEASED.reset(released_token)
        _PARKS.reset(parks_token)
        _PLACES.reset(places_token)
        descriptions_module.SOURCES.reset(text_token)

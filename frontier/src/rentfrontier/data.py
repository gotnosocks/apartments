"""Load the analytical dataset into a flat, typed table.

The source bundle is read-only. The flattened table is cached as parquet under
the output root, keyed by the SHA-256 of observations.jsonl, so a changed
source can never be served from a stale cache.

Row order is the order of observations.jsonl with a default RangeIndex. The
held-out splits depend on that order.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

DATASET = Path(
    os.environ.get(
        "FRONTIER_DATASET",
        # The five neighbourhoods (DATASET_NB5, #460); before that Chelsea + West
        # Village + Greenwich Village, chelsea-wv-gv-analysis-20261005-2d5b3b6
        # (#292), chelsea-west-village-analysis-20261005-1222e51 (Oct 5 captures,
        # #220), chelsea-west-village-analysis-20261001-eea4f66, and Chelsea alone,
        # data/model/chelsea-product-scope-analysis-20260921.
        "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057",
    )
)
# Chelsea + West Village + Greenwich Village with Flatiron + Gramercy Park
# (flatiron-gramercy-park-analysis-20261007-34b958d), combined by
# `rentfrontier.cohort combine`: 135,759 rows. Never served: DATASET_NB5
# splits Flatiron + Gramercy Park.
DATASET_NB4 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-fgp-analysis-20261008-b193e55"
)
# The five neighbourhoods: the same rows, with each Flatiron + Gramercy Park row
# named Flatiron or Gramercy Park by its building's StreetEasy area
# (`rentfrontier.cohort areas`, areas/20261008-6027acc), then combined. The
# served dataset (DATASET).
DATASET_NB5 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057"
)
# The six neighbourhoods: DATASET_NB5 and Stuyvesant Town/PCV
# (stuyvesant-town-pcv-analysis-20261008-966f0a0), combined by
# `rentfrontier.cohort combine`: 139,387 rows. Not served or fitted yet.
DATASET_NB6 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-analysis-20261008-d2a8364"
)
# The six plus NoMad (cohort nomad-analysis-20261009-d3b4050), no rule change.
DATASET_NB7 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-analysis-20261009-d3b4050"
)
OUTPUT_ROOT = Path(os.environ.get("FRONTIER_OUTPUT_ROOT", "/data1/apartments/frontier"))

# Version of the flattened row (the cache key): v2 adds the neighbourhood.
SCHEMA = "v2"
VIEWS = ("city", "courtyard", "garden", "park", "skyline", "street", "water")
WINDOWS = ("east", "north", "south", "west")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tristate(value) -> str:
    """Keep unknown separate from no."""
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _flatten(row: dict) -> dict:
    views = row.get("view_exposures") or {}
    windows = row.get("window_exposures") or {}
    out = {
        "audit_id": row["audit_id"],
        "unit_id": row["unit_id"],
        "building": row["building"],
        "canonical_unit_url": row["canonical_unit_url"],
        "source_listing_id": row["source_listing_id"],
        "asking_rent": float(row["asking_rent"]),
        "period": row["period"],
        "price_at": row["price_at"],
        "price_basis": row["analysis_price_basis"],
        "bedrooms": row["bedrooms"],
        "bathrooms": row["bathrooms"],
        "full_baths": row["reported_full_bathrooms"],
        "half_baths": row["reported_half_bathrooms"],
        "square_feet": row["square_feet"],
        "listed_floor": row["listed_floor"],
        "label_derived_floor": row["label_derived_floor"],
        "elevator": _tristate(row["elevator"]),
        "doorman": row["doorman_type"] or "unknown",
        "laundry": row["laundry_type"] or "unknown",
        "hvac": row["hvac_type"] or "unknown",
        "pets": row["pet_policy"] or "unknown",
        "has_description": row.get("description_interpreted_at") is not None,
        # Datasets before the combined cohort are Chelsea's.
        "neighbourhood": row.get("neighbourhood", "Chelsea"),
    }
    for name in VIEWS:
        out[f"view_{name}"] = _tristate(views.get(name))
    for name in WINDOWS:
        out[f"window_{name}"] = _tristate(windows.get(name))
    return out


def load(dataset: Path = DATASET, cache_root: Path = OUTPUT_ROOT) -> pd.DataFrame:
    source = dataset / "observations.jsonl"
    digest = sha256(source)
    cache = cache_root / "cache" / f"observations-{digest[:16]}-{SCHEMA}.parquet"
    if cache.exists():
        frame = pd.read_parquet(cache)
    else:
        with open(source) as f:
            frame = pd.DataFrame(
                [_flatten(json.loads(line)) for line in f if line.strip()]
            )
        cache.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache.with_suffix(".tmp"))
        cache.with_suffix(".tmp").rename(cache)
    frame["period"] = pd.to_datetime(frame["period"])
    frame["price_at"] = pd.to_datetime(frame["price_at"], utc=True, format="ISO8601")
    frame["square_feet"] = pd.to_numeric(frame["square_feet"], errors="coerce")
    if frame.audit_id.duplicated().any() or not (frame.asking_rent > 0).all():
        raise ValueError("Invalid source cohort")
    frame.attrs["source_sha256"] = digest
    frame.attrs["dataset"] = str(dataset)
    frame["log_rent"] = np.log(frame.asking_rent)
    return frame


def unit_label_key(label: str) -> str:
    """A unit label written one way: "APT-4B", "UNIT4B", "4-B", "04B" -> "4B";
    "7TH-FLOOR", "7THFL" -> "7THFL"."""
    label = re.sub(r"^(?:APT|UNIT)\.?-?|^NO\.?-?(?=\d)", "", label.upper())
    label = re.sub(r"[-_#. ]", "", label)
    label = re.sub(r"(?:FLOOR|FLR)$", "FL", label)
    return re.sub(r"^0+(?=\d)", "", label)


def merge_unit_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """One unit id for the units of a building whose labels are the same label
    written differently (521 groups, 1,055 unit ids, 2,023 rows: "4-FLR" and
    "4FLR", "02" and "2", "UNIT4J" and "4J"). The canonical id is the group's
    lexicographically smallest unit id. Rows are unchanged."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].map(unit_label_key)
    key = frame.building + "/" + label
    canonical = frame.groupby(key).unit_id.transform("min")
    out = frame.copy()
    out["unit_id"] = canonical.where(label.notna(), frame.unit_id)
    return out


# The West Village unit spelling alias table (apartments.unit_spelling_aliases,
# PR #80) for west-village-granular-20260930-canonical-url-v1: units of one
# building whose labels are equal after lowercasing, removing punctuation and
# stripping the leading zeros of every number ("ph04" and "ph4", "r01" and
# "r1"), one JSON line per member; provenance beside it.
UNIT_ALIASES = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "unit-aliases"
    / "west-village-20260930.jsonl"
)
# That table with Greenwich Village's appended: the unit spelling alias rule v2
# (PR #213) on greenwich-village-granular-20261005-canonical-url-v1, 136
# history-confirmed groups; provenance beside it.
UNIT_ALIASES_GV = UNIT_ALIASES.with_name("wv-gv-20261005.jsonl")
# That table with Flatiron + Gramercy Park's appended (unit-spelling-alias-v2 on
# flatiron-gramercy-park-granular-20261007-canonical-url-v1, 522
# history-confirmed groups); provenance beside it.
UNIT_ALIASES_FGP = UNIT_ALIASES.with_name("wv-gv-fgp-20261007.jsonl")
# That table with Stuyvesant Town/PCV's appended (unit-spelling-alias-v2 on
# stuyvesant-town-pcv-granular-20261008-canonical-url-v1, 265
# history-confirmed groups); provenance beside it.
UNIT_ALIASES_STUY = UNIT_ALIASES.with_name("wv-gv-fgp-stuy-20261008.jsonl")
# That table with NoMad's appended (unit-spelling-alias-v2 on
# nomad-granular-20261009-canonical-url-v1, 107 history-confirmed groups);
# provenance beside it.
UNIT_ALIASES_NOMAD = UNIT_ALIASES.with_name("wv-gv-fgp-stuy-nomad-20261009.jsonl")


@functools.lru_cache(maxsize=3)
def unit_aliases(path: Path = UNIT_ALIASES) -> tuple:
    """Groups of unit ids the alias table joins, history-confirmed groups only
    (a crawled unit page lists an ad the transform gave the other spelling)."""
    groups = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r["history_confirmed"]:
                    groups.setdefault(r["alias_group_id"], []).append(r["unit_id"])
    return tuple(tuple(sorted(g)) for g in groups.values() if len(g) > 1)


def merge_unit_aliases(
    frame: pd.DataFrame, aliases: Path = UNIT_ALIASES
) -> pd.DataFrame:
    """unit-labels-v1, and the West Village alias table's history-confirmed
    groups joined too (248 groups; most are already the same label under v1;
    the rest pad zeros inside the label: "ph04" and "ph4"). Groups that share
    a unit through either rule are one unit, whose id is the smallest. Rows
    are unchanged."""
    out = merge_unit_labels(frame)
    parent = {}

    def find(u):
        parent.setdefault(u, u)
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for old, new in zip(frame.unit_id, out.unit_id):
        union(old, new)
    for group in unit_aliases(aliases):
        for u in group[1:]:
            union(group[0], u)
    out["unit_id"] = frame.unit_id.map(find)
    return out


# Unit labels written as words ("four", "third-fl") and the number they stand for.
LABEL_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "first": "1",
    "second": "2", "third": "3", "fourth": "4", "fifth": "5",
}  # fmt: skip
_WORD_LABEL = re.compile(r"^(" + "|".join(LABEL_WORDS) + r")(?=$|[-_ ]?(?:fl|floor)$)")


def merge_word_labels(
    frame: pd.DataFrame, aliases: Path = UNIT_ALIASES
) -> pd.DataFrame:
    """unit-labels-v2, and units labelled with a number word joined to the unit
    of the same building whose label is that number ("four" and "4",
    "third-fl" and "3fl"), where both units' median bedroom counts agree.
    Rows are unchanged."""
    out = merge_unit_aliases(frame, aliases)
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    word = raw.str.extract(_WORD_LABEL)[0]
    numbered = (
        word.map(LABEL_WORDS) + raw.str.replace(_WORD_LABEL, "", regex=True)
    ).where(word.notna())
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    word_key = numbered.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    beds = frame.bedrooms.groupby(out.unit_id).transform("median")
    by_label = (
        pd.DataFrame(
            {"building": frame.building, "key": key, "unit": out.unit_id, "beds": beds}
        )
        .drop_duplicates(["building", "key"])
        .set_index(["building", "key"])
    )
    joined = out.unit_id.copy()
    for i in np.flatnonzero(word_key.notna().to_numpy()):
        twin = (frame.building.iat[i], word_key.iat[i])
        if twin in by_label.index and by_label.loc[twin, "beds"] == beds.iat[i]:
            target = by_label.loc[twin, "unit"]
            joined[out.unit_id == out.unit_id.iat[i]] = min(target, out.unit_id.iat[i])
            joined[out.unit_id == target] = min(target, out.unit_id.iat[i])
    out["unit_id"] = joined
    return out


# Unit-id pairs a StreetEasy unit page's own rental history joins (an ad filed
# under one unit appears in the other's page history), Chelsea, West Village and
# Greenwich Village; built by frontier/scripts/unit_history_pairs.py, provenance
# beside it.
UNIT_HISTORY_PAIRS = UNIT_ALIASES.with_name("history-20261006.jsonl")
# The same pairs with Flatiron + Gramercy Park's (551) appended.
UNIT_HISTORY_PAIRS_FGP = UNIT_ALIASES.with_name("history-20261007.jsonl")
# The same pairs with Stuyvesant Town/PCV's (276) appended.
UNIT_HISTORY_PAIRS_STUY = UNIT_ALIASES.with_name("history-20261008.jsonl")
# The same pairs with NoMad's appended.
UNIT_HISTORY_PAIRS_NOMAD = UNIT_ALIASES.with_name("history-20261009.jsonl")


@functools.lru_cache(maxsize=2)
def unit_history_pairs(path: Path = UNIT_HISTORY_PAIRS) -> tuple:
    """(unit id, unit id) pairs a unit page's own rental history joins."""
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return tuple((r["unit_id"], r["other_unit_id"]) for r in rows)


def merge_history_pairs(
    frame: pd.DataFrame,
    pairs: Path = UNIT_HISTORY_PAIRS,
    aliases: Path = UNIT_ALIASES_GV,
) -> pd.DataFrame:
    """unit-labels-v5, and units joined where one's ad appears in the other's
    StreetEasy unit-page history, when both are in the same building and their
    median bedroom counts (under v5) agree. Groups that share a unit are one
    unit, whose id is the smallest. Rows are unchanged."""
    out = merge_word_labels(frame, aliases)
    v5 = dict(zip(frame.unit_id, out.unit_id))
    building = dict(zip(out.unit_id, frame.building))
    beds = frame.bedrooms.groupby(out.unit_id).median().to_dict()
    parent = {}

    def find(u):
        parent.setdefault(u, u)
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    for first, second in unit_history_pairs(pairs):
        a, b = v5.get(first), v5.get(second)
        if a is None or b is None or a == b or building[a] != building[b]:
            continue
        if beds[a] == beds[b]:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    out["unit_id"] = out.unit_id.map(find)
    return out


_LETTER_FIRST = re.compile(r"^([A-Z]{1,2})(\d{1,2})$")


def merge_swapped_labels(frame: pd.DataFrame, base=merge_history_pairs) -> pd.DataFrame:
    """unit-labels-v6, and units labelled letter first ("C7", "D4") joined to
    the unit of the same building labelled digit first ("7C", "4D"), where both
    units' median bedroom counts (under the base rule) agree. Before the guard,
    bedrooms agree for 89% of such pairs and square footage within 5% for 66%,
    against 47% and 20% for other pairs of a building's lettered units
    (2026-10-06, 635 pairs, 858 rows; #335 had the swaps alone on v5). Groups
    that share a unit are one unit, whose id is the smallest. Rows are
    unchanged."""
    out = base(frame)
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0]
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    beds = frame.bedrooms.groupby(out.unit_id).median().to_dict()
    unit_of = dict(zip(zip(frame.building, key), out.unit_id))
    parent = {}

    def find(u):
        parent.setdefault(u, u)
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    for (building, k), a in unit_of.items():
        m = _LETTER_FIRST.match(k) if isinstance(k, str) else None
        b = unit_of.get((building, m.group(2) + m.group(1))) if m else None
        if b is None or a == b or beds[a] != beds[b]:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    out["unit_id"] = out.unit_id.map(find)
    return out


# Number words in unit labels with a letter after them ("fourb", "five-a"),
# longest first so "fourth" is not read as "four" and "th".
WORD_LETTER_WORDS = {
    **LABEL_WORDS,
    "eleven": "11", "twelve": "12", "sixth": "6", "seventh": "7",
    "eighth": "8", "ninth": "9", "tenth": "10",
}  # fmt: skip
_WORD_LETTER = re.compile(
    r"^(" + "|".join(sorted(WORD_LETTER_WORDS, key=len, reverse=True)) + r")"
    r"[-_ ]?([a-z]{0,2})$"
)


def merge_word_letter_labels(
    frame: pd.DataFrame, base=merge_swapped_labels
) -> pd.DataFrame:
    """unit-labels-v8, and units labelled with a number word and a letter
    ("fourb", "five-a", "eleven") joined to the unit of the same building
    labelled with that number ("4B", "5A", "11"), where both units' median
    bedroom counts (under the base rule) agree. On the three-neighbourhood
    cohort (2026-10-07) that joins 46 more unit ids than v8 does, 297 rows in
    32 buildings ("one-e" and "1e", "twelvea" and "12a"). Groups that share a
    unit are one unit, whose id is the smallest. Rows are unchanged."""
    out = base(frame)
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    beds = frame.bedrooms.groupby(out.unit_id).median().to_dict()
    unit_of = dict(zip(zip(frame.building, key), out.unit_id))
    parent = {}

    def find(u):
        parent.setdefault(u, u)
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    for building, label, a in zip(frame.building, raw, out.unit_id):
        m = _WORD_LETTER.match(label) if isinstance(label, str) else None
        if m is None:
            continue
        b = unit_of.get((building, unit_label_key(WORD_LETTER_WORDS[m[1]] + m[2])))
        if b is None or a == b or beds[a] != beds[b]:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    out["unit_id"] = out.unit_id.map(find)
    return out


# A unit's history splits where its bedroom count moves by at least this much.
UNIT_SPLIT_BEDROOMS = 2


def split_unit_histories(
    frame: pd.DataFrame,
    bedrooms: int = UNIT_SPLIT_BEDROOMS,
    rejoin: bool = False,
    footage_holds: bool = False,
) -> pd.DataFrame:
    """A unit's history split into separate units where an ad's bedroom count
    differs by 2 or more from the unit's previous ad with a bedroom count (as
    prevprice reads the previous listing): a 1-bedroom let at $3,395 and a
    4-bedroom at $14,999 under one unit page are a combined or rebuilt
    apartment, or a miscoded one, and should not share a unit effect or a price
    history. On the served rows (2026-10-07), 583 consecutive listing pairs in
    285 buildings change by 2 or more; 63% of them move rent by over 40% and
    5.8% have a high Pareto k, against 6.8% and 0.6% for pairs with no change.
    Under v8 or v9 it moves 1,058 rows of 463 units. An ad's rows stay together in
    the piece of its first row. Ads are taken by first date, then listing id,
    so a row's unit depends only on its own and earlier rows. Later pieces get
    the unit id plus "~1", "~2", ...; an ad with no bedroom count never splits.
    It reads the unit ids and bedroom counts it is given, so `apply_rules`
    refuses it anywhere but last. Rows are unchanged.

    With `rejoin`, an ad whose bedroom count an earlier piece of the unit
    already had goes back to that piece instead of starting a new one, so a
    convertible apartment coded 1, 2, 1 keeps its two 1-bedroom ads together.
    It looks only at earlier ads, like the split itself.

    With `footage_holds`, a change of one bedroom does not split when the
    previous ad gave no square footage and this ad gives one. Under v3 those
    splits gained +5.3 on 538 rows in the exploration pair, and they cut
    110 W 26th St, a building of 1,400-1,650 sq ft lofts listed as anything
    from studio to 3-bedroom, into one-ad units: footage-less "1-bedroom" ads
    split away from the lofts' full listings. That building alone failed the
    group R-hat gate on the v3 serving fit (1.08; 1.00 under v1)."""
    out = frame.copy()
    at = pd.to_datetime(frame.price_at, utc=True).to_numpy()
    units = frame.unit_id.to_numpy()
    ids = frame.source_listing_id.astype(str).to_numpy()
    beds = frame.bedrooms.to_numpy(dtype=float)
    sqft = frame.get("square_feet", pd.Series(np.nan, index=frame.index)).to_numpy(
        dtype=float
    )
    new = units.astype(object).copy()
    piece_of, piece, pieces, last_beds, last_sqft, seen = {}, 0, 1, np.nan, np.nan, {}
    order = np.lexsort((ids, at, units))
    for k, i in enumerate(order):
        if k == 0 or units[order[k - 1]] != units[i]:
            piece_of, piece, pieces, last_beds, last_sqft, seen = (
                {},
                0,
                1,
                np.nan,
                np.nan,
                {},
            )
        if ids[i] not in piece_of:
            change = abs(beds[i] - last_beds)
            held = (
                footage_holds
                and change < 2
                and np.isnan(last_sqft)
                and not np.isnan(sqft[i])
            )
            if change >= bedrooms and not held:
                if rejoin and beds[i] in seen:
                    piece = seen[beds[i]]
                else:
                    piece, pieces = pieces, pieces + 1
            piece_of[ids[i]] = piece
            if not np.isnan(beds[i]):
                seen[beds[i]] = piece
                last_beds, last_sqft = beds[i], sqft[i]
        if piece_of[ids[i]]:
            new[i] = f"{units[i]}~{piece_of[ids[i]]}"
    out["unit_id"] = new
    return out


def unit_line_key(frame: pd.DataFrame) -> pd.Series:
    """Each row's line ("column") within its building, from the unit label:
    "23C" and "4C" are line C, "1204" and "304" are line 04, "2ND", "4TH" and
    "4THFL" are the floor-through line FL; "building/line", or NaN for labels
    without a line (PH, GARDEN, 12)."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].map(unit_label_key)
    lettered = label.str.extract(r"^\d{1,2}([A-Z]{1,2})$")[0]
    numbered = label.str.extract(r"^\d{1,2}(\d\d)$")[0]
    # "2ND", "3RD", "4TH", "4THFL": floor-through units, stacked as one line.
    through = label.str.match(r"^\d{1,2}(?:ST|ND|RD|TH)(?:FL)?$", na=False)
    line = lettered.fillna(numbered).where(~through, "FL")
    return (frame.building + "/" + line).where(line.notna())


REPO = Path(__file__).resolve().parents[3]
# The divergence review of 2026-09-29: advertisements whose own words, or
# MapPLUTO, show they are not an open-market lease of a whole Chelsea apartment
# at the recorded address, one JSON line each with its reason and evidence.
QUARANTINE_V1 = (
    REPO / "config" / "reviews" / "chelsea-divergence-quarantine-20260929.jsonl"
)
# v1 plus the second review (2026-09-30): ads that name another street for the
# apartment, and bedroom counts the ad flatly contradicts, over every row.
QUARANTINE_V2 = REPO / "config" / "reviews" / "chelsea-quarantine-v2-20260930.jsonl"
# v2 plus the third review (2026-10-02): West Village, read for the first time
# (its ads from the granular crawl), and Chelsea's ads against the same detectors.
QUARANTINE_V3 = REPO / "config" / "reviews" / "quarantine-v3-20261002.jsonl"
# v3 and a fourth review (2026-10-03): the ads of single-listing apartments the
# served fit gives a very large unit effect, read for errors their own words show.
QUARANTINE_V4 = REPO / "config" / "reviews" / "quarantine-v4-20261003.jsonl"
# v4 and a fifth review (2026-10-04): the ads of listings far from their estimate
# in apartments with other listings, read for errors their own words show.
QUARANTINE_V5 = REPO / "config" / "reviews" / "quarantine-v5-20261004.jsonl"


@functools.lru_cache(maxsize=4)
def quarantined(path: Path = QUARANTINE_V1) -> frozenset:
    with open(path) as f:
        return frozenset(json.loads(line)["audit_id"] for line in f if line.strip())


def quarantine_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the advertisements the divergence review quarantined (143 rows:
    non-residential offers, ads that place the apartment elsewhere, SRO rooms,
    income-restricted and short-stay offers, a net-of-incentive ask, and bedroom
    counts the ad contradicts). The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined())]


def quarantine_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """v1 and the second review's rows (188 in all): 37 more ads whose own words
    place the apartment at another address or on a street its building does not
    front, and eight more bedroom counts the ad flatly contradicts. The other rows
    are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V2))]


# The corrections overlay (rentfrontier.corrections): bedroom counts the
# listing's own ad clearly states otherwise, one JSON line per row with the
# ad's first sentence as evidence; provenance beside it.
BEDROOM_CORRECTIONS = REPO / "config" / "corrections" / "bedrooms-ad-20261003.jsonl"


@functools.lru_cache(maxsize=2)
def corrections(path: Path = BEDROOM_CORRECTIONS) -> dict:
    """audit_id -> (field, corrected value) for each row of a corrections file."""
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["audit_id"]: (r["field"], r["corrected"]) for r in rows}


def correct_bedrooms_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """The bedroom count of rows whose ad's first sentence states another count
    than the record, every count in the ad agreeing and no flex, den, office or
    conversion words, the unit's other listings not contradicting it (100 rows).
    Every row is kept; only `bedrooms` changes."""
    return _correct_bedrooms(frame, "bedrooms-ad-v1")


def correct_bedrooms_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """v1's rule, and half of the unit's other listings (units joined as
    unit-labels-v2) recording the ad's count, and no ad that places the
    apartment in the other neighbourhood or on another avenue, no bedroom
    range, rec room or disagreeing "true" count, no bare count on a unit with
    no other listing (84 rows)."""
    return _correct_bedrooms(frame, "bedrooms-ad-v2")


def _correct_bedrooms(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    listed = corrections(RULE_SOURCES[rule])
    fixes = {a: v for a, (field, v) in listed.items() if field == "bedrooms"}
    out = frame.copy()
    hit = out.audit_id.isin(fixes)
    out.loc[hit, "bedrooms"] = out.loc[hit, "audit_id"].map(fixes).to_numpy()
    return out


BATH_CORRECTIONS = REPO / "config" / "corrections" / "baths-ad-20261003.jsonl"
# The second pass (rentfrontier.corrections --version 2): stricter on units
# whose other listings disagree and on ads written for another apartment.
BEDROOM_CORRECTIONS_V2 = (
    REPO / "config" / "corrections" / "bedrooms-ad-v2-20261003.jsonl"
)
BATH_CORRECTIONS_V2 = REPO / "config" / "corrections" / "baths-ad-v2-20261003.jsonl"
# The third pass (rentfrontier.corrections --version 3): the second's method on
# the five neighbourhoods and all four crawls' ads. It keeps every v2 row.
BEDROOM_CORRECTIONS_V3 = (
    REPO / "config" / "corrections" / "bedrooms-ad-v3-20261008.jsonl"
)
BATH_CORRECTIONS_V3 = REPO / "config" / "corrections" / "baths-ad-v3-20261008.jsonl"
# Field errors a review found by reading ads (the fourth review, of single-listing
# apartments with a very large unit effect): bedroom and bath counts.
FIELD_REVIEW = REPO / "config" / "corrections" / "fields-review-20261003.jsonl"


def correct_baths_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """The full and half baths of rows whose ad states more bathrooms than the
    record (one count in the ad, no shared, powder-room, hedging or other-area
    words, the unit's other listings not contradicting it; 47 rows).
    Every row is kept; only `full_baths` and `half_baths` change."""
    return _correct_baths(frame, "baths-ad-v1")


def correct_baths_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """v1's rule, and half of the unit's other listings recording the ad's
    count, no ad placed elsewhere or whose own bedroom counts leave out the
    record's, and at most one bath beyond the bedrooms (41 rows)."""
    return _correct_baths(frame, "baths-ad-v2")


def correct_bedrooms_v3(frame: pd.DataFrame) -> pd.DataFrame:
    """v2's rule on the five neighbourhoods: units joined by their alias table,
    Flatiron and Gramercy Park other neighbourhoods to Chelsea and the Villages,
    and no ad placed in another part of the city or whose count is a
    comparison (148 rows: v2's 84 but one no longer in the dataset, and 65
    more)."""
    return _correct_bedrooms(frame, "bedrooms-ad-v3")


def correct_baths_v3(frame: pd.DataFrame) -> pd.DataFrame:
    """v2's rule on the five neighbourhoods, as bedrooms-ad-v3 (59 rows: v2's
    41 and 18 more)."""
    return _correct_baths(frame, "baths-ad-v3")


def _correct_baths(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    with open(RULE_SOURCES[rule]) as f:
        rows = {
            r["audit_id"]: r
            for r in (json.loads(line) for line in f if line.strip())
            if "full_baths" in r
        }
    out = frame.copy()
    hit = out.audit_id.isin(rows)
    if not hit.any():
        # No listed row in this dataset (a new neighbourhood): an empty
        # assignment would fail on the integer columns.
        return out
    for col in ("full_baths", "half_baths"):
        out.loc[hit, col] = (
            out.loc[hit, "audit_id"].map(lambda a, col=col: rows[a][col]).to_numpy()
        )
    return out


def correct_fields_review_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """Bedroom and bath counts a review read in the listing's own ad, where the
    record contradicts it (16 rows: "huge alcove studio" recorded as a
    one-bedroom, "3br 2 bath" with one bath). Every row is kept; only
    `bedrooms`, `full_baths` and `half_baths` change."""
    return _correct_baths(
        _correct_bedrooms(frame, "fields-review-v1"), "fields-review-v1"
    )


def correct_fields_review_v3(frame: pd.DataFrame) -> pd.DataFrame:
    """Reverts v1: the listings keep their recorded bedroom and bath counts.
    v1's 16 corrections came from the ad's words alone, and none of those
    apartments has another listing to back them (Ben chose to revert them on
    2026-10-05; since 2026-10-04 an ad's description does not override the
    coded fields). As the latest version of the family, it takes v1 out of
    the current rules. (v2, #170, was never merged.)"""
    return frame


def quarantine_v3(frame: pd.DataFrame) -> pd.DataFrame:
    """v2 and the third review's rows (261 in all): 65 West Village and 8
    Chelsea ads whose own words place the apartment elsewhere (Brooklyn's
    Grove and Bleecker Streets, Park Slope's avenues, Harlem, the Upper West
    Side), offer a shop, restaurant, office or event space, a room, or a short
    stay only, or contradict the recorded ask. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V3))]


def quarantine_v4(frame: pd.DataFrame) -> pd.DataFrame:
    """v3 and the fourth review's rows (272 in all): the ads of 553 apartments
    with one listing and a very large unit effect, read in full; 7 place the
    apartment at another address (One Morton Square, The Grove, PS90 in
    Harlem, near Columbia), 2 offer a short stay only, 1 a room, and 1 states
    another rent than the ask. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V4))]


def quarantine_v5(frame: pd.DataFrame) -> pd.DataFrame:
    """v4 and the fifth review's rows (277 in all): the ads of 477 listings
    more than 0.3 in log rent from their estimate, in apartments with other
    listings, read in full; 1 is a commercial lease, 1 an office, 1 places the apartment
    on Broadway at West 104th, 1 is a three-month stay, and 1 states another
    rent than the ask. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V5))]


# v5 and a sixth review (2026-10-07): 110 West 26th Street's ads whose unit
# label gives no floor side.
QUARANTINE_V6 = REPO / "config" / "reviews" / "quarantine-v6-20261007.jsonl"


def quarantine_v6(frame: pd.DataFrame) -> pd.DataFrame:
    """v5 and the sixth review's rows (282 in all): 110 West 26th Street has a
    front and a rear apartment on each floor (Ben, 2026-10-07: the R and B
    listings "both refer to the unit at the back of the building"), and 5 of its
    ads, labelled "3", "4", "5" or "6", say neither. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V6))]


QUARANTINE_V7 = REPO / "config" / "reviews" / "quarantine-v7-20261008.jsonl"


def quarantine_v7(frame: pd.DataFrame) -> pd.DataFrame:
    """v6 and the seventh review's rows (327 in all), the first of Greenwich
    Village, Gramercy Park and Flatiron: of 338 listings whose ads name another
    borough or area, a room share, a short stay or a commercial space, or whose
    rent is over 2.2 times or under 0.45 times the building's median for its
    bedrooms, read in full, 45 are an ad for another address (Bushwick's
    Bleecker Street, Prospect Park, the Upper West Side), a short stay only, or
    a shop or office. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V7))]


QUARANTINE_V8 = REPO / "config" / "reviews" / "quarantine-v8-20261008.jsonl"


def quarantine_v8(frame: pd.DataFrame) -> pd.DataFrame:
    """v7 and the eighth review's rows (378 in all): of 604 Greenwich Village,
    Gramercy Park and Flatiron listings the served model found far out of line
    (rent over 1.8 times or under 0.56 times its estimate, Pareto k over 0.7,
    or an extreme PIT) and v7 had not read, read in full, 51 are an ad for
    another address (Harlem, the Upper West Side, Prospect Park, Park Slope), a
    shop, office or restaurant, a room with a shared bath, or one ask for two
    apartments. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V8))]


QUARANTINE_V9 = REPO / "config" / "reviews" / "quarantine-v9-20261008.jsonl"


def quarantine_v9(frame: pd.DataFrame) -> pd.DataFrame:
    """v6 and the rent-blind review's rows (377 in all). v7 and v8 read only
    ads picked by their rent or residual, which favours rows the model fits
    badly. v9 replaces both: generic text checks (a far neighbourhood from
    NYC's area list or a street above 40th, a shop or office, a shared bath or
    room share, one ask for several apartments, a short stay) run over every
    Greenwich Village, Gramercy Park and Flatiron ad whatever its rent, and
    each hit read with no rent shown: 95 are left out. The other rows are
    unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V9))]


QUARANTINE_V10 = REPO / "config" / "reviews" / "quarantine-v10-20261008.jsonl"


def quarantine_v10(frame: pd.DataFrame) -> pd.DataFrame:
    """Only rows a review that never looks at rent finds (219 in all). v1 to
    v6 read Chelsea and West Village ads picked partly by their rent (a
    divergence review, a large unit effect, residuals over 0.3), which favours
    rows the model fits badly. v10 runs v9's text checks over every Chelsea
    and West Village ad as well, each hit read with no rent shown: 124 are left
    out there, 91 of them already in v6. With v9's 95 Greenwich Village,
    Gramercy Park and Flatiron rows that is 219; the 191 v6 rows no rent-blind
    check reaches come back. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V10))]


# Units of one building a review found to be one apartment under different
# labels, one JSON line per group with its evidence (2026-10-07).
UNIT_JOINS = REPO / "config" / "reviews" / "unit-joins-20261007.jsonl"


def join_reviewed_units(frame: pd.DataFrame, path: Path = UNIT_JOINS) -> pd.DataFrame:
    """The units of each reviewed group (a building and the labels of one
    apartment) given one unit id, the group's smallest: at 110 West 26th Street,
    4R and 4B, and 5R and 5B, are each floor's rear apartment (Ben, 2026-10-07:
    the R and B listings "both refer to the unit at the back of the building").
    It reads the rows' labels and the unit ids it is given, so it runs after the
    unit-labels rules. Rows are unchanged."""
    with open(path) as f:
        groups = [json.loads(line) for line in f if line.strip()]
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0]
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    out = frame.copy()
    for g in groups:
        hit = (frame.building == g["building"]) & key.isin(g["unit_labels"])
        if hit.any():
            out.loc[hit, "unit_id"] = out.unit_id[hit].min()
    return out


# Named data rules, applied after the held-out split is drawn (the row split
# depends on unit ids, and scored rows must not change). Run records list them.
# Tuning subsets (Ben, 2026-10-01: "consider using a subset of the listings or
# units for tuning the fit"): a fixed share of buildings, chosen by a hash of the
# building slug, so every tuning fit has the same rows and pairs with the others.
# Tuning fits are never served (rentfrontier.autoselect).
TUNING_PREFIX = "tune-"
TUNE_B35_SHARE = 35  # percent of buildings


def in_tuning_subset(building: str, share: int = TUNE_B35_SHARE) -> bool:
    digest = hashlib.sha256(f"tune-buildings:{building}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 100 < share


def tune_b35_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows of 35% of buildings (in every neighbourhood alike)."""
    keep = frame.building.map(in_tuning_subset)
    return frame[keep.to_numpy()]


DATA_RULES = {
    "tune-b35-v1": tune_b35_v1,
    "unit-labels-v1": merge_unit_labels,
    "unit-labels-v2": merge_unit_aliases,
    "unit-labels-v3": merge_word_labels,
    # unit-labels-v3 with Greenwich Village's alias groups too (UNIT_ALIASES_GV).
    "unit-labels-v5": functools.partial(merge_word_labels, aliases=UNIT_ALIASES_GV),
    "unit-labels-v6": merge_history_pairs,
    # unit-labels-v6 with letter-first labels joined to their digit-first twins.
    "unit-labels-v8": merge_swapped_labels,
    # unit-labels-v8 with number-word-and-letter labels joined to their twins.
    "unit-labels-v9": merge_word_letter_labels,
    # unit-labels-v9 on the alias table and history pairs with Flatiron +
    # Gramercy Park's appended (UNIT_ALIASES_FGP, UNIT_HISTORY_PAIRS_FGP).
    "unit-labels-v11": functools.partial(
        merge_word_letter_labels,
        base=functools.partial(
            merge_swapped_labels,
            base=functools.partial(
                merge_history_pairs,
                pairs=UNIT_HISTORY_PAIRS_FGP,
                aliases=UNIT_ALIASES_FGP,
            ),
        ),
    ),
    # unit-labels-v11 on the tables with Stuyvesant Town/PCV's appended too
    # (UNIT_ALIASES_STUY, UNIT_HISTORY_PAIRS_STUY).
    "unit-labels-v13": functools.partial(
        merge_word_letter_labels,
        base=functools.partial(
            merge_swapped_labels,
            base=functools.partial(
                merge_history_pairs,
                pairs=UNIT_HISTORY_PAIRS_STUY,
                aliases=UNIT_ALIASES_STUY,
            ),
        ),
    ),
    # unit-labels-v13 on the tables with NoMad's appended too
    # (UNIT_ALIASES_NOMAD, UNIT_HISTORY_PAIRS_NOMAD).
    "unit-labels-v14": functools.partial(
        merge_word_letter_labels,
        base=functools.partial(
            merge_swapped_labels,
            base=functools.partial(
                merge_history_pairs,
                pairs=UNIT_HISTORY_PAIRS_NOMAD,
                aliases=UNIT_ALIASES_NOMAD,
            ),
        ),
    ),
    "unit-splits-v1": split_unit_histories,
    # unit-splits-v1 at any change of bedroom count: 3,871 more listing pairs,
    # 20.7% of them moving rent by over 40% against 6.8% with no change.
    "unit-splits-v2": functools.partial(split_unit_histories, bedrooms=1),
    "unit-splits-v3": functools.partial(split_unit_histories, bedrooms=1, rejoin=True),
    "unit-splits-v4": functools.partial(
        split_unit_histories, bedrooms=1, rejoin=True, footage_holds=True
    ),
    "quarantine-v1": quarantine_v1,
    "quarantine-v2": quarantine_v2,
    "bedrooms-ad-v1": correct_bedrooms_v1,
    "baths-ad-v1": correct_baths_v1,
    "bedrooms-ad-v2": correct_bedrooms_v2,
    "baths-ad-v2": correct_baths_v2,
    "bedrooms-ad-v3": correct_bedrooms_v3,
    "baths-ad-v3": correct_baths_v3,
    "fields-review-v1": correct_fields_review_v1,
    "fields-review-v3": correct_fields_review_v3,
    "quarantine-v3": quarantine_v3,
    "quarantine-v4": quarantine_v4,
    "quarantine-v5": quarantine_v5,
    "quarantine-v6": quarantine_v6,
    "quarantine-v7": quarantine_v7,
    "quarantine-v8": quarantine_v8,
    "quarantine-v9": quarantine_v9,
    "quarantine-v10": quarantine_v10,
    "unit-reviews-v1": join_reviewed_units,
}
# Rules that read a file; run records hash the files.
RULE_SOURCES = {
    "quarantine-v1": QUARANTINE_V1,
    "quarantine-v2": QUARANTINE_V2,
    "quarantine-v3": QUARANTINE_V3,
    "quarantine-v4": QUARANTINE_V4,
    "quarantine-v5": QUARANTINE_V5,
    "quarantine-v6": QUARANTINE_V6,
    "quarantine-v7": QUARANTINE_V7,
    "quarantine-v8": QUARANTINE_V8,
    "quarantine-v9": QUARANTINE_V9,
    "quarantine-v10": QUARANTINE_V10,
    "unit-reviews-v1": UNIT_JOINS,
    "unit-labels-v2": UNIT_ALIASES,
    "unit-labels-v3": UNIT_ALIASES,
    "unit-labels-v5": UNIT_ALIASES_GV,
    "unit-labels-v6": UNIT_HISTORY_PAIRS,
    "unit-labels-v8": UNIT_HISTORY_PAIRS,
    "unit-labels-v9": UNIT_HISTORY_PAIRS,
    "unit-labels-v11": UNIT_ALIASES_FGP,
    "unit-labels-v13": UNIT_ALIASES_STUY,
    "unit-labels-v14": UNIT_ALIASES_NOMAD,
    "bedrooms-ad-v1": BEDROOM_CORRECTIONS,
    "baths-ad-v1": BATH_CORRECTIONS,
    "bedrooms-ad-v2": BEDROOM_CORRECTIONS_V2,
    "baths-ad-v2": BATH_CORRECTIONS_V2,
    "bedrooms-ad-v3": BEDROOM_CORRECTIONS_V3,
    "baths-ad-v3": BATH_CORRECTIONS_V3,
    "fields-review-v1": FIELD_REVIEW,
}
# Of those, the rules that drop the rows their file lists.
DROPPING_RULES = (
    "quarantine-v1",
    "quarantine-v2",
    "quarantine-v3",
    "quarantine-v4",
    "quarantine-v5",
    "quarantine-v6",
    "quarantine-v7",
    "quarantine-v8",
    "quarantine-v9",
    "quarantine-v10",
)


def dropped_rows() -> frozenset:
    """Audit ids some data rule drops: the only rows two runs' scores may
    differ by (cleaning is scored on the rows both keep)."""
    return frozenset().union(*(quarantined(RULE_SOURCES[r]) for r in DROPPING_RULES))


def recorded_rules(result: dict) -> tuple:
    """A run record's data rules, refused if a rule is unknown or its file
    differs now from the hash the run recorded (the rows would not be the
    run's rows)."""
    rules = tuple(result.get("data_rules", ()))
    for rule in rules:
        if rule not in DATA_RULES:
            raise SystemExit(f"unknown data rule {rule} in the run's record")
        if rule in RULE_SOURCES:
            src = result.get("data_rule_sources", {}).get(rule)
            if src is None:
                raise SystemExit(f"the run records no hash for data rule {rule}'s file")
            if sha256(RULE_SOURCES[rule]) != src["sha256"]:
                raise SystemExit(
                    f"data rule {rule}'s file differs from the run's record"
                )
    return rules


def rows_sha256(frame: pd.DataFrame, heldout) -> str:
    """A hash of a run's rows after its split and data rules: the column names,
    every value in order, and the held-out mask. Two rule sets whose rows hash
    the same give a fit the same data, so autoselect treats them as the same
    rules (Ben, 2026-10-08)."""
    digest = hashlib.sha256()
    digest.update(json.dumps([str(c) for c in frame.columns]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=False).to_numpy().tobytes())
    digest.update(np.asarray(heldout, dtype=bool).tobytes())
    return digest.hexdigest()


def split_and_rules(frame: pd.DataFrame, split: str, rules) -> tuple:
    """(frame, heldout) for a run's split and data rules, in the run's order: most
    splits are drawn first and the rules applied after; a split in
    `splits.AFTER_RULES` (latest) is drawn after the rules, on merged units and
    kept rows. Every reader of a run rebuilds its rows through this."""
    from . import splits

    if split in splits.AFTER_RULES:
        frame, _ = apply_rules(frame, np.zeros(len(frame), dtype=bool), rules)
        held = splits.SPLITS[split](frame)
        # As apply_rules: a held-out row needs a training row in its building.
        if "building" in frame:
            held = held & frame.building.isin(set(frame.building[~held])).to_numpy()
        return frame, held
    return apply_rules(frame, splits.SPLITS[split](frame), rules)


def apply_rules(frame: pd.DataFrame, heldout: np.ndarray, rules):
    """(frame, heldout) after the named rules. A rule that drops rows drops them
    from the held-out mask too, so every other row keeps its split; the frame
    gets a fresh RangeIndex. A held-out row whose building has no training row
    left (the building's other rows dropped, by a rule or in a new dataset)
    moves to training: a fit cannot score a building it never saw. On the
    datasets fit before 2026-10-05 no row moves."""
    rules = tuple(rules)
    splits = [i for i, r in enumerate(rules) if r.startswith("unit-splits-")]
    if splits and splits != list(range(len(rules) - len(splits), len(rules))):
        raise ValueError(f"unit-splits rules must come last: {rules}")
    labels = [i for i, r in enumerate(rules) if r.startswith("unit-labels-")]
    reviews = [i for i, r in enumerate(rules) if r.startswith("unit-reviews-")]
    if labels and reviews and min(reviews) < max(labels):
        raise ValueError(f"unit-reviews rules must follow unit-labels: {rules}")
    mask = pd.Series(np.asarray(heldout, dtype=bool), index=frame.index)
    for rule in rules:
        frame = DATA_RULES[rule](frame)
    held = mask.loc[frame.index].to_numpy().copy()
    if "building" in frame:
        held &= frame.building.isin(set(frame.building[~held])).to_numpy()
    return frame.reset_index(drop=True), held

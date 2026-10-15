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
        # The eight neighbourhoods (DATASET_NB8, #625); before that the five
        # (DATASET_NB5, #460, chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057),
        # and before that Chelsea + West
        # Village + Greenwich Village, chelsea-wv-gv-analysis-20261005-2d5b3b6
        # (#292), chelsea-west-village-analysis-20261005-1222e51 (Oct 5 captures,
        # #220), chelsea-west-village-analysis-20261001-eea4f66, and Chelsea alone,
        # data/model/chelsea-product-scope-analysis-20260921.
        "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-analysis-20261010-3ebfea0",
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
# The seven plus East Village (cohort east-village-analysis-20261010-3ebfea04),
# no rule change. The served dataset (DATASET).
DATASET_NB8 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-analysis-20261010-3ebfea0"
)
# The eight plus Hell's Kitchen and Hudson Yards (cohort
# midtown-west-areas-analysis-20261014-cd891c8, the Midtown West crawl split by
# each building page's area), no rule change.
DATASET_NB9 = Path(
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-mw-analysis-20261014-cd891c8"
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
# That table with East Village's appended (unit-spelling-alias-v2 on
# east-village-granular-20261010-canonical-url-v1, 405 history-confirmed
# groups); provenance beside it.
UNIT_ALIASES_EV = UNIT_ALIASES.with_name("wv-gv-fgp-stuy-nomad-ev-20261010.jsonl")
# That table with Midtown West's appended (unit-spelling-alias-v2 on
# midtown-west-granular-20261014-canonical-url-v1, 833 history-confirmed
# groups); provenance beside it.
UNIT_ALIASES_MW = UNIT_ALIASES.with_name("wv-gv-fgp-stuy-nomad-ev-mw-20261014.jsonl")


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
# The same pairs with East Village's appended.
UNIT_HISTORY_PAIRS_EV = UNIT_ALIASES.with_name("history-20261010.jsonl")
# The same pairs with Midtown West's appended.
UNIT_HISTORY_PAIRS_MW = UNIT_ALIASES.with_name("history-20261014.jsonl")


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


# Unit labels spelled out, each rewritten to its short spelling, in order:
# "3RDFL", "3FL", "3RD" -> "3"; "THIRD", "THREEFL" -> "3"; "2WFL" -> "2W";
# "3FRONT" -> "3F", "3REAR", "3BACK" -> "3R"; "PENTHOUSEA" -> "PHA";
# "GARDEN", "GDN", "GROUND", "GARDENFL" -> "G"; "PARLOUR", "PARLORFL" -> "PARLOR".
_SPELLED_WORDS = {k.upper(): v for k, v in WORD_LETTER_WORDS.items()}
SPELLED_LABELS = [
    (re.compile(r"^(" + "|".join(sorted(_SPELLED_WORDS, key=len, reverse=True))
                + r")(?=(?:FL)?$)"), lambda m: _SPELLED_WORDS[m[1]]),
    (re.compile(r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?$"), r"\1"),
    (re.compile(r"^(\d+[A-Z])FL$"), r"\1"),
    (re.compile(r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?FRONT$"), r"\1F"),
    (re.compile(r"^(\d+)(?:ST|ND|RD|TH)?(?:FL)?(?:REAR|BACK)$"), r"\1R"),
    (re.compile(r"^PENTHOUSE"), "PH"),
    (re.compile(r"^(?:GARDEN|GDN|GROUND)(?:FL)?$"), "G"),
    (re.compile(r"^PARLOU?R(?:FL)?$"), "PARLOR"),
]  # fmt: skip


def spelled_label_key(label: str) -> str:
    """A unit label's short spelling (see SPELLED_LABELS)."""
    key = unit_label_key(label)
    for pattern, short in SPELLED_LABELS:
        key = pattern.sub(short, key)
    return key


def merge_spelled_labels(frame: pd.DataFrame, base) -> pd.DataFrame:
    """A labels rule (`base`), and units of a building whose labels are one
    label spelled out and short ("3RDFL" and "3", "PENTHOUSEA" and "PHA",
    "GARDEN" and "G", "4REAR" and "4R", "THIRD" and "3") joined where both
    units' median bedroom counts (under the base rule) agree, the guard the
    label rules since v3 use. Units whose labels are already one label
    written differently ("3A" and "3-A") are grouped too, and the base rule
    has joined most of them. Groups that share a unit are one unit, whose id
    is the smallest. Rows are unchanged."""
    out = base(frame)
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0]
    key = raw.map(lambda v: spelled_label_key(v) if isinstance(v, str) else v)
    beds = frame.bedrooms.groupby(out.unit_id).median().to_dict()
    parent = {}

    def find(u):
        parent.setdefault(u, u)
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    groups = {}
    for building, k, a in zip(frame.building, key, out.unit_id):
        if isinstance(k, str):
            groups.setdefault((building, k), set()).add(a)
    for units in groups.values():
        units = sorted(units)
        for i, a in enumerate(units):
            for b in units[i + 1 :]:
                if beds[a] == beds[b]:
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


BEDROOM_CORRECTIONS_V4 = (
    REPO / "config" / "corrections" / "bedrooms-ad-v4-20261015.jsonl"
)


def correct_bedrooms_v4(frame: pd.DataFrame) -> pd.DataFrame:
    """v3's rows, then 22 rows the ad-fit screen's bedroom check
    (`adfit.bedroom_conflicts`) flagged on NB9. A reader read each flagged
    row's ads in full (`config/reviews/ad-fit-reads-20261015-bedrooms.jsonl`).
    A count changes only when an ad states or describes it and something
    independent of that ad backs it, recorded as the read's `second_signal`:
      - another ad for the same unit stating the count,
      - a stated size nearer that count's median size than the coded count's,
      - a floor plan, photos or a video walkthrough Ben reviewed.
    Price chooses which rows get read and never backs a count. Rows whose ad
    states a count with nothing to back it keep their coded count. Every row
    is kept; only `bedrooms` changes."""
    return _correct_bedrooms(correct_bedrooms_v3(frame), "bedrooms-ad-v4")


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


QUARANTINE_V12 = REPO / "config" / "reviews" / "quarantine-v12-20261010.jsonl"
# The rows v12's review read: every hit of the rent-blind screens over East
# Village, NoMad and Stuyvesant Town/PCV.
QUARANTINE_V12_READ = REPO / "config" / "reviews" / "quarantine-v12-read-20261010.txt"


def quarantine_v12(frame: pd.DataFrame) -> pd.DataFrame:
    """v10 and 50 more rows (269 in all) from neighbourhoods v10 never read.
    v10's text checks run over every East Village ad (quarantine_v13_screen.py),
    every NoMad ad (quarantine_v12_screen.py) and every Stuyvesant Town/PCV ad
    (quarantine_v10_screen.py with its centre moved), each place measured from
    the neighbourhood's own centre. Every hit (quarantine-v12-read-20261010.txt)
    is read with no rent shown: 39 East Village rows (shops, offices and medical
    offices; ads for apartments elsewhere; dorm rooms with a shared bath; summer
    and few-month sublets), 10 NoMad rows and a Stuyvesant Town ad for a studio
    in Harlem are left out. v11's rows are not in it. The other rows are
    unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V12))]


QUARANTINE_V13 = REPO / "config" / "reviews" / "quarantine-v13-20261014.jsonl"
# The rows v13's review read: every hit of price_mismatch_screen.py at a factor
# over 2.5.
QUARANTINE_V13_READ = REPO / "config" / "reviews" / "quarantine-v13-read-20261014.txt"


def quarantine_v13(frame: pd.DataFrame) -> pd.DataFrame:
    """v12 and 2 more rows (271 in all) from a screen on price. With every row
    at its latest ask (`latest-ask-v2`), price_mismatch_screen.py flags a row
    whose ask is more than a factor of 3 off both the median of its unit's other
    rows with the same bedroom count and the median of its building's. The
    screen compares a row with its unit's later listings as well as its earlier
    ones, which a quarantine of read rows allows and a feature would not. Each
    hit over a factor of 2.5 (quarantine-v13-read-20261014.txt) is read with its
    ad: a studio whose ad offers a 3-bedroom with two baths, and a 2-bedroom
    ask in a teaser ad for "other similar units", are left out. The other rows
    are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V13))]


# Units of one building a review found to be one apartment under different
# labels, one JSON line per group with its evidence (2026-10-07).
UNIT_JOINS_20261007 = REPO / "config" / "reviews" / "unit-joins-20261007.jsonl"
# unit-reviews-v1 amended in place (Ben, 2026-10-11: "treat it as the same
# dataset"): that list with 21 West 12th Street's second-floor rear apartment
# (2, 2B, 2F and 2R, one apartment by its ad text) appended. Runs recorded on the
# first list rebuild with it (`RULE_AMENDMENTS`); docs/data/rule-amendments.md.
UNIT_JOINS = UNIT_JOINS_20261007.with_name("unit-joins-20261011.jsonl")


def join_reviewed_units(frame: pd.DataFrame, path: Path = UNIT_JOINS) -> pd.DataFrame:
    """The units of each reviewed group (a building and the labels of one
    apartment) given one unit id, the group's smallest: at 110 West 26th Street,
    4R and 4B, and 5R and 5B, are each floor's rear apartment (Ben, 2026-10-07:
    the R and B listings "both refer to the unit at the back of the building").
    It reads the rows' labels and the unit ids it is given, so it runs after the
    unit-labels rules. Rows are unchanged."""
    with open(path) as f:
        groups = [json.loads(line) for line in f if line.strip()]
    return _join_units(frame, groups)


def _join_units(frame: pd.DataFrame, groups: list[dict]) -> pd.DataFrame:
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0]
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    out = frame.copy()
    for g in groups:
        hit = (frame.building == g["building"]) & key.isin(g["unit_labels"])
        if hit.any():
            out.loc[hit, "unit_id"] = out.unit_id[hit].min()
    return out


# Reviewed units, second version (2026-10-14): the joins above, verbatim, and
# listings split off the unit they were filed under.
UNIT_REVIEWS = UNIT_JOINS.with_name("unit-reviews-20261014.jsonl")


def review_units(frame: pd.DataFrame, path: Path = UNIT_REVIEWS) -> pd.DataFrame:
    """Applies the reviewed unit joins and splits in the file at `path`.

    1. The `join_units` lines go through the same join as `join_reviewed_units`.
    2. Each `split_listings` line names a building, a unit id and the listings
       a reader found to be a different apartment from the rest of that unit's
       history, judged from ad text, page and sizes, not rent: at 1 Patchin
       Place, the 2020 ads for an 1,800 sq ft duplex filed under unit 2, whose
       2014 ads give 900 to 950 sq ft. The rows of those listings get the id
       `{unit_id}~review-{first listing}`, which unit-splits then pieces like
       any other unit, since it runs last.

    Rows are unchanged apart from their unit ids."""
    with open(path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    out = _join_units(frame, [g for g in lines if g["action"] == "join_units"])
    listing = out.source_listing_id.astype(str)
    for s in (g for g in lines if g["action"] == "split_listings"):
        hit = (
            (out.building == s["building"])
            & (out.unit_id == s["unit_id"])
            & listing.isin(s["source_listing_ids"])
        )
        out.loc[hit, "unit_id"] = f"{s['unit_id']}~review-{s['source_listing_ids'][0]}"
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


# Held-out lots (2026-10-13, the grouped-building check of the new-building
# score): every row of about 10% of buildings, drawn by tax lot, dropped so a
# fit never sees them; `rentfrontier.newbuilding.score_holdout` scores them.
# A subset of buildings, so the name is a tuning one: never served or paired.
HOLDOUT_PREFIX = TUNING_PREFIX + "holdout-"
HOLDOUT_LOTS_V1 = REPO / "config" / "holdout" / "lots-v1.tsv"


def holdout_buildings(path: Path = HOLDOUT_LOTS_V1) -> frozenset:
    """The building slugs of a held-out-lots file (tab-separated lot, building)."""
    lines = Path(path).read_text().splitlines()
    return frozenset(
        line.split("\t")[1] for line in lines if line and not line.startswith("#")
    )


def drop_holdout_lots(
    frame: pd.DataFrame, path: Path = HOLDOUT_LOTS_V1
) -> pd.DataFrame:
    """Rows outside the held-out lots' buildings."""
    return frame[~frame.building.isin(holdout_buildings(path)).to_numpy()]


# Final asks (2026-10-13, Ben's final-ask fit): each row priced at its
# listing's last ask (#554), for a fit on what a listing ended at. A different
# price, so the name is a tuning one: never served or paired.
FINAL_ASK_MAX_RATIO = 2.0


def final_ask_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows priced at their listing's last ask, of listings over by the last
    capture whose last ask is within a factor of `FINAL_ASK_MAX_RATIO` of the
    first ask: a still-live listing, one no crawl captured, and a sale price
    or typo (0.5% of captured rows) are left out."""
    from . import listing_outcomes

    out = listing_outcomes.attach(frame)
    ratio = out.final_ask / out.asking_rent
    keep = (
        out.final_ask.notna()
        & out.still_listed.eq(False)
        & ratio.between(1 / FINAL_ASK_MAX_RATIO, FINAL_ASK_MAX_RATIO)
    ).to_numpy()
    final = out.final_ask.to_numpy()[keep]
    return frame[keep].assign(asking_rent=final, log_rent=np.log(final))


# Latest asks (2026-10-13, Ben 13:51Z): every row priced at its listing's
# latest available ask, from outcomes rebuilt over every crawl (East Village's
# crawl came after the 2026-10-08 file). A tuning name: never served or paired.
LATEST_ASK_OUTCOMES = Path(
    "/data1/apartments/external/listing-outcomes/20261013-57c2a78/listing-outcomes.parquet"
)


def latest_ask_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """Every row, priced at its listing's latest ask: the last ask a crawl
    captured, at the last capture for a still-live listing. A row whose listing
    no crawl captured keeps its own ask (its only one), and so does a row whose
    captured ask is more than twice or under half its own (a sale price or a
    typo; `FINAL_ASK_MAX_RATIO`)."""
    from . import listing_outcomes

    out = listing_outcomes.attach(frame, LATEST_ASK_OUTCOMES)
    ratio = (out.final_ask / out.asking_rent).to_numpy()
    take = (
        out.final_ask.notna().to_numpy()
        & (ratio >= 1 / FINAL_ASK_MAX_RATIO)
        & (ratio <= FINAL_ASK_MAX_RATIO)
    )
    price = np.where(take, out.final_ask.to_numpy(), frame.asking_rent.to_numpy())
    return frame.assign(asking_rent=price, log_rent=np.log(price))


QUARANTINE_V14 = REPO / "config" / "reviews" / "quarantine-v14-20261014.jsonl"
# The rows the screen behind v14's new rows read: every hit outside v9's and
# v10's screens (frontier/scripts/quarantine_v14_screen.py).
QUARANTINE_V14_READ = REPO / "config" / "reviews" / "quarantine-v14-read-20261014.txt"


def quarantine_v14(frame: pd.DataFrame) -> pd.DataFrame:
    """v13 and 13 more rows (284 in all). v10's guard dropped "restaurant
    space", since all its hits were rent-picked quarantine-v6 rows, so
    storefronts came back. quarantine_v14_screen.py reruns v10's rent-blind
    checks with more words for shops and restaurants (retail, frontage, a
    certificate of occupancy, kitchen exhaust, an event space) over the five
    neighbourhoods before East Village, NoMad and Stuyvesant Town, and every
    hit outside v9's and v10's screens (quarantine-v14-read-20261014.txt) is
    read with no rent shown: shops, restaurants and an event studio on and
    near Bleecker, two 5-month leases, and one ad for Battery Park are left
    out. 10 of the 13 are v6 rows. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V14))]


QUARANTINE_V15 = REPO / "config" / "reviews" / "quarantine-v15-20261014.jsonl"
# The rows v15's review read: every Midtown West hit of price_mismatch_screen.py's
# factors at over 2.5, on the NB9 rows under latest-ask-v4 and unit-labels-v17.
QUARANTINE_V15_READ = REPO / "config" / "reviews" / "quarantine-v15-read-20261014.txt"


def quarantine_v15(frame: pd.DataFrame) -> pd.DataFrame:
    """v14 and 2 Midtown West rows (286 in all). The price screen behind v13,
    run on the NB9 rows, flags 4 Midtown West rows over a factor of 2.5
    (quarantine-v15-read-20261014.txt), each read with its ad and its unit's
    other asks. The two over 3 are mistyped prices: a Hudson Landing studio at
    $22,953 and a Via 57 West 3-bedroom at $1,559. A 2,500 square foot loft
    coded a studio and a 1-bedroom at $7,495 stay in. The other rows are
    unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V15))]


QUARANTINE_V16 = REPO / "config" / "reviews" / "quarantine-v16-20261014.jsonl"
# The rows v16's review read: every hit of quarantine_v16_screen.py on the NB9
# rows under the rules of 2026-10-14, and the five one-bedroom asks at 110 W 26th St.
QUARANTINE_V16_READ = REPO / "config" / "reviews" / "quarantine-v16-read-20261014.txt"


def quarantine_v16(frame: pd.DataFrame) -> pd.DataFrame:
    """v15 and 33 rows filed under the wrong address (319 in all).
    quarantine_v16_screen.py looks for ads that place the apartment by Prospect
    Park, Cortelyou Road, Ditmas Avenue, PLG, Park Slope, Fort Greene and other
    Brooklyn places, with no rent shown. Of its 39 hits, 28 are Brooklyn
    apartments filed under a Manhattan address with the same number and street
    name, such as 37 East 21st Street and 519 8th Avenue. The other 11 mention
    Park Slope as a broker's other listing, or call Midtown West "Clinton".
    The five one-bedroom asks at 110 W 26th St, at about $2,400 to $2,600 in
    a building of 1,600 sq ft lofts, are held out as East Village ads under
    the wrong address. quarantine-v18 keeps them out under a corrected reason:
    four of their pages carry 112 W 26th St, the same tax lot, and the asks
    are not for whole lofts. The other rows are unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V16))]


QUARANTINE_V17 = REPO / "config" / "reviews" / "quarantine-v17-20261014.jsonl"
QUARANTINE_V17_READ = REPO / "config" / "reviews" / "quarantine-v17-read-20261014.txt"


def quarantine_v17(frame: pd.DataFrame) -> pd.DataFrame:
    """v16 plus seven more Brooklyn ads (326 rows in all).

    StreetEasy links some Brooklyn listings to the Manhattan building with the
    same number and street name (`brooklyn`). v16's 28 such rows and seven
    more, found by a wider place list (`brooklyn.screen`) and read in full,
    carry the reason code `brooklyn_misjoin`, and `brooklyn.MISJOINS` records
    their evidence. The read list is `QUARANTINE_V17_READ`. The other rows are
    unchanged."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V17))]


QUARANTINE_V18 = REPO / "config" / "reviews" / "quarantine-v18-20261014.jsonl"


def quarantine_v18(frame: pd.DataFrame) -> pd.DataFrame:
    """v17's 326 rows, with the reason for the five asks at 110 W 26th St
    corrected. Four of the pages give the address 112 West 26th Street, on
    the same tax lot (BBL 1008010049) as the building's lofts of 1,400 to
    1,650 sq ft, and they carry the loft labels 5F, 5R, 3 and 3R. Picture
    Realty listed them with no square footage and no photos of their own at
    $2,395 to $2,595, a third of the lofts' asks: 5F went for 3 days at
    $2,395 in May 2015, and Douglas Elliman listed it at $7,500 a month
    later. The fifth is a 2021 same-day closed-deal record reading "1-bed",
    at the price of the 2016 ad on the same unit page. All five now carry
    `quarantine_product_scope` in place of `quarantine_location_conflict`.
    The held-out rows are the same as v17's."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V18))]


QUARANTINE_V19 = REPO / "config" / "reviews" / "quarantine-v19-20261014.jsonl"


def quarantine_v19(frame: pd.DataFrame) -> pd.DataFrame:
    """v18's 326 rows and 51 more from the first reads of the ad-fit screen
    (`rentfrontier.adfit`), whose tiers A and B we read in full on NB9
    (`config/reviews/ad-fit-reads-20261014.jsonl`). Each new row quotes the
    ad or the page:
    1. 32 ads offer a stay of six months or less, a summer rental or a
       vacation rental, sometimes with an option to renew.
    2. Seven ads say the listed price holds only for a short-term lease, or
       for the first six months.
    3. Seven are rooms: a bathroom or kitchen shared with other units, or a
       roommate wanted.
    4. Five put the apartment somewhere else: a nearby building, 68 E 1st St
       under the 64 E 1st St condo, 60 E 12th St under 173 11th Ave, and the
       Upper East Side under 250 W 19th St.
    We keep sublets of seven months or more, ads that offer a sublet or
    a full lease, asks at the full-lease price beside a short-term special,
    minimum stays with no upper bound, and placeholder ads with a far price but no words against
    the row."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V19))]


QUARANTINE_V20 = REPO / "config" / "reviews" / "quarantine-v20-20261014.jsonl"


def quarantine_v20(frame: pd.DataFrame) -> pd.DataFrame:
    """v19's 377 rows and 58 more from the second reads of the ad-fit screen.
    After #802 tightened the size check, we read the screen's 1,364 unread
    NB9 hits in full: tiers A to C in `config/reviews/ad-fit-reads-20261014-2.jsonl`
    and tier D in `ad-fit-reads-20261014-3.jsonl`. Each new row quotes the ad:
    1. 14 ads offer a stay of six months or less, or a furnished travel
       rental priced by season and length of stay.
    2. 14 put the apartment somewhere else: Brooklyn, Harlem, the Upper East
       and West Sides, or another Manhattan building. We kept an address
       when the tax lot filed for the row carries it too, as a through-block
       lot or a wide lot does.
    3. 14 are rooms or live/work spaces: a room in a share, a bathroom
       shared with other tenants, or an ask covering commercial floor area.
    4. 10 are stores, offices, a bar, a nightclub or a workshop.
    5. Six asks hold only for a short first term, or vary with the length
       of the stay.
    We keep the same cases v19 keeps, and also an ad quoting a per-roommate
    figure when the ask is for the whole apartment."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V20))]


QUARANTINE_V21 = QUARANTINE_V20.with_name("quarantine-v21-20261014.jsonl")


def quarantine_v21(frame: pd.DataFrame) -> pd.DataFrame:
    """v20's 435 rows and 52 more found by searching the kept rows' ads for the
    stock wording behind some of v20's hold-outs. We read each of the 90
    matches in full and recorded the reads in
    `config/reviews/ad-fit-reads-20261014-4.jsonl`:
    1. 21 Atelier rental office ads say the price may vary with the length of
       the term and with furnishing, and name neither for the advertised
       price. We kept the 34 Atelier ads that say their prices are for a
       one-year term, all but two of them saying unfurnished too.
    2. 29 June ads offer a flexible 1 to 18 month lease whose monthly rate
       depends on furnishing and on the move-in and move-out dates.
    3. Two Rove Travel ads offer furnished stays of 30 days or more, priced
       by season and stay length. We kept the Rove ads with a six-month
       minimum term, as v20 does."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V21))]


QUARANTINE_V22 = QUARANTINE_V20.with_name("quarantine-v22-20261015.jsonl")


def quarantine_v22(frame: pd.DataFrame) -> pd.DataFrame:
    """v21's 487 rows and 146 studios of the bedroom review whose 0 looks
    like a blank field. The ad-fit screen's bedroom check (`beds_price_bldg`)
    flags rows priced out of line with their building's other units, and a
    reader read each flagged row's ads in full
    (`config/reviews/ad-fit-reads-20261015-bedrooms.jsonl`). A row coded 0 is
    held out when no ad for its unit states a count and the row's own ad says
    nothing about the apartment: it is blank, a placeholder ("apt", "-",
    "n/a"), legal boilerplate, or a line about the building. Studios with a
    described layout but no count, such as a duplex loft, keep their 0, as
    does every row coded 1 or more."""
    return frame[~frame.audit_id.isin(quarantined(QUARANTINE_V22))]


# Latest asks (Ben, 2026-10-14: the target is each listing's most current
# price): every row priced at its listing's last on-market ask, built by
# latest_ask.py from the listings' own records.
LATEST_ASK = Path(
    "/data1/apartments/external/latest-ask/20261014-003dd7d/latest-ask.parquet"
)


def latest_ask_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """Every row priced at its listing's latest ask: the last price the listing
    showed while on the market, skipping the placeholder prices advertisers
    type in on the day they take a listing down. A latest ask more than twice
    or under half the first takes whichever of the two is nearer the building's
    other rows with the same bedroom count, and a page price 9 to 11 times off
    is taken the same way (latest_ask.py). A row the file lacks keeps its
    ask."""
    table = pd.read_parquet(LATEST_ASK, columns=["audit_id", "latest_ask"])
    price = (
        frame.audit_id.map(table.set_index("audit_id").latest_ask)
        .fillna(frame.asking_rent)
        .to_numpy(float)
    )
    return frame.assign(asking_rent=price, log_rent=np.log(price))


# Latest asks from rental records only. A sale listing can carry a rental's id,
# and in LATEST_ASK the sale's capture stood in for 210 rows' last capture; the
# 2x check kept their first ask, so 92 of them lacked their last rental ask.
LATEST_ASK_V3 = Path(
    "/data1/apartments/external/latest-ask/20261014-9ae2b6e/latest-ask.parquet"
)


# LATEST_ASK_V3's rows plus Midtown West's (DATASET_NB9), built the same way;
# NB8's rows are identical in both.
LATEST_ASK_V4 = Path(
    "/data1/apartments/external/latest-ask/20261014-717ad9c/latest-ask.parquet"
)


def latest_ask_v3(frame: pd.DataFrame, path: Path = LATEST_ASK_V3) -> pd.DataFrame:
    """`latest_ask_v2` on latest asks built from the listings' rental records
    alone (`LATEST_ASK_V3`). A row the file lacks keeps its ask."""
    table = pd.read_parquet(path, columns=["audit_id", "latest_ask"])
    price = (
        frame.audit_id.map(table.set_index("audit_id").latest_ask)
        .fillna(frame.asking_rent)
        .to_numpy(float)
    )
    return frame.assign(asking_rent=price, log_rent=np.log(price))


# The West Coast (95-97 Horatio St) is one tax lot with two structures in HPD's
# registry, BIN 1012154 (the-west-coast) and BIN 1012155
# (97-horatio-street-new_york), under one StreetEasy building. Its rows carry two
# label schemes: three digits on floors 1 to 7 ("425") and a floor and a letter
# on floors 2 to 10 ("7E", "007E", "PHD").
WESTCOAST = ("the-west-coast", "97-horatio-street-new_york")


def tune_westcoast_split_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """The West Coast's rows split by label scheme, as a tuning rule: a row of
    either building with a floor-and-letter label (or a penthouse) goes to
    97-horatio-street-new_york, and one with a three-digit label goes to
    the-west-coast. Rows with other labels ("7", "26", "42") stay where they
    are. Both names are in the lot registry, so the building features still
    resolve. Run it before the unit rules, so units merge within a scheme."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    lot = frame.building.isin(WESTCOAST).to_numpy()
    letter = (label.str.fullmatch(r"\d+[a-z]+") | label.str.startswith("ph")).to_numpy(
        dtype=bool, na_value=False
    )
    three = label.str.fullmatch(r"\d{3}").to_numpy(dtype=bool, na_value=False)
    building = np.where(
        lot & letter, WESTCOAST[1], np.where(lot & three, WESTCOAST[0], frame.building)
    )
    return frame.assign(building=building)


def tune_westcoast_split_v2(frame: pd.DataFrame) -> pd.DataFrame:
    """`tune_westcoast_split_v1` with the two names swapped: floor-and-letter
    rows go to the-west-coast, three-digit rows to 97-horatio-street-new_york.
    The building footprints put the lot's taller structure at BIN 1012154
    (122.6 ft, the-west-coast in the registry) and the shorter at BIN 1012155
    (91.9 ft, 97-horatio-street-new_york). Floor-and-letter labels run to floor
    10 and three-digit labels stop at floor 7, so the floor-and-letter scheme
    belongs to the taller structure."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    lot = frame.building.isin(WESTCOAST).to_numpy()
    letter = (label.str.fullmatch(r"\d+[a-z]+") | label.str.startswith("ph")).to_numpy(
        dtype=bool, na_value=False
    )
    three = label.str.fullmatch(r"\d{3}").to_numpy(dtype=bool, na_value=False)
    building = np.where(
        lot & letter, WESTCOAST[0], np.where(lot & three, WESTCOAST[1], frame.building)
    )
    return frame.assign(building=building)


def building_joins_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """StreetEasy's 97-horatio-street-new_york page folded into
    the-west-coast. The West Coast is one complex on lot 1006430001, and 97
    Horatio Street is another of its addresses. BIN 1012155, the registry's
    match for the address, is a 6,700 sqft section on the Horatio side inside
    the outline of BIN 1012154 (52,400 sqft). The page holds 8 NB8 rows from
    2015 to 2019 in both label schemes. A `tune-westcoast-split-` rule run
    after this one still splits the lot by label scheme."""
    building = frame.building.where(frame.building.ne(WESTCOAST[1]), WESTCOAST[0])
    return frame.assign(building=building)


WESTCOAST_WEST_WING = "the-west-coast-west-wing"


def west_coast_wings_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """The West Coast's rows with three-digit labels ("425", "620") moved to
    the-west-coast-west-wing. The complex is nine warehouses joined into
    apartments in 1980 to 1982, and its units carry two numbering schemes:
    three digits on floors 1 to 7 at the West Street end, a floor and a letter
    ("9L", "PHD") on floors 2 to 10 toward Washington Street. Rows with a
    floor and a letter, or other labels ("7", "26"), stay on the-west-coast.
    The lot registry gives both names lot 1006430001, BIN 1012154 and the
    same position, so the wings differ only in their building and walk terms.
    Run it after `building-joins-v1`, which folds 97 Horatio Street's page in,
    and before the unit rules, so units merge within a wing."""
    label = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    three = label.str.fullmatch(r"\d{3}").to_numpy(dtype=bool, na_value=False)
    wing = frame.building.eq(WESTCOAST[0]).to_numpy() & three
    return frame.assign(building=np.where(wing, WESTCOAST_WEST_WING, frame.building))


# The elevator each NB9 row's own ad states (`python -m rentfrontier.adfills
# elevator`), for rows whose text says exactly one of "yes" and "no".
ELEVATOR_FROM_AD = Path(
    "/data1/apartments/external/adfills/20261014-62610e9/elevator.parquet"
)


def fill_from_ad(frame: pd.DataFrame, field: str, path: Path) -> pd.DataFrame:
    """`field` filled from the row's own ad text (`path`, built by
    `rentfrontier.adfills`) where its coded value is "unknown". A known code
    stays, and a row the file lacks stays unknown."""
    table = pd.read_parquet(path, columns=["audit_id", field])
    stated = frame.audit_id.map(table.set_index("audit_id")[field])
    fill = frame[field].eq("unknown") & stated.notna()
    return frame.assign(**{field: frame[field].where(~fill, stated)})


def elevator_from_ad_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """An unknown elevator filled from the row's own ad: "no" when the ad says
    walk-up, flights up or no elevator, "yes" when it mentions an elevator
    otherwise (`ELEVATOR_FROM_AD`). An ad saying both, or neither, leaves the
    row unknown. No row reads another listing's ad."""
    return fill_from_ad(frame, "elevator", ELEVATOR_FROM_AD)


# The pet policy each NB9 row's own ad states (`python -m rentfrontier.adfills
# pets`), as a coded level, for rows whose text has a class with one.
PETS_FROM_AD = Path("/data1/apartments/external/adfills/20261014-5298c80/pets.parquet")


def pets_from_ad_v1(frame: pd.DataFrame) -> pd.DataFrame:
    """An unknown pet policy filled from the row's own ad (`PETS_FROM_AD`):
    "not_allowed" for no pets, "approval_required" for case by case and
    "allowed_restrictions_unknown" for pets allowed, read by
    `petstext.classify`. An ad saying no dogs, which has no coded level, or
    saying nothing, leaves the row unknown. No row reads another listing's ad."""
    return fill_from_ad(frame, "pets", PETS_FROM_AD)


# The price a fit models. A row starts at its listing's first ask; a rule of a
# family below replaces that price. Two fits on different prices score their
# rows on different outcomes, so their paired PSIS-LOO and held-out sums mean
# nothing (rentfrontier.autoselect does not pair them).
FIRST_ASK = "first ask"
PRICE_TARGETS = {
    "latest-ask": "latest ask",
    "tune-latestask": "latest ask",
    "tune-finalask": "final ask",
}


def rule_family(name: str) -> str:
    """A rule's family: its name without the version ("quarantine-v12" ->
    "quarantine") or an amendment's suffix."""
    m = re.fullmatch(r"(.+)-v\d+(@.*)?", name)
    return m.group(1) if m else name


def price_target(rules) -> str:
    """The price a fit on these rules models: `FIRST_ASK`, or the target of
    its repricing rule (`PRICE_TARGETS`)."""
    targets = {PRICE_TARGETS.get(rule_family(r)) for r in rules} - {None}
    if len(targets) > 1:
        raise ValueError(f"rules reprice rows two ways: {sorted(rules)}")
    return targets.pop() if targets else FIRST_ASK


DATA_RULES = {
    "tune-b35-v1": tune_b35_v1,
    "tune-holdout-lots-v1": drop_holdout_lots,
    "tune-finalask-v1": final_ask_v1,
    "tune-latestask-v1": latest_ask_v1,
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
    # unit-labels-v14 on the tables with East Village's appended too
    # (UNIT_ALIASES_EV, UNIT_HISTORY_PAIRS_EV).
    "unit-labels-v15": functools.partial(
        merge_word_letter_labels,
        base=functools.partial(
            merge_swapped_labels,
            base=functools.partial(
                merge_history_pairs,
                pairs=UNIT_HISTORY_PAIRS_EV,
                aliases=UNIT_ALIASES_EV,
            ),
        ),
    ),
    # unit-labels-v15 with labels spelled out joined to their short spelling
    # (#420's joins, where both units' median bedrooms agree).
    "unit-labels-v16": functools.partial(
        merge_spelled_labels,
        base=functools.partial(
            merge_word_letter_labels,
            base=functools.partial(
                merge_swapped_labels,
                base=functools.partial(
                    merge_history_pairs,
                    pairs=UNIT_HISTORY_PAIRS_EV,
                    aliases=UNIT_ALIASES_EV,
                ),
            ),
        ),
    ),
    # unit-labels-v16 on the tables with Midtown West's appended too
    # (UNIT_ALIASES_MW, UNIT_HISTORY_PAIRS_MW).
    "unit-labels-v17": functools.partial(
        merge_spelled_labels,
        base=functools.partial(
            merge_word_letter_labels,
            base=functools.partial(
                merge_swapped_labels,
                base=functools.partial(
                    merge_history_pairs,
                    pairs=UNIT_HISTORY_PAIRS_MW,
                    aliases=UNIT_ALIASES_MW,
                ),
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
    "bedrooms-ad-v4": correct_bedrooms_v4,
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
    "quarantine-v12": quarantine_v12,
    "quarantine-v13": quarantine_v13,
    "quarantine-v14": quarantine_v14,
    "quarantine-v15": quarantine_v15,
    "quarantine-v16": quarantine_v16,
    "quarantine-v17": quarantine_v17,
    "quarantine-v18": quarantine_v18,
    "quarantine-v19": quarantine_v19,
    "quarantine-v20": quarantine_v20,
    "quarantine-v21": quarantine_v21,
    "quarantine-v22": quarantine_v22,
    "latest-ask-v2": latest_ask_v2,
    "latest-ask-v3": latest_ask_v3,
    "latest-ask-v4": functools.partial(latest_ask_v3, path=LATEST_ASK_V4),
    "tune-westcoast-split-v1": tune_westcoast_split_v1,
    "tune-westcoast-split-v2": tune_westcoast_split_v2,
    "building-joins-v1": building_joins_v1,
    "west-coast-wings-v1": west_coast_wings_v1,
    "elevator-from-ad-v1": elevator_from_ad_v1,
    "pets-from-ad-v1": pets_from_ad_v1,
    "unit-reviews-v1": join_reviewed_units,
    "unit-reviews-v2": review_units,
    # The rule as fit before its amendment, for runs that recorded the first list.
    "unit-reviews-v1@20261007": functools.partial(
        join_reviewed_units, path=UNIT_JOINS_20261007
    ),
}
# Rules that read a file; run records hash the files.
RULE_SOURCES = {
    "tune-holdout-lots-v1": HOLDOUT_LOTS_V1,
    "tune-finalask-v1": Path(
        "/data1/apartments/external/listing-outcomes/20261008-afb3446/"
        "listing-outcomes.parquet"
    ),
    "tune-latestask-v1": LATEST_ASK_OUTCOMES,
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
    "quarantine-v12": QUARANTINE_V12,
    "quarantine-v13": QUARANTINE_V13,
    "quarantine-v14": QUARANTINE_V14,
    "quarantine-v15": QUARANTINE_V15,
    "quarantine-v16": QUARANTINE_V16,
    "quarantine-v17": QUARANTINE_V17,
    "quarantine-v18": QUARANTINE_V18,
    "quarantine-v19": QUARANTINE_V19,
    "quarantine-v20": QUARANTINE_V20,
    "quarantine-v21": QUARANTINE_V21,
    "quarantine-v22": QUARANTINE_V22,
    "latest-ask-v2": LATEST_ASK,
    "latest-ask-v3": LATEST_ASK_V3,
    "latest-ask-v4": LATEST_ASK_V4,
    "elevator-from-ad-v1": ELEVATOR_FROM_AD,
    "pets-from-ad-v1": PETS_FROM_AD,
    "unit-reviews-v1": UNIT_JOINS,
    "unit-reviews-v2": UNIT_REVIEWS,
    "unit-reviews-v1@20261007": UNIT_JOINS_20261007,
    "unit-labels-v2": UNIT_ALIASES,
    "unit-labels-v3": UNIT_ALIASES,
    "unit-labels-v5": UNIT_ALIASES_GV,
    "unit-labels-v6": UNIT_HISTORY_PAIRS,
    "unit-labels-v8": UNIT_HISTORY_PAIRS,
    "unit-labels-v9": UNIT_HISTORY_PAIRS,
    "unit-labels-v11": UNIT_ALIASES_FGP,
    "unit-labels-v13": UNIT_ALIASES_STUY,
    "unit-labels-v14": UNIT_ALIASES_NOMAD,
    "unit-labels-v15": UNIT_ALIASES_EV,
    "unit-labels-v16": UNIT_ALIASES_EV,
    "unit-labels-v17": UNIT_ALIASES_MW,
    "bedrooms-ad-v1": BEDROOM_CORRECTIONS,
    "baths-ad-v1": BATH_CORRECTIONS,
    "bedrooms-ad-v2": BEDROOM_CORRECTIONS_V2,
    "baths-ad-v2": BATH_CORRECTIONS_V2,
    "bedrooms-ad-v3": BEDROOM_CORRECTIONS_V3,
    "bedrooms-ad-v4": BEDROOM_CORRECTIONS_V4,
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
    "quarantine-v12",
    "quarantine-v13",
    "quarantine-v14",
    "quarantine-v15",
    "quarantine-v16",
    "quarantine-v17",
    "quarantine-v18",
    "quarantine-v19",
    "quarantine-v20",
    "quarantine-v21",
    "quarantine-v22",
)


def dropped_rows() -> frozenset:
    """Audit ids some data rule drops: the only rows two runs' scores may
    differ by (cleaning is scored on the rows both keep)."""
    return frozenset().union(*(quarantined(RULE_SOURCES[r]) for r in DROPPING_RULES))


# Rules whose file Ben chose to amend in place rather than version: the rule and
# the hash of the file before the amendment, mapped to the rule that applies that
# file. A run that recorded the old hash rebuilds its own rows under the old rule;
# it still carries, and is compared under, the rule's name.
RULE_AMENDMENTS = {
    (
        "unit-reviews-v1",
        "a3f9630b57bd52019c7e0b5a190f835bf107a9da304f916659f5df2dd0bb66c2",
    ): "unit-reviews-v1@20261007",
}


def amended_rule(name: str) -> bool:
    """Whether a DATA_RULES name is a rule as it stood before an in-place
    amendment (`RULE_AMENDMENTS`): never chosen for a new run or listed as a rule."""
    return "@" in name


def recorded_rules(result: dict) -> tuple:
    """A run record's data rules, refused if a rule is unknown or its file
    differs now from the hash the run recorded (the rows would not be the
    run's rows). A rule amended in place since the run (`RULE_AMENDMENTS`) comes
    back as the rule that applies the file the run recorded."""
    rules = []
    for rule in result.get("data_rules", ()):
        if rule not in DATA_RULES or amended_rule(rule):
            raise SystemExit(f"unknown data rule {rule} in the run's record")
        if rule in RULE_SOURCES:
            src = result.get("data_rule_sources", {}).get(rule)
            if src is None:
                raise SystemExit(f"the run records no hash for data rule {rule}'s file")
            rule = RULE_AMENDMENTS.get((rule, src["sha256"]), rule)
            if sha256(RULE_SOURCES[rule]) != src["sha256"]:
                raise SystemExit(
                    f"data rule {rule}'s file differs from the run's record"
                )
        rules.append(rule)
    return tuple(rules)


def rows_sha256(frame: pd.DataFrame, heldout) -> str:
    """A hash of a run's rows after its split and data rules: the column names,
    every value in order, and the held-out mask, recorded with each run."""
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
    joins = [i for i, r in enumerate(rules) if r.startswith("building-joins-")]
    wings = [
        i
        for i, r in enumerate(rules)
        if r.startswith(("tune-westcoast-split-", "west-coast-wings-"))
    ]
    if joins and wings and max(joins) > min(wings):
        raise ValueError(
            f"building-joins rules must precede the West Coast wing rules: {rules}"
        )
    split = [i for i, r in enumerate(rules) if r.startswith("west-coast-wings-")]
    if split and labels and max(split) > min(labels):
        raise ValueError(f"west-coast-wings rules must precede unit-labels: {rules}")
    mask = pd.Series(np.asarray(heldout, dtype=bool), index=frame.index)
    for rule in rules:
        frame = DATA_RULES[rule](frame)
    held = mask.loc[frame.index].to_numpy().copy()
    if "building" in frame:
        held &= frame.building.isin(set(frame.building[~held])).to_numpy()
    return frame.reset_index(drop=True), held

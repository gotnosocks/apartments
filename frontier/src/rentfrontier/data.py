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
        # Chelsea + West Village (Ben, 2026-10-01: the full data is the target);
        # Chelsea alone was data/model/chelsea-product-scope-analysis-20260921.
        "/data1/apartments/frontier/datasets/chelsea-west-village-analysis-20261001-eea4f66",
    )
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


@functools.lru_cache(maxsize=2)
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


def merge_unit_aliases(frame: pd.DataFrame) -> pd.DataFrame:
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
    for group in unit_aliases():
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


def merge_word_labels(frame: pd.DataFrame) -> pd.DataFrame:
    """unit-labels-v2, and units labelled with a number word joined to the unit
    of the same building whose label is that number ("four" and "4",
    "third-fl" and "3fl"), where both units' median bedroom counts agree.
    Rows are unchanged."""
    out = merge_unit_aliases(frame)
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


# The West Village alias table under unit-spelling-alias-v2 (PR #213): v1's
# groups, and labels that only name a floor ("2nd-floor", "4fl", "4") or carry an
# apt/unit word, folded together; history-confirmed groups are used.
UNIT_ALIASES_V2 = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "unit-aliases"
    / "west-village-20260930-v2.jsonl"
)


def merge_unit_labels_v4(frame: pd.DataFrame) -> pd.DataFrame:
    """unit-labels-v2; the West Village alias table's v2 history-confirmed groups
    (labels that only name a floor: "4fl", "4th-floor" and "4") where every part's
    median bedroom count agrees; and number-word labels joined to the same
    building's numbered unit when both units' median bedroom counts agree (as
    unit-labels-v3). Every join goes through one union-find, so
    two words that name one numbered unit end as one unit, whose id is the
    smallest. The medians read the bedrooms as the frame has them when this rule
    runs. Rows are unchanged."""
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
    for group in unit_aliases(UNIT_ALIASES):
        for u in group[1:]:
            union(group[0], u)
    # The v2 table's further joins (floor-only labels) only where every part's
    # median bedroom count agrees: they mix bedroom counts far more often (37% of
    # joined units against 14% of West Village units with several listings).
    units = frame.unit_id.map(find)
    medians = frame.bedrooms.groupby(units).median()
    for group in unit_aliases(UNIT_ALIASES_V2):
        roots = {find(u) for u in group if u in parent}
        if len(roots) > 1 and medians.reindex(list(roots)).nunique(dropna=False) == 1:
            first, *rest = sorted(roots)
            for u in rest:
                union(first, u)
    units = frame.unit_id.map(find)
    raw = frame.canonical_unit_url.str.extract(r"/([^/]+)$")[0].str.lower()
    word = raw.str.extract(_WORD_LABEL)[0]
    numbered = (
        word.map(LABEL_WORDS) + raw.str.replace(_WORD_LABEL, "", regex=True)
    ).where(word.notna())
    key = raw.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    word_key = numbered.map(lambda v: unit_label_key(v) if isinstance(v, str) else v)
    beds = frame.bedrooms.groupby(units).transform("median")
    by_label = (
        pd.DataFrame(
            {"building": frame.building, "key": key, "unit": units, "beds": beds}
        )
        .drop_duplicates(["building", "key"])
        .set_index(["building", "key"])
    )
    for i in np.flatnonzero(word_key.notna().to_numpy()):
        twin = (frame.building.iat[i], word_key.iat[i])
        if twin in by_label.index and by_label.loc[twin, "beds"] == beds.iat[i]:
            union(by_label.loc[twin, "unit"], units.iat[i])
    out["unit_id"] = frame.unit_id.map(find)
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


def _correct_baths(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    with open(RULE_SOURCES[rule]) as f:
        rows = {
            r["audit_id"]: r
            for r in (json.loads(line) for line in f if line.strip())
            if "full_baths" in r
        }
    out = frame.copy()
    hit = out.audit_id.isin(rows)
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
    "unit-labels-v4": merge_unit_labels_v4,
    "quarantine-v1": quarantine_v1,
    "quarantine-v2": quarantine_v2,
    "bedrooms-ad-v1": correct_bedrooms_v1,
    "baths-ad-v1": correct_baths_v1,
    "bedrooms-ad-v2": correct_bedrooms_v2,
    "baths-ad-v2": correct_baths_v2,
    "fields-review-v1": correct_fields_review_v1,
    "quarantine-v3": quarantine_v3,
    "quarantine-v4": quarantine_v4,
    "quarantine-v5": quarantine_v5,
}
# Rules that read a file; run records hash the files.
RULE_SOURCES = {
    "quarantine-v1": QUARANTINE_V1,
    "quarantine-v2": QUARANTINE_V2,
    "quarantine-v3": QUARANTINE_V3,
    "quarantine-v4": QUARANTINE_V4,
    "quarantine-v5": QUARANTINE_V5,
    "unit-labels-v2": UNIT_ALIASES,
    "unit-labels-v3": UNIT_ALIASES,
    "unit-labels-v4": UNIT_ALIASES_V2,
    "bedrooms-ad-v1": BEDROOM_CORRECTIONS,
    "baths-ad-v1": BATH_CORRECTIONS,
    "bedrooms-ad-v2": BEDROOM_CORRECTIONS_V2,
    "baths-ad-v2": BATH_CORRECTIONS_V2,
    "fields-review-v1": FIELD_REVIEW,
}
# Of those, the rules that drop the rows their file lists.
DROPPING_RULES = (
    "quarantine-v1",
    "quarantine-v2",
    "quarantine-v3",
    "quarantine-v4",
    "quarantine-v5",
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


def apply_rules(frame: pd.DataFrame, heldout: np.ndarray, rules):
    """(frame, heldout) after the named rules. A rule that drops rows drops them
    from the held-out mask too, so every other row keeps its split; the frame
    gets a fresh RangeIndex."""
    mask = pd.Series(np.asarray(heldout, dtype=bool), index=frame.index)
    for rule in rules:
        frame = DATA_RULES[rule](frame)
    return frame.reset_index(drop=True), mask.loc[frame.index].to_numpy()

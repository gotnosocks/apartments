"""Load the analytical dataset into a flat, typed table.

The source bundle is read-only. The flattened table is cached as parquet under
the output root, keyed by the SHA-256 of observations.jsonl, so a changed
source can never be served from a stale cache.

Row order is the order of observations.jsonl with a default RangeIndex. The
held-out splits depend on that order.
"""

from __future__ import annotations

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
        "/home/ben/code/apartments/data/model/chelsea-product-scope-analysis-20260921",
    )
)
OUTPUT_ROOT = Path(os.environ.get("FRONTIER_OUTPUT_ROOT", "/data1/apartments/frontier"))

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
    }
    for name in VIEWS:
        out[f"view_{name}"] = _tristate(views.get(name))
    for name in WINDOWS:
        out[f"window_{name}"] = _tristate(windows.get(name))
    return out


def load(dataset: Path = DATASET, cache_root: Path = OUTPUT_ROOT) -> pd.DataFrame:
    source = dataset / "observations.jsonl"
    digest = sha256(source)
    cache = cache_root / "cache" / f"observations-{digest[:16]}.parquet"
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


# Named data rules, applied after the held-out split is drawn (the row split
# depends on unit ids, and scored rows must not change). Run records list them.
DATA_RULES = {"unit-labels-v1": merge_unit_labels}


def apply_rules(frame: pd.DataFrame, rules) -> pd.DataFrame:
    for rule in rules:
        frame = DATA_RULES[rule](frame)
    return frame

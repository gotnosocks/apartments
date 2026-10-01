"""A loader-ready analysis cohort for a new neighbourhood (West Village first).

Chelsea's analysis dataset (`chelsea-product-scope-analysis-20260921`) came from
its historical own-advertisement rows through a chain of projections and
Chelsea-specific reviews, each version-gated to the one before. This module
builds the same row shape for another neighbourhood from its own sources, with
the chain's generic rules and none of Chelsea's review decisions:

- **Rows** (as `models.amenity_rent_model.load_analytical`): the month of the
  initial ask, the building, the ask. It excludes invalid identities, asks
  outside $750-50,000, invalid layouts, and furnished, short-term and
  concession offers. It drops unit-months whose rows disagree on the layout,
  keeps the latest initial ask in each other unit-month, and treats square feet
  outside 150-6,000 as unknown.
- **Reported full and half bathrooms** (as `models.bathroom_projection`): the
  value every capture of the advertisement reports, else unknown.
- **The floor** (as `floor_label_projection` and `expanded_floor_projection`):
  - The advertisement's own explicit floor if it has one.
  - Otherwise, a floor its unit label reads as under the same numbering rules
    ("4D", "1205", "N3A", "5RE", "3rd floor"), when every capture agrees.
  - A label floor above the building's own floor count is refused, and so is a
    label of 10 or more when the building has no count. The result is a label
    proxy, not a measured floor.
- **Price basis:** every row is a historical initial own-advertisement ask.

`python -m rentfrontier.cohort <history dir> <granular dir> <output dir>` writes
`observations.jsonl` and `complete.json`. Use the result with
`FRONTIER_DATASET=<output dir>`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "neighbourhood-analysis-cohort-v1"
PRICE_BASIS = "historical_initial_own_advertisement_ask"


def _boolean(value) -> bool:
    return value is True or value == 1 or str(value).lower() in ("true", "yes")


def label_floor(label) -> tuple[str | None, int | None]:
    """The named numbering rule a unit label matches, and the floor it reads."""
    if not isinstance(label, str):
        return None, None
    value = label.strip().removeprefix("#").strip().upper()
    for rule, pattern, read in (
        ("one-or-two-digit-prefix-letter", r"([1-9][0-9]?)[A-Z]", int),
        ("numeric_hundreds", r"([1-9][0-9]{2,3})", lambda s: int(s) // 100),
        ("north_south_wing_prefix", r"[NS]([1-9][0-9]?)[A-Z]", int),
        ("front_rear_suffix", r"([1-9][0-9]?)(?:FE|FW|RE|RW|FR|RR|FF|RF)", int),
        ("explicit_ordinal_label", r"([1-9][0-9]?)(?:ST|ND|RD|TH)(?:FL|FLOOR)", int),
    ):
        m = re.fullmatch(pattern, value)
        if m:
            return rule, read(m.group(1))
    return None, None


def floor_of(row: dict, labels: list, floor_count) -> tuple[int | None, str]:
    """(listed floor, status) for one advertisement."""
    explicit = next(
        (
            v
            for v in (row.get("listed_floor"), row.get("advertised_floor"))
            if v is not None and not (isinstance(v, float) and np.isnan(v))
        ),
        None,
    )
    if explicit is not None:
        return explicit, "explicit_source_floor"
    reads = {label_floor(lab)[1] for lab in labels}
    if len(reads) != 1 or None in reads:
        return None, "unresolved_or_conflicting_capture_labels"
    value = reads.pop()
    if floor_count is not None and value > floor_count:
        return None, "above_captured_building_floor_count"
    if floor_count is None and value >= 10:
        return None, "two_digit_label_without_building_count"
    return value, "label_proxy"


def consensus(values: list):
    """The single valid count every capture reports, else None."""
    ok = [
        v
        for v in values
        if isinstance(v, (int, float))
        and not isinstance(v, bool)
        and v >= 0
        and v == int(v)
    ]
    if not values or len(ok) != len(values) or len(set(ok)) != 1:
        return None
    return int(ok[0])


def captures(granular: Path) -> dict:
    """snapshot_id -> (display unit, full baths, half baths) from the raw listings."""
    out = {}
    table = pd.read_parquet(
        granular / "listing_observations", columns=["snapshot_id", "raw_listing_json"]
    )
    for sid, raw in table.itertuples(index=False):
        details = (json.loads(raw) if raw else {}).get("propertyDetails") or {}
        out[sid] = (
            (details.get("address") or {}).get("displayUnit"),
            details.get("fullBathroomCount"),
            details.get("halfBathroomCount"),
        )
    return out


def floor_counts(granular: Path) -> dict:
    """building slug -> the smallest floor count its observations report."""
    out = {}
    table = pd.read_parquet(
        granular / "building_observations",
        columns=["building_slug", "raw_building_json"],
    )
    for slug, raw in table.itertuples(index=False):
        n = (json.loads(raw) if raw else {}).get("floorCount")
        if isinstance(n, (int, float)) and n > 0:
            out[slug] = min(int(n), out.get(slug, int(n)))
    return out


def analysis_rows(history: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """load_analytical's rows, exclusions and one row per unit-month."""
    data = history.copy()
    data["period"] = (
        pd.to_datetime(data.price_at, utc=True).dt.tz_localize(None).dt.to_period("M")
    ).dt.to_timestamp()
    data["building"] = data.building_id
    data["asking_rent"] = pd.to_numeric(data.rent, errors="coerce")
    data["square_feet"] = pd.to_numeric(data.get("square_feet"), errors="coerce")
    reasons = pd.Series("", index=data.index)

    def exclude(reason, condition):
        reasons.loc[reasons.eq("") & condition.fillna(True)] = reason

    exclude("invalid_identity", data.unit_id.isna() | data.building.isna())
    exclude(
        "invalid_rent",
        ~data.asking_rent.between(750, 50000) | ~np.isfinite(data.asking_rent),
    )
    exclude(
        "invalid_layout",
        ~data.bedrooms.between(0, 5)
        | data.bedrooms.mod(1).ne(0)
        | ~data.bathrooms.between(1, 5)
        | data.bathrooms.mul(2).mod(1).ne(0),
    )
    for flag in ("furnished", "short_term", "concession"):
        if flag in data:
            exclude(flag, data[flag].map(_boolean))
    good = data[reasons.eq("")].copy()
    layouts = good.groupby(["unit_id", "period"])[["bedrooms", "bathrooms"]].nunique()
    conflicts = layouts[(layouts.bedrooms > 1) | (layouts.bathrooms > 1)].index
    mask = pd.MultiIndex.from_frame(good[["unit_id", "period"]]).isin(conflicts)
    good = good[~mask].sort_values(
        ["price_at", "unit_id", "source_listing_id", "audit_id"], kind="stable"
    )
    before = len(good)
    good = (
        good.drop_duplicates(["unit_id", "period"], keep="last")
        .sort_values(["period", "unit_id"])
        .reset_index(drop=True)
    )
    good.loc[~good.square_feet.between(150, 6000), "square_feet"] = np.nan
    coverage = {
        "input_rows": len(data),
        "exclusions": dict(Counter(reasons[reasons.ne("")])),
        "conflicting_unit_month_rows": int(mask.sum()),
        "superseded_unit_month_rows": before - len(good),
        "rows": len(good),
        "units": int(good.unit_id.nunique()),
        "buildings": int(good.building.nunique()),
    }
    return good, coverage


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(history_dir: Path, granular: Path, output: Path) -> dict:
    manifest = json.loads((history_dir / "complete.json").read_text())
    if manifest.get("dataset_version") != "historical-own-advertisement-v1":
        raise SystemExit(f"{history_dir} is not a historical own-advertisement dataset")
    source = history_dir / "observations.jsonl"
    if manifest["files"]["observations.jsonl"] != _sha(source):
        raise SystemExit("the history's observations differ from its manifest")
    with open(source) as f:
        history = pd.DataFrame(json.loads(line) for line in f if line.strip())
    rows, coverage = analysis_rows(history)
    caps, counts = captures(granular), floor_counts(granular)
    status, missing = Counter(), 0
    out = []
    for r in rows.to_dict("records"):
        found = [caps[c] for c in r["capture_ids"] if c in caps]
        missing += len(found) != len(r["capture_ids"])
        floor, why = floor_of(r, [f[0] for f in found], counts.get(r["building"]))
        status[why] += 1
        row = {
            k: (None if isinstance(v, float) and np.isnan(v) else v)
            for k, v in r.items()
        }
        row.update(
            period=r["period"].strftime("%Y-%m-%d"),
            analysis_price_basis=PRICE_BASIS,
            reported_full_bathrooms=consensus([f[1] for f in found]),
            reported_half_bathrooms=consensus([f[2] for f in found]),
            listed_floor=floor,
            label_derived_floor=floor if why == "label_proxy" else None,
            floor_label_provenance={
                "status": why,
                "building_floor_count": counts.get(r["building"]),
            },
        )
        row.pop("raw_listing_json", None)
        out.append(row)
    if missing:
        raise SystemExit(f"{missing} rows have captures the granular transform lacks")
    output.mkdir(parents=True, exist_ok=False)
    path = output / "observations.jsonl"
    with open(path, "w") as f:
        for row in out:
            f.write(json.dumps(row, default=str) + "\n")
    complete = {
        "version": VERSION,
        "built_at": dt.datetime.now(dt.UTC).isoformat(),
        "history": {
            "path": str(history_dir),
            "complete_sha256": _sha(history_dir / "complete.json"),
        },
        "granular": {
            "path": str(granular),
            "complete_sha256": _sha(granular / "complete.json"),
        },
        "coverage": coverage,
        "floor_status": dict(status),
        "price_basis": PRICE_BASIS,
        "reviews": "none: no review decision of any neighbourhood is applied",
        "files": {"observations.jsonl": _sha(path)},
    }
    (output / "complete.json").write_text(json.dumps(complete, indent=2) + "\n")
    return complete


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("history", type=Path)
    parser.add_argument("granular", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.history, args.granular, args.output), indent=2))


if __name__ == "__main__":
    main()

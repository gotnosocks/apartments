"""Rank current listings by a renter's preference sheet (Ben, 2026-10-06).

A sheet (`/data1/apartments/preferences/<profile>.json`) marks model features
+1 (a pro), -1 (a con) or 0, all else equal; they are not filters. Nothing is
refit: the served model already prices each feature, so a feature's size is
its coefficient and the sheet gives only its sign.

    score = sum over marked features f of  weight_f * |beta_f| * input_f
          + 1/2 * log(1 + building level) + 1/2 * log(1 + building trend a year)

with beta_f = log(1 + pct_f / 100) the posterior mean from the build's
`coefficients` table and input_f the listing's own model input (a continuous
input keeps its sign: a unit smaller than usual for its bedrooms scores
negative on a "more space" pro). The building's level and trend are what the
model learned about the building beyond its features; the sheet weighs them
(`latent`). The score is in log points, shown as exp(score) - 1: what the
listing's features, counted the renter's way, are worth as a share of rent.

Sorts: "deal" (score - log(ask / estimate), the default: fit at a good
price for what it is), "fit" (score alone) and "value" (score - log ask: fit
for the money). Log asks spread about six times wider than scores, so
"value" is close to cheapest first unless bedrooms or a budget narrow the
list (Modeling, 2026-10-06); it is not the default. Point values only for now; intervals can follow if wanted.

Commute (Data improvements' `rentfrontier.commute`, #353): weekday-morning
subway minutes from each building to the destinations in
`config/commute-destinations.json`, read at runtime from the newest
`commute-*.csv` in the wishes folder. A sheet may name the destinations it
wants (`"commute": ["office"]`; all of them otherwise). A trip at or under the
median for the buildings, with no transfer, shows as a plus, otherwise a
minus. It is shown, not counted: the model has no price for it, so it leaves
the score alone.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
from pathlib import Path

DIR = Path(os.environ.get("PREFERENCES_DIR", "/data1/apartments/preferences"))
WISHES = Path(os.environ.get("WISHES_DIR", "/data1/apartments/wishes"))
DEFAULT_PROFILE = "ben-v1"
PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SORTS = {
    "deal": "Fits you, at a good price",
    "fit": "Fits you",
    "value": "Best for the money",
}
DEFAULT_SORT = "deal"
LATENT = {"level": "building level", "trend": "building trend"}

# Features read together, so a floor is one pro rather than three.
COMBINED = {
    "log_floor": "floor",
    "log_floor_above_6": "floor",
    "log_floor_above_15": "floor",
}
LABELS = {
    "bathrooms=half=1": "a half bath",
    "bathrooms=half=2+": "two or more half baths",
    "rooms beyond bedrooms=0-1": "few rooms beyond the bedrooms",
    "rooms beyond bedrooms=3": "extra rooms",
    "rooms beyond bedrooms=4+": "many extra rooms",
    "text:states_fewer_bedrooms": "the ad gives fewer bedrooms",
    "log_floor_x_no_elevator": "stairs to climb (no elevator)",
    "label:penthouse": "a penthouse",
    "label:lower_level": "a lower-level unit",
    "label:garden": "a garden unit",
    "looks onto an avenue, floors 1-4": "a low floor on an avenue",
    "looks onto a wide street, floors 1-4": "a low floor on a wide street",
    "looks onto the rear or a courtyard": "looks onto the rear or a courtyard",
    "looks onto a side street": "looks onto a side street",
    "text:private_outdoor": "private outdoor space (ad)",
    "outdoor:terrace": "a terrace",
    "outdoor:patio": "a patio",
    "outdoor:balcony": "a balcony",
    "outdoor:garden": "a garden",
    "outdoor:roof_deck": "a roof deck",
    "text:outdoor_shared": "shared outdoor space (ad)",
    "laundry=in_unit": "in-unit laundry",
    "text:washer_dryer_in_unit": "a washer-dryer (ad)",
    "text:dishwasher": "a dishwasher (ad)",
    "text:renovated": "renovated (ad)",
    "elevator=no": "no elevator",
    "doorman=full_time": "a full-time doorman",
    "doorman=part_time": "a part-time doorman",
    "doorman=virtual": "a virtual doorman",
    "doorman=none": "no doorman",
    "text:gym": "a gym (ad)",
    "building class=C": "a walk-up building (tax records)",
    "text:concession": "free months or a concession (ad)",
    "text:no_fee": "no broker fee (ad)",
    "text:rent_stabilized": "rent stabilized (ad)",
    "text:short_term": "a short-term lease (ad)",
}
# The model input that says a detail is not stated, the details it hides,
# and the words for it.
UNKNOWN = [
    ("sqft_unknown", ("log_sqft_vs_bedroom_median",), "size"),
    ("floor_unknown", tuple(COMBINED), "floor"),
    ("elevator=unknown", ("elevator=no", "log_floor_x_no_elevator"), "elevator"),
    ("laundry=unknown", ("laundry=in_unit",), "laundry"),
    ("doorman=unspecified", ("doorman=",), "doorman"),
    ("bathrooms=half=unknown", ("bathrooms=half=",), "half baths"),
    ("rooms beyond bedrooms=unknown", ("rooms beyond bedrooms=",), "room count"),
    ("description_missing", ("text:",), "the ad's text"),
]
FACING = "looks onto "


def profile_path(name: str) -> Path | None:
    if not PROFILE_NAME.fullmatch(name or ""):
        return None
    return DIR / f"{name}.json"


def load_profile(path: Path) -> dict:
    """The sheet's numeric weights (zeros dropped), its latent weights and
    its notes; raises OSError or ValueError on a missing or bad file."""
    raw = json.loads(path.read_text())
    weights = {
        str(k): float(v)
        for k, v in (raw.get("weights") or {}).items()
        if isinstance(v, (int, float)) and v
    }
    latent, unmodelled = {}, []
    for key, v in (raw.get("latent") or {}).items():
        kind = next((k for k, words in LATENT.items() if words in key), None)
        if kind and isinstance(v, (int, float)):
            latent[kind] = float(v)
        else:
            unmodelled.append(f"{key}: {v}" if isinstance(v, str) else key)
    return {
        "profile": raw.get("profile") or path.stem,
        "description": raw.get("description"),
        "filters": raw.get("filters") or [],
        "weights": weights,
        "latent": latent,
        "unmodelled": unmodelled,
        "neutral": raw.get("neutral_on_purpose") or [],
        "left_out": raw.get("taste_left_out") or [],
        "commute": [str(d) for d in raw["commute"]]
        if isinstance(raw.get("commute"), list)
        else None,
    }


def commute_path() -> Path | None:
    """The newest commute table, or None."""
    files = sorted(WISHES.glob("commute-*.csv"))
    return files[-1] if files else None


def load_commute(path: Path | None) -> dict:
    """{destination: {address, median, buildings: {building: trip}}}; empty
    without a readable table."""
    if path is None:
        return {}
    try:
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
    except (OSError, ValueError, csv.Error):
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        try:
            trip = {
                "minutes": float(r["minutes"]),
                "transfers": int(float(r["transfers"] or 0)),
                "station": r.get("station") or None,
                "walk": float(r["walk_to_station_min"])
                if r.get("walk_to_station_min")
                else None,
            }
        except (KeyError, ValueError):
            continue
        d = out.setdefault(
            r["destination"], {"address": r.get("address"), "buildings": {}}
        )
        d["buildings"][r["building"]] = trip
    for d in out.values():
        d["median"] = statistics.median(t["minutes"] for t in d["buildings"].values())
    return out


def commute_tags(building_id, commute: dict, wanted=None) -> list[dict]:
    """A plus or minus per destination for one building: at or under the
    median with no transfer is a plus."""
    tags = []
    for name, d in commute.items():
        if wanted is not None and name not in wanted:
            continue
        trip = d["buildings"].get(building_id)
        if trip is None:
            continue
        n = trip["transfers"]
        words = f"{name}: {trip['minutes']:.0f} min by subway" + (
            f", {n} transfer{'s' if n > 1 else ''}" if n else ""
        )
        how = []
        if trip["station"]:
            how.append(
                f"from {trip['station']}"
                + (f", {trip['walk']:.0f} min walk" if trip["walk"] is not None else "")
            )
        how.append(f"median {d['median']:.0f} min")
        tags.append(
            {
                "destination": name,
                "label": words,
                "title": f"{d['address']}; " + "; ".join(how)
                if d["address"]
                else "; ".join(how),
                "good": trip["minutes"] <= d["median"] and not n,
                **trip,
            }
        )
    return tags


def label(feature: str) -> str:
    return LABELS.get(feature, feature.replace("_", " ").replace("text:", ""))


def _floor_words(floor) -> str:
    if floor is None:
        return "a higher floor"
    n = int(floor)
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"the {n}{suffix} floor"


def _hides(prefixes: tuple[str, ...], weights: dict) -> bool:
    return any(
        f == p or (p.endswith(("=", ":")) and f.startswith(p))
        for f in weights
        for p in prefixes
    )


def score(row, inputs: dict, building, profile: dict, betas: dict) -> dict:
    """One listing's score and its signed terms: pros (> 0), cons (< 0),
    largest first, and the marked details it doesn't state."""
    weights = profile["weights"]
    terms: dict[str, float] = {}
    for f, w in weights.items():
        x = inputs.get(f)
        if not x or f not in betas:
            continue
        key = COMBINED.get(f, f)
        terms[key] = terms.get(key, 0.0) + w * abs(betas[f]) * x
    named = []
    for key, points in terms.items():
        if not points:
            continue
        if key == "floor":
            words = _floor_words(row["floor"])
        elif key == "log_sqft_vs_bedroom_median":
            words = (
                "more space than usual for its bedrooms"
                if inputs[key] > 0
                else "less space than usual for its bedrooms"
            )
        else:
            words = label(key)
        named.append({"feature": key, "label": words, "points": points})
    for kind, w in profile["latent"].items():
        pct = building[f"{kind}_pct"] if building is not None else None
        if pct is None or not w:
            continue
        points = w * math.log1p(pct / 100)
        up = points > 0 if w > 0 else points < 0
        if kind == "level":
            words = (
                "a building that rents above similar ones"
                if up
                else "a building that rents below similar ones"
            )
        else:
            words = (
                "a building whose rents rise faster than the area's"
                if up
                else "a building whose rents rise slower than the area's"
            )
        named.append({"feature": f"building {kind}", "label": words, "points": points})
    named.sort(key=lambda t: -abs(t["points"]))
    unknown = [
        words
        for flag, prefixes, words in UNKNOWN
        if inputs.get(flag) and _hides(prefixes, weights)
    ]
    if not any(k.startswith(FACING) for k in inputs) and any(
        f.startswith(FACING) for f in weights
    ):
        unknown.append("which way it faces")
    total = sum(t["points"] for t in named)
    return {
        "score": total,
        "pros": [t for t in named if t["points"] > 0],
        "cons": [t for t in named if t["points"] < 0],
        "unknown": unknown,
    }


def rank(db, profile: dict, commute: dict | None = None) -> dict:
    """Every current listing, scored: {rows, not_modelled, everywhere}.
    `everywhere` lists the unknown details every listing shares (said once
    on the page rather than on every row)."""
    betas = {
        f: math.log1p(pct / 100)
        for f, pct in db.execute("SELECT feature, pct FROM coefficients")
        if pct is not None
    }
    not_modelled = [f for f in profile["weights"] if f not in betas]
    buildings = {
        b["id"]: b
        for b in db.execute(
            "SELECT b.id, b.name, b.address, b.latitude, b.longitude, b.level_pct, "
            "b.trend_pct FROM buildings b "
            "WHERE b.id IN (SELECT building_id FROM listings WHERE is_current = 1)"
        )
    }
    rows = []
    for r in db.execute(
        "SELECT audit_id, building_id, unit_label, neighbourhood, bedrooms, ask, "
        "estimate, floor, reliable, listing_url, inputs FROM listings WHERE is_current = 1 AND ask > 0"
    ):
        inputs = json.loads(r["inputs"])
        s = score(r, inputs, buildings.get(r["building_id"]), profile, betas)
        b = buildings.get(r["building_id"])
        s.update(
            audit_id=r["audit_id"],
            building=(b["name"] or b["address"]) if b else r["building_id"],
            unit=r["unit_label"],
            neighbourhood=r["neighbourhood"],
            bedrooms=r["bedrooms"],
            ask=r["ask"],
            estimate=r["estimate"],
            reliable=r["reliable"],
            listing_url=r["listing_url"],
            building_id=r["building_id"],
            latitude=b["latitude"] if b else None,
            longitude=b["longitude"] if b else None,
            address=b["address"] if b else None,
            commute=commute_tags(
                r["building_id"], commute or {}, profile.get("commute")
            ),
            income_restricted=bool(inputs.get("text:income_restricted")),
            fit_pct=100 * math.expm1(s["score"]),
            vs_estimate=r["ask"] / r["estimate"] - 1 if r["estimate"] else None,
            value=s["score"] - math.log(r["ask"]),
            deal=s["score"] - math.log(r["ask"] / r["estimate"])
            if r["estimate"]
            else -math.inf,  # no estimate: last on this sort
        )
        rows.append(s)
    everywhere = set.intersection(*(set(r["unknown"]) for r in rows)) if rows else set()
    for r in rows:
        r["unknown"] = [u for u in r["unknown"] if u not in everywhere]
    return {
        "rows": rows,
        "not_modelled": not_modelled,
        "everywhere": [u for _, _, u in UNKNOWN if u in everywhere]
        + (["which way it faces"] if "which way it faces" in everywhere else []),
    }


def choose(
    rows: list[dict], *, beds=None, max_rent=None, income=False, sort=DEFAULT_SORT
):
    """The rows the hard filters keep, best first."""
    keep = []
    for r in rows:
        if r["income_restricted"] and not income:
            continue
        if max_rent and r["ask"] > max_rent:
            continue
        if beds is not None:
            b = r["bedrooms"]
            if b is None or (beds >= 3 and b < 3) or (beds < 3 and b != beds):
                continue
        keep.append(r)
    key = sort if sort in SORTS else DEFAULT_SORT
    field = {"fit": "score"}.get(key, key)
    keep.sort(key=lambda r: -r[field])
    return keep

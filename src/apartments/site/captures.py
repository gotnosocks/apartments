"""Current listings captured after the served fit's dataset was made.

The served fit prices the current listings in its own dataset. A later
current-listings capture (Greenwich Village's of 2026-10-06) is not in that
dataset, so its listings are priced here with the run's prediction kit, the
same scoring the estimate form uses: a new apartment in its building, with the
unit's level drawn from the unit prior. Until a fit includes them, these rows
are marked `method = "kit"` and say so on their pages.

A capture's listing gets its model inputs from three places:

- the advertisement itself (bedrooms, baths, size, floor, laundry, views,
  windows), through the estimate form's encoder;
- the unit's label, for the floor when the ad states none and the building
  has that many floors (as `rentfrontier.features.row_floor` reads it);
- the unit's newest earlier listing on the site, for what the dataset keeps
  per unit (which way it faces; the size when the ad states none) and for
  the time since that listing;
- the building's newest listing, for the building's own terms.

The description is not read at capture, as for every current listing, so
rooms beyond the bedrooms and outdoor space are unknown or absent, as there.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import re
import statistics
from pathlib import Path

from . import estimate, estimate_build

# Groups the dataset keeps per unit, taken from the unit's newest earlier listing.
UNIT_GROUPS = ("facing",)
LETTERED = re.compile(r"^(?:APT-?)?(\d{1,2})[A-Z]{1,2}$")
NUMBERED = re.compile(r"^(\d)\d\d$")
METHOD = "kit"


def captures(archives: Path, known: set[str]) -> list[tuple[str, dict]]:
    """(capture directory name, candidate) for every ACTIVE listing of a
    capture whose audit id is not already a site listing; newest capture wins
    per listing."""
    out: dict[str, tuple[str, dict]] = {}
    for d in sorted(p for p in archives.iterdir() if p.is_dir()):
        path = d / "details" / "snapshot" / "candidates.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            c = json.loads(line)
            if c.get("listing_status") != "ACTIVE" or not c.get("rent"):
                continue
            if f"capture:{c['capture_id']}" in known:
                continue
            out[str(c["source_listing_id"])] = (d.name, c)
    # A listing in the fit's own current rows is priced there.
    return [v for k, v in out.items() if k not in known]


def label_floor(url: str | None, height: int | None) -> int | None:
    """The floor a unit label states ("23C" -> 23, "307" -> 3), if the
    building has that many floors, give or take 2."""
    label = (url or "").rsplit("/", 1)[-1].upper()
    m = LETTERED.match(label) or NUMBERED.match(label)
    if m is None or height is None:
        return None
    floor = int(m.group(1))
    return floor if 1 <= floor <= height + 2 else None


def form(c: dict, height: int | None = None) -> estimate.Form:
    """The estimate form the advertisement's own fields fill in."""
    baths = next(
        (
            e["literal"]
            for e in (c.get("attribute_evidence") or {}).get("evidence", [])
            if e.get("attribute") == "bathrooms" and isinstance(e.get("literal"), dict)
        ),
        {},
    )
    return estimate_build.form_from_observation(
        {
            "canonical_unit_url": c.get("canonical_unit_url"),
            "bedrooms": c.get("bedrooms"),
            "reported_full_bathrooms": baths.get(
                "fullBathroomCount", c.get("bathrooms")
            ),
            "reported_half_bathrooms": baths.get("halfBathroomCount"),
            "square_feet": c.get("square_feet"),
            "listed_floor": c.get("physical_floor")
            or c.get("advertised_floor")
            or label_floor(c.get("canonical_unit_url"), height),
            "laundry_type": c.get("laundry_type"),
            "view_exposures": c.get("view_exposures"),
            "window_exposures": c.get("window_exposures"),
        }
    )


def relisting_centre(listings: list[dict]) -> float | None:
    """The fit's centring of log months since the last listing, recovered
    from rows that have one: value = log1p(days / 30.4) - centre."""
    by_unit: dict[str, list[dict]] = {}
    for r in listings:
        by_unit.setdefault(r["unit_id"], []).append(r)
    centres = []
    for rows in by_unit.values():
        rows.sort(key=lambda r: r["price_at"] or r["period"])
        for prev, r in zip(rows, rows[1:]):
            x = json.loads(r["inputs"])
            if "log_months_since_last_listing" not in x:
                continue
            days = (_time(r) - _time(prev)).total_seconds() / 86400
            centres.append(math.log1p(days / 30.4) - x["log_months_since_last_listing"])
            if len(centres) >= 200:
                return statistics.median(centres)
    return statistics.median(centres) if centres else None


def _time(r: dict) -> dt.datetime:
    text = r.get("price_at") or r.get("collected_at") or r["period"]
    t = dt.datetime.fromisoformat(text)
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def encode(
    kit: estimate.Kit,
    c: dict,
    building_inputs: dict[str, float],
    prev: dict | None,
    centre: float | None,
    height: int | None = None,
) -> dict[str, float]:
    """The model inputs of a captured listing (see the module docstring)."""
    f = form(c, height)
    x = estimate.encode(f, kit, building_inputs)
    group_of = dict(zip(kit.features, kit.groups))
    if prev is not None:
        p = json.loads(prev["inputs"])
        groups = list(UNIT_GROUPS)
        if f.square_feet is None and "log_sqft_vs_bedroom_median" in p:
            groups.append("size")
        for g in groups:
            for name in [n for n in x if group_of.get(n) == g]:
                del x[name]
            x.update({n: v for n, v in p.items() if group_of.get(n) == g})
        if centre is not None and kit.has("log_months_since_last_listing"):
            x.pop("first_listing_of_unit", None)
            days = (_time(c) - _time(prev)).total_seconds() / 86400
            x["log_months_since_last_listing"] = (
                math.log1p(max(days, 0) / 30.4) - centre
            )
    if kit.has("rooms beyond bedrooms=unknown"):
        for name in [n for n in x if group_of.get(n) == "rooms beyond bedrooms"]:
            del x[name]
        x["rooms beyond bedrooms=unknown"] = 1.0
    if kit.has("description_missing"):
        x["description_missing"] = 1.0
    return x


def _logmean(a: float, b: float) -> float:
    return a if abs(a - b) < 1e-9 * max(a, b) else (a - b) / (math.log(a) - math.log(b))


def contributions(
    kit: estimate.Kit,
    building: estimate.Building,
    x: dict[str, float],
    bedrooms: int,
    day,
    seed: str,
    names: list[str],
) -> list[dict]:
    """Dollar contributions of the kit estimate against the market reference,
    as `rentfrontier.summary` gives them: per draw, the log-mean (LMDI)
    weight times each term's log, with the unit level's expected factor as
    "unit"; means and 95% intervals over draws."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    group_of = dict(zip(kit.features, kit.groups))
    group = min(max(bedrooms, 0), 3)
    centered = min(max(bedrooms, 0), 4) - 1.0
    frac = estimate.year_fraction(day)
    slopes = [x.get(n, 0.0) for n in kit.slopes]
    per: dict[str, list[float]] = {n: [] for n in names}
    for s in range(len(kit.market)):
        logs = dict.fromkeys(names, 0.0)
        for n, v in x.items():
            j = kit.index.get(n)
            if j is not None and group_of[n] in logs:
                logs[group_of[n]] += kit.beta[s][j] * v
        logs["bedroom_market_curve"] = kit.bedroom_time[s][group]
        logs["building"] = building.level[s]
        logs["building_bedroom_premium"] = building.bedroom_slope[s] * centered
        logs["building_feature_slopes"] = sum(
            f * v for f, v in zip(building.fslope[s], slopes)
        )
        scale = kit.unit_scale[s]
        levels = [
            scale
            * max(
                -estimate.UNIT_CLIP,
                min(
                    estimate.UNIT_CLIP,
                    estimate._student_t(rng, kit.unit_nu[s])
                    if kit.t_units
                    else rng.gauss(0.0, 1.0),
                ),
            )
            for _ in range(estimate.SAMPLES_PER_DRAW)
        ]
        logs["unit"] = math.log(sum(math.exp(v) for v in levels) / len(levels))
        reference = math.exp(kit.market[s] + estimate._season(kit, s, frac, day.month))
        total = reference * math.exp(sum(v for k, v in logs.items() if k != "market"))
        weight = _logmean(total, reference)
        per["market"].append(reference)
        for k, v in logs.items():
            if k != "market":
                per[k].append(weight * v)
    out = []
    for n in names:
        values = sorted(per[n])
        out.append(
            {
                "term": n,
                "usd": round(sum(values) / len(values), 2),
                "lower": round(estimate._quantile(values, 0.025), 2),
                "upper": round(estimate._quantile(values, 0.975), 2),
            }
        )
    return out


def rows(
    kit: estimate.Kit,
    kit_buildings: list[dict],
    listings: list[dict],
    buildings: list[dict],
    archives: Path,
    names: list[str],
) -> tuple[list[dict], dict]:
    """Site listing rows of the captures' listings, and a status for
    build.json: how many were priced and why the others were not."""
    from .build import _true_keys, price_band, unit_label

    terms = {b["building"]: b for b in kit_buildings}
    info = {b["id"]: b for b in buildings}
    by_unit: dict[str, list[dict]] = {}
    newest: dict[str, dict] = {}
    for r in listings:
        by_unit.setdefault(r["unit_id"], []).append(r)
        key = (r["period"], r["price_at"] or "")
        if r["building_id"] not in newest or key > newest[r["building_id"]][0]:
            newest[r["building_id"]] = (key, r)
    centre = relisting_centre(listings)
    known = {r["audit_id"] for r in listings} | {
        r["listing_id"] for r in listings if r["is_current"]
    }
    out, skipped, sources = [], {}, {}
    for source, c in captures(archives, known):
        b = c["building_id"]
        if b not in terms or b not in info or b not in newest:
            skipped[c["capture_id"]] = "building not in the served fit"
            continue
        earlier = sorted(
            (r for r in by_unit.get(c["unit_id"], []) if _time(r) <= _time(c)),
            key=_time,
        )
        prev = earlier[-1] if earlier else None
        t = terms[b]
        x = encode(
            kit,
            c,
            json.loads(newest[b][1]["inputs"]),
            prev,
            centre,
            info[b].get("floors"),
        )
        building = estimate.Building(t["level"], t["bedroom_slope"], t["fslope"], x)
        bedrooms = round(min(max(c.get("bedrooms") or 0, 0), 5))
        day = _time(c).date()
        audit_id = f"capture:{c['capture_id']}"
        got = estimate.score(
            kit, building, x, bedrooms, day, seed=audit_id, ask=float(c["rent"])
        )
        f = form(c, info[b].get("floors"))
        ask = float(c["rent"])
        listing_id = str(c["source_listing_id"])
        out.append(
            {
                "audit_id": audit_id,
                "neighbourhood": info[b].get("neighbourhood") or "",
                "unit_id": c["unit_id"],
                "building_id": b,
                "unit_label": unit_label(c.get("canonical_unit_url")),
                "unit_url": c.get("canonical_unit_url"),
                "listing_id": listing_id,
                "listing_url": f"https://streeteasy.com/rental/{listing_id}"
                if listing_id.isdigit()
                else None,
                "period": f"{day:%Y-%m}-01",
                "price_at": c["collected_at"],
                "is_current": 1,
                "price_basis": "current_capture_gross_ask",
                "ask": ask,
                "bedrooms": c.get("bedrooms"),
                "bathrooms": c.get("bathrooms"),
                "full_baths": f.full_baths,
                "half_baths": None if f.half_baths == "unknown" else int(f.half_baths),
                "square_feet": c.get("square_feet"),
                "floor": c.get("physical_floor") or c.get("advertised_floor"),
                "elevator": {True: "yes", False: "no"}.get(c.get("elevator")),
                "doorman": c.get("doorman_type"),
                "laundry": c.get("laundry_type"),
                "hvac": c.get("hvac_type"),
                "pets": c.get("pet_policy"),
                "views": _true_keys(c.get("view_exposures")),
                "windows": _true_keys(c.get("window_exposures")),
                "concession": None,
                "collected_at": c["collected_at"],
                "in_fit": 0,
                "unit_fit_rows": 0,
                "method": METHOD,
                "estimate": got["estimate"],
                "estimate_lower": got["lower_95"],
                "estimate_upper": got["upper_95"],
                "estimate_median": got["median"],
                "residual_usd": ask - got["estimate"],
                "residual_pct": ask / got["estimate"] - 1,
                "pit": got["ask_share_below"],
                "price_band": price_band(got["ask_share_below"]),
                "pareto_k": None,
                "reliable": 1,
                "fitted": None,
                "fitted_lower": None,
                "fitted_upper": None,
                **{
                    f"pred_{side}_{level}": got[f"pred_{side}_{level}"]
                    for level in (95, 80)
                    for side in ("lower", "upper")
                },
                "contributions": json.dumps(
                    contributions(kit, building, x, bedrooms, day, audit_id, names),
                    separators=(",", ":"),
                ),
                "inputs": json.dumps(x, separators=(",", ":")),
            }
        )
        sources[source] = sources.get(source, 0) + 1
    return out, {"priced": len(out), "by_capture": sources, "skipped": skipped}

"""Current listings from the data pipeline's ads file, priced with the run's prediction kit.

The served fit prices the current listings in its own dataset. The pipeline reads every ad again
at each backfill and weekly top-up, so most ads on the market now are newer than that dataset.
The build prices them here with the run's prediction kit, the same scoring the estimate form
uses: an apartment in its building whose level is the fit's own for a unit the fit has seen (the
kit's `units.parquet`), and otherwise drawn from the unit prior, as for a new apartment. Until a
fit includes them, these rows are marked `method = "kit"` and say so on their pages.

The build takes the files of the pipeline's newest build from its catalog
(`PIPELINE/catalog.ndjson`), after checking each file's sha256 against the catalog:

- the ads file gives the status in each ad's latest API answer, the time of that answer and the
  price on the ad's page;
- the rows file gives the ad's fit-ready values, after the corrections ledger.

An ad counts as on the market when its latest answer says ACTIVE and the pipeline fetched it
within CURRENT_DAYS of the build. The build shows it when it also has a fit-ready row. A fit-ready
row's ask follows the chain's latest-ask rule and can be an earlier price, so the build prices the
ask on the ad's page.

A listing gets its model inputs from:

- its fit-ready row (bedrooms, baths, size, floor, laundry, views, windows), through the
  estimate form's encoder;
- the unit's label, for the floor when the ad states none and the building has that many
  floors (as `rentfrontier.features.row_floor` reads it);
- the unit's newest earlier listing on the site, for what the dataset keeps per unit (which way
  it faces; the size when the ad states none) and for the time since that listing;
- the building's newest listing, for the building's own terms.

The build doesn't read the description, as for every current listing, so rooms beyond the
bedrooms and outdoor space are unknown or absent, as there, unless the unit's newest earlier
listing is the same ad with its description: then they come from it.
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

import duckdb

from .. import pricing
from . import estimate, estimate_build, wings

# Groups the dataset keeps per unit, taken from the unit's newest earlier listing.
UNIT_GROUPS = ("facing",)
# Groups read from the ad's description, taken from the same ad seen earlier.
DESCRIPTION_GROUPS = ("description", "outdoor space", "rooms beyond bedrooms")
LETTERED = re.compile(r"^(?:APT-?)?(\d{1,2})[A-Z]{1,2}$")
NUMBERED = re.compile(r"^(\d)\d\d$")
METHOD = "kit"
PIPELINE = Path("/data1/apartments/pipeline/datasets")
# Two ads of a unit on the market at once must agree on these values of the ads file, or the
# unit has no current ad.
AGREE = ("ask", "ad_bedrooms", "ad_bathrooms", "ad_square_feet")
# A listing is on the market now when it was last seen active within this many
# days of the build. The top-up runs weekly and can start up to 18 hours late
# behind a backfill, so the window runs two days past a week.
CURRENT_DAYS = 9


def now() -> dt.datetime:
    """The build's clock: the windows for current listings end here."""
    return dt.datetime.now(dt.UTC)


def fresh(r: dict, at: dt.datetime) -> bool:
    """Whether a row was last seen within CURRENT_DAYS of `at`. A dataset
    row's `collected_at` is when it was last seen; `price_at` is the ask's own
    date, the same instant for a current capture."""
    text = r.get("collected_at") or r.get("price_at")
    if not text:
        return False
    return (at - pricing._timestamp(text)).total_seconds() <= CURRENT_DAYS * 86400


def supported(c: dict) -> bool:
    """The layout and rent range the dataset's current rows keep
    (`fit_robust_analysis.current_rows`)."""
    beds, baths, rent = (
        pricing._number(c.get(k)) for k in ("bedrooms", "bathrooms", "ask")
    )
    return (
        beds is not None
        and 0 <= beds <= 5
        and not beds % 1
        and baths is not None
        and 1 <= baths <= 5
        and not (baths * 2) % 1
        and rent is not None
        and 750 <= rent <= 50000
    )


def pipeline_files(root: Path) -> dict | None:
    """The ads and rows files of the pipeline's newest build under `root` from a clean checkout,
    from its catalog, or None when the catalog has no such build. A newest build without both
    files, or a file whose sha256 differs from the catalog's, stops the build.

    The pipeline appends a build's line with its line break. A last line without one is still
    being written, and the build reads the lines before it."""
    catalog = root / "catalog.ndjson"
    lines = catalog.read_text().split("\n")[:-1] if catalog.is_file() else []
    # A build from a checkout with changes may write to the same catalog, and the site leaves it
    # out. A clean checkout of a branch counts, so a build from a branch writes to a folder of
    # its own with --out.
    clean = [
        entry
        for entry in map(json.loads, filter(str.strip, lines))
        if entry.get("code", {}).get("clean") is True
    ]
    if not clean:
        return None
    entry = clean[-1]
    files = {"built": entry["built"]}
    for key, name in (("ads", "ads_file"), ("rows", "rows")):
        if name not in entry:
            raise ValueError(f"the newest build in {catalog} has no {name}")
        path = root / entry[name]["path"]
        if estimate_build._sha256(path) != entry[name]["sha256"]:
            raise ValueError(f"{path} differs from the pipeline's catalog")
        files[key] = str(path)
        files[f"{key}_sha256"] = entry[name]["sha256"]
    return files


CURRENT_ADS = """
SELECT a.listing_id, a.unit_id, a.building AS building_id, a.page AS unit_url,
  a.response_id, a.fetched::TIMESTAMP AS collected_at, a.page_price * {net} AS ask,
  a.page_price AS gross_ask, {months_free} AS months_free, {lease_term} AS lease_term,
  a.bedrooms AS ad_bedrooms, a.bathrooms AS ad_bathrooms, a.square_feet AS ad_square_feet,
  r.listing_id IS NOT NULL AS in_rows,
  r.bedrooms, r.bathrooms, r.full_baths, r.half_baths, r.square_feet,
  r.advertised_floor, r.physical_floor, r.elevator, r.laundry_type,
  r.doorman_type, r.hvac_type, r.pet_policy, r.view_exposures, r.window_exposures
FROM read_parquet($ads) a LEFT JOIN read_parquet($rows) r ON r.listing_id = a.listing_id
WHERE a.status = 'ACTIVE' AND a.unit_id IS NOT NULL AND a.fetched BETWEEN $start AND $at
ORDER BY a.unit_id, a.fetched DESC, a.listing_id DESC
"""


def _concession_columns(con, files: dict) -> dict[str, str]:
    """The CURRENT_ADS expressions for an ad's concession, from pipeline files that have
    its columns: the rows file's net ask over its gross ask scales the page's gross price,
    and the ads file gives the free months and the lease term. Files from before the
    pipeline kept concession ads give a factor of 1 and no terms."""

    def columns(path):
        return {
            name
            for name, *_ in con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [path]
            ).fetchall()
        }

    ads, rows = columns(files["ads"]), columns(files["rows"])
    net = "1"
    if {"latest_ask", "latest_gross"} <= rows:
        net = (
            "CASE WHEN r.latest_gross > 0 AND r.latest_ask > 0 "
            "THEN r.latest_ask / r.latest_gross ELSE 1 END"
        )
    terms = {"months_free", "lease_term"} <= ads
    return {
        "net": net,
        "months_free": "a.months_free" if terms else "NULL::DOUBLE",
        "lease_term": "a.lease_term" if terms else "NULL::DOUBLE",
    }


def concession(c: dict) -> str | None:
    """The ad's concession in words, with the gross price the page shows, or None when the
    ad has no free months."""
    free, term = c.get("months_free"), c.get("lease_term")
    if not free or not term or not 0 < free < term:
        return None
    months = f"{free:g} month{'s' if free != 1 else ''}"
    gross = c.get("gross_ask")
    shown = f" (gross ask ${gross:,.0f})" if gross else ""
    return f"{months} free on a {term:g}-month lease{shown}"


def current_ads(
    files: dict,
    skip_listings: set[str],
    skip_units: dict[str, dt.datetime],
    at: dt.datetime | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """One ad on the market at `at` for each unit, with the values of its fit-ready row, and
    the reason the build leaves out each other ad on the market, by listing id.

    The build reads every ad of a unit on the market, with a fit-ready row or without, and
    leaves out all of them when:

    - two of them differ on the ask, the bedrooms, the baths or the size the ads file gives,
      a missing size included;
    - the dataset dropped one of them (`skip_listings`), since its agreeing ads repeat the
      values the dataset dropped.

    Otherwise it leaves out the ads without a fit-ready row and takes the one fetched last of
    the others. It then leaves that ad out when:

    - its layout or ask lies outside the dataset's range (`supported`);
    - the dataset last saw its unit current no earlier than the pipeline fetched the ad
      (`skip_units`), since the dataset prices the unit then.
    """
    at = at or now()
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        cursor = con.execute(
            CURRENT_ADS.format(**_concession_columns(con, files)),
            {
                "ads": files["ads"],
                "rows": files["rows"],
                "start": at - dt.timedelta(days=CURRENT_DAYS),
                "at": at,
            },
        )
        names = [d[0] for d in cursor.description]
        found = [dict(zip(names, values)) for values in cursor.fetchall()]
    finally:
        con.close()
    by_unit: dict[str, list[dict]] = {}
    for c in found:
        # The UTC time of the answer, read as a plain timestamp: DuckDB needs pytz to give
        # a time with its zone.
        c["collected_at"] = c["collected_at"].replace(tzinfo=dt.UTC).isoformat()
        for key in ("view_exposures", "window_exposures"):
            c[key] = json.loads(c[key] or "null")
        by_unit.setdefault(c["unit_id"], []).append(c)
    ads, skipped = [], {}
    for unit, group in by_unit.items():
        if len({tuple(a[k] for k in AGREE) for a in group}) > 1:
            skipped |= {
                a["listing_id"]: "the unit's ads on the market conflict" for a in group
            }
            continue
        if any(a["listing_id"] in skip_listings for a in group):
            skipped |= {
                a["listing_id"]: "the dataset dropped the listing"
                if a["listing_id"] in skip_listings
                else "the dataset dropped another ad of the unit"
                for a in group
            }
            continue
        skipped |= {
            a["listing_id"]: "the ad has no fit-ready row"
            for a in group
            if not a["in_rows"]
        }
        group = [a for a in group if a["in_rows"]]
        if not group:
            continue
        c, seen = group[0], skip_units.get(unit)
        if not supported(c):
            skipped[c["listing_id"]] = "layout or ask outside the dataset's range"
        elif seen is not None and pricing._timestamp(c["collected_at"]) <= seen:
            skipped[c["listing_id"]] = "the dataset prices the unit as current"
        else:
            ads.append(c)
    return ads, skipped


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
    """The estimate form the ad's fit-ready values fill in."""
    full = c.get("full_baths")
    return estimate_build.form_from_observation(
        {
            "canonical_unit_url": c.get("unit_url"),
            "bedrooms": c.get("bedrooms"),
            "reported_full_bathrooms": c.get("bathrooms") if full is None else full,
            "reported_half_bathrooms": c.get("half_baths"),
            "square_feet": c.get("square_feet"),
            "listed_floor": c.get("physical_floor")
            or c.get("advertised_floor")
            or label_floor(c.get("unit_url"), height),
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
    for rows in by_unit.values():
        rows.sort(key=lambda r: r["price_at"] or r["period"])
    return centre_of(by_unit.values())


def centre_of(units) -> float | None:
    """`relisting_centre` from each unit's listings in time order: the median
    over the first 200 listings with a gap to recover."""
    centres = []
    for rows in units:
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
    """The model inputs of a current ad (see the module docstring)."""
    f = form(c, height)
    x = estimate.encode(f, kit, building_inputs)
    group_of = dict(zip(kit.features, kit.groups))
    if prev is not None:
        p = json.loads(prev["inputs"])
        groups = list(UNIT_GROUPS)
        # The size is relative to the bedroom count's median, so only from a
        # listing with as many bedrooms.
        same_beds = prev.get("bedrooms") == c.get("bedrooms")
        if f.square_feet is None and same_beds and "log_sqft_vs_bedroom_median" in p:
            groups.append("size")
        for g in groups:
            for name in [n for n in x if group_of.get(n) == g]:
                del x[name]
            x.update({n: v for n, v in p.items() if group_of.get(n) == g})
        if kit.has("log_months_since_last_listing"):
            # Not the unit's first listing; with no centre to recover, the
            # gap stays at its centre (the average gap).
            x.pop("first_listing_of_unit", None)
            x["log_months_since_last_listing"] = 0.0
            if centre is not None:
                days = (_time(c) - _time(prev)).total_seconds() / 86400
                x["log_months_since_last_listing"] = (
                    math.log1p(max(days, 0) / 30.4) - centre
                )
    p = json.loads(prev["inputs"]) if prev is not None else {}
    same_ad = (
        prev is not None
        and str(prev.get("listing_id")) == str(c.get("listing_id"))
        and not p.get("description_missing")
    )
    if same_ad:
        for name in [n for n in x if group_of.get(n) in DESCRIPTION_GROUPS]:
            del x[name]
        x.update({n: v for n, v in p.items() if group_of.get(n) in DESCRIPTION_GROUPS})
        return x
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
    unit: list[float] | None = None,
) -> list[dict]:
    """Dollar contributions of the kit estimate against the market reference,
    as `rentfrontier.summary` gives them: per draw, the log-mean (LMDI)
    weight times each term's log, with the unit level's expected factor as
    "unit" (the fit's own level, `unit`, when given; "from_fit" says so);
    means and 95% intervals over draws."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    group_of = dict(zip(kit.features, kit.groups))
    group = min(max(bedrooms, 0), 3)
    centered = min(max(bedrooms, 0), 4) - 1.0
    frac = estimate.year_fraction(day)
    slopes = [x.get(n, 0.0) for n in kit.slopes]
    per: dict[str, list[float]] = {}
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
        # The unit levels `estimate.score` draws with the same seed (each
        # followed by its ask's noise), so the parts add up to its estimate.
        scale = kit.unit_scale[s]
        levels = []
        for _ in range(estimate.SAMPLES_PER_DRAW):
            if unit is not None:
                levels.append(unit[s])
            else:
                z = (
                    estimate._student_t(rng, kit.unit_nu[s])
                    if kit.t_units
                    else rng.gauss(0.0, 1.0)
                )
                levels.append(
                    scale * max(-estimate.UNIT_CLIP, min(estimate.UNIT_CLIP, z))
                )
            estimate._student_t(rng, kit.nu[s])
        logs["unit"] = math.log(sum(math.exp(v) for v in levels) / len(levels))
        reference = math.exp(kit.market[s] + estimate._season(kit, s, frac, day.month))
        total = reference * math.exp(sum(v for k, v in logs.items() if k != "market"))
        weight = _logmean(total, reference)
        per.setdefault("market", []).append(reference)
        for k, v in logs.items():
            if k != "market":
                per.setdefault(k, []).append(weight * v)
    out = []
    # In the terms table's order, then any term it does not name.
    for n in [*(n for n in names if n in per), *(n for n in per if n not in names)]:
        values = sorted(per[n])
        out.append(
            {
                "term": n,
                "usd": round(sum(values) / len(values), 2),
                "lower": round(estimate._quantile(values, 0.025), 2),
                "upper": round(estimate._quantile(values, 0.975), 2),
                **({"from_fit": True} if n == "unit" and unit is not None else {}),
            }
        )
    return out


def scaled(parts: list[dict], factor: float) -> list[dict]:
    """The parts, which add up to the mean, scaled to add up to the median
    the estimate reports."""
    return [
        p | {k: round(factor * p[k], 2) for k in ("usd", "lower", "upper")}
        for p in parts
    ]


def rows(
    kit: estimate.Kit,
    kit_buildings: list[dict],
    listings: list[dict],
    buildings: list[dict],
    files: dict,
    names: list[str],
    observations: dict[str, dict] | None = None,
    units=None,
    at: dt.datetime | None = None,
    *,
    local=None,
    fit_ids: set[str] | None = None,
    centre: float | None = None,
) -> tuple[list[dict], dict]:
    """Site listing rows of the ads on the market, and a status for build.json: the pipeline's
    files, how many ads were priced, how many with the fit's own unit level, and why the
    others were not.

    A build of every borough passes `fit_ids` (the audit ids of the fit's rows) and
    `local`, which returns the listings and building rows of the ads' units and
    buildings, in place of every listing; `units` may then be a function from the
    ads' unit ids to their levels. It also passes `centre`, the relisting centre of
    every listing (`centre_of`), which the ads' listings alone would estimate
    differently."""
    at = at or now()
    from .build import _true_keys, price_band, unit_label

    terms = {b["building"]: b for b in kit_buildings}
    # The dataset's rows (`observations`, the bundle's rows when not given):
    # a listing it dropped stays out, and a unit it prices now is priced there.
    if observations is None:
        observations = {r["audit_id"]: r for r in listings}
    if fit_ids is None:
        fit_ids = {r["audit_id"] for r in listings}
    skip_listings: set[str] = set()
    skip_units: dict[str, dt.datetime] = {}
    for a, o in observations.items():
        ids = o.get("listing_ids")
        ids = json.loads(ids) if isinstance(ids, str) else list(ids or [])
        ids.append(o.get("listing_id") or o.get("source_listing_id"))
        # a row the dataset priced as current but last saw before the window
        # is past, so a newer ad of its unit is priced here
        current = o.get(
            "is_current", o.get("analysis_price_basis") == "current_capture_gross_ask"
        ) and fresh(o, at)
        if a not in fit_ids:
            skip_listings |= {str(i) for i in ids if i}
        if current:
            seen = pricing._timestamp(o.get("collected_at") or o["price_at"])
            skip_units[o["unit_id"]] = max(seen, skip_units.get(o["unit_id"], seen))
    ads, skipped = current_ads(files, skip_listings, skip_units, at)
    if local is not None:
        places = set()
        for c in ads:
            places.add(c["building_id"])
            for pages, (_, split, main) in wings.SPLITS.items():
                if c["building_id"] in pages:
                    places |= {split, main}
        listings, buildings = local({c["unit_id"] for c in ads}, places)
    if callable(units):
        units = units({c["unit_id"] for c in ads})
    units = units or {}
    info = {b["id"]: b for b in buildings}
    by_unit: dict[str, list[dict]] = {}
    newest: dict[str, dict] = {}
    for r in listings:
        by_unit.setdefault(r["unit_id"], []).append(r)
        key = (r["period"], r["price_at"] or "")
        if r["building_id"] not in newest or key > newest[r["building_id"]][0]:
            newest[r["building_id"]] = (key, r)
    if centre is None:
        centre = relisting_centre(listings)
    out, fitted_levels = [], 0
    for c in ads:
        b = wings.wing(c["building_id"], unit_label(c.get("unit_url")), terms)
        if b not in terms or b not in info or b not in newest:
            skipped[c["listing_id"]] = "building not in the served fit"
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
        audit_id = f"api:{c['response_id']}:{c['listing_id']}"
        fit_rows = sum(r["in_fit"] for r in by_unit.get(c["unit_id"], []))
        unit = units.get(c["unit_id"]) if fit_rows else None
        got = estimate.score(
            kit,
            building,
            x,
            bedrooms,
            day,
            seed=audit_id,
            ask=float(c["ask"]),
            unit=unit,
        )
        f = form(c, info[b].get("floors"))
        ask = float(c["ask"])
        listing_id = c["listing_id"]
        out.append(
            {
                "audit_id": audit_id,
                "neighbourhood": info[b].get("neighbourhood") or "",
                "unit_id": c["unit_id"],
                "building_id": b,
                "unit_label": unit_label(c.get("unit_url")),
                "unit_url": c.get("unit_url"),
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
                "concession": concession(c),
                "collected_at": c["collected_at"],
                "in_fit": 0,
                "unit_fit_rows": fit_rows,
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
                    scaled(
                        contributions(
                            kit, building, x, bedrooms, day, audit_id, names, unit
                        ),
                        got["median"] / got["mean"],
                    ),
                    separators=(",", ":"),
                ),
                "inputs": json.dumps(x, separators=(",", ":")),
            }
        )
        fitted_levels += unit is not None
    return out, {
        "pipeline": files,
        "priced": len(out),
        "unit_levels": fitted_levels,
        "skipped": dict(sorted(skipped.items())),
    }


def price(
    kit_dir: Path | None,
    listings: list[dict],
    buildings: list[dict],
    files: dict | None,
    names: list[str],
    observations: dict[str, dict] | None = None,
    at: dt.datetime | None = None,
    *,
    local=None,
    fit_ids: set[str] | None = None,
    centre: float | None = None,
    likely=None,
) -> tuple[list[dict], dict]:
    """The ads on the market priced with the run's kit, when it scores the fit's own rows as
    the bundle does (`estimate_build.check_scoring`, which takes `likely`). `files` are the
    pipeline's (`pipeline_files`); `local`, `fit_ids` and `centre` are as in `rows`."""
    if kit_dir is None:
        return [], {"priced": 0, "reason": "no prediction kit for this run"}
    if files is None:
        return [], {"priced": 0, "reason": "no pipeline build to read current ads from"}
    record, kit_buildings = estimate_build.load_kit(kit_dir)
    kit = estimate.Kit.from_record(
        record,
        estimate.sqft_medians(
            (r["bedrooms"], r["square_feet"], r["inputs"]) for r in listings
        ),
    )
    if kit.unknown_groups():
        return [], {"priced": 0, "reason": "the kit has inputs the encoder lacks"}
    check = estimate_build.check_scoring(
        kit,
        {
            b["building"]: estimate.Building(
                b["level"], b["bedroom_slope"], b["fslope"], {}
            )
            for b in kit_buildings
        },
        listings,
        likely,
    )
    if not check["passes"]:
        return [], {"priced": 0, "reason": check["reason"]}

    def units(ids):
        levels = estimate_build.load_units(kit_dir, ids)
        if any(len(v) != len(kit.market) for v in levels.values()):
            raise estimate.KitError("units.parquet has another number of draws")
        return levels

    return rows(
        kit,
        kit_buildings,
        listings,
        buildings,
        files,
        names,
        observations,
        units,
        at=at,
        local=local,
        fit_ids=fit_ids,
        centre=centre,
    )

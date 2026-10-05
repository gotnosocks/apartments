"""Estimate an apartment that is not in the data, from the served run's
prediction kit (`rentfrontier.kit`).

The kit holds, per posterior draw, every term of the served equation at the
fit's last month. A new apartment is scored as the summary scores a held-out
row of a unit the fit never saw: its log rent is

    market + season(date) + beta . x + bedroom_time[group] + level[building]
    + bedroom_slope[building] * beds_centered + fslope[building] . x[slopes]

plus a unit level from the unit prior (clipped to the range `rentfrontier.loo`
integrates over), and its ask adds Student-t noise. Pure Python: the site has
no numpy.

x comes from two places. The building's own inputs (era, size, class, status,
neighbourhood, and the elevator, doorman, heating and pets of its newest
listing) are copied from that listing. Everything about the apartment itself
comes from the form (`encode`), and inputs the form does not ask take their
"not stated" level or, for a new listing, its fixed value: a first listing of
the apartment, at a current ask.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field

# Feature groups the form sets from its own fields, and groups copied from the
# building's newest listing. A run with any other group gets no form: its
# meaning is not known here.
FORM_GROUPS = (
    "bedrooms",
    "bathrooms",
    "size",
    "floor",
    "laundry",
    "views",
    "windows",
    "unit label",
    "price_basis",
    "description",
    "facing",
    "relisting",
    "outdoor space",
    "rooms beyond bedrooms",
)
BUILDING_GROUPS = (
    "elevator",
    "doorman",
    "hvac",
    "pets",
    "building era",
    "building size",
    "building class",
    "building status",
    "neighbourhood",
)
# Draws x simulated asks per draw (250 x 80 = 20,000).
SAMPLES_PER_DRAW = 80
# The unit level's range, in unit scales (`rentfrontier.loo.GRID`).
UNIT_CLIP = 40.0
LOW_FLOORS = 4
SQFT_RANGE = (150, 8000)

BEDROOMS = (
    ("0", "Studio"),
    ("1", "1 bedroom"),
    ("2", "2 bedrooms"),
    ("3", "3 bedrooms"),
    ("4", "4 bedrooms"),
    ("5", "5 or more"),
)
FULL_BATHS = (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4 or more"))
HALF_BATHS = (("0", "None"), ("1", "1"), ("2", "2 or more"), ("unknown", "Not stated"))
LAUNDRY = (
    ("in_unit", "In the apartment"),
    ("in_building", "In the building, or none"),
    ("unknown", "Not stated"),
)
LABELS = (
    ("", "None of these"),
    ("penthouse", "Penthouse"),
    ("garden", "Garden unit"),
    ("lower_level", "Lower level or basement"),
)
ROOMS = (
    ("2", "2: a living room and a kitchen (most common)"),
    ("0-1", "0 or 1 (the kitchen is in the living room)"),
    ("3", "3 (a dining room or office as well)"),
    ("4+", "4 or more"),
    ("unknown", "Not stated"),
)
FACING = (
    ("avenue", "An avenue", "looks onto an avenue"),
    ("wide street", "A wide street (14th, 23rd, 34th...)", "looks onto a wide street"),
    ("side street", "A side street", "looks onto a side street"),
    ("rear", "The rear or a courtyard", "looks onto the rear or a courtyard"),
)
OUTDOOR = (
    ("terrace", "Terrace"),
    ("roof_deck", "Private roof deck"),
    ("garden", "Private garden"),
    ("balcony", "Balcony"),
    ("patio", "Patio"),
)
VIEWS = (
    ("city", "City"),
    ("park", "Park"),
    ("water", "Water"),
    ("skyline", "Skyline"),
    ("garden", "Garden"),
    ("courtyard", "Courtyard"),
    ("street", "Street"),
)
WINDOWS = (("north", "North"), ("south", "South"), ("east", "East"), ("west", "West"))
# The advertisement flags (`rentfrontier.features.DESCRIPTION_FLAGS`), in words.
EXTRAS = (
    ("renovated", "Renovated"),
    ("dishwasher", "Dishwasher"),
    ("washer_dryer_in_unit", "Washer and dryer in the apartment"),
    ("private_outdoor", "Private outdoor space"),
    ("outdoor_shared", "Shared roof deck or garden"),
    ("duplex", "Duplex"),
    ("fireplace", "Fireplace"),
    ("high_ceilings", "High ceilings"),
    ("exposed_brick", "Exposed brick"),
    ("gym", "Gym"),
    ("luxury", "Described as luxury"),
    ("flex_convertible", "Flex or convertible"),
    ("furnished", "Furnished"),
    ("no_fee", "No broker fee"),
    ("concession", "Months free or net effective rent"),
    ("short_term", "Short term or sublet"),
    ("rent_stabilized", "Rent stabilized"),
    ("income_restricted", "Income restricted (housing lottery)"),
    ("shared_space", "Shared kitchen or bathroom"),
    ("walkup_text", "Called a walk-up"),
)


class KitError(Exception):
    pass


@dataclass
class Kit:
    """A run's prediction kit as the site stores it (the `kit` table)."""

    period: str
    features: list[str]
    groups: list[str]
    slopes: list[str]
    market: list[float]
    season_daily: bool
    season: list[list[float]]
    beta: list[list[float]]
    bedroom_time: list[list[float]]
    sigma: list[list[float]]
    nu: list[float]
    unit_scale: list[float]
    unit_nu: list[float]
    t_units: bool
    sqft_median: dict[str, float]
    index: dict[str, int] = field(init=False)

    def __post_init__(self):
        self.index = {name: j for j, name in enumerate(self.features)}

    @classmethod
    def from_record(cls, record: dict, sqft_median: dict[str, float]) -> Kit:
        return cls(
            period=record["period"],
            features=record["features"],
            groups=record["groups"],
            slopes=record["slopes"],
            market=record["market"],
            season_daily=record["season"]["daily"],
            season=record["season"]["coef"],
            beta=record["beta"],
            bedroom_time=record["bedroom_time"],
            sigma=record["sigma"],
            nu=record["nu"],
            unit_scale=record["unit_scale"],
            unit_nu=record["unit_nu"],
            t_units=record["t_units"],
            sqft_median=sqft_median,
        )

    def has(self, name: str) -> bool:
        return name in self.index

    def unknown_groups(self) -> list[str]:
        known = set(FORM_GROUPS) | set(BUILDING_GROUPS)
        return sorted(set(self.groups) - known)


@dataclass
class Building:
    """A building's kit terms (lists over draws) and its newest listing's inputs."""

    level: list[float]
    bedroom_slope: list[float]
    fslope: list[list[float]]
    inputs: dict[str, float]


def bed_label(bedrooms: int) -> str:
    return "5+" if bedrooms >= 5 else str(bedrooms)


def sqft_medians(rows) -> dict[str, float]:
    """The log square feet `log_sqft_vs_bedroom_median` is measured from, per
    bedroom label, recovered from the bundle's rows: log(square feet) less the
    row's deviation, the most common value (rows of units whose size comes
    from the unit's other listings differ)."""
    counts: dict[str, dict[float, int]] = {}
    for bedrooms, square_feet, inputs in rows:
        if bedrooms is None or square_feet is None:
            continue
        if not SQFT_RANGE[0] <= square_feet <= SQFT_RANGE[1]:
            continue
        x = json.loads(inputs)
        if "sqft_unknown" in x:
            continue
        deviation = x.get("log_sqft_vs_bedroom_median", 0.0)
        value = round(math.log(square_feet) - deviation, 3)
        label = bed_label(round(bedrooms))
        bucket = counts.setdefault(label, {})
        bucket[value] = bucket.get(value, 0) + 1
    return {label: max(c, key=c.get) for label, c in counts.items()}


@dataclass
class Form:
    """The form's fields, validated; blanks are "not stated"."""

    bedrooms: int = 1
    full_baths: int = 1
    half_baths: str = "0"
    square_feet: float | None = None
    floor: int | None = None
    laundry: str = "unknown"
    label: str = ""
    rooms: str = "2"
    facing: list[str] = field(default_factory=list)
    outdoor: list[str] = field(default_factory=list)
    views: list[str] = field(default_factory=list)
    windows: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    ask: float | None = None

    @classmethod
    def parse(cls, args) -> Form:
        def choice(name, options, default):
            value = args.get(name)
            return value if value in {o[0] for o in options} else default

        def number(name, low, high):
            try:
                value = float(
                    str(args.get(name) or "").replace(",", "").replace("$", "")
                )
            except ValueError:
                return None
            return value if low <= value <= high and math.isfinite(value) else None

        def many(name, options):
            allowed = [o[0] for o in options]
            chosen = set(args.getlist(name)) if hasattr(args, "getlist") else set()
            return [o for o in allowed if o in chosen]

        floor = number("floor", 1, 120)
        return cls(
            bedrooms=int(choice("bedrooms", BEDROOMS, "1")),
            full_baths=int(choice("baths", FULL_BATHS, "1")),
            half_baths=choice("half", HALF_BATHS, "0"),
            square_feet=number("sqft", SQFT_RANGE[0], SQFT_RANGE[1]),
            floor=int(floor) if floor is not None else None,
            laundry=choice("laundry", LAUNDRY, "unknown"),
            label=choice("label", LABELS, ""),
            rooms=choice("rooms", ROOMS, "2"),
            facing=many("facing", FACING),
            outdoor=many("outdoor", OUTDOOR),
            views=many("views", VIEWS),
            windows=many("windows", WINDOWS),
            extras=many("extras", EXTRAS),
            ask=number("ask", 100, 1_000_000),
        )

    def canonical(self) -> str:
        """A stable text of the inputs (the simulation's seed)."""
        return json.dumps(self.__dict__, sort_keys=True, default=str)


def encode(form: Form, kit: Kit, building_inputs: dict[str, float]) -> dict[str, float]:
    """The model inputs of an apartment: the building's own groups from its
    newest listing, every other column from the form (`FORM_GROUPS`)."""
    x: dict[str, float] = {}
    group_of = dict(zip(kit.features, kit.groups))
    for name, value in building_inputs.items():
        if group_of.get(name) in BUILDING_GROUPS:
            x[name] = value

    def put(name, value=1.0):
        if value and kit.has(name):
            x[name] = float(value)

    beds = bed_label(form.bedrooms)
    if beds != "1":
        put(f"bedrooms={beds}")
    if form.full_baths >= 2:
        put(f"bathrooms={'4+' if form.full_baths >= 4 else form.full_baths}")
    if form.half_baths != "0":
        put(f"bathrooms=half={'2+' if form.half_baths == '2' else form.half_baths}")
    median = kit.sqft_median.get(beds)
    if form.square_feet is not None and median is not None:
        put("log_sqft_vs_bedroom_median", math.log(form.square_feet) - median)
    else:
        put("sqft_unknown")
    no_elevator = x.get("elevator=no", 0.0) > 0
    if form.floor is not None and form.floor >= 1:
        log_floor = math.log(form.floor)
        put("log_floor", log_floor)
        put("log_floor_above_6", max(0.0, log_floor - math.log(6)))
        put("log_floor_above_15", max(0.0, log_floor - math.log(15)))
        if no_elevator:
            put("log_floor_x_no_elevator", log_floor)
    else:
        put("floor_unknown")
    if form.laundry != "in_building":
        put(f"laundry={form.laundry}")
    for name in form.views:
        put(f"view_{name}")
    for name in form.windows:
        put(f"window_{name}")
    if form.label:
        put(f"label:{form.label}")
    put("current_capture_ask")
    for name in form.extras:
        put(f"text:{name}")
    low = form.floor is not None and form.floor <= LOW_FLOORS
    for key, _, column in FACING:
        if key in form.facing:
            put(column)
            if low and key in ("avenue", "wide street"):
                put(f"{column}, floors 1-{LOW_FLOORS}")
    put("first_listing_of_unit")
    for name in form.outdoor:
        put(f"outdoor:{name}")
    if form.rooms != "2":
        put(f"rooms beyond bedrooms={form.rooms}")
    return x


def year_fraction(day) -> float:
    """`rentfrontier.model._year_frac` at midnight UTC of a date."""
    days = (
        366.0
        if (day.year % 4 == 0 and (day.year % 100 or day.year % 400 == 0))
        else 365.0
    )
    return (day.timetuple().tm_yday - 1) / days


def _season(kit: Kit, s: int, frac: float, month: int) -> float:
    coef = kit.season[s]
    if not kit.season_daily:
        return coef[month - 1]
    k = len(coef) // 2
    angles = [2 * math.pi * frac * (h + 1) for h in range(k)]
    return sum(coef[h] * math.sin(a) for h, a in enumerate(angles)) + sum(
        coef[k + h] * math.cos(a) for h, a in enumerate(angles)
    )


def _student_t(rng: random.Random, nu: float) -> float:
    return rng.gauss(0.0, 1.0) / math.sqrt(rng.gammavariate(nu / 2.0, 2.0) / nu)


def _quantile(sorted_values: list[float], p: float) -> float:
    pos = p * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (pos - lo) * (sorted_values[hi] - sorted_values[lo])


def totals(kit: Kit, building: Building, x: dict[str, float], bedrooms: int, day):
    """Per draw, the log rent of every term but the unit level."""
    group = min(max(bedrooms, 0), 3)
    centered = min(max(bedrooms, 0), 4) - 1.0
    frac = year_fraction(day)
    cols = [(kit.index[n], v) for n, v in x.items() if n in kit.index]
    slopes = [x.get(n, 0.0) for n in kit.slopes]
    out = []
    for s in range(len(kit.market)):
        beta = kit.beta[s]
        out.append(
            kit.market[s]
            + _season(kit, s, frac, day.month)
            + sum(beta[j] * v for j, v in cols)
            + kit.bedroom_time[s][group]
            + building.level[s]
            + building.bedroom_slope[s] * centered
            + sum(f * v for f, v in zip(building.fslope[s], slopes))
        )
    return out


def score(
    kit: Kit,
    building: Building,
    x: dict[str, float],
    bedrooms: int,
    day,
    seed: str,
    ask: float | None = None,
    samples: int = SAMPLES_PER_DRAW,
) -> dict:
    """The typical rent of a new apartment like this (mean, median and 95%
    interval of its latent rent), the range its ask is likely to fall in (80%
    and 95% predictive intervals), and where `ask` falls among simulated asks."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16))
    group = min(max(bedrooms, 0), 3)
    latent, asks = [], []
    for s, total in enumerate(totals(kit, building, x, bedrooms, day)):
        scale = kit.unit_scale[s]
        sigma = kit.sigma[s][group if len(kit.sigma[s]) > 1 else 0]
        for _ in range(samples):
            z = _student_t(rng, kit.unit_nu[s]) if kit.t_units else rng.gauss(0.0, 1.0)
            level = scale * max(-UNIT_CLIP, min(UNIT_CLIP, z))
            mu = total + level
            latent.append(mu)
            asks.append(mu + sigma * _student_t(rng, kit.nu[s]))
    latent.sort()
    asks.sort()
    out = {
        "estimate": sum(math.exp(v) for v in latent) / len(latent),
        "median": math.exp(_quantile(latent, 0.5)),
        "lower_95": math.exp(_quantile(latent, 0.025)),
        "upper_95": math.exp(_quantile(latent, 0.975)),
        "pred_lower_80": math.exp(_quantile(asks, 0.10)),
        "pred_upper_80": math.exp(_quantile(asks, 0.90)),
        "pred_lower_95": math.exp(_quantile(asks, 0.025)),
        "pred_upper_95": math.exp(_quantile(asks, 0.975)),
        "samples": len(asks),
    }
    if ask is not None:
        log_ask = math.log(ask)
        below = _bisect(asks, log_ask)
        out["ask"] = ask
        out["ask_share_below"] = below / len(asks)
    return out


def _bisect(values: list[float], target: float) -> int:
    lo, hi = 0, len(values)
    while lo < hi:
        mid = (lo + hi) // 2
        if values[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def parts(
    kit: Kit, building: Building, x: dict[str, float], bedrooms: int
) -> list[dict]:
    """What moves the estimate away from the market reference, per group of
    inputs, as the percentage the posterior mean of its log term gives:
    [{group, pct}], the building's own terms last."""
    d = len(kit.market)
    group_of = dict(zip(kit.features, kit.groups))
    sums: dict[str, float] = {}
    for name, value in x.items():
        j = kit.index.get(name)
        if j is None:
            continue
        g = group_of[name]
        sums[g] = sums.get(g, 0.0) + value * sum(kit.beta[s][j] for s in range(d)) / d
    group = min(max(bedrooms, 0), 3)
    centered = min(max(bedrooms, 0), 4) - 1.0
    slopes = [x.get(n, 0.0) for n in kit.slopes]
    curve = sum(kit.bedroom_time[s][group] for s in range(d)) / d
    if curve:
        sums["bedroom_market_curve"] = curve
    own = (
        sum(
            building.level[s]
            + building.bedroom_slope[s] * centered
            + sum(f * v for f, v in zip(building.fslope[s], slopes))
            for s in range(d)
        )
        / d
    )
    order = list(dict.fromkeys(kit.groups))
    out = [
        {"group": g, "pct": 100.0 * math.expm1(sums[g])}
        for g in sorted(
            sums, key=lambda g: order.index(g) if g in order else len(order)
        )
        if abs(sums[g]) > 1e-9
    ]
    out.append({"group": "building", "pct": 100.0 * math.expm1(own)})
    return out

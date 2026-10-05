"""Why a listing is appealing or not, according to the model, in a few plain
sentences (Ben, 2026-10-05).

Built only from the served fit's own terms (each part's dollar contribution
and its 95% interval) and the coded fields the model read for the listing:
no language model and no ad text. A part is named only when its interval
leaves out zero and it moves the estimate by at least MIN_SHARE of it; a
part whose only input is "not stated" says nothing about the apartment and
is left out. The building's and the unit's own levels get a sentence each,
since they are what the model learned about this building and apartment
beyond their features.
"""

from __future__ import annotations

MIN_SHARE = 0.005  # of the estimate
MIN_USD = 25.0
MOST = 5  # parts named on each side

ORDINAL_WORDS = {2: "two", 3: "three", 4: "four"}
DOORMAN = {
    "full_time": "a full-time doorman",
    "part_time": "a part-time doorman",
    "virtual": "a virtual doorman",
    "none": "no doorman",
}
VIEWS = {
    "park": "the park",
    "water": "the water",
    "skyline": "the skyline",
    "city": "the city",
    "garden": "a garden",
    "courtyard": "a courtyard",
    "street": "the street",
}
OUTDOOR = {
    "terrace": "a terrace",
    "roof_deck": "a roof deck",
    "garden": "a garden",
    "balcony": "a balcony",
    "patio": "a patio",
}
FACING = {
    "looks onto the rear or a courtyard": "the rear or a courtyard",
    "looks onto a side street": "a quiet side street",
    "looks onto a wide street": "a wide street",
    "looks onto an avenue": "an avenue",
}
LOW_FACING = {
    "looks onto a wide street, floors 1-4": "a low floor on a wide street",
    "looks onto an avenue, floors 1-4": "a low floor on an avenue",
}
ERAS = {
    "pre-1900": "a building from before 1900",
    "1930-1959": "a building from 1930-1959",
    "1960-1989": "a building from 1960-1989",
    "1990-2009": "a building from 1990-2009",
    "2010+": "a building from 2010 or later",
}
CLASSES = {
    "C": "a walk-up building",
    "R": "a condominium building",
    "S": "a small building over a store or office",
}
PETS = {
    "allowed": "pets allowed",
    "allowed_restrictions_unknown": "pets allowed",
    "approval_required": "pets with approval",
    "not_allowed": "no pets",
}


def _join(words: list[str]) -> str:
    if len(words) < 3:
        return " and ".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _list(items: list[str]) -> str:
    """A list of phrases; semicolons when a phrase has its own "and", so the
    items stay apart."""
    if len(items) > 1 and any(" and " in w for w in items):
        return "; ".join(items[:-1]) + "; and " + items[-1]
    return _join(items)


def _ordinal(n: int) -> str:
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def _with(inputs: dict, prefix: str) -> list[str]:
    """The levels of a coded field the listing has, in input order."""
    return [
        k.removeprefix(prefix) for k, v in inputs.items() if k.startswith(prefix) and v
    ]


def phrase(term: str, row, inputs: dict, sign: int) -> str | None:
    """What the listing has that a model part prices, in a few words; None
    when the part rests only on a detail the listing leaves out, or is not
    about the apartment (the market, the price basis, time effects)."""
    if term == "bathrooms":
        full, half = row["full_baths"], row["half_baths"]
        words = []
        if full and full >= 2:
            words.append(f"{ORDINAL_WORDS.get(int(full), int(full))} full baths")
        if half:
            words.append("a half bath" if half == 1 else f"{int(half)} half baths")
        return _join(words) or None
    if term == "size":
        if "log_sqft_vs_bedroom_median" not in inputs:
            return None
        return "more space than usual" if sign > 0 else "less space than usual"
    if term == "floor":
        if row["floor"] is None:
            return None
        n = int(row["floor"])
        if inputs.get("log_floor_x_no_elevator"):
            return f"a walk-up {_ordinal(n)} floor"
        return f"the {_ordinal(n)} floor"
    if term == "elevator":
        return "no elevator" if row["elevator"] == "no" else None
    if term == "doorman":
        levels = _with(inputs, "doorman=")
        return DOORMAN.get(levels[0]) if levels else None
    if term == "laundry":
        return "laundry in the unit" if inputs.get("laundry=in_unit") else None
    if term == "hvac":
        return "central air" if inputs.get("hvac=central_ac") else None
    if term == "pets":
        levels = _with(inputs, "pets=")
        return PETS.get(levels[0]) if levels else None
    if term == "views":
        seen = [VIEWS[v] for v in _with(inputs, "view_") if v in VIEWS]
        return "views of " + _join(seen) if seen else None
    if term == "windows":
        sides = _with(inputs, "window_")
        return _join(sides) + "-facing windows" if sides else None
    if term == "facing":
        onto = [v for k, v in FACING.items() if inputs.get(k)]
        low = [v for k, v in LOW_FACING.items() if inputs.get(k)]
        return _join((["windows onto " + _join(onto)] if onto else []) + low) or None
    if term == "unit label":
        labels = [
            k.removeprefix("label:").replace("_", " ") for k in _with(inputs, "label:")
        ]
        return _join(["a " + v for v in labels]) if labels else None
    if term == "outdoor space":
        seen = [
            OUTDOOR.get(v, "a " + v.replace("_", " "))
            for v in _with(inputs, "outdoor:")
        ]
        if len(seen) > 1:
            return "private outdoor space (" + _join(seen) + ")"
        return "a private " + seen[0].removeprefix("a ") if seen else None
    if term == "rooms beyond bedrooms":
        levels = [v for v in _with(inputs, "rooms beyond bedrooms=") if v != "unknown"]
        if not levels:
            return None
        return "more rooms than most" if sign > 0 else "fewer rooms than most"
    if term == "description":
        flags = [
            k.removeprefix("text:").replace("_", " ") for k in _with(inputs, "text:")
        ]
        return "the ad's " + _join(flags) if flags else None
    if term == "building era":
        levels = _with(inputs, "building era=")
        return ERAS.get(levels[0]) if levels else None
    if term == "building class":
        levels = _with(inputs, "building class=")
        return CLASSES.get(levels[0]) if levels else None
    if term == "building size":
        return "the building's height and size"
    if term == "building status":
        words = []
        if inputs.get("landmark"):
            words.append("a landmark building")
        elif inputs.get("historic_district"):
            words.append("being in a historic district")
        if inputs.get("altered_since_2000"):
            words.append("a building altered since 2000")
        return _join(words) or None
    if term == "neighbourhood":
        return "the West Village" if inputs.get("West Village") else "Chelsea"
    return None


def _clear(c, floor: float) -> int:
    """+1 or -1 when the part's 95% interval leaves out zero and it is large
    enough to name; 0 otherwise."""
    if abs(c["usd"]) < floor:
        return 0
    if c["lower"] > 0:
        return 1
    if c["upper"] < 0:
        return -1
    return 0


def listing_summary(row, contributions: list[dict], inputs: dict) -> list[str]:
    """A few sentences on what the model makes of this listing: its building
    and the apartment's own level against peers, then the parts it prices up
    and down, largest first."""
    estimate = row["estimate"] or 0.0
    floor = max(MIN_USD, MIN_SHARE * estimate)
    by_term = {c["term"]: c for c in contributions}
    out = []

    building = by_term.get("building")
    side = _clear(building, floor) if building else 0
    if side:
        share = abs(building["usd"]) / estimate if estimate else 0
        out.append(
            "This listing is in a building that rents "
            + ("higher" if side > 0 else "lower")
            + f" than its peers: about {share:.0%} "
            + ("more" if side > 0 else "less")
            + " than an average building with the same features."
        )
    elif building:
        out.append("Its building rents in line with its peers with the same features.")

    unit = by_term.get("unit")
    side = _clear(unit, floor) if unit else 0
    if side:
        out.append(
            "The apartment itself has rented "
            + ("above" if side > 0 else "below")
            + " what its features and building predict, going by its other listings."
        )

    up, down = [], []
    for c in sorted(contributions, key=lambda c: -abs(c["usd"])):
        side = _clear(c, floor)
        if not side:
            continue
        words = phrase(c["term"], row, inputs, side)
        if not words:
            continue
        (up if side > 0 else down).append(words)
    if up:
        out.append("The model prices it up for " + _list(up[:MOST]) + ".")
    if down:
        out.append("It prices it down for " + _list(down[:MOST]) + ".")
    return out

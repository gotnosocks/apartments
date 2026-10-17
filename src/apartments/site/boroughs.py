"""The borough of each neighbourhood the scrape covers, by StreetEasy's
neighbourhood names. The site groups its neighbourhood choices by borough
and offers a whole borough as a choice once a build covers more than one."""

from __future__ import annotations

BOROUGHS = {
    "Manhattan": (
        "Battery Park City",
        "Beekman",
        "Carnegie Hill",
        "Central Park South",
        "Chelsea",
        "Chinatown",
        "Civic Center",
        "East Harlem",
        "East Village",
        "Financial District",
        "Flatiron",
        "Fulton/Seaport",
        "Gramercy Park",
        "Greenwich Village",
        "Hell's Kitchen",
        "Hudson Square",
        "Hudson Yards",
        "Kips Bay",
        "Lenox Hill",
        "Lincoln Square",
        "Little Italy",
        "Lower East Side",
        "Manhattan Valley",
        "Midtown",
        "Midtown South",
        "Murray Hill",
        "NoMad",
        "Noho",
        "Nolita",
        "Soho",
        "Stuyvesant Town/PCV",
        "Sutton Place",
        "Tribeca",
        "Turtle Bay",
        "Two Bridges",
        "Upper Carnegie Hill",
        "Upper East Side",
        "Upper West Side",
        "West Village",
        "Yorkville",
    ),
    "Brooklyn": (
        "Bedford-Stuyvesant",
        "Boerum Hill",
        "Brooklyn Heights",
        "Bushwick",
        "Carroll Gardens",
        "Clinton Hill",
        "Cobble Hill",
        "Columbia St Waterfront District",
        "Crown Heights",
        "DUMBO",
        "Downtown Brooklyn",
        "East Williamsburg",
        "Fort Greene",
        "Gowanus",
        "Greenpoint",
        "Ocean Hill",
        "Park Slope",
        "Prospect Heights",
        "Red Hook",
        "Stuyvesant Heights",
        "Vinegar Hill",
        "Weeksville",
        "Williamsburg",
    ),
}
BOROUGH_OF = {name: borough for borough, names in BOROUGHS.items() for name in names}


def grouped(counts: dict[str, int]) -> dict[str, dict[str, int]]:
    """Neighbourhood counts by borough, in BOROUGHS order; names the table
    lacks go under "Other"."""
    out: dict[str, dict[str, int]] = {b: {} for b in BOROUGHS}
    for name, n in counts.items():
        out.setdefault(BOROUGH_OF.get(name, "Other"), {})[name] = n
    return {b: names for b, names in out.items() if names}


def areas(choice: str | None, counts: dict[str, int]) -> list[str] | None:
    """The neighbourhoods a choice stands for: itself when it is one of the
    build's, a borough's when the build covers several boroughs, else None."""
    if not choice:
        return None
    if choice in counts:
        return [choice]
    groups = grouped(counts)
    if len(groups) > 1 and choice in groups:
        return sorted(groups[choice])
    return None


def scope_words(names: list[str], most: int = 12) -> str:
    """The neighbourhoods in words: up to `most` by name ("Chelsea and West
    Village"), more by their boroughs ("Manhattan and Brooklyn")."""
    names = sorted(names)
    if len(names) > most:
        known = [b for b in grouped(dict.fromkeys(names, 0)) if b in BOROUGHS]
        return _and(known) if known else f"{len(names)} neighbourhoods"
    return _and(names) if names else "Chelsea"


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]

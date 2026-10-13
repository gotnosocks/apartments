"""Neighborhood scopes added after scope.py was frozen.

scope.py is hashed by saved Chelsea datasets, so its NEIGHBORHOODS table cannot
be edited. Importing this module registers further neighborhoods into that same
table at runtime; scope.py's behavior for existing neighborhoods is unchanged.
Each entry is (StreetEasy area slugs, StreetEasy area display names).
"""

from .scope import NEIGHBORHOODS

ADDED = {
    # StreetEasy area 116. Its child area NoHo (118) is a separate neighborhood
    # and is not included, matching how West Village is scoped.
    "greenwich-village": ({"greenwich-village"}, {"Greenwich Village"}),
    # StreetEasy areas Flatiron and Gramercy Park, crawled together (Ben, Oct 5 2026).
    # Child areas such as NoMad are separate neighborhoods and are not included.
    "flatiron-gramercy-park": (
        {"flatiron", "gramercy-park"},
        {"Flatiron", "Gramercy Park"},
    ),
    # Each its own crawl, scoped like Flatiron + Gramercy Park: one StreetEasy area,
    # without child areas (Ben, Oct 8 2026). Display names as StreetEasy's areaName.
    "nomad": ({"nomad"}, {"NoMad"}),
    "east-village": ({"east-village"}, {"East Village"}),
    "stuyvesant-town-pcv": ({"stuyvesant-town"}, {"Stuyvesant Town/PCV"}),
    # The first Brooklyn crawl, scoped the same way (Ben, Oct 13 2026). StreetEasy's
    # Downtown Brooklyn excludes Brooklyn Heights, DUMBO, Boerum Hill and Fort Greene.
    "downtown-brooklyn": ({"downtown-brooklyn"}, {"Downtown Brooklyn"}),
    # Crawled after Downtown Brooklyn in the same pass (Ben, Oct 13 2026), each on its own.
    "fort-greene": ({"fort-greene"}, {"Fort Greene"}),
    "boerum-hill": ({"boerum-hill"}, {"Boerum Hill"}),
    # The three crawled together as one scrape instead (Ben, Oct 13 2026 02:58Z).
    "downtown-brooklyn-fort-greene-boerum-hill": (
        {"downtown-brooklyn", "fort-greene", "boerum-hill"},
        {"Downtown Brooklyn", "Fort Greene", "Boerum Hill"},
    ),
    # StreetEasy area Midtown West (124) with its child areas Hudson Yards (146) and
    # Hell's Kitchen (152), as StreetEasy's own Midtown West search includes them (Ben,
    # Oct 13 2026). A building's areaName is its most specific area, so all three names.
    "midtown-west": (
        {"midtown-west", "hudson-yards", "hells-kitchen"},
        {"Midtown West", "Hudson Yards", "Hell's Kitchen"},
    ),
}

for _name, _value in ADDED.items():
    NEIGHBORHOODS.setdefault(_name, _value)


def choices():
    return tuple(sorted(NEIGHBORHOODS))

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
}

for _name, _value in ADDED.items():
    NEIGHBORHOODS.setdefault(_name, _value)


def choices():
    return tuple(sorted(NEIGHBORHOODS))

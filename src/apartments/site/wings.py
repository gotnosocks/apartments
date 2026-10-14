"""Complexes a data rule splits into model buildings by unit label.

The West Coast (95 Horatio St, lot 1006430001) is a single StreetEasy building
with two label schemes. A data rule gives each scheme its own model building:
three-digit units ("620") go to the-west-coast-west-wing, the older 6 to 7
story section on West and Horatio Streets; floor-and-letter units ("9L") stay
on the-west-coast, the 9 to 10 story Washington Street end.

The site shows each wing as its own building page under the complex's name,
with the wing in brackets, so every wing keeps its own level and trend. A
capture's listing carries StreetEasy's slug, so its unit label decides the wing,
as the rule decides it for the fit's rows.
"""

from __future__ import annotations

import re

# Every wing of a split complex: its slug, the complex's name, the wing's name.
WINGS = {
    "the-west-coast-west-wing": ("The West Coast", "West Street wing"),
    "the-west-coast": ("The West Coast", "Washington Street wing"),
}
# StreetEasy slugs of a split complex, then (label pattern, wing slug) in order:
# the first pattern to match the whole lower-cased unit label picks the wing.
SPLITS = {
    ("the-west-coast", "97-horatio-street-new_york"): (
        (re.compile(r"\d{3}"), "the-west-coast-west-wing"),
        (re.compile(r"\d+[a-z]+|ph.*"), "the-west-coast"),
    ),
}


def names(slugs) -> dict[str, str]:
    """{slug: shown name} for the wings among `slugs`, the build's buildings.
    A complex gets wing names only when the build has two or more of its
    wings, so a fit without the split keeps the plain building name."""
    present = set(slugs)
    out = {}
    for slug, (complex_name, wing) in WINGS.items():
        siblings = [s for s, (n, _) in WINGS.items() if n == complex_name]
        if slug in present and sum(s in present for s in siblings) > 1:
            out[slug] = f"{complex_name} ({wing})"
    return out


def wing(slug: str, label: str | None, fitted) -> str:
    """The model building for a listing on StreetEasy's `slug` with unit
    `label`: its wing when the label matches a wing's scheme and the fit has
    that wing (`fitted`, the fit's building slugs), and `slug` otherwise."""
    for pages, schemes in SPLITS.items():
        if slug not in pages or not label:
            continue
        for pattern, target in schemes:
            if pattern.fullmatch(label.lower()):
                return target if target in fitted else slug
    return slug

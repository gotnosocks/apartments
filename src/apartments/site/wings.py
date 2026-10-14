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
# StreetEasy slugs of a split complex, then the label pattern for the split-off
# wing, that wing's slug and the slug for every other label. The patterns
# follow the data rule `west-coast-wings-v1`, which runs after
# `building-joins-v1` folds the 97 Horatio page into the-west-coast.
SPLITS = {
    ("the-west-coast", "97-horatio-street-new_york"): (
        re.compile(r"\d{3}"),
        "the-west-coast-west-wing",
        "the-west-coast",
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
    `label`. A label matching the split-off wing's pattern goes to that wing
    when the fit has it (`fitted`, the fit's building slugs), and any other
    label goes to the complex's main slug. A fit without the wing, or a slug
    outside every split, leaves the slug as it is."""
    for pages, (pattern, split, main) in SPLITS.items():
        if slug in pages and split in fitted:
            if label and pattern.fullmatch(label.lower()):
                return split
            return main
    return slug

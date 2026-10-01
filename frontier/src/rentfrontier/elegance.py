"""How simple a design is, as a judged complexity score (lower is simpler).

Ben, 2026-10-01: the research seeks the Pareto frontier of fit quality
(PSIS-LOO), fit time and "model elegance/simplicity". How to measure it: "You
should use your judgement to evaluate the simplicity and elegance of each
design." The served model is the best fit, with ties broken by "which model is
simpler".

The judgement is written down here so that a review can check it and every
fit is rated the same way. A design's complexity is the sum of two parts:

- **Model structure** (`model_complexity`), from the run's recorded
  `ModelConfig`: points for each structural term a renter has to understand
  (`STRUCTURE`).
- **Features** (`feature_complexity`), from the feature set: points for the
  layers of facts it adds (`FEATURES`).

The points weigh how much a term asks of a reader, not how many parameters it
has:
- A term a renter already thinks in ("this building's premium") costs 1.
- A term that moves over time, or overlaps another term, costs more.
- A data control that is not a quality costs nothing.

A feature set or structural option that is not listed has no rating. The design
then cannot be served (`autoselect`) until a reviewed change rates it.
"""

from __future__ import annotations

# Structural terms: ModelConfig field -> (points, why). Bool fields count when
# true. `feature_slopes` counts per slope.
STRUCTURE = {
    "trend": (1, "the market over time: what rents are doing overall"),
    "season": (0, "the month of the year, read with the market trend"),
    "features": (0, "listing attributes; counted with the feature set"),
    "buildings": (1, "this building's premium beyond its apartments"),
    "units": (1, "this apartment's own premium beyond its listed features"),
    "market_drift": (1, "a straight-line market instead of the trend"),
    "building_walk": (
        2,
        (
            "each building's premium moving over time along its own path: a "
            "second clock beside the market's"
        ),
    ),
    "walk_t": (1, "a building's path can jump now and then"),
    "building_trend": (1, "each building's premium moving steadily"),
    "line_effects": (1, "apartments stacked in the same column share a layout"),
    "bedroom_time": (
        2,
        "each bedroom group's own market path, overlapping the market trend",
    ),
    "bedroom_slope": (1, "in some buildings larger apartments cost extra"),
    "feature_slopes": (
        1,
        (
            "per slope: in some buildings extra space, a bath or a floor is worth "
            "more or less than usual"
        ),
    ),
    "unit_t": (
        1,
        (
            "a few apartments differ a lot from their building without pulling the "
            "others' estimates"
        ),
    ),
    "unit_drift": (
        2,
        "this apartment's ask moving on its own, overlapping the building's path",
    ),
}

# Options that change how a term is parameterized or sampled, not what the
# model says: no points.
NEUTRAL = {
    "name",
    "noncentered",
    "coordinates",
    "trend_knot_months",
    "bedroom_time_knot_months",
    "walk_knot_months",
    "walk_zero_sum",
    "walk_min_rows_per_knot",
    "walk_anchor_data",
    "walk_nu_fixed",
    "nu_fixed",
    "unit_nu_fixed",
}

# Feature sets -> (points, why). Each set's points are its base's plus the
# layer it adds.
FEATURES = {
    "none": (0, "no listing attributes"),
    "base-v1": (
        3,
        (
            "what the apartment offers, priced the same everywhere: bedrooms, "
            "baths, size, floor, amenities, views"
        ),
    ),
    "pluto-v1": (5, "base-v1 + what the city records about the building"),
    "desc-v1": (4, "base-v1 + what the ad says (renovated, washer-dryer, ...)"),
    "unitbeds-v1": (4, "base-v1 + one apartment keeps its facts across listings"),
    "unitattrs-v1": (4, "as unitbeds-v1"),
    "unitlabels-v1": (4, "as unitbeds-v1, with penthouse/garden/lower-level flags"),
    "unitfloor-v1": (4, "as unitlabels-v1, with the unit label's floor"),
    "unitfloor-v2": (4, "as unitfloor-v1"),
    "unitdesc-v1": (5, "unitfloor-v2 + what the ad says"),
    **{
        f"unitdescpluto-v{v}": (
            7,
            (
                "unitdesc-v1 + what the city records about the building (age, "
                "height, size, type, landmark, alteration): a bundle of facts"
            ),
        )
        for v in (1, 2, 3, 4, 5)
    },
    "unitdescplutoloc-v1": (9, "unitdescpluto-v1 + a smooth location surface"),
    "unitdescplutotransit-v2": (8, "unitdescpluto-v1 + the walk to the subway"),
    "unitdescplutohpd-v1": (8, "unitdescpluto-v3 + housing-code violations"),
    "unitdescplutohpd-v2": (8, "as unitdescplutohpd-v1"),
    "unitfacing-v2": (8, "unitdescpluto-v3 + which street the apartment faces"),
    "unitfacing-v3": (8, "unitdescpluto-v3 + the streets the apartment looks onto"),
    "unitfacing-v4": (
        9,
        "unitfacing-v3 + a loud street on a low floor (an interaction)",
    ),
    "unitfacing-v5": (9, "as unitfacing-v4, on the corrected registry"),
    "unitnoise-v1": (10, "unitfacing-v5 + 311 noise complaints"),
    "wv-unitpluto-v1": (6, "unitfloor-v2 + the city's building facts"),
    "nb-pluto-base": (6, "as wv-unitpluto-v1, Chelsea and West Village"),
    "nb-unitpluto-v1": (7, "nb-pluto-base + the neighbourhood"),
    "nb-facing-v1": (10, "unitfacing-v4 + the neighbourhood"),
}


def model_complexity(config: dict) -> int | None:
    """Points for a recorded ModelConfig, or None if it has an unrated option."""
    total = 0
    for field, value in config.items():
        if field in NEUTRAL or field.endswith("_sd"):
            continue
        if field not in STRUCTURE:
            if value:
                return None
            continue
        points = STRUCTURE[field][0]
        if field == "feature_slopes":
            total += points * len(value or ())
        elif value:
            total += points
    return total


def feature_complexity(feature_set: str) -> int | None:
    rated = FEATURES.get(feature_set)
    return None if rated is None else rated[0]


def complexity(entry) -> int | None:
    """A board entry's (or run record's) complexity, or None if it is unrated."""
    m = model_complexity(entry["model"]) if len(entry["model"]) > 1 else None
    f = feature_complexity(entry["feature_set"])
    return None if m is None or f is None else m + f

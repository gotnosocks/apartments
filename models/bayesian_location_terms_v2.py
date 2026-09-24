"""Reader location terms for the building-drift + unit-drift model (v2).

The v1 module (`bayesian_location_terms`) is frozen by the selected and running
fits' protocol hashes, so the new experiment's extra term lives here and every
older version is delegated unchanged. Pure numpy; no PyMC import.

Per-unit drift: s_u * scale * (year(t) - ybar_u), where ybar_u is the unit's
mean training year (anchor-relative, as in the graph) and s_u ~ N(0, 1).
"""

from __future__ import annotations

import numpy as np

from . import bayesian_location_terms as v1

DRIFT_EXPERIMENT = "observable-bayesian-drift-experiment-v1"
COMBINED_EXPERIMENT = "observable-bayesian-combined-experiment-v1"
# Versions carrying per-unit drift on top of the structure terms.
DRIFT_VERSIONS = (DRIFT_EXPERIMENT, COMBINED_EXPERIMENT)
# Same location terms as the structure fit, with the attribute feature design.
ATTRIBUTE_EXPERIMENT = "observable-bayesian-attribute-structure-experiment-v1"
# The same terms again, with the intercept as the building-level mean.
EFFICIENT_STRUCTURE_EXPERIMENT = "observable-bayesian-efficient-structure-experiment-v1"


def _v1(protocol):
    if protocol.get("version") in (ATTRIBUTE_EXPERIMENT, EFFICIENT_STRUCTURE_EXPERIMENT):
        return {**protocol, "version": v1.STRUCTURE_EXPERIMENT}
    return protocol


def _years(design):
    return (np.arange(len(design.time.periods)) - design.time.anchor) / 12.0


def unit_year_centers(design, data):
    """Each unit's mean training year, exactly as in the v2 graph."""
    a = design.time.arrays(data)
    years = _years(design)
    n_units = len(design.time.unit_ids)
    totals = np.bincount(a["unit"], weights=years[a["period"]], minlength=n_units)
    return totals / np.maximum(np.bincount(a["unit"], minlength=n_units), 1)


def variable_dims(protocol):
    if protocol.get("version") in DRIFT_VERSIONS:
        return {
            "bedroom_time": ("bedroom_group", "period"),
            "building_time_scale": (),
            "unit_slope_scale": (),
        }
    return v1.variable_dims(_v1(protocol))


def lazy_variable_dims(protocol):
    if protocol.get("version") in DRIFT_VERSIONS:
        return {"building_time_z": ("building_knot",), "unit_slope_z": ("unit",)}
    return v1.lazy_variable_dims(_v1(protocol))


def prepare(protocol, design, data):
    if protocol.get("version") not in DRIFT_VERSIONS:
        return v1.prepare(_v1(protocol), design, data)
    as_structure = {**protocol, "version": v1.STRUCTURE_EXPERIMENT}
    return {
        **v1.prepare(as_structure, design, data),
        "unit_years": unit_year_centers(design, data),
    }


def expected_coords(protocol, design):
    if protocol.get("version") not in DRIFT_VERSIONS:
        return v1.expected_coords(_v1(protocol), design)
    as_structure = {**protocol, "version": v1.STRUCTURE_EXPERIMENT}
    return {
        **v1.expected_coords(as_structure, design),
        "unit": list(design.time.unit_ids),
    }


def unit_drift(z, scale, year, center):
    """z (samples,), scale (samples,) -> per-sample log contribution."""
    return scale * z * (year - center)


def row_terms(protocol, draws, frame, design, select=None, context=None):
    if protocol.get("version") not in DRIFT_VERSIONS:
        return v1.row_terms(_v1(protocol), draws, frame, design, select, context)
    as_structure = {**protocol, "version": v1.STRUCTURE_EXPERIMENT}
    terms = v1.row_terms(as_structure, draws, frame, design, select, context)
    a = design.time.arrays(frame)
    unit = a["unit"][0]
    if unit < 0:
        raise ValueError("Unit drift requires a fitted unit")
    z = select("unit_slope_z", unit, unit + 1)[:, 0]
    terms["unit_drift"] = unit_drift(
        z,
        draws["unit_slope_scale"],
        _years(design)[a["period"][0]],
        context["unit_years"][unit],
    )
    return terms

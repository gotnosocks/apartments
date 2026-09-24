"""Reader location terms for the building-drift + unit-drift model (v2).

The v1 module (`bayesian_location_terms`) is frozen by the selected and running
fits' protocol hashes, so the new experiment's extra term lives here and every
older version is delegated unchanged. Pure numpy; no PyMC import.

Per-unit drift: s_u * scale * (year(t) - ybar_u), where ybar_u is the unit's
mean training year (anchor-relative, as in the graph) and s_u ~ N(0, 1).

Combined v2 (``COMBINED_V2_EXPERIMENT``, graph ``bayesian_structure_graph_v5``)
adds, per row:

* per-building bedroom slope: tau * z_b * (min(bedrooms, 4) - 1);
* per-building feature slopes: sum_j tau_j * z_bj * x_j on raw design columns;
* a citywide random walk (saved per period as ``citywide_walk``);
* building walks centered across buildings: the saved common mode
  ``building_walk_common`` (per knot) is removed from each building's levels
  before its own training-month centering.

This is the LAST code-hash protocol version (Ben, September 24); later work
uses self-contained experiment scripts and a shared summary-output reader.
"""

from __future__ import annotations

import numpy as np

from . import bayesian_location_terms as v1

DRIFT_EXPERIMENT = "observable-bayesian-drift-experiment-v1"
COMBINED_EXPERIMENT = "observable-bayesian-combined-experiment-v1"
# The last code-hash protocol version: combined v1 plus graph v5 terms.
COMBINED_V2_EXPERIMENT = "observable-bayesian-combined-experiment-v2"
# Versions carrying per-unit drift on top of the structure terms.
DRIFT_VERSIONS = (DRIFT_EXPERIMENT, COMBINED_EXPERIMENT, COMBINED_V2_EXPERIMENT)
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
        dims = {
            "bedroom_time": ("bedroom_group", "period"),
            "building_time_scale": (),
            "unit_slope_scale": (),
        }
        if protocol.get("version") == COMBINED_V2_EXPERIMENT:
            dims.update(
                building_bedroom_slope_scale=(),
                building_feature_slope_scale=("slope_feature",),
                citywide_walk=("period",),
                building_walk_common=("building_walk_knot",),
            )
        return dims
    return v1.variable_dims(_v1(protocol))


def lazy_variable_dims(protocol):
    if protocol.get("version") in DRIFT_VERSIONS:
        dims = {"building_time_z": ("building_knot",), "unit_slope_z": ("unit",)}
        if protocol.get("version") == COMBINED_V2_EXPERIMENT:
            dims.update(
                building_bedroom_slope_z=("building",),
                building_feature_slope_z=("building_slope",),
            )
        return dims
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
    coords = {
        **v1.expected_coords(as_structure, design),
        "unit": list(design.time.unit_ids),
    }
    if protocol.get("version") == COMBINED_V2_EXPERIMENT:
        features = list(protocol["building_feature_slopes"])
        knots = len(coords["building_knot"]) // len(design.time.buildings)
        coords.update(
            building=list(design.time.buildings),
            slope_feature=features,
            building_slope=list(range(len(design.time.buildings) * len(features))),
            building_walk_knot=list(range(knots)),
        )
    return coords


def bedroom_step(bedrooms):
    """min(bedrooms, 4) - 1, as in graph v5's per-building bedroom slope."""
    return np.minimum(np.asarray(bedrooms, dtype=float), 4.0) - 1.0


def feature_columns(design, frame, names):
    """Raw (uncentered) design columns carrying per-building slopes: rows x features."""
    raw, raw_names, _ = design.raw_features(frame)
    if not set(names) <= set(raw_names):
        raise ValueError("Slope features missing from the feature design")
    return raw[:, [raw_names.index(n) for n in names]].astype(float)


def centered_building_walk(z, scale, years, basis_rows, center, common):
    """`v1.building_walk` with the cross-building common mode removed first.

    z (samples x K), scale (samples,), basis_rows (rows x K), center (K,),
    common (samples x K) -> samples x rows."""
    levels = scale[:, None] * np.sqrt(years) * np.cumsum(z, axis=1) - common
    return levels @ basis_rows.T - (levels @ center)[:, None]


def unit_drift(z, scale, year, center):
    """z (samples,), scale (samples,) -> per-sample log contribution."""
    return scale * z * (year - center)


def row_terms(protocol, draws, frame, design, select=None, context=None):
    if protocol.get("version") not in DRIFT_VERSIONS:
        return v1.row_terms(_v1(protocol), draws, frame, design, select, context)
    as_structure = {**protocol, "version": v1.STRUCTURE_EXPERIMENT}
    terms = v1.row_terms(as_structure, draws, frame, design, select, context)
    a = design.time.arrays(frame)
    if protocol.get("version") == COMBINED_V2_EXPERIMENT:
        terms.update(
            _combined_v2_terms(protocol, draws, frame, design, select, context, a)
        )
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


def _combined_v2_terms(protocol, draws, frame, design, select, context, a):
    building, period = a["building"][0], a["period"][0]
    width = context["basis"].shape[1]
    z = select("building_time_z", building * width, (building + 1) * width)
    features = list(protocol["building_feature_slopes"])
    n = len(features)
    slopes = select("building_feature_slope_z", building * n, (building + 1) * n)
    x = feature_columns(design, frame, features)[0]
    return {
        # Replaces v1's uncentered walk for the same building and month.
        "building_time": centered_building_walk(
            z,
            draws["building_time_scale"],
            protocol["building_knot_years"],
            context["basis"][[period]],
            context["centers"][building],
            draws["building_walk_common"],
        )[:, 0],
        "building_bedroom_slope": draws["building_bedroom_slope_scale"]
        * select("building_bedroom_slope_z", building, building + 1)[:, 0]
        * bedroom_step(frame.bedrooms.iloc[0]),
        "building_feature_slopes": (
            draws["building_feature_slope_scale"] * slopes * x[None]
        ).sum(1),
        "citywide_walk": draws["citywide_walk"][:, period],
    }

"""Spline feature design plus as-of unit attribute flags.

Like `bayesian_attribute_design`, but the three advertisement-text flags are
**as of each listing**: a listing is flagged when any of the same unit's own
captured descriptions dated at or before that listing's period matches. Later
ads' wording is never carried back onto earlier listings (the project's
no-backward-carry rule). ``penthouse_label`` stays a canonical unit-label flag,
a stable identity like the building.

The flagged audit IDs, patterns and the description archive's manifest hash
are saved in the design, so reconstruction needs no text. A missing
description is "not flagged", never evidence of absence.
"""

from __future__ import annotations

import re

import numpy as np

from . import bayesian_floor_spline_design as spline
from .bayesian_attribute_design import (
    LABEL_PATTERNS,
    PRIOR_SCALE,
    TEXT_PATTERNS,
    unit_label,
)

VERSION = "asof-attribute-spline-design-v1"
ATTRIBUTES = (
    "penthouse_label",
    "duplex_asof",
    "private_outdoor_asof",
    "shared_bath_asof",
)
TEXT_SOURCES = {
    "duplex_asof": TEXT_PATTERNS["duplex_unit"],
    "private_outdoor_asof": TEXT_PATTERNS["private_outdoor_unit"],
    "shared_bath_asof": TEXT_PATTERNS["shared_bath_unit"],
}


def attribute_audits(data, captures):
    """Flagged audit IDs per attribute; ``captures`` is ``{audit_id: [capture dicts]}``."""
    label = re.compile(LABEL_PATTERNS["penthouse_label"])
    result = {
        "penthouse_label": sorted(
            a
            for a, url in zip(data.audit_id, data.canonical_unit_url)
            if label.match(unit_label(url))
        )
    }
    ordered = data[["audit_id", "unit_id", "period"]].sort_values(
        ["unit_id", "period", "audit_id"]
    )
    for name, pattern in TEXT_SOURCES.items():
        regex = re.compile(pattern, re.I)
        own = ordered.audit_id.map(
            lambda audit: any(
                regex.search(c.get("description") or "")
                for c in captures.get(audit) or []
            )
        )
        asof = own.groupby(ordered.unit_id.to_numpy()).cummax()
        result[name] = sorted(ordered.audit_id[asof.to_numpy()])
    return result


def policy():
    return {
        "label_patterns": dict(LABEL_PATTERNS),
        "text_patterns": dict(TEXT_SOURCES),
        "prior_scale": PRIOR_SCALE,
        "as_of": "A listing is flagged when the unit's own ads at or before its period match; never backward.",
        "missing": "No description or no match means not flagged; never evidence of absence.",
    }


class FeatureDesign(spline.FeatureDesign):
    def __init__(
        self,
        train,
        spec="full_half_balance",
        *,
        floor_prior_scale=0.10,
        attribute_audits,
        evidence_manifest_sha256,
    ):
        if set(attribute_audits) != set(ATTRIBUTES):
            raise ValueError(
                "Attribute flags must cover exactly the declared attributes"
            )
        self.attribute_names = list(ATTRIBUTES)
        self.attribute_audits = {k: sorted(attribute_audits[k]) for k in ATTRIBUTES}
        self.attribute_policy = policy()
        self.evidence_manifest_sha256 = evidence_manifest_sha256
        super().__init__(train, spec, floor_prior_scale=floor_prior_scale)
        self.version = VERSION
        self._validate_saved_structure()

    def attribute_matrix(self, data):
        return np.column_stack(
            [
                data.audit_id.isin(set(self.attribute_audits[n])).to_numpy(dtype=float)
                for n in self.attribute_names
            ]
        )

    def raw_features(self, data):
        matrix, names, scales = super().raw_features(data)
        split = len(names) - len(
            self.floor_knots
        )  # spline coordinates plus the unknown indicator
        return (
            np.column_stack(
                [matrix[:, :split], self.attribute_matrix(data), matrix[:, split:]]
            ),
            [*names[:split], *self.attribute_names, *names[split:]],
            [
                *scales[:split],
                *[PRIOR_SCALE] * len(self.attribute_names),
                *scales[split:],
            ],
        )

    def _validate_saved_structure(self):
        own = self.version
        if own not in (VERSION, spline.VERSION):
            raise ValueError("Unsupported as-of attribute design version")
        self.version = spline.VERSION
        try:
            super()._validate_saved_structure()
        finally:
            self.version = own
        if own == VERSION:
            names = self.raw_feature_names
            floor = len(self.floor_knots)
            if (
                self.attribute_names != list(ATTRIBUTES)
                or self.attribute_policy != policy()
                or set(self.attribute_audits) != set(ATTRIBUTES)
                or names[len(names) - floor - len(ATTRIBUTES) : len(names) - floor]
                != list(ATTRIBUTES)
                or not isinstance(self.evidence_manifest_sha256, str)
                or len(self.evidence_manifest_sha256) != 64
            ):
                raise ValueError(
                    "Saved as-of attribute columns, policy or evidence binding differ"
                )

"""Spline feature design plus unit attribute flags (label and advertisement text).

Adds four 0/1 unit attributes to `bayesian_floor_spline_design`, placed before
the floor columns so every spline check still applies:

* ``penthouse_label``: the canonical unit label starts with ``ph``/``penthouse``;
* ``duplex_unit``, ``private_outdoor_unit``, ``shared_bath_unit``: any of the
  unit's own captured advertisement descriptions matches the declared pattern.

Flags are unit-level because ad text varies between relistings while the
attribute should not. The flagged unit IDs, patterns and the description
archive's manifest hash are saved in the design, so reconstruction needs no
text. A missing description is "not flagged", never evidence of absence; these
are reported-attribute associations, not verified physical features.
"""
from __future__ import annotations

import re

import numpy as np

from . import bayesian_floor_spline_design as spline

VERSION = 'unit-attribute-spline-design-v1'
PRIOR_SCALE = .2
LABEL_PATTERNS = {'penthouse_label': r'^(?:ph|penthouse)'}
TEXT_PATTERNS = {
    'duplex_unit': r'\b(?:duplex|triplex)\b',
    'private_outdoor_unit': (r'\b(?:private|your own|own private|exclusive)\s+(?:outdoor space|terrace|balcony|'
                             r'roof ?deck|rooftop|garden|patio|backyard|yard)'),
    'shared_bath_unit': r'\b(?:sro|single room occupancy|shared (?:bath|baths|bathroom|bathrooms|kitchen)|share ?bath)\b',
}
ATTRIBUTES = (*LABEL_PATTERNS, *TEXT_PATTERNS)


def unit_label(url):
    return str(url).rstrip('/').rsplit('/', 1)[-1].lower()


def attribute_units(data, captures):
    """Flagged unit IDs per attribute; ``captures`` is ``{audit_id: [capture dicts]}``."""
    result = {}
    for name, pattern in LABEL_PATTERNS.items():
        regex = re.compile(pattern)
        result[name] = sorted({u for u, url in zip(data.unit_id, data.canonical_unit_url) if regex.match(unit_label(url))})
    for name, pattern in TEXT_PATTERNS.items():
        regex = re.compile(pattern, re.I)
        result[name] = sorted({u for u, audit in zip(data.unit_id, data.audit_id)
                               if any(regex.search(c.get('description') or '') for c in captures.get(audit) or [])})
    return result


def policy():
    return {'label_patterns': dict(LABEL_PATTERNS), 'text_patterns': dict(TEXT_PATTERNS), 'prior_scale': PRIOR_SCALE,
            'unit_level': 'A unit is flagged when any of its own captured advertisements matches.',
            'missing': 'No description or no match means not flagged; never evidence of absence.'}


class FeatureDesign(spline.FeatureDesign):
    def __init__(self, train, spec='full_half_balance', *, floor_prior_scale=.10, attribute_units,
                 evidence_manifest_sha256):
        if set(attribute_units) != set(ATTRIBUTES):
            raise ValueError('Attribute units must cover exactly the declared attributes')
        self.attribute_names = list(ATTRIBUTES)
        self.attribute_units = {k: sorted(attribute_units[k]) for k in ATTRIBUTES}
        self.attribute_policy = policy()
        self.evidence_manifest_sha256 = evidence_manifest_sha256
        super().__init__(train, spec, floor_prior_scale=floor_prior_scale)
        self.version = VERSION
        self._validate_saved_structure()

    def attribute_matrix(self, data):
        return np.column_stack([data.unit_id.isin(set(self.attribute_units[name])).to_numpy(dtype=float)
                                for name in self.attribute_names])

    def raw_features(self, data):
        matrix, names, scales = super().raw_features(data)
        floor = len(self.floor_knots)  # spline coordinates plus the unknown indicator
        split = len(names)-floor
        return (np.column_stack([matrix[:, :split], self.attribute_matrix(data), matrix[:, split:]]),
                [*names[:split], *self.attribute_names, *names[split:]],
                [*scales[:split], *[PRIOR_SCALE]*len(self.attribute_names), *scales[split:]])

    def _validate_saved_structure(self):
        own = self.version
        if own not in (VERSION, spline.VERSION):
            raise ValueError('Unsupported attribute design version')
        self.version = spline.VERSION
        try:
            super()._validate_saved_structure()
        finally:
            self.version = own
        if own == VERSION:
            names = self.raw_feature_names
            floor = len(self.floor_knots)
            if (self.attribute_names != list(ATTRIBUTES) or self.attribute_policy != policy()
                    or set(self.attribute_units) != set(ATTRIBUTES)
                    or names[len(names)-floor-len(ATTRIBUTES):len(names)-floor] != list(ATTRIBUTES)
                    or not isinstance(self.evidence_manifest_sha256, str) or len(self.evidence_manifest_sha256) != 64):
                raise ValueError('Saved attribute columns, policy or evidence binding differ')

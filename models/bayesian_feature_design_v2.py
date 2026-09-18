"""Restore frozen training column order when loading v1 feature-design JSON.

The original serializer sorts dictionary keys, while raw_features iterates those
dictionaries. Restoring the declared training order is necessary before applying
saved active-column positions, means, or posterior beta draws.
"""
from __future__ import annotations

import numpy as np

from .bayesian_feature_model import FeatureDesign, amenity

VERSION = 'ordered-bayesian-feature-design-loader-v2'


def load_design(root, data):
    design = FeatureDesign.load(root)
    for name, order in [('numeric', amenity.NUMERIC), ('categories', amenity.CATEGORIES)]:
        saved = getattr(design, name)
        if set(saved) != set(order):
            raise ValueError('Saved feature metadata differs from frozen training inventory: '+name)
        setattr(design, name, {key: saved[key] for key in order})
    # Verify semantic column identity before any positional beta multiplication.
    _, names, scales = design.raw_features(data.iloc[:1])
    if (design.active.dtype != np.dtype(bool) or design.active.ndim != 1
            or len(design.active) != len(names)
            or [name for name, active in zip(names, design.active) if active] != design.features
            or len(design.means) != len(design.features)
            or not np.array_equal(np.asarray(scales)[design.active], design.prior_scales)):
        raise ValueError('Saved active columns do not match frozen training feature order')
    return design

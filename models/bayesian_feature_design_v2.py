"""Restore frozen training column order when loading v1 feature-design JSON.

The original serializer sorts dictionary keys, while raw_features iterates those
dictionaries. Restoring the declared training order is necessary before applying
saved active-column positions, means, or posterior beta draws.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

from .bayesian_feature_model import FeatureDesign, amenity

VERSION = 'ordered-bayesian-feature-design-loader-v2'


def load_design(root, data, protocol=None):
    from . import bayesian_floor_elevator_contract as interaction_contract
    if protocol and protocol.get('version') == interaction_contract.EXPERIMENT:
        from . import bayesian_floor_elevator_design as interaction
        design = interaction.FeatureDesign.load(root)
        if (protocol.get('feature_design_version') != interaction.VERSION
                or protocol.get('base_feature_design_version') != interaction.floor.VERSION
                or protocol.get('interaction_mode') != design.mode
                or protocol.get('interaction_prior_scale') != design.interaction_prior_scale
                or protocol.get('interaction_thresholds') != list(interaction.THRESHOLDS)
                or protocol.get('interaction_policy') != interaction_contract.POLICY
                or protocol.get('floor_increment_prior_scale') != design.base.floor_increment_prior_scale
                or protocol.get('floor_levels') != design.floor_levels
                or protocol.get('floor_thresholds') != design.floor_thresholds):
            raise ValueError('Saved interaction design differs from protocol')
        design.matrix(data.iloc[:1])
        return design
    if (Path(root)/'interaction-design.json').exists():
        raise ValueError('Interaction design requires explicit v5 protocol; base-only loading is unsafe')
    if protocol and protocol.get('version') == 'observable-bayesian-floor-experiment-v4':
        from . import bayesian_floor_increment_design as floor
        if protocol.get('feature_design_version') != floor.VERSION:
            raise ValueError('Unsupported floor feature design version')
        design = floor.FeatureDesign.load(root)
        if design.floor_increment_prior_scale != protocol.get('floor_increment_prior_scale'):
            raise ValueError('Saved floor prior differs from protocol')
        design.matrix(data.iloc[:1])
        return design
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

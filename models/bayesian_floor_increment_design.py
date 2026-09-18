"""Research-only listed-floor increments; existing fitted designs are untouched.

Observed ordered levels define thresholds. A gap contrast is not evidence for
separate increments at unseen floors. No posterior fit is produced here.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import bayesian_feature_model as reference

VERSION = 'observed-listed-floor-increment-design-v1'


def listed_floor_values(data):
    """Existing listed_floor/advertised_floor semantics, never physical height."""
    values = [reference.pricing._numeric_feature('listed_floor',
              reference.amenity.feature_record(row).get('listed_floor'))
              for row in data.to_dict('records')]
    return np.array([np.nan if value is None else value for value in values], dtype=float)


def _name(threshold):
    return 'listed_floor_gt_' + format(threshold, '.17g')


def _support(data, values, levels):
    by_level = []
    buildings, units = [], []
    for level in levels:
        selected = data.loc[values == level]
        b, u = set(selected.building), set(selected.unit_id)
        buildings.append(b); units.append(u)
        by_level.append({'level': level, 'rows': len(selected), 'units': len(u), 'buildings': len(b)})
    return {'known_rows': int(np.isfinite(values).sum()), 'unknown_rows': int((~np.isfinite(values)).sum()),
            'levels': by_level, 'adjacent_supported_contrasts': [
                {'feature': _name(low), 'threshold': low, 'lower_supported_level': low,
                 'upper_supported_level': high, 'label_distance': high-low,
                 'has_unobserved_integer_labels_between': math.floor(low) + 1 < high,
                 'shared_buildings': len(buildings[i] & buildings[i+1]),
                 'shared_units': len(units[i] & units[i+1]),
                 'interpretation': f'Listed-floor label {low:g} to {high:g}; one observed-level contrast, not separate unobserved-floor increments.'}
                for i, (low, high) in enumerate(zip(levels[:-1], levels[1:]))]}


class FeatureDesign(reference.FeatureDesign):
    """Replace only the listed-floor linear term with supported step increments."""

    def __init__(self, train, spec='full_half_balance', *, floor_increment_prior_scale=.15):
        if (isinstance(floor_increment_prior_scale, bool) or not isinstance(floor_increment_prior_scale, (int, float))
                or not math.isfinite(floor_increment_prior_scale) or floor_increment_prior_scale <= 0):
            raise ValueError('Floor increment prior scale must be finite and positive')
        values = listed_floor_values(train)
        levels = np.unique(values[np.isfinite(values)]).tolist()
        self.version = VERSION
        self.floor_levels = levels
        self.floor_thresholds = levels[:-1]
        self.floor_increment_prior_scale = float(floor_increment_prior_scale)
        self.floor_support = _support(train, values, levels)
        self.floor_policy = {
            'source': 'listed_floor, falling back to advertised_floor under existing normalization',
            'unknown': 'All floor thresholds zero plus a separate unknown indicator when it varies in training.',
            'unseen_known_levels': 'Reject public transformation; require refit or a separately supported research design.',
            'prior': 'Independent zero-mean Normal increments with configurable common scale; signs unconstrained.',
            'cumulative_extreme_log_prior_sd': self.floor_increment_prior_scale * math.sqrt(len(self.floor_thresholds)),
            'research_status': 'Unfitted research design; sparse source support does not establish useful floor effects.'}
        super().__init__(train, spec)
        # The reference constructor computes this metadata, but the replacement
        # never uses its old standardized linear column or prior.
        self.numeric.pop('listed_floor', None)
        self.numeric_order = list(self.numeric)
        self.category_order = list(self.categories)
        _, names, scales = self.raw_features(train.iloc[:1])
        self.raw_feature_names = names
        self.raw_prior_scales = np.asarray(scales, dtype=float)
        self._validate_saved_structure()

    def _check_floor_support(self, values):
        known = np.isfinite(values)
        unseen = np.unique(values[known & ~np.isin(values, self.floor_levels)])
        if len(unseen):
            raise ValueError('Known listed floor absent from fitted support: ' + ', '.join(f'{v:g}' for v in unseen))

    def raw_features(self, data):
        # Inherited constructor calls this after establishing numeric/categories.
        matrix, names, scales = super().raw_features(data)
        keep = [i for i, name in enumerate(names) if name not in ('listed_floor', 'listed_floor.unknown')]
        values = listed_floor_values(data)
        self._check_floor_support(values)
        known = np.isfinite(values)
        columns = [matrix[:, i] for i in keep]
        names = [names[i] for i in keep]
        scales = [scales[i] for i in keep]
        for threshold in self.floor_thresholds:
            columns.append((known & (values > threshold)).astype(float))
            names.append(_name(threshold)); scales.append(self.floor_increment_prior_scale)
        columns.append((~known).astype(float)); names.append('listed_floor.unknown'); scales.append(.2)
        return np.column_stack(columns), names, scales

    def _validate_saved_structure(self):
        if self.version != VERSION or self.spec not in reference.SPECS:
            raise ValueError('Unsupported floor design version or bathroom specification')
        levels = np.asarray(self.floor_levels, dtype=float)
        if (levels.ndim != 1 or not np.isfinite(levels).all() or not np.array_equal(levels, np.unique(levels))
                or self.floor_thresholds != self.floor_levels[:-1]):
            raise ValueError('Floor levels or supported threshold order differs')
        if not math.isfinite(self.floor_increment_prior_scale) or self.floor_increment_prior_scale <= 0:
            raise ValueError('Invalid floor increment prior scale')
        expected_numeric = [name for name in reference.amenity.NUMERIC if name != 'listed_floor']
        if (self.numeric_order != expected_numeric or self.category_order != list(reference.amenity.CATEGORIES)
                or set(self.numeric) != set(self.numeric_order) or set(self.categories) != set(self.category_order)):
            raise ValueError('Saved ordered numeric/category inventory differs')
        # Reconstruct semantic names without depending on JSON object key order.
        names, scales = [], []
        names.extend(f'bedrooms_gt_{i}' for i in range(5)); scales.extend([.25]*5)
        if self.spec == 'linear_total':
            names.append('bathrooms_above_one'); scales.append(.25)
        elif self.spec == 'incremental_total':
            names.extend(f'bathrooms_gt_{value:g}' for value in np.arange(1,5,.5)); scales.extend([.25]*8)
        else:
            names.extend(f'full_bathrooms_gt_{i}' for i in range(1,5)); scales.extend([.25]*4)
            names.extend(f'half_bathrooms_gt_{i}' for i in range(2)); scales.extend([.2]*2)
            if self.spec == 'full_half_balance':names.append('full_bathroom_shortfall'); scales.append(.2)
        names.extend(['bathroom_composition_unknown','log_size_within_bedrooms','size_missing']); scales.extend([.2,.35,.2])
        for name in self.numeric_order:
            if self.numeric[name]['varying']:names.append(name); scales.append(.15)
            if self.numeric[name]['missing_varying']:names.append(name+'.unknown'); scales.append(.2)
        for name in self.category_order:
            meta=self.categories[name]
            if not meta['levels']:continue
            for index in range(len(meta['levels'])-1):names.append(f'{name}.contrast_{index}'); scales.append(.15)
            if meta['missing_varying']:names.append(name+'.unknown'); scales.append(.2)
        names.extend(_name(k) for k in self.floor_thresholds); scales.extend([self.floor_increment_prior_scale]*len(self.floor_thresholds))
        names.append('listed_floor.unknown'); scales.append(.2)
        if (names != self.raw_feature_names or self.active.dtype != np.dtype(bool) or self.active.shape != (len(names),)
                or [n for n, active in zip(names,self.active) if active] != self.features
                or not np.array_equal(self.raw_prior_scales,np.asarray(scales))
                or not np.array_equal(self.prior_scales,np.asarray(scales)[self.active])
                or self.means.shape != (len(self.features),) or not np.isfinite(self.means).all()):
            raise ValueError('Saved floor feature order, active mask, centering, or priors differ')

    def save(self, root):
        self._validate_saved_structure()
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.time.save(root/'time-design.json')
        metadata={key:value for key,value in self.__dict__.items() if key!='time'}
        for key in ('active','prior_scales','means','raw_prior_scales'):metadata[key]=metadata[key].tolist()
        (root/'feature-design.json').write_text(json.dumps(metadata,sort_keys=True,indent=2,allow_nan=False)+'\n')

    @classmethod
    def load(cls, root):
        root=Path(root);result=cls.__new__(cls)
        result.__dict__.update(json.loads((root/'feature-design.json').read_text()))
        for key in ('active','prior_scales','means','raw_prior_scales'):
            setattr(result,key,np.array(getattr(result,key)))
        result._validate_saved_structure()
        result.numeric={key:result.numeric[key] for key in result.numeric_order}
        result.categories={key:result.categories[key] for key in result.category_order}
        result.time=reference.base.Design.load(root/'time-design.json')
        return result

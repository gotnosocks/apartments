"""Source-verified analysis of retained joint PyMC posterior draws; never fits.

Intervals describe latent conditional median asking rent. Encoded contributions
are additive posterior mean log terms, not causal premiums or dollar allocations.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from threading import RLock

from threadpoolctl import threadpool_limits

import numpy as np
import pandas as pd
import xarray as xr

from apartments import pricing
from models import bayesian_feature_report as report
from models import bayesian_location_terms as location_terms
from models.bayesian_feature_design_v2 import load_design
from models.bayesian_source_sensitivity import verify_design, reconstruction_dependencies


_RECONSTRUCTION_LOCK = RLock()

def bundle_signature(*directories):
    """Cache invalidation hint; loading separately verifies content hashes."""
    stamps = []
    for directory in directories:
        root = Path(directory).resolve()
        meta = json.loads((root/'complete.json').read_text())
        for name in ['complete.json', *sorted(meta['files'])]:
            path = (root/name).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Bundle file escapes its directory')
            stat = path.stat()
            stamps.append((str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return hashlib.sha256(json.dumps(stamps).encode()).hexdigest()


def _frame(rows):
    frame = pd.DataFrame(rows)
    frame.period = pd.to_datetime(frame.period)
    frame.square_feet = pd.to_numeric(frame.square_feet, errors='coerce')
    return frame


def _interval(values, transform=None):
    values = np.asarray(values)
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite posterior quantity')
    quantiles = np.quantile(values, [.025, .5, .975])
    if transform is not None:
        quantiles = transform(quantiles)
    if not np.isfinite(quantiles).all():
        raise ValueError('Nonfinite posterior interval')
    return dict(zip(('lower_95', 'median', 'upper_95'), map(float, quantiles)))


def contrast_diagnostics(values, shape):
    """Gate newly requested joint functions, not just previously saved parameters."""
    import arviz as az
    stochastic = {k: (('chain', 'draw'), np.asarray(v).reshape(shape))
                  for k, v in values.items() if np.ptp(v) != 0}
    if not stochastic:
        return {'acceptable': True, 'deterministic': True}
    stats = az.summary(xr.Dataset(stochastic), kind='diagnostics', round_to='none')
    numbers = stats[['r_hat', 'ess_bulk', 'ess_tail']].to_numpy()
    finite = bool(np.isfinite(numbers).all())
    result = {'acceptable': finite and bool((stats.r_hat < 1.01).all()
                and (stats.ess_bulk >= 400).all() and (stats.ess_tail >= 400).all()),
              'variables': {name: {k: float(v) if math.isfinite(v) else None
                                  for k, v in row.items()} for name, row in stats.to_dict('index').items()}}
    return result


class BayesianAnalysis:
    @classmethod
    def load(cls, experiment, dataset):
        self = cls()
        self.experiment, self.dataset = Path(experiment), Path(dataset)
        self._directories = (self.experiment/'protocol', self.experiment/'fit', self.dataset)
        initial = bundle_signature(*self._directories)
        self.summary, self.manifests = report.build_report(self.experiment, self.dataset)
        self.protocol = json.loads((self.experiment/'protocol'/'protocol.json').read_text())
        # Frozen designs were constructed with one BLAS thread. Exact JSON
        # centers can change in the last bit with parallel reductions; reproduce
        # that arithmetic instead of relaxing the source/design identity check.
        with _RECONSTRUCTION_LOCK, threadpool_limits(limits=1, user_api='blas'):
            self.design_verification = verify_design(self.experiment, self.dataset, self.protocol, self.manifests)
        self._source = report.jsonl((self.dataset/'observations.jsonl').read_bytes())
        self._saved_residuals = report.jsonl((self.experiment/'fit'/'residuals.jsonl').read_bytes())
        self._rows = {r['audit_id']: r for r in self._source}
        self._residuals = {r['audit_id']: r for r in self._saved_residuals}
        self._data = _frame(self._source)
        self.design = load_design(self.experiment/'fit', self._data, self.protocol)
        self._posterior = xr.open_dataset(self.experiment/'fit'/'posterior.nc', group='posterior',
                                          engine='h5netcdf', chunks=None, cache=False)
        self._groups = OrderedDict()
        self._details = OrderedDict()
        self._field_observations = {}
        try:
            self._validate_posterior()
            self._draws = {name: self._values(self._posterior[name]) for name in
                ('alpha', 'beta', 'trend_coefficients', 'annual_drift', 'season_coefficients', 'sigma_unit')}
            for name in location_terms.variable_dims(self.protocol):
                self._draws[name] = self._values(self._posterior[name])
            if np.any(self._draws['sigma_unit'] <= 0):
                raise ValueError('Nonpositive unit scale')
            self._signature = initial
            self._code_stamps = self._implementation_stamps()
            self._fresh()
            self.fields = self._fields()
        except Exception:
            self.close()
            raise
        return self

    def _validate_posterior(self):
        p, d = self._posterior, self.design.time
        dims = {'alpha': (), 'beta': ('feature',), 'trend_coefficients': ('trend_basis',),
                'annual_drift': (), 'season_coefficients': ('season_basis',),
                'building_effect': ('building',), 'sigma_unit': (), 'unit_z': ('unit',), 'sigma': ()}
        coords = {'feature': self.design.features, 'building': d.buildings, 'unit': d.unit_ids,
                  'trend_basis': np.arange(d.time_matrix.shape[1]),
                  'season_basis': np.arange(d.season_matrix.shape[1])}
        dims.update(location_terms.variable_dims(self.protocol))
        coords.update(location_terms.expected_coords(self.protocol, self.design))
        mode = self.protocol.get('residual_scale', 'shared')
        residual_names = {'residual_bedroom_z', 'residual_bedroom_scale', 'sigma_by_bedroom', 'residual_bedroom_offset'}
        if mode == 'bedroom':
            coords['residual_bedroom'] = self.protocol['graph_configuration']['residual_bedroom_levels']
            dims.update(residual_bedroom_z=('residual_bedroom',), residual_bedroom_scale=(),
                        sigma_by_bedroom=('residual_bedroom',))
            if self.protocol.get('residual_parameterization', 'noncentered') == 'centered':
                dims['residual_bedroom_offset'] = ('residual_bedroom',)
            elif 'residual_bedroom_offset' in p:
                raise ValueError('Noncentered fit contains centered residual draws')
        elif residual_names & set(p.data_vars) or 'residual_bedroom' in p.coords:
            raise ValueError('Shared fit contains bedroom residual draws')
        self._shape = (self.protocol['chains'], self.protocol['draws'])
        if tuple(p.sizes.get(k) for k in ('chain', 'draw')) != self._shape:
            raise ValueError('Retained posterior chain/draw count differs from protocol')
        for axis in ('chain', 'draw'):
            if axis not in p.coords or len(np.unique(p[axis])) != p.sizes[axis]:
                raise ValueError('Invalid posterior sample coordinates')
        for name, expected in coords.items():
            if name not in p.coords or not np.array_equal(p[name].values, expected):
                raise ValueError('Posterior coordinate differs from ordered design: '+name)
        for name, extra in dims.items():
            if name not in p or p[name].dims != ('chain', 'draw', *extra):
                raise ValueError('Posterior dimensions differ: '+name)
        sigma = self._values(p['sigma'])
        if np.any(sigma <= 0):
            raise ValueError('Nonpositive residual scale')
        if mode == 'bedroom':
            z, scale, by_bedroom = (self._values(p[name]) for name in
                                    ('residual_bedroom_z', 'residual_bedroom_scale', 'sigma_by_bedroom'))
            if (np.any(scale <= 0) or np.any(by_bedroom <= 0)
                    or not np.allclose(z.sum(axis=1), 0., rtol=0, atol=1e-10)
                    or not np.allclose(by_bedroom, sigma[:, None]*np.exp(scale[:, None]*z), rtol=1e-10, atol=0)):
                raise ValueError('Bedroom residual scales differ from joint parameterization')
            if 'residual_bedroom_offset' in dims and not np.allclose(
                    self._values(p['residual_bedroom_offset']), scale[:, None]*z, rtol=1e-10, atol=1e-12):
                raise ValueError('Centered residual offsets differ from joint parameterization')

    @staticmethod
    def _values(array):
        result = np.asarray(array.values, dtype=float)
        if not np.isfinite(result).all():
            raise ValueError('Nonfinite posterior draws')
        return result.reshape((-1, *result.shape[2:]))

    def _implementation_stamps(self):
        _, paths = reconstruction_dependencies(self.protocol)
        paths.append(Path(__import__('models.bayesian_feature_design_v2', fromlist=['']).__file__))
        return [(str(p), p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in paths]

    def _fresh(self):
        if self._posterior is None:
            raise ValueError('Analysis workspace is closed')
        if (bundle_signature(*self._directories) != self._signature
                or self._implementation_stamps() != self._code_stamps):
            raise ValueError('Stale analysis: source, fit, protocol or reconstruction code changed; reload')

    @property
    def rows(self):
        self._fresh()
        return deepcopy(self._source)

    @property
    def residuals(self):
        self._fresh()
        return deepcopy(self._saved_residuals)

    def close(self):
        if getattr(self, '_posterior', None) is not None:
            self._posterior.close()
            self._posterior = None
        self._groups = OrderedDict()

    def _group(self, name, axis, value):
        key = (name, value)
        if key not in self._groups:
            # Selection MUST precede materialization: never load all unit draws.
            self._groups[key] = self._values(self._posterior[name].sel({axis: value}))
            if len(self._groups) > 32:
                self._groups.popitem(last=False)
        self._groups.move_to_end(key)
        return self._groups[key]

    def _terms(self, row):
        frame = _frame([row]); d = self.design.time; a = d.arrays(frame); s = self._draws
        x = self.design.matrix(frame)[0]
        period, month = a['period'][0], a['season'][0]
        terms = {'intercept': s['alpha'],
            'trend': s['trend_coefficients'] @ (d.time_matrix-d.time_center)[period],
            'annual_drift': s['annual_drift']*(d.linear_time-d.linear_center)[period],
            'season': s['season_coefficients'] @ (d.season_matrix-d.season_weights@d.season_matrix)[month],
            'building': self._group('building_effect', 'building', row['building']),
            'unit_within_building': s['sigma_unit']*self._group('unit_z', 'unit', row['unit_id'])}
        extra = location_terms.row_terms(getattr(self, 'protocol', {}), s, frame, self.design)
        for i, name in enumerate(self.design.features):
            terms['feature:'+name] = s['beta'][:, i]*x[i]
        # Follow the frozen runner's arithmetic order for fitted quantile parity.
        mu = (terms['intercept'] + s['beta'] @ x + terms['trend'] + terms['annual_drift']
              + terms['season'] + terms['building'] + terms['unit_within_building'])
        for name, value in extra.items():
            terms[name] = value
            mu = mu + value
        return mu, terms, x

    def _verify_fitted(self, audit_id, mu):
        interval = _interval(mu, np.exp)
        saved = self._residuals[audit_id]
        expected = [saved[k] for k in ('latent_rent_lower_95', 'fitted_rent', 'latent_rent_upper_95')]
        if not np.allclose(list(interval.values()), expected, rtol=1e-10, atol=1e-7):
            raise ValueError('Reconstructed posterior interval differs from saved residual')
        return interval

    def detail(self, audit_id):
        self._fresh()
        if audit_id in self._details:
            self._details.move_to_end(audit_id)
            return deepcopy(self._details[audit_id])
        row = self._rows[audit_id]; mu, terms, x = self._terms(row)
        interval = self._verify_fitted(audit_id, mu)
        saved = self._residuals[audit_id]
        contributions = [{'term': name, 'mean_log_contribution': float(value.mean()),
            'kind': ('reporting' if 'unknown' in name or 'missing' in name else
                     'floor_elevator' if name.startswith('feature:floor_elevator_') else
                     'floor_spline' if name.startswith('feature:listed_floor_spline_') else
                     'encoded_feature' if name.startswith('feature:') else name)} for name, value in terms.items()]
        grouped, grouped_draws = {}, {}
        for item in contributions:
            group = item['kind']; grouped[group] = grouped.get(group, 0.)+item['mean_log_contribution']
            grouped_draws[group] = grouped_draws.get(group, 0.)+terms[item['term']]
        derived = contrast_diagnostics({**terms, **{'group:'+k: v for k,v in grouped_draws.items()},
                                        'fitted_log_rent': mu}, self._shape)
        group_intervals = []
        if derived['acceptable']:
            for item in contributions:
                item['log_interval'] = _interval(terms[item['term']])
            group_intervals = [{'group': k, 'log_interval': _interval(v)} for k,v in grouped_draws.items()]
        result = {'audit_id': audit_id, 'source_record': deepcopy(row), 'residual': deepcopy(saved),
            'fitted_median_rent': interval, 'mean_log_rent': float(mu.mean()),
            'contributions': contributions, 'grouped_contributions': grouped,
            'grouped_contribution_intervals': group_intervals, 'contribution_diagnostics': derived,
            'feature_values': dict(zip(self.design.features, map(float, x))),
            'source_values': {field: self._value(row, field) for field in self.fields},
            'unit_history': deepcopy([r for r in self._saved_residuals if r['unit_id'] == row['unit_id']]),
            'draws': int(np.prod(self._shape)), 'uncertainty': 'Latent conditional median, not predictive or arithmetic mean rent.',
            'contribution_semantics': 'Posterior mean encoded log terms sum to E[mu]. Category basis terms are not premiums; bedroom terms alone do not hold area fixed. Unit offsets are within-building residual effects.',
            'warnings': self._warnings(row)}
        if not derived['acceptable']:
            result['warnings'].append('New contribution diagnostics failed; contribution intervals are withheld.')
        self._details[audit_id] = result
        if len(self._details) > 8:
            self._details.popitem(last=False)
        return deepcopy(result)

    def _fields(self):
        fields = {name: {'kind': 'numeric'} for name in
                  ('bedrooms', 'full_bathrooms', 'half_bathrooms', 'square_feet')}
        for name, meta in self.design.numeric.items():
            if meta['varying'] and name not in ('physical_floor_x_elevator', 'floor_label_gap'):
                fields[name] = {'kind': 'boolean' if name == 'elevator' or '.' in name else 'numeric'}
        for name, meta in self.design.categories.items():
            if len(meta['levels']) > 1:
                fields[name] = {'kind': 'category', 'options': list(meta['levels'])}
        if len(getattr(self.design,'floor_levels',[])) > 1:
            fields['listed_floor'] = {'kind':'numeric','observed_levels':self.design.floor_levels}
        return fields

    def _warnings(self, row):
        warnings = ['Conditional model association, not a causal renovation value or personal willingness to pay.',
                    'Building and within-building unit effects are held fixed; offsets absorb omitted attributes.']
        if getattr(self, 'protocol', {}).get('version') == report.EXPERIMENT_BEDROOM_TIME:
            warnings.append('Each bedroom group (studio, 1, 2, 3+) has its own smooth deviation from the Chelsea trend; changing bedrooms also changes that time term.')
        if getattr(self, 'protocol', {}).get('version') in report.SPLINE_FAMILY:
            warnings.append('Listed-floor contrasts use a regularized natural cubic spline across observed labels. Smoothness shares information across floors; sparse same-building support and prior sensitivity limit interpretation. This does not measure physical height.')
        elif hasattr(self.design,'floor_thresholds'):
            warnings.append('Listed-floor increments compare observed labels; gaps and sparse same-building support limit interpretation. They do not measure physical height.')
        else:
            warnings.append('This accepted fit uses linear standardized floor terms and configured interactions; encoded log contributions are not per-floor prices.')
        if getattr(self, 'protocol', {}).get('version') == report.EXPERIMENT_V5:
            warnings.append('The floor/elevator interaction varies only across floors 2–5 and then saturates. Unknown access uses the midpoint convention; marginal endpoint support does not establish joint support.')
        if report.composition(row) is None:
            warnings.append('Full/half bathroom composition is unknown or disputed; missing evidence is not zero.')
        if pricing._numeric_feature('square_feet', row.get('square_feet')) is None:
            warnings.append('Area is unreported; bedroom-specific reference area is used by the encoding.')
        return warnings

    def _value(self, row, field):
        if field in ('full_bathrooms', 'half_bathrooms'):
            composition = report.composition(row)
            return composition[0 if field == 'full_bathrooms' else 1] if composition else None
        if field in self.design.categories:
            value = pricing._category(row.get(field))
            return value if value in self.design.categories[field]['levels'] else None
        if field in self.design.numeric or field == 'listed_floor':
            from models.amenity_rent_model import feature_record
            value = pricing._raw_features(feature_record(row), '2000-01-01')[field]
            return bool(value) if value is not None and self.fields[field]['kind'] == 'boolean' else value
        return pricing._numeric_feature(field, row.get(field))

    def _support(self, row, fields=()):
        comp = report.composition(row)
        matched = [r for r in self._source if r['bedrooms'] == row['bedrooms'] and report.composition(r) == comp]
        known_size = pd.to_numeric(self._data.square_feet, errors='coerce').dropna()
        field_support = {}
        for field in fields:
            if field not in self._field_observations:
                self._field_observations[field] = [(self._value(r, field), r) for r in self._source]
            observed = [(value, r) for value, r in self._field_observations[field] if value is not None]
            value = self._value(row, field)
            exact = [r for candidate, r in observed if candidate == value]
            numeric = self.fields[field]['kind'] == 'numeric'
            bounds = [min(v for v,r in observed), max(v for v,r in observed)] if observed and numeric else None
            field_support[field] = {'value': value, **report.support(exact), 'observed_range': bounds,
                'within_observed_range': bounds is not None and value is not None and bounds[0] <= value <= bounds[1] if numeric else bool(exact)}
        return {'fields': field_support, 'bedrooms': row['bedrooms'], 'full_half': list(comp) if comp else None,
                'layout': report.support(matched), 'interpretation': 'Unmatched observed endpoints; not independent or causal replications.',
                'area_observed_range': [float(known_size.min()), float(known_size.max())] if len(known_size) else None}

    def counterfactual(self, audit_id, changes):
        self._fresh()
        if not isinstance(changes, dict) or not changes:
            raise ValueError('Supply a nonempty mapping of supported changes')
        before = self._rows[audit_id]; after = deepcopy(before); normalized = {}
        aliases = {'reported_full_bathrooms': 'full_bathrooms', 'reported_half_bathrooms': 'half_bathrooms'}
        for name, value in changes.items():
            field = aliases.get(name, name)
            if field in normalized:
                raise ValueError('Duplicate field after alias normalization')
            if field not in self.fields:
                raise ValueError('Unsupported or unmodeled counterfactual field: '+str(name))
            meta = self.fields[field]
            if meta['kind'] == 'category':
                if not isinstance(value, str) or value not in meta['options']:
                    raise ValueError('Unknown or unsupported category: '+field)
            elif meta['kind'] == 'boolean':
                if type(value) is not bool:
                    raise ValueError('Boolean amenities require explicit true or false: '+field)
            else:
                value = pricing._number(value)
                if value is None:
                    raise ValueError('Unknown or nonfinite counterfactual value: '+field)
                if field in ('bedrooms', 'full_bathrooms', 'half_bathrooms'):
                    limits = {'bedrooms': (0, 5), 'full_bathrooms': (1, 5), 'half_bathrooms': (0, 2)}
                    low, high = limits[field]
                    if not value.is_integer() or not low <= value <= high:
                        raise ValueError('Count outside encoded support: '+field)
                if field == 'square_feet' and value <= 0:
                    raise ValueError('Area must be positive')
            normalized[field] = value
        bath = {'full_bathrooms', 'half_bathrooms'} & normalized.keys()
        if bath and report.composition(before) is None and bath != {'full_bathrooms', 'half_bathrooms'}:
            raise ValueError('Unknown bathroom composition requires both explicit full and half counts')
        for field, value in normalized.items():
            target = 'reported_'+field if field in ('full_bathrooms', 'half_bathrooms') else field
            if '.' in target:
                parent, child = target.split('.')
                old = after.get(parent)
                if not isinstance(old, (dict, type(None))):
                    raise ValueError('Cannot safely edit nonmapping exposure source')
                after[parent] = {**(old or {}), child: value}
            else:
                after[target] = value
        if bath:
            after['bathrooms'] = after['reported_full_bathrooms']+.5*after['reported_half_bathrooms']
            after['bathroom_count_evidence'] = {'flags': [], 'hypothetical': True}
        mu, _, x = self._terms(before)
        self._verify_fitted(audit_id, mu)
        next_x = self.design.matrix(_frame([after]))[0]
        difference = next_x-x
        delta = self._draws['beta'] @ difference
        # Version-specific location terms (e.g. a bedroom-group time curve)
        # depend on the changed source values too; move them jointly.
        before_extra = location_terms.row_terms(getattr(self, 'protocol', {}), self._draws, _frame([before]), self.design)
        after_extra = location_terms.row_terms(getattr(self, 'protocol', {}), self._draws, _frame([after]), self.design)
        for name, value in after_extra.items():
            delta = delta + value - before_extra[name]
        after_mu = mu+delta
        with np.errstate(over='raise', invalid='raise'):
            percent = 100*np.expm1(delta); dollars = np.exp(mu)*np.expm1(delta)
        diag = contrast_diagnostics({'delta_log': delta, 'delta_percent': percent,
            'delta_dollars': dollars, 'after_log_rent': after_mu}, self._shape)
        warnings = self._warnings(before)
        changed_features = {name: float(v) for name, v in zip(self.design.features, difference) if abs(v) > 1e-14}
        reporting_change = any(self._value(before, field) is None for field in normalized)
        if reporting_change or any('unknown' in name or 'missing' in name for name in changed_features):
            warnings.append('This scenario changes reporting/missingness indicators as well as physical attributes.')
        support = {'before': self._support(before, normalized), 'after': self._support(after, normalized)}
        unsupported = any(support[endpoint]['layout']['rows'] == 0 for endpoint in ('before', 'after'))
        if unsupported:
            warnings.append('The hypothetical bedroom/full/half endpoint has no observed layout support.')
        if (getattr(self, 'protocol', {}).get('version') == report.EXPERIMENT_V5
                and {'listed_floor', 'elevator'} & normalized.keys()):
            for endpoint, record in (('before', before), ('after', after)):
                floor, access = self._value(record, 'listed_floor'), self._value(record, 'elevator')
                matching = [r for r in self._source if floor is not None and access is not None
                            and self._value(r, 'listed_floor') == floor and self._value(r, 'elevator') == access]
                support[endpoint]['floor_elevator'] = {'listed_floor': floor, 'elevator': access,
                                                       **report.support(matching)}
                if not matching:
                    unsupported = True
            if any(not support[e]['floor_elevator']['rows'] for e in ('before', 'after')):
                warnings.append('A joint listed-floor/elevator endpoint has no observed known-access support.')
        size = pricing._number(after.get('square_feet')); limits = support['after']['area_observed_range']
        if size is not None and limits and not limits[0] <= size <= limits[1]:
            warnings.append('Hypothetical area is outside the observed training range.')
            unsupported = True
        if any(not cell['within_observed_range'] for cell in support['after']['fields'].values()):
            unsupported = True
            warnings.append('A changed feature endpoint is outside observed field support.')
        status = ('reporting_change' if reporting_change else 'unsupported_endpoint' if unsupported
                  else 'accepted' if diag['acceptable'] else 'diagnostic_only')
        result = {'audit_id': audit_id, 'changes': normalized, 'before': deepcopy(before), 'after': after,
                  'changed_encoded_features': changed_features, 'support': support, 'warnings': warnings,
                  'diagnostics': diag, 'status': status,
                  'draws': int(np.prod(self._shape)), 'held_fixed': 'Date, building, within-building unit offset, and every unspecified source input.',
                  'uncertainty': 'Joint retained posterior draws; latent conditional-median rent, not predictive or causal uncertainty.'}
        if status == 'accepted':
            result.update(delta_log=_interval(delta), delta_percent=_interval(delta, lambda q: 100*np.expm1(q)),
                          delta_dollars=_interval(dollars), before_rent=_interval(mu, np.exp),
                          after_rent=_interval(after_mu, np.exp))
        else:
            warnings.append('Physical counterfactual intervals withheld: '+status+'.')
        return result

    contrast = counterfactual


AnalysisWorkspace = BayesianAnalysis
load = BayesianAnalysis.load

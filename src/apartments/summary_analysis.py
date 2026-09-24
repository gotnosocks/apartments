"""Read-only analysis of a model's page-ready summary outputs; never fits.

A summary directory is written by the model's own code (for the frontier
line, `python -m rentfrontier.summary <run>`): per-row fitted and
leave-own-row-out rent with 95% intervals, additive log terms and dollar
contributions, coefficients, and a `complete.json` manifest with provenance
and the sha256 of every file. This reader verifies those hashes and the
dataset binding, then serves the rows; it does not re-derive the predictor,
so it does not depend on the model version.

Residuals: `residual_*` compare the ask with the leave-own-row-out fitted
rent (an estimate that does not use the listing's own ask); `in_sample_*`
keep the in-fit comparison, which is pulled toward the ask.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

VERSION = 'frontier-summary-v1'
PARETO_K_LIMIT = 0.7


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _finite(value):
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value


class SummaryAnalysis:
    @classmethod
    def load(cls, summary, dataset):
        self = cls()
        self.summary_dir, self.dataset = Path(summary), Path(dataset)
        manifest_path = self.summary_dir/'complete.json'
        if manifest_path.is_symlink():
            raise ValueError('Summary manifest must not be a symlink')
        self.manifest = json.loads(manifest_path.read_text())
        if self.manifest.get('version') != VERSION:
            raise ValueError('Unsupported summary version')
        for name, expected in self.manifest['files'].items():
            path = self.summary_dir/name
            if path.is_symlink() or not path.resolve().is_relative_to(self.summary_dir.resolve()):
                raise ValueError('Summary file escapes its directory')
            if sha256(path) != expected:
                raise ValueError(f'Summary file differs from its manifest: {name}')
        observations = self.dataset/'observations.jsonl'
        if sha256(observations) != self.manifest['dataset_observations_sha256']:
            raise ValueError('Dataset differs from the one the summarized model was fit on')
        self._source = [json.loads(line) for line in observations.read_text().splitlines() if line.strip()]
        self._rows = {r['audit_id']: r for r in self._source}
        table = pd.read_parquet(self.summary_dir/'rows.parquet')
        if len(table) != len(self._source) or set(table.audit_id) != set(self._rows):
            raise ValueError('Summary rows differ from the dataset rows')
        self.terms = json.loads((self.summary_dir/'terms.json').read_text())
        self.coefficients = pd.read_csv(self.summary_dir/'coefficients.csv')
        self._table = table.set_index('audit_id', drop=False)
        self._residuals = [self._residual(r) for r in table.to_dict('records')]
        self._by_id = {r['audit_id']: r for r in self._residuals}
        self.fields = {}  # counterfactual inputs: not served from summaries yet
        self.summary = {k: self.manifest.get(k) for k in (
            'run', 'run_commit', 'summary_commit', 'model', 'feature_set', 'split', 'dataset',
            'rows', 'rows_in_fit', 'draws', 'sampler', 'hardware', 'fit_seconds', 'diagnostics',
            'score', 'loo', 'uncertainty', 'created_at')}
        return self

    @staticmethod
    def _residual(r):
        loo = r['loo_fitted_rent']
        return {
            'audit_id': r['audit_id'], 'unit_id': r['unit_id'], 'building': r['building'],
            'source_listing_id': r['source_listing_id'], 'period': r['period'],
            'asking_rent': float(r['asking_rent']), 'in_fit': bool(r['in_fit']),
            # Primary comparison: leave-own-row-out.
            'fitted_rent': float(loo),
            'latent_rent_lower_95': float(r['loo_latent_rent_lower_95']),
            'latent_rent_upper_95': float(r['loo_latent_rent_upper_95']),
            'residual_dollars': float(r['asking_rent'] - loo),
            'residual_log': float(r['loo_residual_log']),
            'loo_method': r['loo_method'],
            'loo_pareto_k': _finite(float(r['loo_pareto_k'])),
            'loo_reliable': not (r['loo_method'] == 'psis' and float(r['loo_pareto_k']) > PARETO_K_LIMIT),
            'in_sample_fitted_rent': float(r['fitted_rent']),
            'in_sample_latent_rent_lower_95': float(r['latent_rent_lower_95']),
            'in_sample_latent_rent_upper_95': float(r['latent_rent_upper_95']),
            'in_sample_residual_dollars': float(r['residual_dollars']),
            'in_sample_residual_log': float(r['residual_log']),
        }

    @property
    def rows(self):
        return deepcopy(self._source)

    @property
    def residuals(self):
        return deepcopy(self._residuals)

    def close(self):
        pass

    def detail(self, audit_id):
        if audit_id not in self._by_id:
            raise KeyError('Unknown observation')
        r = self._table.loc[audit_id]
        residual = self._by_id[audit_id]
        order = self.terms['order']
        grouped = {t: float(r[f'{t}_log']) for t in order}
        intervals = [{'group': t, 'log_interval': {'lower_95': float(r[f'{t}_log_lower_95']),
                                                  'median': float(r[f'{t}_log']),
                                                  'upper_95': float(r[f'{t}_log_upper_95'])}}
                     for t in order]
        contributions = [{'term': t, 'description': self.terms['descriptions'].get(t),
                          'mean_log_contribution': float(r[f'{t}_log']),
                          'mean_dollar_contribution': float(r[f'{t}_usd']),
                          'dollar_lower_95': float(r[f'{t}_usd_lower_95']),
                          'dollar_upper_95': float(r[f'{t}_usd_upper_95'])} for t in order]
        warnings = []
        if not residual['loo_reliable']:
            warnings.append(f"The leave-own-row-out estimate is unreliable (Pareto k {residual['loo_pareto_k']:.2f} > "
                            f"{PARETO_K_LIMIT}): this listing's own ask strongly informs its unit's effect.")
        if residual['loo_method'] == 'unit_prior':
            warnings.append("This unit has one listing in the fit; leaving it out returns the unit's own effect to its prior.")
        if not residual['in_fit']:
            warnings.append('This listing is not in the fit (row-split held-out row); its estimate is out of sample.')
        return {
            'audit_id': audit_id, 'source_record': deepcopy(self._rows[audit_id]), 'residual': deepcopy(residual),
            'fitted_median_rent': {'lower_95': residual['latent_rent_lower_95'], 'median': residual['fitted_rent'],
                                   'upper_95': residual['latent_rent_upper_95']},
            'in_sample_fitted_median_rent': {'lower_95': residual['in_sample_latent_rent_lower_95'],
                                             'median': residual['in_sample_fitted_rent'],
                                             'upper_95': residual['in_sample_latent_rent_upper_95']},
            'mean_log_rent': float(r['mean_log_rent']),
            'contributions': contributions, 'grouped_contributions': grouped,
            'grouped_contribution_intervals': intervals,
            'contribution_diagnostics': {'acceptable': bool(self.manifest['diagnostics'].get('passes')),
                                         'source': 'run-level convergence gate', **self.manifest['diagnostics']},
            'dollar_reference': self.terms['reference'],
            'source_values': {},
            'unit_history': deepcopy([x for x in self._residuals if x['unit_id'] == residual['unit_id']]),
            'draws': int(self.manifest['draws']['kept']),
            'uncertainty': self.manifest.get('uncertainty'),
            'warnings': warnings,
        }

    def counterfactual(self, audit_id, changes):
        raise ValueError('Feature comparisons are not available from summary outputs yet')

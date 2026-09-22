"""Matched comparison of a bedroom-time fit against a shared-trend fit.

Both fits must use the same source observations. Reports: mean deviation
(unit effect + residual) by bedroom group x year, scale parameters, feature
coefficient shifts, and current-cohort fitted-rent changes by bedroom group.
Report-only; reads saved fit products plus scalar posterior draws.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import bayesian_bedroom_time_graph as graph


def load(fit):
    fit = Path(fit)
    residuals = pd.read_json(fit/'fit/residuals.jsonl', lines=True)
    effects = pd.read_json(fit/'fit/group-effects.jsonl', lines=True)
    units = effects[effects.kind.eq('unit')].set_index('id').log_effect.map(lambda v: v['median'])
    residuals['deviation'] = residuals.residual_log+residuals.unit_id.map(units).fillna(0.)
    coefficients = pd.DataFrame(json.loads((fit/'fit/coefficients.json').read_text())).set_index('feature')
    protocol = json.loads((fit/'protocol/protocol.json').read_text())
    return residuals, coefficients, protocol


def scalars(fit, names):
    import xarray as xr
    tree = xr.open_datatree(Path(fit)/'fit/posterior.nc', engine='h5netcdf', cache=False)
    try:
        posterior = tree['posterior']
        return {n: {'mean': float(posterior[n].mean()), 'sd': float(posterior[n].std())}
                for n in names if n in posterior.data_vars}
    finally:
        tree.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, base_coef, base_protocol = load(args.baseline)
    cand, cand_coef, cand_protocol = load(args.candidate)
    if base_protocol['source_observations_sha256'] != cand_protocol['source_observations_sha256']:
        raise ValueError('Fits use different source observations')
    observations = pd.read_json(args.dataset/'observations.jsonl', lines=True)
    meta = observations.set_index('audit_id')[['bedrooms', 'analysis_price_basis']]
    frame = base[['audit_id', 'period', 'asking_rent', 'fitted_rent', 'deviation', 'residual_log']].merge(
        cand[['audit_id', 'fitted_rent', 'deviation', 'residual_log']], on='audit_id', suffixes=('_base', '_cand'))
    if len(frame) != len(base) or len(frame) != len(cand):
        raise ValueError('Fits cover different observations')
    frame = frame.join(meta, on='audit_id')
    frame['group'] = pd.Categorical.from_codes(graph.bedroom_groups(frame.bedrooms), graph.GROUP_LABELS)
    frame['year'] = pd.to_datetime(frame.period).dt.year
    cells = frame.groupby(['year', 'group'], observed=True).agg(
        rows=('audit_id', 'size'), base=('deviation_base', 'mean'), candidate=('deviation_cand', 'mean'))
    table = (cells[['base', 'candidate']]*100).round(2).unstack('group')
    weighted_abs = {k: float((cells[k].abs()*cells.rows).sum()/cells.rows.sum()*100) for k in ('base', 'candidate')}
    current = frame[frame.analysis_price_basis.eq('current_capture_gross_ask')]
    current_change = current.assign(change=100*(current.fitted_rent_cand/current.fitted_rent_base-1)).groupby(
        'group', observed=True).change.describe()[['count', 'mean', 'min', 'max']]
    joined = base_coef[['median']].join(cand_coef[['median']], lsuffix='_base', rsuffix='_cand')
    joined['shift'] = joined.median_cand-joined.median_base
    names = ['alpha', 'sigma', 'sigma_unit', 'sigma_building', 'annual_drift', 'trend_scale', 'bedroom_walk_scale']
    params = {label: scalars(fit, names) for label, fit in (('base', args.baseline), ('candidate', args.candidate))}
    result = {
        'baseline': str(args.baseline), 'candidate': str(args.candidate),
        'rows': len(frame), 'current_rows': len(current),
        'weighted_mean_abs_group_year_deviation_percent': weighted_abs,
        'median_abs_residual_log': {'base': float(frame.residual_log_base.abs().median()),
                                    'candidate': float(frame.residual_log_cand.abs().median())},
        'parameters': params,
        'largest_coefficient_shifts': json.loads(joined.reindex(joined['shift'].abs().sort_values(ascending=False).index)
                                                 .head(12).round(4).to_json(orient='index')),
        'current_fitted_rent_change_percent': json.loads(current_change.round(2).to_json(orient='index')),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'comparison.json').write_text(json.dumps(result, indent=1)+'\n')
    table.to_csv(args.output/'group-year-deviation.csv')
    print(json.dumps(result, indent=1))
    print(table.to_string())


if __name__ == '__main__':
    main()

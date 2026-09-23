"""Held-out screen: shared trend versus bedroom-group time deviations.

Also evaluates cheap screening methods against full-data NUTS on the same
held-out rows: `--method map` (pm.find_MAP point estimate, plug-in density)
and `--subset-fraction` (fit on a random subset of buildings or units; the
held-out split is drawn first on all data, then restricted to the subset).

Research triage only; never a main selection. Declared before fitting:
hold out ~10% of observations from repeat-listed units (each unit keeps at
least one training row; seed fixed), fit every mode on the same training rows
and design, and score held-out rows by exact posterior predictive log density
(Student-t, nu=5) plus signed log error by bedroom group x era.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import special, stats
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as v3
from . import bayesian_floor_spline_design as floor
from . import bayesian_bedroom_time_graph as graph

ERAS = ((2010, 2013), (2014, 2016), (2017, 2019), (2020, 2022), (2023, 2024), (2025, 2026))


def split(data, fraction, seed):
    rng = np.random.default_rng(seed)
    counts = data.unit_id.map(data.unit_id.value_counts())
    keep = pd.Series(False, index=data.index)
    keep[data[counts.ge(2)].groupby('unit_id').sample(1, random_state=seed).index] = True
    candidates = data.index[counts.ge(2) & ~keep]
    chosen = rng.choice(candidates, size=int(round(fraction*len(data))), replace=False)
    test = data.index.isin(chosen)
    return data[~test].reset_index(drop=True), data[test].reset_index(drop=True)


def subset(train, test, fraction, by, seed):
    if fraction >= 1:
        return train, test
    column = 'building' if by == 'building' else 'unit_id'
    ids = np.sort(train[column].unique())
    chosen = set(np.random.default_rng(seed).choice(ids, size=int(round(fraction*len(ids))), replace=False))
    return (train[train[column].isin(chosen)].reset_index(drop=True),
            test[test[column].isin(chosen)].reset_index(drop=True))


def map_posterior(model, seed, maxeval, fixed=None):
    """find_MAP as a one-draw posterior dataset with the model's named dims.

    `fixed` holds variance components at given values (pm.do) so the joint
    mode is not the degenerate zero-scale/inflated-scale hierarchical mode.
    """
    import pymc as pm
    import xarray as xr
    original = model
    if fixed:
        model = pm.do(model, {model[name]: np.asarray(value, dtype=float) for name, value in fixed.items()})
    with model:
        point = pm.find_MAP(maxeval=maxeval, progressbar=False, seed=seed)
    variables = {}
    point = {**{k: v for k, v in (fixed or {}).items()}, **point}
    for rv in original.free_RVs+original.deterministics:
        name = rv.name
        dims = original.named_vars_to_dims.get(name, ()) or ()
        if name not in point:
            continue
        value = np.asarray(point[name])
        if len(dims) != value.ndim:
            dims = tuple(f'{name}_dim_{i}' for i in range(value.ndim))
        coords = {d: list(original.coords[d]) for d in dims if d in original.coords}
        variables[name] = xr.DataArray(value[None, None], dims=('chain', 'draw', *dims), coords=coords)
    return xr.Dataset(variables)


def pseudo_groups(data, seed):
    """Negative control: per-unit random groups with the bedroom-group marginals."""
    units = np.sort(data.unit_id.unique())
    first = data.drop_duplicates('unit_id').set_index('unit_id').bedrooms.reindex(units).to_numpy()
    shuffled = np.random.default_rng(seed).permutation(graph.bedroom_groups(first))
    return data.unit_id.map(dict(zip(units, shuffled))).to_numpy()


def predictive(posterior, design, test, mode, thin, group_column='bedrooms'):
    d = design.time
    a = d.arrays(test)
    if (a['building'] < 0).any() or (a['unit'] < 0).any():
        raise ValueError('Held-out rows must have fitted buildings and units')
    p = posterior.stack(sample=('chain', 'draw')).isel(sample=slice(None, None, thin))
    x = design.matrix(test)
    monthly = ((d.time_matrix-d.time_center) @ p.trend_coefficients.values
               + np.outer(d.linear_time-d.linear_center, p.annual_drift.values))
    seasonal = (d.season_matrix-d.season_weights@d.season_matrix) @ p.season_coefficients.values
    mu = (p.alpha.values[None] + x @ p.beta.values + monthly[a['period']] + seasonal[a['season']]
          + p.building_effect.values[a['building']] + p.sigma_unit.values[None]*p.unit_z.values[a['unit']])
    if mode != 'none':
        g = graph.bedroom_groups(test[group_column])
        mu = mu + p.bedroom_time.values[g, a['period']]
    y = np.log(test.asking_rent.to_numpy())[:, None]
    logpdf = stats.t.logpdf(y, 5., loc=mu, scale=p.sigma.values[None])
    lpd = special.logsumexp(logpdf, axis=1)-math.log(logpdf.shape[1])
    return lpd, y[:, 0]-np.median(mu, axis=1)


def summarize(test, lpd, error):
    frame = pd.DataFrame({'lpd': lpd, 'error': error, 'group': graph.bedroom_groups(test.bedrooms),
                          'year': test.period.dt.year.to_numpy()})
    frame['era'] = pd.cut(frame.year, [e[0]-1 for e in ERAS]+[ERAS[-1][1]],
                          labels=[f'{a}-{b}' for a, b in ERAS])
    cells = frame.groupby(['group', 'era'], observed=True).agg(
        rows=('lpd', 'size'), mean_error=('error', 'mean'), lpd=('lpd', 'sum')).reset_index()
    cells['group'] = cells.group.map(dict(enumerate(graph.GROUP_LABELS)))
    return {'rows': len(frame), 'elpd': float(frame.lpd.sum()), 'elpd_se': float(frame.lpd.std()*math.sqrt(len(frame))),
            'rmse_log': float(np.sqrt((frame.error**2).mean())), 'mae_log': float(frame.error.abs().mean()),
            'cells': json.loads(cells.to_json(orient='records'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=graph.MODES, required=True)
    parser.add_argument('--fraction', type=float, default=.10)
    parser.add_argument('--split-seed', type=int, default=20260922)
    parser.add_argument('--seed', type=int, default=20260918)
    parser.add_argument('--tune', type=int, default=1000)
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--chains', type=int, default=4)
    parser.add_argument('--thin', type=int, default=2)
    parser.add_argument('--walk-prior-scale', type=float, default=.05)
    parser.add_argument('--linear-prior-scale', type=float, default=.02)
    parser.add_argument('--negative-control-seed', type=int, default=None,
        help='Key the deviation curves to random per-unit pseudo-groups instead of bedrooms')
    parser.add_argument('--method', choices=('nuts', 'map'), default='nuts')
    parser.add_argument('--maxeval', type=int, default=50000)
    parser.add_argument('--fix-scales-from', type=Path, default=None,
        help='NUTS screen result.json whose scalar means fix sigma, sigma_unit, sigma_building and trend_scale for MAP')
    parser.add_argument('--subset-fraction', type=float, default=1.)
    parser.add_argument('--subset-by', choices=('building', 'unit'), default='building')
    parser.add_argument('--subset-seed', type=int, default=7)
    args = parser.parse_args()
    if args.method == 'nuts':
        import nutpie
    args.output.mkdir(parents=True, exist_ok=True)
    data, manifest = v3.load_data(args.dataset)
    group_column = 'bedrooms'
    if args.negative_control_seed is not None:
        data['pseudo_group'] = pseudo_groups(data, args.negative_control_seed)
        group_column = 'pseudo_group'
    train, test = split(data, args.fraction, args.split_seed)
    design = floor.FeatureDesign(train, 'full_half_balance', floor_prior_scale=.10)
    values = floor.listed_floor_values(test)
    supported = ~np.isfinite(values) | ((values >= min(design.floor_levels)) & (values <= max(design.floor_levels)))
    in_horizon = test.period.between(design.time.periods[0], design.time.periods[-1])
    test = test[supported & in_horizon.to_numpy()].reset_index(drop=True)
    if args.subset_fraction < 1:
        # Rebuild the design on the subset: the screen must not see other rows.
        train, test = subset(train, test, args.subset_fraction, args.subset_by, args.subset_seed)
        design = floor.FeatureDesign(train, 'full_half_balance', floor_prior_scale=.10)
        values = floor.listed_floor_values(test)
        supported = ~np.isfinite(values) | ((values >= min(design.floor_levels)) & (values <= max(design.floor_levels)))
        in_horizon = test.period.between(design.time.periods[0], design.time.periods[-1])
        test = test[supported & in_horizon.to_numpy()].reset_index(drop=True)
    if group_column == 'bedrooms':
        model = graph.build_model(train, design, mode=args.mode, walk_prior_scale=args.walk_prior_scale,
                                  linear_prior_scale=args.linear_prior_scale)
    else:
        # The promoted graph file is frozen by its fit's protocol hash; the
        # equivalent structure graph carries the control's group override.
        from . import bayesian_structure_graph as structure
        if args.mode != 'walk':
            raise ValueError('The negative control is defined for walk mode only')
        model = structure.build_model(train, design, walk_prior_scale=args.walk_prior_scale,
                                      group_column=group_column)
    names = ['alpha', 'sigma', 'sigma_unit', 'sigma_building', 'annual_drift', 'trend_scale']
    if args.mode == 'walk':
        names.append('bedroom_walk_scale')
    started = time.monotonic()
    if args.method == 'map':
        fixed = None
        if args.fix_scales_from:
            saved = json.loads(args.fix_scales_from.read_text())['scalars']
            fixed = {n: saved[n]['mean'] for n in ('sigma', 'sigma_unit', 'sigma_building', 'trend_scale')}
        posterior = map_posterior(model, args.seed, args.maxeval, fixed)
        elapsed = time.monotonic()-started
        diagnostic = {'divergences': None, 'max_rhat': None, 'min_ess_bulk': None}
        summary = None
    else:
        compiled = nutpie.compile_pymc_model(model, backend='numba')
        inference = nutpie.sample(compiled, draws=args.draws, tune=args.tune, chains=args.chains,
                                  cores=args.chains, seed=args.seed, target_accept=.93, progress_bar=False)
        elapsed = time.monotonic()-started
        import arviz as az
        diagnostic, _ = v3.v2.base.diagnostics(inference)
        posterior = inference['posterior'].to_dataset()
        summary = az.summary(inference, var_names=names, round_to='none')
    lpd, error = predictive(posterior, design, test, args.mode, args.thin if args.method == 'nuts' else 1, group_column)
    result = {'mode': args.mode, 'method': args.method, 'negative_control_seed': args.negative_control_seed, 'dataset': str(args.dataset),
              'source_manifest_version': manifest.get('version'),
              'subset_fraction': args.subset_fraction, 'subset_by': args.subset_by, 'subset_seed': args.subset_seed,
              'train_rows': len(train), 'split_seed': args.split_seed, 'sampling_seconds': elapsed,
              'tune': args.tune, 'draws': args.draws, 'chains': args.chains,
              'divergences': diagnostic['divergences'], 'max_rhat': diagnostic['max_rhat'],
              'min_ess_bulk': diagnostic['min_ess_bulk'], 'diagnostics': diagnostic,
              'scalars': {n: {'mean': float(posterior[n].mean()), 'sd': float(posterior[n].std())} for n in names},
              'heldout': summarize(test, lpd, error),
              'configuration': model.graph_configuration}
    if args.mode != 'none':
        curve = posterior.bedroom_time
        jan = [i for i, p in enumerate(design.time.periods) if p.month == 1]
        result['curves'] = {g: {design.time.periods[i].strftime('%Y'): {
            'median': float(curve.sel(bedroom_group=g).isel(period=i).median()),
            'lower_95': float(curve.sel(bedroom_group=g).isel(period=i).quantile(.025)),
            'upper_95': float(curve.sel(bedroom_group=g).isel(period=i).quantile(.975))} for i in jan}
            for g in graph.GROUP_LABELS}
    np.savez_compressed(args.output/'heldout.npz', lpd=lpd, error=error, audit_id=test.audit_id.to_numpy())
    if summary is not None:
        summary.to_csv(args.output/'summary.csv')
    (args.output/'result.json').write_text(json.dumps(result, indent=1, default=float)+'\n')
    print(json.dumps({k: result[k] for k in ('mode', 'sampling_seconds', 'divergences', 'max_rhat', 'min_ess_bulk')}
                     | {'elpd': result['heldout']['elpd'], 'rmse_log': result['heldout']['rmse_log']}))


if __name__ == '__main__':
    with threadpool_limits(limits=1, user_api='blas'):
        main()

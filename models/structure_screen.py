"""Held-out screen for `bayesian_structure_graph` variants against the promoted model.

Same declared split as `bedroom_time_screen` (10% of rows from repeat-listed
units, split seed 20260922). `--method map` is conditional MAP: variance
components are fixed at a NUTS screen's posterior means (`--fix-scales-from`),
and any new drift scale is fixed by `--building-scale` (screen a grid of values;
free hierarchical scales degenerate at the joint mode).
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy import special, stats
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as v3
from . import bayesian_floor_spline_design as floor
from . import bayesian_structure_graph as graph
from .bedroom_time_screen import split, map_posterior, summarize

FIXED = ('sigma', 'sigma_unit', 'sigma_building', 'trend_scale', 'bedroom_walk_scale')


def predictive(posterior, design, test, options, building_weights, thin, shock=None):
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
    g = graph.groups(test.bedrooms, options['bedroom_groups'])
    mu = mu + p.bedroom_time.values[g, a['period']]
    mu = mu + graph.building_time_numpy(p, design, test, building_weights,
        building_time=options['building_time'], building_scale=options['building_scale'],
        building_knot_years=options['building_knot_years'])
    if shock and shock['months']:
        mu = mu + graph.building_shock_numpy(p, design, test, shock['weights'],
            shock_months=shock['months'], shock_scale=shock['scale'])
    nu = p['nu'].values[None] if 'nu' in p else 5.
    y = np.log(test.asking_rent.to_numpy())[:, None]
    logpdf = stats.t.logpdf(y, nu, loc=mu, scale=p.sigma.values[None])
    lpd = special.logsumexp(logpdf, axis=1)-math.log(logpdf.shape[1])
    return lpd, y[:, 0]-np.median(mu, axis=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--method', choices=('nuts', 'map'), default='map')
    parser.add_argument('--fix-scales-from', type=Path)
    parser.add_argument('--bedroom-groups', type=int, choices=(4, 5), default=4)
    parser.add_argument('--building-time', choices=graph.BUILDING_TIME, default='none')
    parser.add_argument('--building-scale', type=float, default=None)
    parser.add_argument('--building-knot-years', type=float, default=4)
    parser.add_argument('--building-scale-prior', type=float, default=.02,
        help='HalfNormal prior scale for the drift scale when --building-scale is omitted')
    parser.add_argument('--estimate-nu', action='store_true')
    parser.add_argument('--shock-months', type=int, default=None)
    parser.add_argument('--shock-scale', type=float, default=None)
    parser.add_argument('--shock-scale-prior', type=float, default=.05)
    parser.add_argument('--fraction', type=float, default=.10)
    parser.add_argument('--split-seed', type=int, default=20260922)
    parser.add_argument('--seed', type=int, default=20260918)
    parser.add_argument('--tune', type=int, default=1000)
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--chains', type=int, default=4)
    parser.add_argument('--thin', type=int, default=2)
    parser.add_argument('--maxeval', type=int, default=50000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data, _ = v3.load_data(args.dataset)
    train, test = split(data, args.fraction, args.split_seed)
    design = floor.FeatureDesign(train, 'full_half_balance', floor_prior_scale=.10)
    values = floor.listed_floor_values(test)
    supported = ~np.isfinite(values) | ((values >= min(design.floor_levels)) & (values <= max(design.floor_levels)))
    test = test[supported & test.period.between(design.time.periods[0], design.time.periods[-1]).to_numpy()]
    test = test.reset_index(drop=True)
    options = {'bedroom_groups': args.bedroom_groups, 'building_time': args.building_time,
               'building_scale': args.building_scale, 'building_knot_years': args.building_knot_years}
    model = graph.build_model(train, design, nu=None if args.estimate_nu else 5.,
                              building_scale_prior=args.building_scale_prior,
                              shock_months=args.shock_months, shock_scale=args.shock_scale,
                              shock_scale_prior=args.shock_scale_prior, **options)
    started = time.monotonic()
    diagnostic = None
    if args.method == 'map':
        fixed = None
        if args.fix_scales_from:
            saved = json.loads(args.fix_scales_from.read_text())['scalars']
            fixed = {n: saved[n]['mean'] for n in FIXED if n in saved}
        posterior = map_posterior(model, args.seed, args.maxeval, fixed)
    else:
        import nutpie
        compiled = nutpie.compile_pymc_model(model, backend='numba')
        inference = nutpie.sample(compiled, draws=args.draws, tune=args.tune, chains=args.chains,
                                  cores=args.chains, seed=args.seed, target_accept=.93, progress_bar=False)
        diagnostic, _ = v3.v2.base.diagnostics(inference)
        posterior = inference['posterior'].to_dataset()
    elapsed = time.monotonic()-started
    shock = {'months': args.shock_months, 'scale': args.shock_scale,
             'weights': getattr(model, 'shock_weights', None)}
    lpd, error = predictive(posterior, design, test, options, model.building_weights,
                            args.thin if args.method == 'nuts' else 1, shock)
    scalars = {n: {'mean': float(posterior[n].mean()), 'sd': float(posterior[n].std())}
               for n in ('alpha', 'sigma', 'sigma_unit', 'sigma_building', 'annual_drift', 'trend_scale',
                         'season_scale', 'bedroom_walk_scale', 'building_time_scale', 'building_shock_scale', 'nu')
               if n in posterior}
    result = {'method': args.method, **options, 'estimate_nu': args.estimate_nu, 'seconds': elapsed,
              'shock_months': args.shock_months, 'shock_scale': args.shock_scale,
              'train_rows': len(train), 'scalars': scalars, 'heldout': summarize(test, lpd, error),
              'diagnostics': diagnostic, 'configuration': model.graph_configuration}
    np.savez_compressed(args.output/'heldout.npz', lpd=lpd, error=error, audit_id=test.audit_id.to_numpy())
    (args.output/'result.json').write_text(json.dumps(result, indent=1, default=float)+'\n')
    print(json.dumps({'output': str(args.output), 'seconds': round(elapsed), 'elpd': result['heldout']['elpd'],
                      **{k: v['mean'] for k, v in scalars.items() if k in ('nu', 'building_time_scale')}}))


if __name__ == '__main__':
    with threadpool_limits(limits=1, user_api='blas'):
        main()

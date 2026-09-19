"""Common diagnostics and honest timing denominators for completed NUTS runs."""
import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_increment_design as floor
from models import bayesian_feature_experiment_v4 as floor_reports


def normalized_statistics(stats, max_tree_depth):
    """Add the common saturation flag without modifying the saved posterior."""
    if 'maxdepth_reached' in stats:
        return stats
    if 'tree_depth' not in stats or max_tree_depth < 1:
        raise ValueError('Tree-depth evidence required')
    return stats.assign(maxdepth_reached=stats.tree_depth >= max_tree_depth)


def efficiency(table, timings):
    """Each rate explicitly names its wall-time scope; draws are never ESS."""
    result = table.copy()
    for name, seconds in timings.items():
        if not isinstance(seconds, (int, float)) or not np.isfinite(seconds) or seconds <= 0:
            raise ValueError('Finite positive timing denominator required')
        for kind in ('bulk', 'tail'):
            result[f'ess_{kind}_per_second_{name}'] = result[f'ess_{kind}']/seconds
    return result


def warmup_boundary_bounds(progress, tune, draws, chains):
    """Bound retained duration from measured per-chain progress, without extrapolation.

    Progress callbacks straddle the exact warmup boundary. Return an interval,
    not a falsely precise retained duration or a short-run startup subtraction.
    """
    result = []
    for chain in range(chains):
        points = [c for r in progress for c in r.get('chains', []) if c['chain'] == chain]
        before = [c for c in points if c['finished_draws'] <= tune]
        after = [c for c in points if c['finished_draws'] >= tune]
        finished = [c for c in points if c['finished_draws'] == tune+draws and not c['tuning']]
        if not before or not after or not finished:
            raise ValueError('Need measured warmup bracketing and completed chain')
        lo = max(c['runtime_seconds'] for c in before)
        hi = min(c['runtime_seconds'] for c in after)
        end = finished[-1]['runtime_seconds']
        if not 0 <= lo <= hi < end:
            raise ValueError('Invalid progress timing order')
        result.append({'chain': chain, 'retained_seconds_lower': end-hi,
                       'retained_seconds_upper': end-lo, 'warmup_and_retained_seconds': end})
    return result


def run(benchmark, dataset, output):
    benchmark, dataset, output = map(Path, (benchmark, dataset, output))
    completed = json.loads((benchmark/'sampled.json').read_text())
    _, files = _verified_bundle(benchmark/'protocol', retain={'settings.json'})
    settings = json.loads(files['settings.json'])
    if (completed['settings'] != settings or settings['float64'] is not True
            or completed['status'] != 'sampled_diagnostics_and_ess_comparison_pending'
            or completed['posterior_sha256'] != digest(benchmark/'posterior.nc')):
        raise ValueError('Completed benchmark evidence differs')
    paths = [*runner.implementation_paths(), Path(floor.__file__)]
    if any(settings['implementation_sha256'].get(p.name) != digest(p) for p in paths):
        raise ValueError('Model/report implementation differs from sampled benchmark')
    if output.exists():
        raise ValueError('Diagnostic output must be new')
    data, source = runner.load_data(dataset)
    design = floor.FeatureDesign(data, 'full_half_balance', floor_increment_prior_scale=.15)
    if (settings['source_manifest_sha256'] != digest(dataset/'complete.json')
            or settings['source_observations_sha256'] != source['files']['observations.jsonl']
            or settings['feature_names'] != design.features
            or settings['feature_prior_scales'] != design.prior_scales.tolist()):
        raise ValueError('Benchmark source or design differs')
    if settings['graph_configuration'] != runner.graph.graph_configuration(data):
        raise ValueError('Benchmark graph differs from the shared-noise comparison')
    output.mkdir(parents=True)
    seconds = completed['timings']
    denominators = {
        'retained_compute_including_jit': seconds['retained_sampling_including_loop_jit_seconds'],
        'retained_compute_and_storage': seconds['retained_sampling_including_loop_jit_seconds']
            + seconds['retained_transfer_and_storage_seconds'],
        'warmup_and_retained': seconds['warmup_including_initialization_and_jit_seconds']
            + seconds['retained_sampling_including_loop_jit_seconds']
            + seconds['retained_transfer_and_storage_seconds'],
        'pymc_call_and_posterior_write': seconds['pymc_call_including_postprocessing_seconds']
            + seconds['posterior_write_seconds'],
    }
    with xr.open_datatree(benchmark/'posterior.nc', engine='h5netcdf', cache=False) as trace:
        if (trace['posterior'].sizes['chain'] != settings['chains']
                or trace['posterior'].sizes['draw'] != settings['draws_per_chain']
                or trace['posterior'].feature.values.tolist() != design.features
                or trace['posterior'].unit.values.tolist() != design.time.unit_ids
                or trace['posterior'].building.values.tolist() != design.time.buildings):
            raise ValueError('Posterior dimensions or coordinate order differ')
        stats = normalized_statistics(trace['sample_stats'].to_dataset(), settings['max_tree_depth'])
        inference = {'posterior': trace['posterior'], 'sample_stats': xr.DataTree(stats)}
        parameters, pt = runner.v2.base.diagnostics(inference)
        derived, dt = runner.v2.derived_diagnostics(inference, design, data)
        floor_contrasts = floor_reports.floor_contrasts(inference, design)
    acceptable = all(d['acceptable'] and d['maxdepth_reached'] == 0
                     for d in (parameters, derived, floor_contrasts['diagnostics']))
    result = {'version': 'sampler-efficiency-diagnostics-v1', 'parameters': parameters,
        'derived_unit_and_bathroom_contributions': derived, 'timing_denominators_seconds': denominators,
        'joint_floor_contrasts': floor_contrasts['diagnostics'],
        'acceptable': acceptable, 'backend_ranking_established': False,
        'benchmark_record_sha256': digest(benchmark/'sampled.json'),
        'posterior_sha256': completed['posterior_sha256'],
        'policy': 'All chains and retained draws; same parameter and derived-contribution diagnostics as the CPU model. No backend ranking from raw draw rate. GPU compute excludes transfer while CPU durable sampling includes it: compare storage-inclusive rates too.'}
    publish_bundle(output/'complete', {
        'diagnostics.json': canonical(result)+'\n',
        'parameter-efficiency.csv': efficiency(pt, denominators).to_csv(index_label='parameter'),
        'derived-efficiency.csv': efficiency(dt, denominators).to_csv(index_label='parameter'),
        'floor-contrasts.json': canonical(floor_contrasts)+'\n',
        'floor_report_implementation.py': Path(floor_reports.__file__).read_text(),
        Path(__file__).name: Path(__file__).read_text(),
    }, {'version': result['version'], 'acceptable': acceptable})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('benchmark', 'dataset', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

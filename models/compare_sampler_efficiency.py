"""Compare completed, equivalent CPU/GPU posterior sampling by named parameter."""
import argparse
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def paired_rates(cpu, gpu, cpu_bounds, gpu_seconds):
    """Preserve per-parameter bulk/tail rates and the CPU timing interval."""
    if (not cpu.index.is_unique or not gpu.index.is_unique or set(cpu.index) != set(gpu.index)
            or not np.isfinite([*cpu_bounds, gpu_seconds]).all()
            or not 0 < cpu_bounds[0] <= cpu_bounds[1] or gpu_seconds <= 0):
        raise ValueError('Matching unique parameters and valid timing bounds required')
    cpu, gpu = cpu.sort_index(), gpu.sort_index()
    result = pd.DataFrame(index=cpu.index)
    for kind in ('bulk', 'tail'):
        left, right = cpu['ess_'+kind], gpu['ess_'+kind]
        if not np.isfinite([left, right]).all() or (left <= 0).any() or (right <= 0).any():
            raise ValueError('Finite positive ESS required')
        result[f'cpu_{kind}_ess_per_second_lower'] = left/cpu_bounds[1]
        result[f'cpu_{kind}_ess_per_second_upper'] = left/cpu_bounds[0]
        result[f'gpu_{kind}_ess_per_second'] = right/gpu_seconds
        result[f'cpu_to_gpu_{kind}_rate_ratio_lower'] = left/right*gpu_seconds/cpu_bounds[1]
        result[f'cpu_to_gpu_{kind}_rate_ratio_upper'] = left/right*gpu_seconds/cpu_bounds[0]
    return result


def families(table):
    groups = pd.Series([str(n).split('[', 1)[0] for n in table.index], index=table.index)
    result = []
    for name in sorted(groups.unique()):
        rows = table.loc[groups == name]
        item = {'family': name, 'parameters': len(rows)}
        for kind in ('bulk', 'tail'):
            low = rows[f'cpu_to_gpu_{kind}_rate_ratio_lower']
            high = rows[f'cpu_to_gpu_{kind}_rate_ratio_upper']
            item[kind] = {'cpu_faster_throughout_timing_bounds': int((low > 1).sum()),
                          'gpu_faster_throughout_timing_bounds': int((high < 1).sum()),
                          'timing_bounds_overlap_equal_rate': int(((low <= 1) & (high >= 1)).sum()),
                          'median_cpu_to_gpu_rate_ratio_bounds': [float(low.median()), float(high.median())]}
        result.append(item)
    return result


def run(cpu_efficiency, gpu_efficiency, cpu_experiment, gpu_benchmark, output):
    ce, ge, cx, gb, output = map(Path, (cpu_efficiency, gpu_efficiency, cpu_experiment, gpu_benchmark, output))
    cm, cf = _verified_bundle(ce, retain={'summary.json', 'parameter-efficiency.csv', 'derived-efficiency.csv'})
    _, gf = _verified_bundle(ge/'complete', retain={'diagnostics.json', 'parameter-efficiency.csv', 'derived-efficiency.csv'})
    pm, pf = _verified_bundle(cx/'protocol', retain={'protocol.json'})
    fm, ff = _verified_bundle(cx/'fit', retain={'feature-design.json'})
    _, bf = _verified_bundle(gb/'protocol', retain={'settings.json'})
    c, g = json.loads(cf['summary.json']), json.loads(gf['diagnostics.json'])
    cp, gp = json.loads(pf['protocol.json']), json.loads(bf['settings.json'])
    completed = json.loads((gb/'sampled.json').read_text())
    if (not c['acceptable'] or not g['acceptable']
            or cm['fit_manifest_sha256'] != digest(cx/'fit/complete.json')
            or cm['protocol_manifest_sha256'] != digest(cx/'protocol/complete.json')
            or fm['protocol_sha256'] != pm['protocol_sha256']
            or g['benchmark_record_sha256'] != digest(gb/'sampled.json')
            or g['posterior_sha256'] != completed['posterior_sha256']
            or g['posterior_sha256'] != digest(gb/'posterior.nc') or completed['settings'] != gp):
        raise ValueError('Completed diagnostic gates or fit bindings differ')
    for left, right in [('source_manifest_sha256', 'source_manifest_sha256'),
                        ('source_observations_sha256', 'source_observations_sha256'),
                        ('chains', 'chains'), ('draws', 'draws_per_chain'), ('tune', 'warmup_per_chain'),
                        ('seed', 'seed'), ('target_accept', 'target_accept'), ('rows', 'rows'),
                        ('units', 'units'), ('buildings', 'buildings'), ('graph_configuration', 'graph_configuration')]:
        if cp[left] != gp[right]:
            raise ValueError('CPU/GPU comparison settings differ: '+left)
    design = json.loads(ff['feature-design.json'])
    if (design['features'] != gp['feature_names'] or design['prior_scales'] != gp['feature_prior_scales']
            or gp['float64'] is not True or gp['dense_mass'] is not False or cp['adaptation'] != 'diag'):
        raise ValueError('Feature design, precision or mass matrix differs')
    shared_code = cp['implementation_sha256'].keys() & gp['implementation_sha256'].keys()
    if any(cp['implementation_sha256'][name] != gp['implementation_sha256'][name] for name in shared_code):
        raise ValueError('Shared CPU/GPU model implementation differs')
    bounds = [c['timing']['retained_wall_seconds_lower'], c['timing']['retained_wall_seconds_upper']]
    seconds = g['timing_denominators_seconds']['retained_compute_and_storage']
    files = {}
    comparison = {}
    for name in ('parameter', 'derived'):
        cpu = pd.read_csv(io.BytesIO(cf[name+'-efficiency.csv']), index_col=0)
        gpu = pd.read_csv(io.BytesIO(gf[name+'-efficiency.csv']), index_col=0)
        table = paired_rates(cpu, gpu, bounds, seconds)
        files[name+'-comparison.csv'] = table.to_csv(index_label='parameter')
        comparison[name] = families(table)
    quality = {}
    for name, gpu_key in [('parameters', 'parameters'), ('derived', 'derived_unit_and_bathroom_contributions'),
                          ('floor', 'joint_floor_contrasts')]:
        cd, gd = c['diagnostics'][name], g[gpu_key]
        quality[name] = {'cpu': {k: cd[k] for k in ('max_rhat', 'min_ess_bulk', 'min_ess_tail')},
                         'gpu': {k: gd[k] for k in ('max_rhat', 'min_ess_bulk', 'min_ess_tail')}}
        for kind in ('bulk', 'tail'):
            quality[name]['cpu']['minimum_'+kind+'_ess_per_second_bounds'] = [cd['min_ess_'+kind]/bounds[1], cd['min_ess_'+kind]/bounds[0]]
            quality[name]['gpu']['minimum_'+kind+'_ess_per_second'] = gd['min_ess_'+kind]/seconds
    result = {'version': 'matched-sampler-efficiency-comparison-v1',
              'cpu_retained_wall_seconds_bounds': bounds, 'gpu_retained_compute_and_storage_seconds': seconds,
              'all_diagnostic_families_acceptable': True, 'family_comparisons': comparison,
              'diagnostic_family_minima': quality,
              'shared_model_code_files': sorted(shared_code),
              'scope': 'Nutpie/Numba on Ryzen 5 3600X versus NumPyro float64 vectorized chains on RTX 2060 SUPER, this exact model and run. CPU bounds include asynchronous warmup overlap; GPU retained time includes first-loop JIT and all batch transfers/writes. Neither rate includes final posterior conversion. Timing intervals are not statistical confidence intervals. No universal fastest-backend claim, and repeated-run variability has not been measured.'}
    files.update({'comparison.json': canonical(result)+'\n', Path(__file__).name: Path(__file__).read_text()})
    publish_bundle(output, files, {'version': result['version'],
        'cpu_efficiency_manifest_sha256': digest(ce/'complete.json'),
        'gpu_efficiency_manifest_sha256': digest(ge/'complete/complete.json'),
        'cpu_fit_manifest_sha256': digest(cx/'fit/complete.json'),
        'gpu_completed_record_sha256': digest(gb/'sampled.json')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cpu_efficiency', 'gpu_efficiency', 'cpu_experiment', 'gpu_benchmark', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

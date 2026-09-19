import numpy as np
import pandas as pd
import pytest

from models.compare_sampler_efficiency import families, paired_rates, run


def inputs():
    return (pd.DataFrame({'ess_bulk': [600, 2400], 'ess_tail': [300, 1200]}, index=['beta[a]', 'unit_z[u]']),
            pd.DataFrame({'ess_bulk': [1000, 200], 'ess_tail': [600, 100]}, index=['unit_z[u]', 'beta[a]']))


def test_comparison_aligns_names_and_propagates_inverse_timing_bounds():
    cpu, gpu = inputs()
    table = paired_rates(cpu, gpu, (100, 200), 100)
    assert table.loc['beta[a]', 'cpu_to_gpu_bulk_rate_ratio_lower'] == 1.5
    assert table.loc['beta[a]', 'cpu_to_gpu_bulk_rate_ratio_upper'] == 3
    assert table.loc['unit_z[u]', 'cpu_to_gpu_tail_rate_ratio_lower'] == 1
    summary = {r['family']: r for r in families(table)}
    assert summary['beta']['bulk']['cpu_faster_throughout_timing_bounds'] == 1
    assert summary['unit_z']['tail']['timing_bounds_overlap_equal_rate'] == 1


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'negative_ess', 'nan', 'reversed_bounds', 'zero_time'])
def test_invalid_alignment_or_rates_cannot_produce_ranking(fault):
    cpu, gpu = inputs()
    bounds, seconds = (100, 200), 100
    if fault == 'missing': gpu = gpu.iloc[:1]
    elif fault == 'duplicate': gpu.index = ['beta[a]', 'beta[a]']
    elif fault == 'negative_ess': cpu.iloc[0, 0] = -1
    elif fault == 'nan': gpu.iloc[0, 1] = np.nan
    elif fault == 'reversed_bounds': bounds = (200, 100)
    elif fault == 'zero_time': seconds = 0
    with pytest.raises(ValueError):
        paired_rates(cpu, gpu, bounds, seconds)


def comparison_bundles(root, fault=None):
    from apartments.corrections import canonical
    from apartments.research_pipeline import digest, publish_bundle
    cpu, gpu = inputs()
    cp = dict(source_manifest_sha256='dataset', source_observations_sha256='observations',
              chains=4, draws=6000, tune=4000, seed=123, target_accept=.93, rows=20,
              units=10, buildings=2, graph_configuration={}, adaptation='diag',
              implementation_sha256={'graph.py': 'same-graph'})
    gp = {k: v for k, v in cp.items() if k not in ('draws', 'tune', 'adaptation')}
    gp.update(draws_per_chain=6000, warmup_per_chain=4000, feature_names=['a'],
              feature_prior_scales=[.15], float64=True, dense_mass=False)
    if fault == 'cohort': gp['source_observations_sha256'] = 'different'
    if fault == 'prior': gp['feature_prior_scales'] = [.30]
    if fault == 'code': gp['implementation_sha256'] = {'graph.py': 'different'}
    cx, gb, ce, ge = (root/n for n in ('cpu-fit', 'gpu-fit', 'cpu-rates', 'gpu-rates'))
    publish_bundle(cx/'protocol', {'protocol.json': canonical(cp)+'\n'}, {'protocol_sha256': 'cpu-protocol'})
    publish_bundle(cx/'fit', {'feature-design.json': canonical({'features': ['a'], 'prior_scales': [.15]})+'\n'},
                   {'protocol_sha256': 'cpu-protocol'})
    publish_bundle(gb/'protocol', {'settings.json': canonical(gp)+'\n'}, {})
    (gb/'posterior.nc').write_bytes(b'fixed posterior bytes for binding tests')
    posterior_hash = digest(gb/'posterior.nc')
    (gb/'sampled.json').write_text(canonical({'settings': gp, 'posterior_sha256': posterior_hash})+'\n')
    diagnostic = {'max_rhat': 1.001, 'min_ess_bulk': 600., 'min_ess_tail': 500.}
    cs = {'acceptable': True, 'timing': {'retained_wall_seconds_lower': 100, 'retained_wall_seconds_upper': 200},
          'diagnostics': {k: diagnostic for k in ('parameters', 'derived', 'floor')}}
    gs = {'acceptable': fault != 'diagnostics', 'benchmark_record_sha256': digest(gb/'sampled.json'),
          'posterior_sha256': posterior_hash, 'timing_denominators_seconds': {'retained_compute_and_storage': 100},
          **{k: diagnostic for k in ('parameters', 'derived_unit_and_bathroom_contributions', 'joint_floor_contrasts')}}
    files = {n+'-efficiency.csv': cpu.to_csv(index_label='parameter') for n in ('parameter', 'derived')}
    publish_bundle(ce, {**files, 'summary.json': canonical(cs)+'\n'},
                   {'fit_manifest_sha256': digest(cx/'fit/complete.json'),
                    'protocol_manifest_sha256': digest(cx/'protocol/complete.json')})
    files = {n+'-efficiency.csv': gpu.to_csv(index_label='parameter') for n in ('parameter', 'derived')}
    publish_bundle(ge/'complete', {**files, 'diagnostics.json': canonical(gs)+'\n'}, {})
    if fault == 'posterior': (gb/'posterior.nc').write_bytes(b'changed after diagnostics')
    return ce, ge, cx, gb, root/'comparison'


def test_completed_comparison_publishes_separate_parameter_families(tmp_path):
    args = comparison_bundles(tmp_path)
    result = run(*args)
    assert [r['family'] for r in result['family_comparisons']['parameter']] == ['beta', 'unit_z']
    assert result['diagnostic_family_minima']['floor']['cpu']['minimum_bulk_ess_per_second_bounds'] == [3, 6]
    assert (args[-1]/'complete.json').exists()


@pytest.mark.parametrize('fault', ['cohort', 'prior', 'code', 'diagnostics', 'posterior'])
def test_completed_comparison_refuses_mismatch_or_failed_diagnostics(tmp_path, fault):
    args = comparison_bundles(tmp_path, fault)
    with pytest.raises(ValueError):
        run(*args)
    assert not args[-1].exists()

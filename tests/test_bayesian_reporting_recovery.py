import pandas as pd
import pytest
from models.bayesian_feature_report import verify_reporting_recovery, verify_reporting_cache


def valid():
    diag = {n: n+'-hash' for n in ('diagnostics.json', 'derived-diagnostics.json',
        'parameter-diagnostics.csv', 'derived-diagnostics.csv')}
    code = {n: n+'-hash' for n in ('recover_bayesian_reports.py', 'bayesian_report_cache.py', 'bayesian_feature_report.py')}
    recovery = {'version': 'completed-diagnostics-report-recovery-v1', 'protocol_sha256': 'p',
        'posterior_sha256': 'posterior', 'completed_diagnostic_sha256': diag,
        'implementation_sha256': code, 'maximum_source_block_bytes': 1024}
    return {'files': {'posterior.nc': 'posterior', **diag, **code}}, recovery


@pytest.mark.parametrize('damage', ['none', 'posterior', 'protocol', 'diagnostic', 'code', 'block'])
def test_recovery_binds_completed_inference_and_override_code(damage):
    manifest, recovery = valid()
    if damage == 'none':
        assert verify_reporting_recovery('p', manifest, recovery) == recovery
        return
    if damage == 'posterior': recovery['posterior_sha256'] = 'different'
    if damage == 'protocol': recovery['protocol_sha256'] = 'different'
    if damage == 'diagnostic': manifest['files']['diagnostics.json'] = 'different'
    if damage == 'code': manifest['files']['bayesian_report_cache.py'] = 'different'
    if damage == 'block': recovery['maximum_source_block_bytes'] = 9*1024*1024
    with pytest.raises(ValueError, match='Reporting recovery'):
        verify_reporting_recovery('p', manifest, recovery)


def test_completed_diagnostic_table_cannot_be_substituted():
    from models.recover_bayesian_reports import check_table
    table = pd.DataFrame({'r_hat': [1., 1.001], 'ess_bulk': [1000., 1100.], 'ess_tail': [1200., 1300.]})
    diag = {'max_rhat': 1.001, 'min_ess_bulk': 1000., 'median_ess_bulk': 1050., 'min_ess_tail': 1200.,
            'parameters': 2, 'rhat_over_1_01': 0, 'nonfinite_diagnostics': 0}
    check_table(diag, table)
    table.loc[0, 'ess_bulk'] = 50
    with pytest.raises(ValueError, match='table differs'): check_table(diag, table)


@pytest.mark.parametrize('damage', ['none', 'draws', 'posterior', 'code', 'order', 'block'])
def test_forward_cache_binds_all_draws_and_implementation(damage):
    protocol = {'chains': 4, 'draws': 6000, 'units': 100}
    manifest = {'files': {'posterior.nc': 'posterior', 'bayesian_report_cache.py': 'code'}}
    cache = {**protocol, 'version': 'bayesian-unit-report-cache-v1', 'protocol_sha256': 'p',
        'posterior_sha256': 'posterior', 'implementation_sha256': 'code', 'all_retained_draws': True,
        'sample_order': 'chain_major_then_draw', 'maximum_source_block_bytes': 4096}
    if damage == 'none':
        assert verify_reporting_cache(protocol, 'p', manifest, cache) == cache
        return
    if damage == 'draws': cache['draws'] = 1000
    if damage == 'posterior': cache['posterior_sha256'] = 'different'
    if damage == 'code': cache['implementation_sha256'] = 'different'
    if damage == 'order': cache['sample_order'] = 'unknown'
    if damage == 'block': cache['maximum_source_block_bytes'] = 9*1024*1024
    with pytest.raises(ValueError, match='Reporting cache'): verify_reporting_cache(protocol, 'p', manifest, cache)

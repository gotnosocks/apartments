"""Finish an interrupted disk fit from its posterior and completed diagnostics.

No sampling or numerical model changes. The original inference protocol remains
immutable; a separate recovery plan binds the completed diagnostic products and
the report execution override, which is also recorded in the final fit bundle.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_disk_experiment as disk
from . import bayesian_feature_report as verified
from . import bayesian_report_cache as cache
from . import bayesian_source_sensitivity as source

VERSION = 'completed-diagnostics-report-recovery-v1'
DIAGNOSTICS = ('diagnostics.json', 'derived-diagnostics.json',
               'parameter-diagnostics.csv', 'derived-diagnostics.csv')


def check_table(diag, table):
    """Completed tables must agree with the summary actually checked by readers."""
    fields = {'max_rhat': table.r_hat.max(), 'min_ess_bulk': table.ess_bulk.min(),
              'min_ess_tail': table.ess_tail.min(), 'median_ess_bulk': table.ess_bulk.median()}
    if any(not np.isclose(diag[k], v, rtol=1e-12, atol=1e-12) for k, v in fields.items()):
        raise ValueError('Completed diagnostic table differs from summary')
    if (diag['parameters'] != len(table) or diag['rhat_over_1_01'] != int((table.r_hat > 1.01).sum())
            or diag['nonfinite_diagnostics'] != int((~np.isfinite(table[['r_hat','ess_bulk','ess_tail']])).sum().sum())):
        raise ValueError('Completed diagnostic count differs')


def run(experiment, dataset):
    root = Path(experiment); target = root/'fit'
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pm, pf = _verified_bundle(root/'protocol', retain={'protocol.json'})
        protocol = json.loads(pf['protocol.json']); ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        if pm.get('protocol_sha256') != ph or not disk.disk_protocol.verify_protocol(protocol):
            raise ValueError('Invalid original disk protocol')
        base = disk.increments if protocol['version'] == disk.increments.VERSION else disk.linear
        if protocol['version'] != base.VERSION:
            raise ValueError('Unsupported inference protocol')
        for path in base.implementation_paths():
            if protocol['implementation_sha256'].get(path.name) != digest(path):
                raise ValueError('Original scientific implementation changed: '+path.name)
        data, sm = base.load_data(dataset)
        if (digest(Path(dataset)/'complete.json') != protocol['source_manifest_sha256']
                or sm['files']['observations.jsonl'] != protocol['source_observations_sha256']):
            raise ValueError('Original dataset differs')
        if (target/'complete.json').exists():
            report, _ = verified.build_report(root, dataset)
            return {'status': report['status'], 'reused_complete_fit': True}
        posterior_hash = digest(target/'posterior.nc')
        if json.loads((target/'posterior-checkpoint.json').read_text()) != {'protocol_sha256': ph, 'posterior_sha256': posterior_hash}:
            raise ValueError('Original posterior checkpoint differs')
        partial_files = {p.name: digest(p) for p in target.iterdir() if p.is_file() and p.name in
                         {*DIAGNOSTICS, *source.comparison.DESIGNS, 'posterior.nc'}}
        source.verify_design(root, dataset, protocol, {'protocol_manifest': pm,
            'fit_manifest': {'protocol_sha256': ph, 'files': partial_files}})
        diag, derived = [json.loads((target/name).read_text()) for name in DIAGNOSTICS[:2]]
        diagnostic_payloads = {name: (target/name).read_bytes() for name in DIAGNOSTICS}
        table, derived_table = [pd.read_csv(target/name, index_col=0, float_precision='round_trip') for name in DIAGNOSTICS[2:]]
        check_table(diag, table); check_table(derived, derived_table)
        verified.check_diagnostics({'status': 'exploratory_converged', 'diagnostics': diag,
                                    'derived_diagnostics': derived}, diag, derived)
        configuration = json.loads((target/'graph-configuration.json').read_text())
        if configuration != protocol['graph_configuration']: raise ValueError('Graph configuration differs')
        disk.disk_protocol.verify_products(protocol, json.loads((target/'storage.json').read_text()),
            json.loads((target/'trace-manifest.json').read_text()), posterior_hash)
        paths = [Path(__file__), Path(cache.__file__), Path(verified.__file__)]
        plan = {'version': VERSION, 'protocol_sha256': ph, 'posterior_sha256': posterior_hash,
            'completed_diagnostic_sha256': {n: digest(target/n) for n in DIAGNOSTICS},
            'implementation_sha256': {p.name: digest(p) for p in paths},
            'policy': 'Reuse both completed, passing diagnostic tables from the interrupted run. Preserve every posterior draw, original scientific reporting formula, cohort and inference protocol. Disk-backed unit access only; no sampling or model promotion.'}
        publish_bundle(root/'report-recovery', {'recovery.json': canonical(plan)+'\n',
            **{p.name: p.read_text() for p in paths}}, {'version': VERSION, 'protocol_sha256': ph})
        design = (disk.increments.floor.FeatureDesign(data, protocol['specification'],
                  floor_increment_prior_scale=protocol['floor_increment_prior_scale'])
                  if base is disk.increments else base.v2.feature.FeatureDesign(data, protocol['specification']))
        args = argparse.Namespace(**protocol)
        with xr.open_datatree(target/'posterior.nc', engine='h5netcdf', cache=False) as inference:
            base.validate_posterior(inference, args, design, configuration)
            base.v2.sampler.write_status(root/'progress.json', 'recovering_reports', recovery_version=VERSION)
            with cache.bounded_unit_samples(base.v2.base, inference, root/'report-cache', posterior_hash) as cached:
                def saved_parameters(actual):
                    if actual is not inference: raise ValueError('Unexpected diagnostic input')
                    return dict(diag), table.copy()
                def saved_derived(actual, actual_design, actual_data):
                    if actual is not inference or actual_design is not design or actual_data is not data:
                        raise ValueError('Unexpected derived-diagnostic input')
                    return dict(derived), derived_table.copy()
                with ExitStack() as stack:
                    stack.enter_context(patch.object(base.v2.base, 'diagnostics', saved_parameters))
                    stack.enter_context(patch.object(base.v2, 'derived_diagnostics', saved_derived))
                    result = base.v2.write_reports(target, inference, design, data, ph)
            # These are reused completed products, not newly computed diagnostics.
            # Preserve their exact serialization after the reference writer runs.
            for name, payload in diagnostic_payloads.items():
                (target/name).write_bytes(payload)
            if base is disk.increments:
                floors = disk.increments.floor_contrasts(inference, design)
                (target/'floor-contrasts.json').write_text(canonical(floors)+'\n')
                result['floor_diagnostics'] = floors['diagnostics']
                if not floors['diagnostics']['acceptable']: result['status'] = 'diagnostic_only_do_not_interpret_intervals'
                (target/'summary.json').write_text(canonical(result)+'\n')
            (target/'residual-scales.json').write_text(canonical(base.residual_scale_summary(inference, data, configuration))+'\n')
        recovery = {**plan, 'cache_manifest_sha256': digest(root/'report-cache/complete.json'),
                    'maximum_source_block_bytes': cached['maximum_source_block_bytes'],
                    'recovery_manifest_sha256': digest(root/'report-recovery/complete.json')}
        (target/'reporting-recovery.json').write_text(canonical(recovery)+'\n')
        for p in paths:
            if digest(p) != plan['implementation_sha256'][p.name]: raise ValueError('Recovery code changed')
            (target/p.name).write_bytes(p.read_bytes())
        if any(digest(target/n) != plan['completed_diagnostic_sha256'][n] for n in DIAGNOSTICS):
            raise ValueError('Recovery changed completed diagnostics')
        base.v2.sampler.publish_fit(target, version=base.VERSION, protocol_hash=ph)
        verified.build_report(root, dataset)
        base.v2.sampler.write_status(root/'progress.json', 'complete', status=result['status'], recovery_version=VERSION)
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', type=Path, required=True); p.add_argument('--dataset', type=Path, required=True)
    with threadpool_limits(limits=1, user_api='blas'):
        result = run(**vars(p.parse_args()))
    print(canonical({'status': result['status']}))

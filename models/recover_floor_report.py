"""Finish the floor report after the xarray variable/dimension name collision."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'floor-contrast-coordinate-recovery-v1'
RUNNER = 'bayesian_feature_experiment_v4.py'
PRESERVED = {'posterior.nc', 'prior.nc', 'posterior-checkpoint.json', 'diagnostics.json',
    'derived-diagnostics.json', 'parameter-diagnostics.csv', 'derived-diagnostics.csv',
    'coefficients.json', 'bathroom-contrasts.json', 'group-effects.jsonl', 'residuals.jsonl',
    'feature-design.json', 'time-design.json', 'time-design.npz', 'graph-configuration.json',
    'compression.json', 'storage.json', 'trace-manifest.json', 'reporting-cache.json',
    'bayesian_report_cache.py'}


def coordinate_fix(original):
    substitutions = [("dims=('floor_contrast','feature')", "dims=('contrast','feature')"),
        ("coords={'floor_contrast':np.arange(len(pairs))", "coords={'contrast':np.arange(len(pairs))"),
        ('joint.isel(floor_contrast=i)', 'joint.isel(contrast=i)')]
    for before, after in substitutions:
        if original.count(before) != 1: raise ValueError('Unexpected original floor report implementation')
        original = original.replace(before, after)
    return original


def verify_recovery(protocol, ph, manifest, recovery, original_code, fixed_code, before, after):
    files = manifest['files']
    code = {RUNNER, 'recover_floor_report.py', 'bayesian_feature_report.py'}
    if (recovery.get('version') != VERSION or recovery.get('protocol_sha256') != ph
            or protocol.get('version') != 'observable-bayesian-floor-experiment-v4'
            or recovery.get('original_runner_sha256') != protocol['implementation_sha256'].get(RUNNER)
            or hashlib.sha256(original_code.encode()).hexdigest() != recovery['original_runner_sha256']
            or coordinate_fix(original_code) != fixed_code
            or set(recovery.get('implementation_sha256', {})) != code
            or any(files.get(k) != v for k,v in recovery['implementation_sha256'].items())
            or hashlib.sha256(fixed_code.encode()).hexdigest() != files.get(RUNNER)
            or set(recovery.get('preserved_product_sha256', {})) != PRESERVED
            or any(files.get(k) != v for k,v in recovery['preserved_product_sha256'].items())
            or files.get('pre-floor-summary.json') != recovery.get('original_summary_sha256')):
        raise ValueError('Floor reporting recovery binding differs')
    if ({k:v for k,v in before.items() if k != 'status'}
            != {k:v for k,v in after.items() if k not in ('floor_diagnostics','status')}):
        raise ValueError('Floor recovery changed earlier report summaries')
    expected_status = (before['status'] if after['floor_diagnostics']['acceptable']
                       else 'diagnostic_only_do_not_interpret_intervals')
    if after['status'] != expected_status: raise ValueError('Floor diagnostic status differs')
    return recovery


def run(experiment, dataset):
    from . import bayesian_feature_experiment_v4 as base
    from . import bayesian_feature_report as report
    from . import bayesian_disk_protocol as disk
    from . import bayesian_source_sensitivity as source
    from . import recover_bayesian_reports as diagnostics
    root, dataset = Path(experiment), Path(dataset); target = root/'fit'
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pm, pf = _verified_bundle(root/'protocol', retain={'protocol.json', RUNNER})
        protocol = json.loads(pf['protocol.json']); ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        if (protocol['version'] != base.VERSION or pm['protocol_sha256'] != ph or not disk.verify_protocol(protocol)):
            raise ValueError('Original floor disk protocol required')
        original_code = pf[RUNNER].decode(); fixed_code = Path(base.__file__).read_text()
        if coordinate_fix(original_code) != fixed_code: raise ValueError('Only the coordinate naming fix is permitted')
        for p in base.implementation_paths():
            if p.name != RUNNER and digest(p) != protocol['implementation_sha256'][p.name]:
                raise ValueError('Scientific implementation changed: '+p.name)
        if (target/'complete.json').exists(): return report.build_report(root,dataset)[0]['status']
        data, sm = base.load_data(dataset)
        if digest(dataset/'complete.json') != protocol['source_manifest_sha256'] or sm['files']['observations.jsonl'] != protocol['source_observations_sha256']:
            raise ValueError('Original dataset differs')
        preserved = {n: digest(target/n) for n in PRESERVED}
        if json.loads((target/'posterior-checkpoint.json').read_text()) != {'protocol_sha256':ph,'posterior_sha256':preserved['posterior.nc']}:
            raise ValueError('Original posterior checkpoint differs')
        source.verify_design(root,dataset,protocol,{'protocol_manifest':pm,'fit_manifest':{'protocol_sha256':ph,'files':preserved}})
        recovery_root=root/'floor-report-recovery'
        previous = (_verified_bundle(recovery_root,retain={'pre-floor-summary.json'})[1]['pre-floor-summary.json']
                    if (recovery_root/'complete.json').exists() else (target/'summary.json').read_bytes())
        before=json.loads(previous)
        diag, derived = [json.loads((target/n).read_text()) for n in diagnostics.DIAGNOSTICS[:2]]
        report.check_diagnostics(before,diag,derived)
        for name, d in zip(diagnostics.DIAGNOSTICS[2:], (diag,derived), strict=True):
            diagnostics.check_table(d,diagnostics.pd.read_csv(target/name,index_col=0,float_precision='round_trip'))
        paths=[Path(__file__),Path(base.__file__),Path(report.__file__)]
        plan={'version':VERSION,'protocol_sha256':ph,'original_runner_sha256':protocol['implementation_sha256'][RUNNER],
            'preserved_product_sha256':preserved,'original_summary_sha256':hashlib.sha256(previous).hexdigest(),
            'implementation_sha256':{p.name:digest(p) for p in paths},
            'policy':'Only rename the xarray contrast dimension. Preserve all posterior draws and completed inference/report products; compute floor diagnostics without resampling.'}
        publish_bundle(recovery_root,{'recovery.json':canonical(plan)+'\n','pre-floor-summary.json':previous.decode(),
            **{p.name:p.read_text() for p in paths}}, {'version':VERSION,'protocol_sha256':ph})
        design=base.floor.FeatureDesign.load(target)
        configuration=json.loads((target/'graph-configuration.json').read_text())
        if configuration != protocol['graph_configuration']: raise ValueError('Graph configuration differs')
        with xr.open_datatree(target/'posterior.nc',engine='h5netcdf',cache=False) as inference:
            base.validate_posterior(inference,argparse.Namespace(**protocol),design,configuration)
            floors=base.floor_contrasts(inference,design)
            scales=base.residual_scale_summary(inference,data,configuration)
        after={**before,'floor_diagnostics':floors['diagnostics']}
        if not floors['diagnostics']['acceptable']: after['status']='diagnostic_only_do_not_interpret_intervals'
        files={'floor-contrasts.json':canonical(floors)+'\n','residual-scales.json':canonical(scales)+'\n',
            'summary.json':canonical(after)+'\n','pre-floor-summary.json':previous.decode(),
            'floor-report-recovery.json':canonical(plan)+'\n',**{p.name:p.read_text() for p in paths}}
        for name, payload in files.items(): (target/name).write_text(payload)
        if any(digest(target/n)!=sha for n,sha in preserved.items()): raise ValueError('Completed product changed during recovery')
        if any(digest(p)!=plan['implementation_sha256'][p.name] for p in paths): raise ValueError('Recovery code changed')
        disk.verify_products(protocol,json.loads((target/'storage.json').read_text()),json.loads((target/'trace-manifest.json').read_text()),preserved['posterior.nc'])
        base.v2.sampler.publish_fit(target,version=base.VERSION,protocol_hash=ph)
        result=report.build_report(root,dataset)[0]
        base.v2.sampler.write_status(root/'progress.json','complete',status=result['status'],recovery_version=VERSION)
        return result['status']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'): status=run(**vars(p.parse_args()))
    print(canonical({'status':status}))

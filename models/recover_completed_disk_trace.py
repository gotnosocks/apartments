"""Validate/export finished draws whose reader stalled before finalization.

Preparation is read-only on the original experiment. Installation requires its
exclusive run lock and rechecks the complete raw inventory. Never resamples.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle, _verified_bundle
from models import bayesian_disk_sampling as storage


def validate_finished(identity, protocol, progress, trace):
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    fields = ('chains', 'draws', 'tune', 'seed', 'adaptation', 'target_accept')
    if identity['protocol_sha256'] != ph or any(identity[k] != protocol[k] for k in fields):
        raise ValueError('Recovery identity differs from frozen protocol')
    chains = progress.get('chains', [])
    if (len(chains) != identity['chains']
            or {r['chain'] for r in chains} != set(range(identity['chains']))
            or any(r['finished_draws'] != identity['draws']+identity['tune']
                   or r['total_draws'] != r['finished_draws'] or r['tuning'] for r in chains)):
        raise ValueError('Sampler has not reported every chain finished')
    settings = trace.attrs['sampler_settings']
    for raw, key in [('num_chains', 'chains'), ('num_draws', 'draws'),
                     ('num_tune', 'tune'), ('seed', 'seed')]:
        if settings[raw] != identity[key]:
            raise ValueError('Raw sampler settings differ')
    if (trace.attrs.get('adaptation_kind') != 'diagonal' or identity['adaptation'] != 'diag'
            or settings['adapt_options']['step_size_settings']['target_accept'] != identity['target_accept']):
        raise ValueError('Unsupported or different raw adaptation')
    groups = storage.retained_groups(trace, identity['contract'])
    if not np.all(groups['sample_stats'].n_steps.values > 0):
        raise ValueError('Missing retained sampler statistics')
    return ph


def prepare(experiment, output):
    experiment, output = Path(experiment), Path(output)
    if output.exists():
        raise ValueError('Recovery output must be new')
    output.mkdir(parents=True)
    identity = json.loads((experiment/'trace/intent.json').read_text())
    _, blobs = _verified_bundle(experiment/'protocol', retain={'protocol.json'})
    protocol = json.loads(blobs['protocol.json'])
    progress = json.loads((experiment/'progress.json').read_text())
    raw = experiment/'trace/raw.zarr'
    inventory = storage.trace_files(raw)
    with xr.open_datatree(raw, engine='zarr', consolidated=False) as trace:
        ph = validate_finished(identity, protocol, progress, trace)
        print('Validating/exporting every retained posterior value in bounded slabs', flush=True)
        exported = storage.export_trace(trace, identity['contract'], output/'posterior.nc')
    if inventory != storage.trace_files(raw):
        raise ValueError('Raw trace changed during recovery')
    manifest = {'identity': identity, 'files': inventory}
    exported['trace_manifest_sha256'] = hashlib.sha256((canonical(manifest)+'\n').encode()).hexdigest()
    publish_bundle(output/'validation', {
        'trace-manifest.json': canonical(manifest)+'\n',
        'storage.json': canonical(exported)+'\n',
        'sampler-progress.json': canonical(progress)+'\n',
        'recovery.json': canonical({'experiment': str(experiment.resolve()),
            'protocol_sha256': ph, 'posterior_sha256': digest(output/'posterior.nc'),
            'reason': 'All chains finished; synchronous Zarr reader stalls in sandbox and opens on host. Existing raw values exported unchanged; no resampling.'})+'\n',
        Path(__file__).name: Path(__file__).read_text(),
    }, {'version': 'completed-disk-trace-recovery-v1'})
    print('Recovery prepared; original experiment remains untouched', flush=True)


def install(experiment, output):
    experiment, output = Path(experiment), Path(output)
    with (experiment/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _, blobs = _verified_bundle(output/'validation', retain={
            'trace-manifest.json', 'storage.json', 'recovery.json'})
        record = json.loads(blobs['recovery.json'])
        manifest = json.loads(blobs['trace-manifest.json'])
        if (record['experiment'] != str(experiment.resolve())
                or record['posterior_sha256'] != digest(output/'posterior.nc')
                or manifest['identity'] != json.loads((experiment/'trace/intent.json').read_text())
                or manifest['files'] != storage.trace_files(experiment/'trace/raw.zarr')):
            raise ValueError('Recovery or raw trace binding changed')
        target = experiment/'fit'
        destinations = [experiment/'trace/complete.json', target/'posterior.nc',
                        target/'storage.json', target/'trace-manifest.json', target/'posterior-checkpoint.json']
        if any(p.exists() for p in destinations):
            raise ValueError('Existing finalized products must not be overwritten')
        # Original raw archive is preserved. All installation writes are new.
        shutil.copyfile(output/'posterior.nc', target/'posterior.nc.partial')
        (target/'posterior.nc.partial').replace(target/'posterior.nc')
        storage.atomic_json(experiment/'trace/complete.json', manifest)
        (target/'trace-manifest.json').write_bytes(blobs['trace-manifest.json'])
        (target/'storage.json').write_bytes(blobs['storage.json'])
        storage.atomic_json(target/'posterior-checkpoint.json', {
            'protocol_sha256': record['protocol_sha256'], 'posterior_sha256': record['posterior_sha256']})
        print('Verified posterior checkpoint installed; reports can resume without sampling', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'install'))
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args())
    (prepare if args.pop('action') == 'prepare' else install)(**args)

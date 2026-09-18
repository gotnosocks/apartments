"""Verification of storage-only execution metadata shared by experiment readers."""
from __future__ import annotations
import hashlib
from apartments.corrections import canonical

VERSION='bayesian-disk-experiment-v1'
CODE={'bayesian_disk_sampling.py','bayesian_disk_experiment.py','bayesian_disk_protocol.py'}
POLICY={'version':'bayesian-disk-sampling-v1','backend':'nutpie_zarr_local',
    'all_retained_draws':True,'warmup_in_export':False,'raw_trace_includes_warmup':True,
    'raw_event_statistics_preserved':True,'export_max_array_block_bytes':8*1024*1024}
FIELDS={'execution_version','storage_policy','storage_versions'}


def verify_protocol(protocol):
    present=FIELDS & protocol.keys()
    if not present:return False
    if (present!=FIELDS or protocol['execution_version']!=VERSION or protocol['storage_policy']!=POLICY
            or not CODE<=protocol['implementation_sha256'].keys()
            or set(protocol['storage_versions'])!={'zarr','obstore','xarray','h5py'}
            or any(not isinstance(v,str) or not v for v in protocol['storage_versions'].values())):
        raise ValueError('Unsupported disk execution protocol')
    return True


def verify_products(protocol,storage,trace_manifest,posterior_sha256):
    if not verify_protocol(protocol):raise ValueError('Missing disk execution protocol')
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    identity=trace_manifest.get('identity',{})
    if (identity.get('protocol_sha256')!=ph or identity.get('version')!=POLICY['version']
            or any(identity.get(k)!=protocol[k] for k in ('chains','draws','tune','seed','adaptation','target_accept'))
            or not trace_manifest.get('files')
            or storage.get('version')!=POLICY['version'] or storage.get('posterior_sha256')!=posterior_sha256
            or storage.get('trace_manifest_sha256')!=hashlib.sha256((canonical(trace_manifest)+'\n').encode()).hexdigest()
            or storage.get('chains')!=protocol['chains'] or storage.get('draws')!=protocol['draws']
            or storage.get('warmup_exported') is not False or storage.get('raw_event_statistics_preserved') is not True
            or storage.get('block_budget_bytes')!=POLICY['export_max_array_block_bytes']
            or type(storage.get('maximum_array_block_bytes')) is not int
            or not 0<storage['maximum_array_block_bytes']<=storage['block_budget_bytes']):
        raise ValueError('Disk storage products differ from protocol or posterior')
    expected=identity.get('contract',{})
    if (expected.get('chains')!=protocol['chains'] or expected.get('draws')!=protocol['draws']
            or set(storage.get('posterior_variables',[]))!=set(expected.get('variables',{}))):
        raise ValueError('Disk posterior contract differs')
    return True

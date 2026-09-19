"""Optional exact floor graph and tree-depth execution settings."""
from __future__ import annotations
import json
from pathlib import Path
from apartments.research_pipeline import _verified_bundle, digest
from . import bayesian_disk_protocol as storage_protocol
from . import bayesian_floor_block_graph as graph

PARITY_VERSION='bayesian-floor-block-graph-parity-v1'


def add_arguments(parser):
    parser.add_argument('--maxdepth',type=int,default=None,help='Explicit nutpie maximum tree depth (1..20); omitted preserves backend default')
    parser.add_argument('--floor-block-graph-validation',type=Path,default=None,
        help='Verified full-cohort original PyMC versus exact floor-block graph parity bundle')


def implementation_paths():
    return [Path(__file__),Path(graph.__file__),Path(__file__).with_name('verify_floor_block_graph.py')]


def update_protocol(result,args,code):
    value=getattr(args,'maxdepth',None)
    if value is not None:result['maxdepth']=value
    execution_options(result)
    path=getattr(args,'floor_block_graph_validation',None)
    if path is None:return result
    manifest,files=_verified_bundle(path,retain={'parity.json'})
    proof=json.loads(files['parity.json'])
    validate_graph_proof(result,proof,manifest,code)
    sha=digest(Path(path)/'complete.json')
    result['graph_verification']={'manifest_sha256':sha,'version':PARITY_VERSION,'rows':proof['rows']}
    result['execution_graph']={'version':graph.VERSION,'parity_manifest_sha256':sha}
    execution_options(result)
    return result


def validate_graph_proof(result,proof,manifest,code=None):
    """Verify frozen proof against statistical protocol and archived code hashes."""
    code=result['implementation_sha256'] if code is None else code
    expected={k:result[k] for k in ('source_manifest_sha256','source_observations_sha256',
        'specification','floor_increment_prior_scale','floor_levels','graph_configuration','rows')}
    for key in ('interaction_mode','interaction_prior_scale','interaction_thresholds'):
        if key in result:expected[key]=result[key]
        elif key in proof:raise ValueError('Floor block proof has unexpected interaction design')
    if (manifest.get('version')!=PARITY_VERSION or proof.get('version')!=PARITY_VERSION
            or proof.get('passed') is not True or proof.get('mode')!='NUMBA'
            or proof.get('fresh_design_matches_saved') is not True
            or any(proof.get(k)!=v for k,v in expected.items())):
        raise ValueError('Floor block graph proof differs from source or design settings')
    from . import bayesian_feature_experiment_v4 as floor
    required={p.name for p in floor.previous.implementation_paths()
              if 'experiment' not in p.name and p.name!='bayesian_sampling.py'} | {
                  Path(floor.floor.__file__).name,Path(graph.__file__).name,'verify_floor_block_graph.py'}
    if 'interaction_mode' in result:required.add('bayesian_floor_elevator_design.py')
    validated=proof.get('implementation_sha256',{})
    if not required<=validated.keys() or any(code.get(k)!=v for k,v in validated.items()):
        raise ValueError('Floor block graph proof implementation differs')
    return True


def protocol_files(args):
    path=getattr(args,'floor_block_graph_validation',None)
    if path is None:return {}
    path=Path(path)
    return {'floor-block-parity.json':(path/'parity.json').read_text(),
            'floor-block-parity-manifest.json':(path/'complete.json').read_text()}


def verify_archived_proof(result,files):
    import hashlib
    execution_options(result)
    if 'execution_graph' not in result:
        if {'floor-block-parity.json','floor-block-parity-manifest.json'} & files.keys():
            raise ValueError('Unexpected floor block proof without execution graph')
        return False
    if not {'floor-block-parity.json','floor-block-parity-manifest.json'} <= files.keys():
        raise ValueError('Missing archived floor block proof or manifest')
    execution_options(result)
    if not {'floor-block-parity.json','floor-block-parity-manifest.json'}<=files.keys():
        raise ValueError('Missing archived floor block proof')
    raw=files['floor-block-parity-manifest.json'];payload=files['floor-block-parity.json']
    encode=lambda value:value.encode() if isinstance(value,str) else value
    manifest=json.loads(raw);proof=json.loads(payload)
    sha=hashlib.sha256(encode(raw)).hexdigest()
    if (sha!=result['execution_graph']['parity_manifest_sha256']
            or result['graph_verification']!={'manifest_sha256':sha,'version':PARITY_VERSION,'rows':result['rows']}
            or hashlib.sha256(encode(payload)).hexdigest()!=manifest['files']['parity.json']):
        raise ValueError('Archived floor block proof hash binding differs')
    return validate_graph_proof(result,proof,manifest)


def verify_saved_design(args,target):
    path=getattr(args,'floor_block_graph_validation',None)
    if path is None:return
    _,files=_verified_bundle(path,retain={'parity.json'})
    expected=json.loads(files['parity.json']).get('design_sha256',{})
    actual={p.name:digest(p) for p in Path(target).glob('*design.json')}
    if not expected or actual!=expected:raise ValueError('Floor block proof saved design differs')


def sample_options(protocol):
    return execution_options(protocol)


OPTIONAL_FIELDS={'maxdepth','execution_graph'}


def execution_options(value):
    result={k:value[k] for k in OPTIONAL_FIELDS if k in value}
    if 'maxdepth' in result and (type(result['maxdepth']) is not int or not 1<=result['maxdepth']<=20):
        raise ValueError('Unsupported disk execution maxdepth: require integer 1..20')
    if 'execution_graph' in result:
        item=result['execution_graph']
        if (not isinstance(item,dict) or set(item)!={'version','parity_manifest_sha256'}
                or item['version']!=graph.VERSION
                or not isinstance(item['parity_manifest_sha256'],str)
                or len(item['parity_manifest_sha256'])!=64
                or any(c not in '0123456789abcdef' for c in item['parity_manifest_sha256'])):
            raise ValueError('Unsupported disk execution graph')
    return result


def verify_protocol(value):
    options=execution_options(value)
    result=storage_protocol.verify_protocol(value)
    if options and not result:raise ValueError('Missing disk execution protocol')
    return result


def verify_products(protocol,storage,trace_manifest,posterior_sha256):
    verify_protocol(protocol)
    storage_protocol.verify_products(protocol,storage,trace_manifest,posterior_sha256)
    options=execution_options(protocol)
    if execution_options(trace_manifest.get('identity',{}))!=options or execution_options(storage)!=options:
        raise ValueError('Disk storage products differ from execution options')
    return True

"""Publish an immutable design-only floor audit, never sample or fit a model."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import bayesian_floor_increment_design as floor
from . import bayesian_feature_model as reference
from apartments import corrections, research_pipeline

VERSION = 'listed-floor-increment-design-audit-v1'


def _json(value):
    return json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n'


def _array_hash(value):
    return hashlib.sha256(np.ascontiguousarray(value,dtype='<f8').tobytes()).hexdigest()


def implementation_paths():
    return [Path(__file__),*(Path(module.__file__) for module in
        (floor,reference,reference.base,reference.amenity,reference.amenity.baseline,
         reference.pricing,corrections,research_pipeline))]


def _publish(output, files, metadata):
    """Binary-capable immutable publication; identical replay verifies hashes."""
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    hashes={name:hashlib.sha256(value).hexdigest() for name,value in files.items()}
    manifest={**metadata,'files':hashes}
    with (output/'.audit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (output/'complete.json').exists():
            saved,_=research_pipeline._verified_bundle(output)
            if saved!=manifest:raise ValueError('Immutable audit differs; use a new directory')
            return saved
        plan=output/'plan.json'
        if plan.exists():
            if json.loads(plan.read_text())!=manifest:raise ValueError('Incomplete audit identity differs')
        elif any(p.name!='.audit.lock' for p in output.iterdir()):
            raise ValueError('Output directory is not empty')
        plan.write_text(_json(manifest))
        for name,value in files.items():
            with tempfile.NamedTemporaryFile(dir=output,prefix='.partial-',delete=False) as handle:
                handle.write(value);temporary=Path(handle.name)
            temporary.replace(output/name)
        with tempfile.NamedTemporaryFile('w',dir=output,prefix='.partial-',delete=False) as handle:
            handle.write(_json(manifest));temporary=Path(handle.name)
        temporary.replace(output/'complete.json')
    research_pipeline._verified_bundle(output)
    return manifest


def run(dataset,output,*,floor_increment_prior_scale=.15):
    dataset=Path(dataset)
    source,blobs=research_pipeline._verified_bundle(dataset,retain={'observations.jsonl'})
    if source.get('version')!='reviewed-scope-composition-projection-v2':
        raise ValueError('Cleaned reviewed scope/composition dataset required')
    data=pd.DataFrame(json.loads(line) for line in blobs['observations.jsonl'].decode().split('\n') if line.strip())
    del blobs
    if data.audit_id.duplicated().any() or data.duplicated(['unit_id','period']).any():
        raise ValueError('Duplicate source observation identity')
    data.period=pd.to_datetime(data.period);data.square_feet=pd.to_numeric(data.square_feet,errors='coerce')
    with threadpool_limits(limits=1,user_api='blas'):
        old=reference.FeatureDesign(data,'full_half_balance')
        new=floor.FeatureDesign(data,'full_half_balance',floor_increment_prior_scale=floor_increment_prior_scale)
        old_raw,old_names,old_scales=old.raw_features(data)
        new_raw,new_names,new_scales=new.raw_features(data)
        old_matrix,new_matrix=old.matrix(data),new.matrix(data)
        proof=[]
        for i,name in enumerate(old_names):
            if name=='listed_floor':continue
            j=new_names.index(name)
            raw_equal=np.array_equal(old_raw[:,i],new_raw[:,j])
            prior_equal=old_scales[i]==new_scales[j]
            active_equal=bool(old.active[i])==bool(new.active[j])
            centered_equal=True
            centered_hash=None
            if old.active[i] and new.active[j]:
                a,b=old_matrix[:,old.features.index(name)],new_matrix[:,new.features.index(name)]
                centered_equal=np.array_equal(a,b);centered_hash=_array_hash(a)
            if not all((raw_equal,prior_equal,active_equal,centered_equal)):
                raise ValueError('Nonfloor column changed: '+name)
            proof.append({'feature':name,'raw_exact':raw_equal,'prior_exact':prior_equal,
                          'active_exact':active_equal,'centered_exact':centered_equal,
                          'raw_float64_le_sha256':_array_hash(old_raw[:,i]),
                          'centered_float64_le_sha256':centered_hash})
        extras=set(new_names)-set(old_names)
        if extras!={floor._name(k) for k in new.floor_thresholds} or 'listed_floor' in new_names:
            raise ValueError('Unexpected replacement feature inventory')
        for name in ('time_matrix','time_center','time_prior_scales','linear_time','season_matrix','season_weights'):
            if not np.array_equal(getattr(old.time,name),getattr(new.time,name)):
                raise ValueError('Nonfloor time design changed')
        with tempfile.TemporaryDirectory(prefix='floor-design-audit-') as temporary:
            directory=Path(temporary);new.save(directory)
            restored=floor.FeatureDesign.load(directory)
            if not np.array_equal(restored.matrix(data),new_matrix):
                raise ValueError('New design reload changes its matrix')
            files={p.name:p.read_bytes() for p in directory.iterdir()}
        old_floor=old.numeric['listed_floor']
        old_sd=float(old.prior_scales[old.features.index('listed_floor')])
        prior_contrasts=[]
        pairs=list(zip(new.floor_levels[:-1],new.floor_levels[1:]))
        if len(new.floor_levels)>2:pairs.append((new.floor_levels[0],new.floor_levels[-1]))
        for low,high in pairs:
            increments=sum(low<=k<high for k in new.floor_thresholds)
            prior_contrasts.append({'lower':low,'upper':high,'crossed_observed_thresholds':increments,
                'old_log_contrast_prior_sd':old_sd*(high-low)/old_floor['scale'],
                'new_log_contrast_prior_sd':new.floor_increment_prior_scale*np.sqrt(increments),
                'common_global_prior_multiplier_assumed':1.,
                'interpretation':'Conditional on encoded floor contribution only. Same numeric coefficient SD does not imply the same joint prior.'})
        result={'version':VERSION,'status':'design_only_no_fit_no_posterior',
                'source_rows':len(data),'old_active_features':len(old.features),'new_active_features':len(new.features),
                'old_matrix_rank':old.support['matrix_rank'],'new_matrix_rank':new.support['matrix_rank'],
                'floor_support':new.floor_support,'floor_policy':new.floor_policy,
                'old_floor_normalization':old_floor,'prior_contrasts':prior_contrasts,
                'unchanged_nonfloor_columns':proof,'time_design_exact':True,'saved_design_reload_exact':True,
                'source_row_order_sha256':hashlib.sha256(corrections.canonical(data.audit_id.tolist()).encode()).hexdigest(),
                'gap_policy':'Observed endpoint increments only; unseen known floor labels rejected. Negative/ground labels preserved when supported.',
                'interpretation':['No coefficient or posterior estimate was produced.',
                    'Design rank is not identification separately from building/unit effects.',
                    'Sparse upper floors and absent same-building endpoint overlap require scrutiny.',
                    'These priors are for the floor feature component; other features, groups, and hyperpriors remain outside this calculation.']}
    code_index={}
    repository=Path(__file__).resolve().parents[1]
    for path in implementation_paths():
        relative=str(path.resolve().relative_to(repository))
        frozen='code__'+relative.replace('/','__')
        content=path.read_bytes();files[frozen]=content
        code_index[relative]={'frozen_file':frozen,'sha256':hashlib.sha256(content).hexdigest()}
    files['source-manifest.json']=(dataset/'complete.json').read_bytes()
    files['audit.json']=_json(result).encode()
    files['implementation.json']=_json(code_index).encode()
    gaps=[x for x in new.floor_support['adjacent_supported_contrasts'] if x['has_unobserved_integer_labels_between']]
    lines=['# Listed-floor increment design audit','',
        '**Design only: no fit and no posterior floor increments.**','',
        f"Verified cleaned source: {len(data):,} rows. Known floor rows: {new.floor_support['known_rows']:,}.",
        f'Active columns/rank: old {len(old.features)}/{old.support["matrix_rank"]}; new {len(new.features)}/{new.support["matrix_rank"]}.',
        f'Exact unchanged nonfloor/reporting columns: {len(proof)}; time design and saved-design reload also exact.','',
        '| Gap endpoints | Source-label distance | Shared buildings |','|---|---:|---:|']
    lines += [f"| {x['lower_supported_level']:g} → {x['upper_supported_level']:g} | {x['label_distance']:g} | {x['shared_buildings']} |" for x in gaps]
    extreme=prior_contrasts[-1]
    lines += ['',f"For the {extreme['lower']:g}→{extreme['upper']:g} floor-only contrast, old prior log SD = {extreme['old_log_contrast_prior_sd']:.6f}; new = {extreme['new_log_contrast_prior_sd']:.6f}.",
        'The common numeric coefficient SD is not a matched prior on floor contrasts. No monotonic sign constraint is imposed.',
        '', 'Reproduce from the repository using the frozen source dataset and matching implementation/runtime:', '', '```sh',
        'UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m models.publish_floor_increment_audit \\',
        '  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \\',
        '  --output data/model/chelsea-listed-floor-increment-design-20260918', '```', '']
    files['report.md']='\n'.join(lines).encode()
    return _publish(output,files,{'version':VERSION,'status':result['status'],
        'source_manifest_sha256':research_pipeline.digest(dataset/'complete.json'),
        'source_observations_sha256':source['files']['observations.jsonl'],
        'implementation':code_index,'runtime_versions':{name:importlib.metadata.version(name) for name in
            ('numpy','pandas','scipy','pymc','pytensor','arviz','threadpoolctl')},
        'spec':'full_half_balance','floor_increment_prior_scale':new.floor_increment_prior_scale})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--floor-increment-prior-scale',type=float,default=.15)
    args=parser.parse_args()
    print(_json(run(args.dataset,args.output,floor_increment_prior_scale=args.floor_increment_prior_scale)))

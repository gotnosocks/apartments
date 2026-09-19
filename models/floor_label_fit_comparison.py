"""Compare source-bound label-floor expansion with a matched v4 baseline.

No selection changes and no pairing of draws from independent posteriors.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from apartments import floor_label_projection as projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import quarantine_fit_comparison as shared
from . import bayesian_floor_increment_design as floor

VERSION = 'matched-label-floor-fit-comparison-v1'
SOURCE_FIELDS = shared.source.SOURCE_FIELDS - {'rows', 'units', 'buildings', 'current_rows'}
VARIABLE = SOURCE_FIELDS | {'graph_verification', 'implementation_sha256', 'floor_levels', 'floor_thresholds'}
LOADER_CODE = {'reviewed_source_lineage.py', 'bayesian_feature_experiment_v3.py', 'bayesian_evidence.py'}


def check_protocols(a, b):
    if (a.get('version') != shared.floors.V4 or b.get('version') != shared.floors.V4
            or a.get('source_version') != projection.PARENT or b.get('source_version') != projection.VERSION
            or a.get('residual_scale') != 'shared'
            or not shared.disk.verify_protocol(a) or not shared.disk.verify_protocol(b)):
        raise ValueError('Expected matched durable v4 source-floor and expanded label-floor fits')
    if {k:v for k,v in a.items() if k not in VARIABLE} != {k:v for k,v in b.items() if k not in VARIABLE}:
        raise ValueError('Sampler, nonfloor model, prior or population changed')
    old,new = a['implementation_sha256'],b['implementation_sha256']
    if set(new)-set(old) != {'floor_label_projection.py'} or not old.keys() <= new.keys():
        raise ValueError('Unexpected implementation inventory change')
    changed = {k for k in old if old[k] != new[k]}
    if changed-LOADER_CODE: raise ValueError('Mathematical or sampling implementation changed')
    for p in (a,b):
        levels = p.get('floor_levels', [])
        if len(levels)<2 or levels != sorted(set(levels)) or p.get('floor_thresholds') != levels[:-1]:
            raise ValueError('Invalid floor support or threshold order')
    if not set(a['floor_levels']) <= set(b['floor_levels']): raise ValueError('Explicit floor support lost')
    return sorted(changed)


def verify_revision(reference, candidate):
    bundles = [_verified_bundle(p, retain={'observations.jsonl', projection.SIDECAR}) for p in (reference,candidate)]
    before,after = [shared.report.jsonl(f['observations.jsonl']) for _,f in bundles]
    if projection.SIDECAR not in bundles[1][1]: raise ValueError('Missing source-bound floor projection sidecar')
    changes = shared.report.jsonl(bundles[1][1][projection.SIDECAR])
    if projection.parent_rows(bundles[1][0],after,changes) != (bundles[0][0],before):
        raise ValueError('Floor projection does not restore exact baseline source')
    if [r['audit_id'] for r in before] != [r['audit_id'] for r in after]:
        raise ValueError('Floor projection changed observation membership or order')
    return before,after


def is_floor(name):
    return name in ('listed_floor','listed_floor.unknown') or name.startswith('listed_floor_gt_')


def check_designs(a,b):
    left,right = a['design'],b['design']
    names = [n for n in left.features if not is_floor(n)]
    if names != [n for n in right.features if not is_floor(n)]:
        raise ValueError('Nonfloor feature inventory or ordering changed')
    ai,bi = [[d.features.index(n) for n in names] for d in (left,right)]
    for x,y in [(left.means[ai],right.means[bi]),(left.prior_scales[ai],right.prior_scales[bi]),
                (left.matrix(a['data'])[:,ai],right.matrix(b['data'])[:,bi])]:
        if not np.array_equal(x,y): raise ValueError('Nonfloor encoding, centering or priors changed')
    times = [json.loads(shared.common.bound_bytes(f['root']/'fit','time-design.json',f['provenance']['fit_manifest'])) for f in (a,b)]
    if times[0] != times[1] or a['reconstruction']['time_arrays'] != b['reconstruction']['time_arrays']:
        raise ValueError('Time design or group structure changed')
    return names


def residual_slices(before,after,movements):
    import pandas as pd
    old,new = [floor.listed_floor_values(pd.DataFrame(rows)) for rows in (before,after)]
    masks = {'all':np.ones(len(after),dtype=bool),
        'current_capture':np.array([r['analysis_price_basis']=='current_capture_gross_ask' for r in after]),
        'newly_inferred_floor':~np.isfinite(old)&np.isfinite(new),
        'explicit_floor':np.isfinite(old),'missing_floor':~np.isfinite(new)}
    indexed = {r['audit_id']:r for r in movements}
    if len(indexed)!=len(movements) or set(indexed)!={r['audit_id'] for r in after}:
        raise ValueError('Residual slice membership differs')
    return {name:{**shared.laundry.summarize_slice([indexed[r['audit_id']] for r,keep in zip(after,mask,strict=True) if keep]),
        'buildings':len({r['building'] for r,keep in zip(after,mask,strict=True) if keep})} for name,mask in masks.items()}


def contrast_comparison(a,b):
    # Compare identical observed endpoints, and separately expose all new intervals.
    levels = sorted(set(a['design'].floor_levels)&set(b['design'].floor_levels))
    common = [shared.floors.joint_floor_contrasts(f['root'],f['protocol'],f['design'],levels) for f in (a,b)]
    expanded = shared.floors.joint_floor_contrasts(b['root'],b['protocol'],b['design'],b['design'].floor_levels)
    return {'common_endpoint_contrasts':shared.compare_floors(*common),
        'common_endpoint_diagnostics':[v['diagnostics'] for v in common],
        'expanded_candidate_contrasts':expanded,
        'interpretation':'Joint coefficient draws preserve covariance within each fit. New thresholds change the induced prior over some common endpoint contrasts; prior and posterior SDs are explicit. Between-fit interval changes are descriptive summaries, not paired posterior differences.'}


def build_comparison(reference,reference_dataset,candidate,dataset):
    before,after = verify_revision(reference_dataset,dataset)
    a,b = shared.load_fits(reference,candidate,reference_dataset,dataset,before,after)
    changed = check_protocols(a['protocol'],b['protocol']); names = check_designs(a,b)
    movements,residuals = shared.compare_residuals(a['residuals'],b['residuals'],before,after)
    groups,removed = shared.compare_groups(a['groups'],b['groups'],before,after)
    if removed or residuals['excluded_reference_rows']: raise ValueError('Matched comparison lost observations or groups')
    buildings = sorted({r['building'] for r in after})
    common = [shared.building_contrasts(f,buildings) for f in (a,b)]
    building_changes = [{'id':x['id'],'log_effect':shared.common.interval_change(x['log_effect'],y['log_effect'])}
        for x,y in zip(common[0]['contrasts'],common[1]['contrasts'],strict=True)]
    building_changes.sort(key=lambda r:(-abs(r['log_effect']['median_change']),r['id']))
    distinct=[];seen=set()
    for r in movements:
        if r['unit_id'] not in seen: distinct.append(r);seen.add(r['unit_id'])
        if len(distinct)==25: break
    result = {'version':VERSION,'main_selection_changed':False,'rows':len(after),
        'changed_loader_implementations':changed,'unchanged_nonfloor_features':names,
        'fits':[{'protocol':f['protocol'],'diagnostics':f['report']['diagnostics'],
            'design_reconstruction':f['reconstruction'],'bindings':{k:digest(path/'complete.json') for k,path in
                [('fit',f['root']/'fit'),('protocol',f['root']/'protocol'),('source',f['dataset'])]}} for f in (a,b)],
        'floor_support':[f['design'].floor_support for f in (a,b)],'floor_contrasts':contrast_comparison(a,b),
        'residuals':residuals,'residual_slices':residual_slices(before,after,movements),
        'largest_distinct_unit_movements':distinct,
        'largest_unit_offset_movements':[r for r in groups if r['kind']=='unit'][:25],
        'largest_common_reference_building_movements':building_changes[:25],
        'building_reference':{'definition':'Unweighted mean over identical buildings subtracted within each joint posterior draw.',
            'buildings':buildings,'diagnostics':[v['diagnostics'] for v in common]},
        'limitations':[shared.common.LIMITATION,
            'The inferred feature is an advertised unit-label proxy, not independently verified physical floor or building height.',
            'Residuals are in sample, including refreshed captures. Current is a dated collection cohort, not a representative fixed test panel.',
            'Floor missingness, centering and threshold support change. Nonfloor columns, time design, group membership, priors and sampler are matched.',
            'Building and unit movements identify cases for source review; residual improvement alone does not justify feature adoption.']}
    for f in (a,b):
        if digest(f['root']/'fit/posterior.nc') != f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result,movements,groups,building_changes


def run(output,**kwargs):
    modules = (shared,shared.report,shared.source,shared.common,shared.laundry,shared.floors,projection,floor)
    paths = [Path(__file__),*[Path(m.__file__) for m in modules]]
    hashes = {p.name:digest(p) for p in paths}
    result,movements,groups,buildings = build_comparison(**kwargs)
    if any(digest(p)!=hashes[p.name] for p in paths): raise ValueError('Comparison implementation changed')
    publish_bundle(output,{'comparison.json':canonical(result)+'\n',
        'residual-movements.jsonl':''.join(canonical(r)+'\n' for r in movements),
        'raw-group-movements.jsonl':''.join(canonical(r)+'\n' for r in groups),
        'common-reference-building-movements.jsonl':''.join(canonical(r)+'\n' for r in buildings),
        **{p.name:p.read_text() for p in paths}},
        {'version':VERSION,'fits':[f['bindings'] for f in result['fits']],'implementation_sha256':hashes})
    print(canonical({'rows':result['rows'],'output':str(output),'main_selection_changed':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','reference-dataset','candidate','dataset','output'):parser.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):run(**vars(parser.parse_args()))

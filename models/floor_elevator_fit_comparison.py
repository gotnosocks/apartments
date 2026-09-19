"""Matched-source floor/elevator representation comparison; no fit promotion."""
import argparse
import json
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import quarantine_fit_comparison as shared
from . import bayesian_floor_elevator_contract as contract
from . import bayesian_floor_elevator_design as interaction
from . import bayesian_category_contrasts as categories
from . import bayesian_floor_execution as execution

VERSION = 'matched-floor-elevator-fit-comparison-v1'
VARIABLE = {'version', 'feature_design_version', 'base_feature_design_version', 'graph',
            'graph_verification', 'implementation_sha256', 'interaction_mode',
            'interaction_prior_scale', 'interaction_thresholds', 'interaction_policy', 'execution_graph'}
ADDED_CODE = {'bayesian_floor_elevator_design.py', 'bayesian_floor_elevator_experiment.py',
              'bayesian_category_contrasts.py'}


def check_protocols(reference, candidate):
    if (reference.get('version') != shared.report.EXPERIMENT_V4
            or candidate.get('version') != contract.EXPERIMENT
            or reference.get('feature_design_version') != contract.BASE
            or candidate.get('base_feature_design_version') != contract.BASE
            or candidate.get('feature_design_version') != contract.DESIGN
            or candidate.get('interaction_thresholds') != contract.THRESHOLDS
            or candidate.get('interaction_policy') != contract.POLICY
            or candidate.get('interaction_mode') not in ('pooled', 'separate')
            or not contract.positive(candidate.get('interaction_prior_scale'))):
        raise ValueError('Expected the baseline and explicit lower-floor interaction model')
    if (not execution.verify_protocol(reference) or not execution.verify_protocol(candidate)
            or reference.get('residual_scale') != 'shared'):
        raise ValueError('Matched durable shared-noise fits required')
    if (reference.get('execution_graph',{}).get('version') != candidate.get('execution_graph',{}).get('version')):
        raise ValueError('Exact graph execution strategy differs')
    if ({k:v for k,v in reference.items() if k not in VARIABLE}
            != {k:v for k,v in candidate.items() if k not in VARIABLE}):
        raise ValueError('Source, sampler, environment or unchanged model parameters differ')
    a,b = reference['implementation_sha256'],candidate['implementation_sha256']
    if set(b)-set(a) != ADDED_CODE or not a.keys() <= b.keys() or any(b[k] != v for k,v in a.items()):
        raise ValueError('Shared mathematical, source or sampling implementation changed')


def check_designs(a, b):
    """No re-standardization, altered base priors or changed time construction."""
    left,right = a['design'],b['design']
    extra = interaction.names(b['protocol']['interaction_mode'])
    if (right.features != left.features+extra
            or not np.array_equal(right.prior_scales[:len(left.features)],left.prior_scales)
            or not np.array_equal(left.matrix(a['data']),right.matrix(b['data'])[:,:len(left.features)])):
        raise ValueError('Interaction changed existing columns, ordering or priors')
    for name in ('feature-design.json','time-design.json'):
        files = [json.loads(shared.common.bound_bytes(f['root']/'fit',name,f['provenance']['fit_manifest'])) for f in (a,b)]
        if files[0] != files[1]: raise ValueError('Saved base/time design semantics changed')
    if a['reconstruction']['time_arrays'] != b['reconstruction']['time_arrays']:
        raise ValueError('Time design arrays changed')


def residual_slices(rows, movements):
    values = dict(zip((r['audit_id'] for r in rows),contract.source_values(rows)))
    claims = {}
    for row in rows:
        _,access = values[row['audit_id']]
        if access is not None: claims.setdefault(row['building'],set()).add(access)
    opposing = {b for b,v in claims.items() if v == {0,1}}
    slices = {}
    for name,condition in [
        ('known_floor_no_elevator', lambda r,f,e: f is not None and e == 0),
        ('known_floor_elevator', lambda r,f,e: f is not None and e == 1),
        ('known_floor_unknown_access', lambda r,f,e: f is not None and e is None),
        ('unknown_floor', lambda r,f,e: f is None),
        ('lower_2_to_5_no_elevator', lambda r,f,e: f in (2,3,4,5) and e == 0),
        ('lower_2_to_5_elevator', lambda r,f,e: f in (2,3,4,5) and e == 1),
        ('opposing_claim_buildings', lambda r,f,e: r['building'] in opposing),
        ('other_buildings', lambda r,f,e: r['building'] not in opposing)]:
        chosen = [m for m in movements if condition(m,*values[m['audit_id']])]
        slices[name] = {**shared.laundry.summarize_slice(chosen),
                        'buildings':len({m['building'] for m in chosen})}
    return {'opposing_claim_buildings':sorted(opposing),'slices':slices,
        'interpretation':'Opposing claims occur anywhere in the recorded building history. This is a descriptive slice, not adjudication of truth or a refit excluding those buildings.'}


def beta_draws(fit):
    with xr.open_dataset(fit['root']/'fit/posterior.nc',group='posterior',engine='h5netcdf',cache=False) as p:
        if (p.beta.dims != ('chain','draw','feature') or p.feature.values.tolist() != fit['design'].features
                or p.sizes['chain'] != fit['protocol']['chains'] or p.sizes['draw'] != fit['protocol']['draws']):
            raise ValueError('Joint coefficient coordinates or retained draws differ')
        return p.beta.load().values


def contrast_comparison(a,b):
    """Use joint draws within each model; never subtract draws across fits."""
    definitions = b['report']['floor_elevator']['contrasts']
    if (b['report']['floor_elevator'].get('all_contrasts_acceptable') is not True
            or not all(r['diagnostics']['acceptable'] for r in definitions)):
        raise ValueError('Candidate joint floor contrasts fail diagnostics')
    by_id = {r['id']:r for r in definitions}
    if len(by_id) != len(definitions): raise ValueError('Duplicate joint floor contrasts')
    # The baseline has zero interaction by construction, not an uncertain gamma.
    floor_definitions = [{k:v for k,v in r.items() if k not in
        {'log_effect','percent_effect','diagnostics','status','log_contrast_prior_sd'}}
        for r in definitions if r['kind']=='floor_change_at_known_access']
    for r in floor_definitions:
        r['design_vector'] = r['design_vector'][:len(a['design'].features)]
        r['log_contrast_prior_sd'] = float(np.linalg.norm(np.asarray(r['design_vector'])*a['design'].prior_scales)*a['protocol']['prior_multiplier'])
    old_beta = beta_draws(a)
    old,_ = categories.calculate(old_beta,floor_definitions)
    if not all(r['diagnostics']['acceptable'] for r in old):
        raise ValueError('Baseline joint floor contrasts fail diagnostics')
    floor_changes = [{'id':r['id'],'reference':r,'candidate':by_id[r['id']],
        'percent_effect':shared.common.interval_change(r['percent_effect'],by_id[r['id']]['percent_effect'])} for r in old]
    new_beta = beta_draws(b)
    gamma = []
    for name in interaction.names(b['protocol']['interaction_mode']):
        index = b['design'].features.index(name)
        vector = np.zeros(len(b['design'].features));vector[index]=1
        result,_ = categories.calculate(new_beta,[{'id':name,'design_vector':vector.tolist()}])
        if not result[0]['diagnostics']['acceptable']: raise ValueError('Interaction coefficient fails diagnostics')
        prior = float(b['design'].prior_scales[index]*b['protocol']['prior_multiplier'])
        sd = float(new_beta[:,:,index].std(ddof=1))
        gamma.append({'feature':name,'encoded_log_coefficient':result[0]['log_effect'],
            'diagnostics':result[0]['diagnostics'],'normal_prior_sd':prior,'posterior_sd':sd,
            'posterior_sd_over_prior_sd':sd/prior,
            'interpretation':'Encoded interaction coefficient; use joint access-specific floor scenarios for price interpretation. SD contraction is descriptive, not an identification test.'})
    return {'floor_changes':floor_changes,'interaction_coefficients':gamma,
        'interaction_differences':[{'reference_log_effect':{'point_mass':0.,'reason':'No interaction in baseline'},
            'candidate':r} for r in definitions if r['kind']=='elevator_minus_no_elevator_floor_change']}


def build_comparison(reference,candidate,dataset):
    _,files = _verified_bundle(dataset,retain={'observations.jsonl'})
    rows = shared.report.jsonl(files['observations.jsonl'])
    a,b = shared.load_fits(reference,candidate,dataset,dataset,rows,rows)
    check_protocols(a['protocol'],b['protocol']); check_designs(a,b)
    movements,residuals = shared.compare_residuals(a['residuals'],b['residuals'],rows,rows)
    groups,removed = shared.compare_groups(a['groups'],b['groups'],rows,rows)
    if removed or residuals['excluded_reference_rows']: raise ValueError('Matched comparison lost observations or groups')
    buildings = sorted({r['building'] for r in rows})
    common = [shared.building_contrasts(f,buildings) for f in (a,b)]
    building_changes = [{'id':x['id'],'log_effect':shared.common.interval_change(x['log_effect'],y['log_effect'])}
                        for x,y in zip(common[0]['contrasts'],common[1]['contrasts'],strict=True)]
    building_changes.sort(key=lambda r:(-abs(r['log_effect']['median_change']),r['id']))
    result = {'version':VERSION,'main_selection_changed':False,'rows':len(rows),
        'fits':[{'protocol':f['protocol'],'diagnostics':f['report']['diagnostics'],
                 'design_reconstruction':f['reconstruction'],
                 'bindings':{k:digest(path/'complete.json') for k,path in
                     [('fit',f['root']/'fit'),('protocol',f['root']/'protocol'),('source',f['dataset'])]}} for f in (a,b)],
        **contrast_comparison(a,b),'residuals':residuals,'residual_slices':residual_slices(rows,movements),
        'largest_distinct_unit_movements':[],
        'largest_unit_offset_movements':[r for r in groups if r['kind']=='unit'][:25],
        'largest_common_reference_building_movements':building_changes[:25],
        'building_reference':{'definition':'Unweighted mean across the identical buildings, subtracted within each joint posterior draw.',
            'buildings':buildings,'diagnostics':[v['diagnostics'] for v in common]},
        'limitations':[shared.common.LIMITATION,
            'Same source observations, asking prices, base columns, priors and sampler settings. Adding interaction variance widens access-specific floor priors.',
            'In-sample residual changes do not measure held-out performance; current captures participate in both fits.',
            'Compare summaries of independent fits. No paired-draw uncertainty for between-fit changes is claimed.',
            'Prior sensitivity, building/unit shrinkage and sparse or conflicting source support require review before selecting an interaction model.']}
    seen=set()
    for r in movements:
        if r['unit_id'] in seen: continue
        seen.add(r['unit_id']);result['largest_distinct_unit_movements'].append(r)
        if len(seen)==25: break
    for f in (a,b):
        if digest(f['root']/'fit/posterior.nc') != f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result,movements,groups,building_changes


def run(reference,candidate,dataset,output):
    result,movements,groups,buildings = build_comparison(reference,candidate,dataset)
    modules=(shared,shared.report,shared.source,shared.common,shared.laundry,contract,interaction,categories,execution)
    publish_bundle(output,{'comparison.json':canonical(result)+'\n',
        'residual-movements.jsonl':''.join(canonical(r)+'\n' for r in movements),
        'raw-group-movements.jsonl':''.join(canonical(r)+'\n' for r in groups),
        'common-reference-building-movements.jsonl':''.join(canonical(r)+'\n' for r in buildings),
        Path(__file__).name:Path(__file__).read_text(),
        **{Path(m.__file__).name:Path(m.__file__).read_text() for m in modules}},
        {'version':VERSION,'fits':[f['bindings'] for f in result['fits']]})
    print(canonical({'rows':result['rows'],'output':str(output),'main_selection_changed':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','dataset','output'):parser.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):run(**vars(parser.parse_args()))

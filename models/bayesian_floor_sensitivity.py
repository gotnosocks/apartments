"""Compare floor representations/priors on an identical verified rental cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report
from . import bayesian_feature_sensitivity as common
from . import bayesian_source_sensitivity as source
from . import bayesian_feature_design_v2 as loader
from . import bayesian_floor_increment_design as floor
from . import bayesian_disk_protocol as disk
from . import bayesian_rent_model as base
from . import bayesian_feature_experiment as summaries

VERSION='bayesian-floor-sensitivity-v1'
V3='observable-bayesian-bathroom-experiment-v3'
V4='observable-bayesian-floor-experiment-v4'
FLOOR_FIELDS={'feature_design_version','floor_increment_prior_scale','floor_levels','floor_thresholds','floor_policy'}
FLOOR_CODE={'bayesian_feature_experiment_v4.py','bayesian_floor_increment_design.py'}
ALLOWED={'version','chains','draws','tune','seed','graph','graph_verification','implementation_sha256'}|FLOOR_FIELDS|disk.FIELDS


def check_protocols(reference,candidate):
    if reference.get('version') not in (V3,V4) or candidate.get('version')!=V4:
        raise ValueError('Expected v3/v4 reference and a v4 floor-increment candidate')
    for p in (reference,candidate):
        disk.verify_protocol(p)
        for key,minimum in [('chains',2),('draws',1),('tune',1),('seed',0)]:
            if type(p.get(key)) is not int or p[key]<minimum:raise ValueError('Invalid sampling protocol')
    if {k:v for k,v in reference.items() if k not in ALLOWED}!={k:v for k,v in candidate.items() if k not in ALLOWED}:
        raise ValueError('Source, nonfloor model, priors or numerical environment changed')
    def mathematical_code(p):
        ignored=FLOOR_CODE if p['version']==V4 else set()
        if disk.verify_protocol(p):ignored=ignored|disk.CODE
        return {k:v for k,v in p['implementation_sha256'].items() if k not in ignored}
    if not mathematical_code(reference) or mathematical_code(reference)!=mathematical_code(candidate):
        raise ValueError('Shared mathematical implementation changed')
    if not FLOOR_CODE<=candidate['implementation_sha256'].keys():raise ValueError('Missing floor implementation')
    if reference['version']==V4:
        if any(reference.get(k)!=candidate.get(k) for k in FLOOR_FIELDS-{'floor_increment_prior_scale'}):
            raise ValueError('Floor support or policy changed in prior-only comparison')
        if any(reference['implementation_sha256'].get(k)!=candidate['implementation_sha256'][k] for k in FLOOR_CODE):
            raise ValueError('Floor implementation changed')


def is_floor_value(name):return name=='listed_floor' or name.startswith('listed_floor_gt_')


def verify_other_columns(a,b,data):
    names=[n for n in a.features if not is_floor_value(n)]
    if set(names)!={n for n in b.features if not is_floor_value(n)}:
        raise ValueError('Nonfloor feature inventory changed')
    ai=[a.features.index(n) for n in names];bi=[b.features.index(n) for n in names]
    for x,y in [(a.means[ai],b.means[bi]),(a.prior_scales[ai],b.prior_scales[bi]),
                (a.matrix(data)[:,ai],b.matrix(data)[:,bi])]:
        if not np.array_equal(x,y):raise ValueError('Nonfloor encoding, centering or priors changed')
    return names


def directions(design,levels):
    pairs=list(zip(levels[:-1],levels[1:]))
    if len(levels)>2:pairs.append((levels[0],levels[-1]))
    vectors=[]
    for low,high in pairs:
        vector=np.zeros(len(design.features))
        if hasattr(design,'floor_thresholds'):
            for threshold in design.floor_thresholds:
                if low<=threshold<high:vector[design.features.index(floor._name(threshold))]=1.
        else:
            if 'listed_floor' not in design.features:raise ValueError('Reference has no varying floor coefficient')
            vector[design.features.index('listed_floor')]=(high-low)/design.numeric['listed_floor']['scale']
        vectors.append(vector)
    if not vectors:raise ValueError('No observed floor contrast to compare')
    return pairs,np.asarray(vectors)


def joint_floor_contrasts(experiment,protocol,design,levels):
    pairs,vectors=directions(design,levels)
    with xr.open_dataset(Path(experiment)/'fit/posterior.nc',group='posterior',engine='h5netcdf',cache=False) as p, \
         xr.open_dataset(Path(experiment)/'fit/posterior.nc',group='sample_stats',engine='h5netcdf',cache=False) as s:
        if (p.beta.dims!=('chain','draw','feature') or p.feature.values.tolist()!=design.features
                or p.sizes.get('chain')!=protocol['chains'] or p.sizes.get('draw')!=protocol['draws']):
            raise ValueError('Joint floor posterior dimensions or coordinates differ')
        draws=np.einsum('cdf,kf->cdk',p.beta.values,vectors)
        posterior=xr.Dataset({'floor_contrast':(('chain','draw','contrast'),draws)},coords={'contrast':range(len(pairs))})
        inference=xr.DataTree.from_dict({'posterior':posterior,'sample_stats':s.load()})
        diagnostic,_=base.diagnostics(inference)
    if not diagnostic['acceptable']:raise ValueError('Joint floor contrasts fail convergence diagnostics')
    values=[]
    for index,(low,high) in enumerate(pairs):
        samples=draws[:,:,index].ravel();effect=summaries.interval(samples)
        values.append({'lower_floor':low,'upper_floor':high,'log_effect':effect,
            'percent_effect':{**effect,**{key:100*float(np.expm1(effect[key])) for key in ('median','lower_95','upper_95')}},
            'prior_log_sd':float(np.linalg.norm(vectors[index]*design.prior_scales*protocol['prior_multiplier'])),
            'posterior_log_sd':float(np.std(samples,ddof=1))})
    return {'contrasts':values,'diagnostics':diagnostic,'draws':int(draws.shape[0]*draws.shape[1])}


def floor_residual_slices(data,a,b):
    floors=floor.listed_floor_values(data)
    ai={r['audit_id']:r for r in a};bi={r['audit_id']:r for r in b}
    if len(ai)!=len(a) or len(bi)!=len(b) or set(ai)!=set(data.audit_id) or set(bi)!=set(ai):
        raise ValueError('Floor residual cohort differs')
    result=[]
    for label,mask in [('known listed floor',np.isfinite(floors)),('unknown listed floor',~np.isfinite(floors))]:
        rows=data.loc[mask];ids=rows.audit_id.tolist()
        if not ids:continue
        result.append({'slice':label,'rows':len(ids),'units':int(rows.unit_id.nunique()),'buildings':int(rows.building.nunique()),
            'reference_median_absolute_log_residual':float(np.median([abs(ai[k]['residual_log']) for k in ids])),
            'candidate_median_absolute_log_residual':float(np.median([abs(bi[k]['residual_log']) for k in ids])),
            'median_absolute_fitted_rent_change':float(np.median([abs(bi[k]['fitted_rent']-ai[k]['fitted_rent']) for k in ids]))})
    return result


def build_comparison(reference,candidate,dataset):
    roots=list(map(Path,(reference,candidate)));dataset=Path(dataset)
    _,payload=_verified_bundle(dataset,retain={'observations.jsonl'})
    rows=report.jsonl(payload['observations.jsonl']);data=pd.DataFrame(rows)
    data.period=pd.to_datetime(data.period);data.square_feet=pd.to_numeric(data.square_feet,errors='coerce')
    values=floor.listed_floor_values(data);levels=np.unique(values[np.isfinite(values)]).tolist()
    fits=[]
    for root in roots:
        verified,provenance=report.build_report(root,dataset,top=5)
        protocol=json.loads(common.bound_bytes(root/'protocol','protocol.json',provenance['protocol_manifest']))
        with threadpool_limits(limits=1,user_api='blas'):
            reconstruction=source.verify_design(root,dataset,protocol,provenance)
        design=loader.load_design(root/'fit',data,protocol)
        residuals=report.jsonl(common.bound_bytes(root/'fit','residuals.jsonl',provenance['fit_manifest']))
        fits.append({'root':root,'report':verified,'protocol':protocol,'provenance':provenance,
            'design':design,'reconstruction':reconstruction,'residuals':residuals})
    a,b=fits;check_protocols(a['protocol'],b['protocol'])
    with threadpool_limits(limits=1,user_api='blas'):nonfloor=verify_other_columns(a['design'],b['design'],data)
    for name in ('time-design.json','time-design.npz'):
        if a['provenance']['fit_manifest']['files'][name]!=b['provenance']['fit_manifest']['files'][name]:
            raise ValueError('Saved time basis differs')
    joint=[joint_floor_contrasts(f['root'],f['protocol'],f['design'],levels) for f in fits]
    comparisons=[]
    for x,y in zip(joint[0]['contrasts'],joint[1]['contrasts'],strict=True):
        if (x['lower_floor'],x['upper_floor'])!=(y['lower_floor'],y['upper_floor']):raise ValueError('Floor endpoints differ')
        comparisons.append({'lower_floor':x['lower_floor'],'upper_floor':x['upper_floor'],
            'reference':x,'candidate':y,'median_change_percentage_points':y['percent_effect']['median']-x['percent_effect']['median']})
    result={'version':VERSION,'cohort':a['report']['cohort'],'source_observations_sha256':a['protocol']['source_observations_sha256'],
        'unchanged_nonfloor_features':nonfloor,'floor_support':floor._support(data,values,levels),
        'floor_contrasts':comparisons,'floor_diagnostics':[j['diagnostics'] for j in joint],
        'fits':[{'experiment':str(f['root']),'protocol':f['protocol'],'diagnostics':f['report']['diagnostics'],
            'design_reconstruction':f['reconstruction']} for f in fits],
        'bathrooms':{name:common.compare_tables(a['report']['bathrooms'][name],b['report']['bathrooms'][name],fields)
            for name,fields in [('full_bath_increments',('log_effect','percent_effect')),('half_bath_increments',('log_effect','percent_effect')),
                                ('net_balance',('difference',))]},
        'residuals':source.matched_residuals(a['residuals'],b['residuals'],a['report'],b['report'],rows,[]),
        'floor_residual_slices':floor_residual_slices(data,a['residuals'],b['residuals']),
        'limitations':[common.LIMITATION,'Changing floor representation also changes its induced prior. Prior and posterior contrast SDs are reported explicitly.',
            'Floor contrasts hold other encoded terms and group effects fixed. They are recorded-label associations, not physical-height or causal effects.',
            'In-sample residual improvement alone does not justify flexibility; sparse overlap, source contradictions, group confounding and prior sensitivity remain relevant.',
            *a['report']['limitations']]}
    return result,[f['provenance'] for f in fits]


def markdown(result):
    lines=['# Listed-floor sensitivity','',f"{result['cohort']['rows']:,} identical observations; all nonfloor features and priors verified unchanged.",'',
        '| Labels | Reference % [95%] | Candidate % [95%] | Reference / candidate prior log SD |',
        '| --- | ---: | ---: | ---: |']
    def cell(v):return f"{v['median']:+.2f} [{v['lower_95']:+.2f}, {v['upper_95']:+.2f}]"
    for row in result['floor_contrasts']:
        a,b=row['reference'],row['candidate']
        lines.append(f"| {row['lower_floor']:g} → {row['upper_floor']:g} | {cell(a['percent_effect'])} | {cell(b['percent_effect'])} | {a['prior_log_sd']:.4f} / {b['prior_log_sd']:.4f} |")
    lines+=['','Endpoint/shared-building support, known/unknown floor residual slices, current-apartment movements, bathroom contrasts and exact protocols are preserved in comparison.json.','',*result['limitations']]
    return '\n\n'.join(lines)+'\n'


def run(reference,candidate,dataset,output):
    paths=[Path(__file__),*[Path(module.__file__) for module in (report,common,source,loader,floor,disk,base,summaries)]]
    hashes={p.name:digest(p) for p in paths}
    result,provenance=build_comparison(reference,candidate,dataset)
    if any(digest(p)!=hashes[p.name] for p in paths):raise ValueError('Comparison implementation changed')
    return publish_bundle(output,{'comparison.json':canonical(result)+'\n','comparison.md':markdown(result),
        **{p.name:p.read_text() for p in paths}},{'version':VERSION,'experiments':provenance,'implementation_sha256':hashes})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','dataset','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    with threadpool_limits(limits=1,user_api='blas'):run(args.reference,args.candidate,args.dataset,args.output)

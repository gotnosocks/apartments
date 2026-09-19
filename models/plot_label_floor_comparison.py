"""Verified joint-posterior floor curves and source coverage; never fit or select."""
import argparse
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from . import floor_label_fit_comparison as label_comparison
from . import floor_elevator_fit_comparison as elevator_comparison
from . import bayesian_category_contrasts as categories
from . import bayesian_floor_elevator_design as interaction
from . import bayesian_floor_increment_design as floor
from . import publish_floor_increment_audit as publisher

shared = label_comparison.shared
VERSION = 'joint-label-floor-curve-report-v1'
REFERENCE_FLOOR = 2.


def vector(design, frame, level, access=None):
    levels=design.floor_levels
    if REFERENCE_FLOOR not in levels or level not in levels:
        raise ValueError('Floor curve requires supported endpoints; extrapolation refused')
    if access is not None and type(access) is not bool: raise ValueError('Known elevator state required')
    if level==REFERENCE_FLOOR:return np.zeros(len(design.features))
    if access is not None:
        low,high=sorted([REFERENCE_FLOOR,level])
        value=interaction.floor_contrast_vector(design,frame,low,high,access)
        return value if level>REFERENCE_FLOOR else -value
    if hasattr(design,'base'): raise ValueError('Interaction curve requires explicit elevator state')
    result=np.zeros(len(design.features))
    for threshold in design.floor_thresholds:
        result[design.features.index(floor._name(threshold))]=float(level>threshold)-float(REFERENCE_FLOOR>threshold)
    return result


def curve(fit, access=None):
    design=fit['design'];beta=elevator_comparison.beta_draws(fit)
    if REFERENCE_FLOOR not in design.floor_levels:raise ValueError('Reference floor 2 absent')
    definitions=[{'id':f'floor:{REFERENCE_FLOOR:g}->{level:g}:access={access}',
        'floor':level,'reference_floor':REFERENCE_FLOOR,'elevator':access,
        'design_vector':vector(design,fit['data'],level,access).tolist()} for level in design.floor_levels if level!=REFERENCE_FLOOR]
    calculated,_=categories.calculate(beta,definitions)
    calculated.append({'id':f'floor:2->2:access={access}','floor':REFERENCE_FLOOR,
        'reference_floor':REFERENCE_FLOOR,'elevator':access,'design_vector':[0.]*len(design.features),
        'log_effect':{'median':0.,'lower_95':0.,'upper_95':0.},
        'percent_effect':{'median':0.,'lower_95':0.,'upper_95':0.},
        'status':'deterministic_reference','diagnostics':{'deterministic':True,'reason':'Identical endpoint contrast; no sampling ESS or R-hat claimed.'}})
    for row in calculated:
        row['normal_prior_log_sd']=float(np.linalg.norm(np.asarray(row['design_vector'])*design.prior_scales)*fit['protocol']['prior_multiplier'])
    source_values=floor.listed_floor_values(fit['data'])
    access_values=np.array([v[1] for v in elevator_comparison.contract.source_values(fit['data'].to_dict('records'))],dtype=object) if access is not None else None
    for row in calculated:
        mask=(source_values==row['floor'])
        baseline_mask=(source_values==REFERENCE_FLOOR)
        if access is not None:
            mask &= access_values==int(access);baseline_mask &= access_values==int(access)
        row['endpoint_rows_at_access']=int(mask.sum())
        row['reference_rows_at_access']=int(baseline_mask.sum())
        row['both_endpoints_observed_at_access']=bool(mask.any() and baseline_mask.any())
        supported=row['both_endpoints_observed_at_access']
        row['source_support_status']='both_endpoints_observed' if supported else 'withheld_missing_joint_floor_access_endpoint'
        row['source_support_reason']=None if supported else 'No fitted observations at the reference or target floor with this known elevator state.'
        row['display_percent_effect']=row['percent_effect'] if supported else None
    return {'elevator':access,'points':sorted(calculated,key=lambda r:r['floor']),
        'withheld_points':sum(r['status']=='withheld_derived_diagnostics' for r in calculated),
        'source_withheld_points':sum(not r['both_endpoints_observed_at_access'] for r in calculated),
        'reference_floor':REFERENCE_FLOOR}


def source_counts(frame):
    values=floor.listed_floor_values(frame)
    records=frame.to_dict('records')
    proxy=np.array([r.get('floor_label_provenance',{}).get('status')=='label_proxy' for r in records])
    known=np.isfinite(values)
    result=[]
    for level in np.unique(values[known]):
        mask=values==level
        result.append({'floor':float(level),'explicit_rows':int((mask&~proxy).sum()),
            'label_proxy_rows':int((mask&proxy).sum()),'units':int(frame.loc[mask,'unit_id'].nunique()),
            'buildings':int(frame.loc[mask,'building'].nunique())})
    return {'levels':result,'missing_rows':int((~known).sum()),'rows':len(frame),
        'interpretation':'Counts are fitted observations, including historical advertisements; repeated unit observations are not independent units.'}


def load_fit(root,dataset,rows):
    root,dataset=Path(root),Path(dataset)
    report,provenance=shared.report.build_report(root,dataset)
    protocol=json.loads(shared.common.bound_bytes(root/'protocol','protocol.json',provenance['protocol_manifest']))
    reconstruction=shared.source.verify_design(root,dataset,protocol,provenance)
    frame=pd.DataFrame(rows);frame.period=pd.to_datetime(frame.period)
    frame.square_feet=pd.to_numeric(frame.square_feet,errors='coerce')
    return {'root':root,'dataset':dataset,'report':report,'provenance':provenance,'protocol':protocol,
        'reconstruction':reconstruction,'data':frame,'design':shared.load_design(root/'fit',frame,protocol)}


def build(reference,reference_dataset,candidate,candidate_dataset,interaction_fit,interaction_dataset):
    before,after=label_comparison.verify_revision(reference_dataset,candidate_dataset)
    third_manifest,third_files=_verified_bundle(interaction_dataset,retain={'observations.jsonl'})
    second_manifest,_=_verified_bundle(candidate_dataset,retain=set())
    if third_manifest!=second_manifest or shared.report.jsonl(third_files['observations.jsonl'])!=after:
        raise ValueError('Interaction fit must use the exact expanded-floor source')
    fits=[load_fit(root,data,rows) for root,data,rows in
        [(reference,reference_dataset,before),(candidate,candidate_dataset,after),(interaction_fit,interaction_dataset,after)]]
    a,b,c=fits
    label_comparison.check_protocols(a['protocol'],b['protocol']);label_comparison.check_designs(a,b)
    elevator_comparison.check_protocols(b['protocol'],c['protocol']);elevator_comparison.check_designs(b,c)
    result={'version':VERSION,'reference_floor':REFERENCE_FLOOR,'main_selection_changed':False,
        'curves':{'explicit_source_baseline':curve(a),'expanded_label_floor':curve(b),
            'expanded_with_elevator':curve(c,True),'expanded_without_elevator':curve(c,False)},
        'source_counts':{'baseline':source_counts(a['data']),'expanded':source_counts(b['data'])},
        'fits':[{'root':str(f['root']),'dataset':str(f['dataset']),'protocol':f['protocol'],
            'bindings':{k:digest(path/'complete.json') for k,path in [('fit',f['root']/'fit'),('protocol',f['root']/'protocol'),('source',f['dataset'])]},
            'design_reconstruction':f['reconstruction']} for f in fits],
        'interpretation':[
            'Floor-feature contribution relative to listed floor 2, holding other features and building/unit/time effects fixed. Conditional associations, not causal premiums or measured physical height.',
            'Bands are pointwise 95% posterior credible intervals from joint beta draws within each fit, not simultaneous or predictive intervals. Independent fit draws are never paired.',
            'Every nonzero cumulative contrast is checked for R-hat <1.01 and bulk/tail ESS >=400. Failed points and their intervals are withheld. Floor 2 is a deterministic zero without ESS.',
            'Baseline is shown only at its observed supported labels. Connecting displayed supported endpoints does not estimate unobserved labels.',
            'Known elevator curves include the full floor plus interaction component. Upper-floor interaction saturation is a model restriction, not evidence for access effects at every height.',
            'The interaction panel shows only floor labels observed in both known elevator states, so its axis focuses on their shared source support. Full supported curves remain in this summary.',
            'Displayed curves and intervals omit any endpoint with no observed joint floor/access support. Raw conditional research contrasts remain in the summary with separate source and sampling statuses.',
            'Unit-label proxies may differ from the building physical floor. Source coverage and prior sensitivity remain necessary when interpreting high-floor uncertainty.']}
    for f in fits:
        if digest(f['root']/'fit/posterior.nc')!=f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed while computing floor curves')
    return result


def render(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':VERSION}):
        fig=plt.figure(figsize=(13,9),layout='constrained');grid=fig.add_gridspec(2,2,height_ratios=[2,1])
        left=fig.add_subplot(grid[0,0]);right=fig.add_subplot(grid[0,1]);counts=fig.add_subplot(grid[1,:])
        def draw(ax,key,label,color,levels=None):
            points=[r for r in result['curves'][key]['points'] if levels is None or r['floor'] in levels]
            x=[r['floor'] for r in points]
            ys=[[r['display_percent_effect'][k] if r['display_percent_effect'] is not None else np.nan for r in points]
                for k in ('median','lower_95','upper_95')]
            ax.plot(x,ys[0],'.-',label=label,color=color,linewidth=1.3,markersize=4)
            ax.fill_between(x,ys[1],ys[2],alpha=.15,color=color)
        draw(left,'explicit_source_baseline','Explicit-source floor baseline','#6c757d')
        draw(left,'expanded_label_floor','Expanded with unit-label proxies','#1368aa')
        common_levels=set.intersection(*[{r['floor'] for r in result['curves'][key]['points']
            if r['both_endpoints_observed_at_access']} for key in ('expanded_without_elevator','expanded_with_elevator')])
        draw(right,'expanded_without_elevator','Known no elevator','#bd5c22',common_levels)
        draw(right,'expanded_with_elevator','Known elevator','#2a8060',common_levels)
        for ax,title in [(left,'Adding advertised unit-label floors'),(right,'Floor + elevator: shared floor support')]:
            ax.axhline(0,color='#555555',linewidth=.7);ax.set(title=title,xlabel='Supported listed-floor label',ylabel='Floor component vs floor 2 (%)')
            ax.legend(fontsize=9);ax.grid(alpha=.15)
        levels=result['source_counts']['expanded']['levels'];x=[r['floor'] for r in levels]
        explicit=[r['explicit_rows'] for r in levels];proxy=[r['label_proxy_rows'] for r in levels]
        counts.bar(x,explicit,label='Explicit floor',color='#6c757d')
        counts.bar(x,proxy,bottom=explicit,label='Unit-label proxy',color='#1368aa')
        counts.set(xlabel='Supported listed-floor label',ylabel='Fitted observations',
            title=f"Expanded source coverage; {result['source_counts']['expanded']['missing_rows']:,} observations remain without floor")
        counts.legend(fontsize=9)
        withheld=sum(v['withheld_points'] for v in result['curves'].values())
        unsupported=sum(v['source_withheld_points'] for v in result['curves'].values())
        fig.suptitle('Conditional floor contributions • joint posterior pointwise 95% intervals\n'
            f'Not physical height • Withheld: {withheld} sampling diagnostics; {unsupported} missing floor/access support',fontsize=13)
        payload={}
        for extension in ('png','svg'):
            stream=BytesIO();fig.savefig(stream,format=extension,dpi=170,metadata={'Date':None} if extension=='svg' else {})
            payload[f'floor-curves.{extension}']=stream.getvalue()
        plt.close(fig)
    return payload


def run(output,**kwargs):
    modules=(label_comparison,elevator_comparison,categories,interaction,floor,shared,shared.report,shared.source,shared.common,publisher)
    paths=[Path(__file__),*[Path(m.__file__) for m in modules]]
    hashes={p.name:digest(p) for p in paths}
    result=build(**kwargs);files=render(result)
    if any(digest(p)!=hashes[p.name] for p in paths):raise ValueError('Plot implementation changed during analysis')
    files.update({'summary.json':(canonical(result)+'\n').encode(),**{p.name:p.read_bytes() for p in paths}})
    publisher._publish(output,files,{'version':VERSION,'fits':[f['bindings'] for f in result['fits']],'implementation_sha256':hashes})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','reference-dataset','candidate','candidate-dataset','interaction-fit','interaction-dataset','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):run(**vars(parser.parse_args()))

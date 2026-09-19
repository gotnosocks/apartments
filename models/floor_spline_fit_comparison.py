"""Matched source comparison of increment and regularized spline floor models."""
import argparse
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from . import quarantine_fit_comparison as shared
from . import bayesian_floor_execution as execution
from . import bayesian_floor_increment_design as increment
from . import bayesian_floor_spline_design as spline
from . import bayesian_floor_spline_experiment as experiment
from . import bayesian_category_contrasts as contrasts
from . import floor_elevator_fit_comparison as elevator
from . import publish_floor_increment_audit as publisher

VERSION='matched-floor-spline-fit-comparison-v1'
VARIABLE={'version','feature_design_version','floor_increment_prior_scale','floor_thresholds',
    'floor_prior_scale','floor_knots','floor_reference','floor_policy','graph','graph_verification',
    'implementation_sha256','maxdepth','execution_graph'}
ADDED={'bayesian_floor_spline_design.py','bayesian_floor_spline_experiment.py'}
REMOVED={'bayesian_feature_experiment_v4.py'}
EXECUTION_CODE={'bayesian_disk_sampling.py','bayesian_disk_experiment.py','bayesian_floor_execution.py'}
EXECUTION_ADDED={'bayesian_floor_execution.py','bayesian_floor_block_graph.py','verify_floor_block_graph.py'}


def check_protocols(a,b):
    if (a.get('version')!=shared.floors.V4 or b.get('version')!=experiment.VERSION
            or a.get('residual_scale')!='shared' or not execution.verify_protocol(a)
            or not execution.verify_protocol(b)):
        raise ValueError('Expected durable increment and spline fits with shared residual scale')
    if {k:v for k,v in a.items() if k not in VARIABLE}!={k:v for k,v in b.items() if k not in VARIABLE}:
        raise ValueError('Source, nonfloor model, population, priors or sampler changed')
    for p in (a,b):
        if p.get('maxdepth',10) not in (10,14):raise ValueError('Unspecified tree-depth comparison')
        expected={'chains':4,'tune':4000,'draws':6000,'target_accept':.93,'adaptation':'diag','seed':20260924}
        if any(p.get(k)!=v for k,v in expected.items()):raise ValueError('Production sampling settings differ')
        levels=p.get('floor_levels',[])
        if len(levels)<2 or levels!=sorted(set(levels)):raise ValueError('Invalid observed floor support')
    if a.get('floor_thresholds')!=a['floor_levels'][:-1]:raise ValueError('Invalid increment thresholds')
    knots,anchor=spline.knot_specification(b['floor_levels'])
    if (b.get('floor_knots')!=knots or b.get('floor_reference')!=anchor
            or b.get('floor_policy')!=spline.policy()):raise ValueError('Invalid spline specification')
    old,new=a['implementation_sha256'],b['implementation_sha256']
    if (set(new)-set(old))-ADDED-EXECUTION_ADDED or (set(old)-set(new))-REMOVED:
        raise ValueError('Unexpected implementation inventory change')
    if not ADDED<=new.keys():raise ValueError('Spline implementation missing')
    changed={k for k in old.keys()&new.keys() if old[k]!=new[k]}
    if changed-EXECUTION_CODE:raise ValueError('Shared mathematical implementation changed')
    return sorted(changed)


def is_floor(name):
    return name in ('listed_floor','listed_floor.unknown') or name.startswith(('listed_floor_gt_','listed_floor_spline_'))


def check_design_arrays(a,b,adata,bdata):
    names=[n for n in a.features if not is_floor(n)]
    if names!=[n for n in b.features if not is_floor(n)]:raise ValueError('Nonfloor columns changed')
    ai,bi=[[d.features.index(n) for n in names] for d in (a,b)]
    for x,y in [(a.means[ai],b.means[bi]),(a.prior_scales[ai],b.prior_scales[bi]),
                (a.matrix(adata)[:,ai],b.matrix(bdata)[:,bi])]:
        if not np.array_equal(x,y):raise ValueError('Nonfloor encoding, centering or priors changed')
    # Missingness is not part of the intended smoothness change.
    for d,e,data,other in [(a,b,adata,bdata)]:
        name='listed_floor.unknown'
        if (name in d.features)!=(name in e.features):raise ValueError('Floor missingness representation changed')
        if name in d.features:
            i,j=d.features.index(name),e.features.index(name)
            if (d.means[i]!=e.means[j] or d.prior_scales[i]!=e.prior_scales[j]
                    or not np.array_equal(d.matrix(data)[:,i],e.matrix(other)[:,j])):
                raise ValueError('Floor missingness representation changed')
    return names


def check_designs(a,b):
    names=check_design_arrays(a['design'],b['design'],a['data'],b['data'])
    times=[json.loads(shared.common.bound_bytes(f['root']/'fit','time-design.json',f['provenance']['fit_manifest'])) for f in (a,b)]
    if times[0]!=times[1] or a['reconstruction']['time_arrays']!=b['reconstruction']['time_arrays']:
        raise ValueError('Time or group design changed')
    return names


def curve_vector(design,level):
    if 2. not in design.floor_levels or level not in design.floor_levels:
        raise ValueError('Observed reference and target floors required')
    if isinstance(design,spline.FeatureDesign):return design.contrast_vector(2.,level)
    result=np.zeros(len(design.features))
    for threshold in design.floor_thresholds:
        result[design.features.index(increment._name(threshold))]=float(level>threshold)-float(2.>threshold)
    return result


def curve_from_draws(design,beta,prior_multiplier):
    levels=design.floor_levels
    definitions=[{'id':f'floor:2->{level:g}','floor':level,'reference_floor':2.,
        'design_vector':curve_vector(design,level).tolist()} for level in levels if level!=2.]
    rows,diagnostics=contrasts.calculate(beta,definitions)
    rows.append({'id':'floor:2->2','floor':2.,'reference_floor':2.,'design_vector':[0.]*len(design.features),
        'log_effect':{'median':0.,'lower_95':0.,'upper_95':0.},
        'percent_effect':{'median':0.,'lower_95':0.,'upper_95':0.},'status':'deterministic_reference',
        'diagnostics':{'deterministic':True}})
    for row in rows:
        sd=float(np.linalg.norm(np.asarray(row['design_vector'])*design.prior_scales)*prior_multiplier)
        row['normal_prior_log_sd']=sd
        row['prior_log_effect']={'median':0.,'lower_95':-1.959963984540054*sd,'upper_95':1.959963984540054*sd}
    return {'reference_floor':2.,'points':sorted(rows,key=lambda r:r['floor']),
        'withheld_points':sum(r['status']=='withheld_derived_diagnostics' for r in rows),
        'interpretation':'Joint within-fit coefficient draws preserve covariance. Pointwise intervals; independent fits are never paired. Prior bands are analytical marginal Normal intervals for the same endpoint contrast.'}


def residual_slices(rows,movements):
    indexed={r['audit_id']:r for r in movements}
    if len(indexed)!=len(movements) or set(indexed)!={r['audit_id'] for r in rows}:
        raise ValueError('Residual membership differs')
    from pandas import DataFrame
    values=increment.listed_floor_values(DataFrame(rows))
    proxy=np.array([r.get('floor_label_provenance',{}).get('status')=='label_proxy' for r in rows])
    masks={'all':np.ones(len(rows),dtype=bool),
        'current_capture':np.array([r['analysis_price_basis']=='current_capture_gross_ask' for r in rows]),
        'newly_inferred_floor':proxy,'explicit_floor':np.isfinite(values)&~proxy,'missing_floor':~np.isfinite(values)}
    return {name:{**shared.laundry.summarize_slice([indexed[r['audit_id']] for r,keep in zip(rows,mask,strict=True) if keep]),
        'buildings':len({r['building'] for r,keep in zip(rows,mask,strict=True) if keep})} for name,mask in masks.items()}


def floor_parameter_diagnostics(fit):
    from io import StringIO
    import pandas as pd
    root=fit['root']/'fit';manifest=fit['provenance']['fit_manifest']
    raw=shared.common.bound_bytes(root,'parameter-diagnostics.csv',manifest)
    table=pd.read_csv(StringIO(raw.decode() if isinstance(raw,bytes) else raw)).set_index('parameter')
    coefficients=json.loads(shared.common.bound_bytes(root,'coefficients.json',manifest))
    lookup={r['feature']:r for r in coefficients}
    rows=[]
    for name in fit['design'].features:
        if not is_floor(name):continue
        diag=table.loc['beta['+name+']'].to_dict()
        if not np.isfinite(list(diag.values())).all():raise ValueError('Nonfinite floor coefficient diagnostics')
        rows.append({'feature':name,'posterior':lookup[name],'diagnostics':diag,
            'prior_sd':float(fit['design'].prior_scales[fit['design'].features.index(name)]*fit['protocol']['prior_multiplier'])})
    return rows


def summarize_sampler_work(steps,step_size,diverging,maxdepth_reached):
    arrays=[np.asarray(v) for v in (steps,step_size,diverging,maxdepth_reached)]
    steps,step_size,diverging,maxdepth_reached=arrays
    if (steps.ndim!=2 or not steps.size or any(a.shape!=steps.shape for a in arrays)
            or any(not np.isfinite(a).all() for a in arrays)
            or np.any(steps<1) or np.any(steps!=np.floor(steps)) or np.any(step_size<=0)
            or any(not np.isin(a,[0,1]).all() for a in (diverging,maxdepth_reached))):
        raise ValueError('Invalid retained sampler-work arrays')
    total=int(steps.sum());long=steps>1023
    return {'retained_draws':int(steps.size),'chains':int(steps.shape[0]),
        'n_steps':{'median':float(np.median(steps)),'mean':float(np.mean(steps)),
            'p90':float(np.quantile(steps,.90)),'p99':float(np.quantile(steps,.99)),
            'max':int(steps.max()),'total':total},
        'fraction_draws_above_1023_steps':float(np.mean(long)),
        'fraction_steps_from_draws_above_1023':float(steps[long].sum()/total),
        'divergences':int(diverging.sum()),'maxdepth_hits':int(maxdepth_reached.sum()),
        'per_chain_step_size_median':[float(v) for v in np.median(step_size,axis=1)],
        'interpretation':'Retained-draw leapfrog work counts only; warmup excluded. This is not a controlled wall-time benchmark. Graph costs, startup, hardware contention and model geometry may differ.'}


def sampler_work(fit):
    import xarray as xr
    path=fit['root']/'fit/posterior.nc';p=fit['protocol']
    with xr.open_dataset(path,group='sample_stats',engine='h5netcdf',cache=False) as stats:
        names=('n_steps','step_size','diverging','maxdepth_reached')
        if (stats.sizes.get('chain')!=p['chains'] or stats.sizes.get('draw')!=p['draws']
                or any(stats[name].dims!=('chain','draw') for name in names)
                or np.any(stats['tuning'].values)):
            raise ValueError('Sampler-work dimensions or warmup differ from retained protocol')
        result=summarize_sampler_work(*(stats[name].values for name in names))
    floor_diags=floor_parameter_diagnostics(fit)
    result['minimum_floor_parameter_bulk_ess']=min(r['diagnostics']['ess_bulk'] for r in floor_diags)
    return result


def build_comparison(reference,candidate,reference_dataset,dataset):
    bundles=[_verified_bundle(p,retain={'observations.jsonl'}) for p in (reference_dataset,dataset)]
    if bundles[0][0]!=bundles[1][0] or bundles[0][1]['observations.jsonl']!=bundles[1][1]['observations.jsonl']:
        raise ValueError('Spline comparison requires identical source manifests and observations')
    rows=shared.report.jsonl(bundles[0][1]['observations.jsonl'])
    a,b=shared.load_fits(reference,candidate,reference_dataset,dataset,rows,rows)
    changed=check_protocols(a['protocol'],b['protocol']);names=check_designs(a,b)
    movements,residuals=shared.compare_residuals(a['residuals'],b['residuals'],rows,rows)
    groups,removed=shared.compare_groups(a['groups'],b['groups'],rows,rows)
    if removed or residuals['excluded_reference_rows']:raise ValueError('Matched population lost observations or groups')
    buildings=sorted({r['building'] for r in rows});common=[shared.building_contrasts(f,buildings) for f in (a,b)]
    building_changes=[{'id':x['id'],'log_effect':shared.common.interval_change(x['log_effect'],y['log_effect'])}
        for x,y in zip(common[0]['contrasts'],common[1]['contrasts'],strict=True)]
    building_changes.sort(key=lambda r:(-abs(r['log_effect']['median_change']),r['id']))
    curves=[curve_from_draws(f['design'],elevator.beta_draws(f),f['protocol']['prior_multiplier']) for f in (a,b)]
    distinct=[];seen=set()
    for row in movements:
        if row['unit_id'] not in seen:distinct.append(row);seen.add(row['unit_id'])
        if len(distinct)==25:break
    result={'version':VERSION,'main_selection_changed':False,'rows':len(rows),'unchanged_nonfloor_features':names,
        'changed_execution_implementations':changed,'curves':curves,
        'fits':[{'protocol':f['protocol'],'diagnostics':f['report']['diagnostics'],
            'design_reconstruction':f['reconstruction'],'floor_parameter_diagnostics':floor_parameter_diagnostics(f),'retained_sampler_work':sampler_work(f),'bindings':{k:digest(path/'complete.json') for k,path in
                [('fit',f['root']/'fit'),('protocol',f['root']/'protocol'),('source',f['dataset'])]}} for f in (a,b)],
        'floor_support':[f['design'].floor_support for f in (a,b)],'residuals':residuals,
        'residual_slices':residual_slices(rows,movements),'largest_distinct_unit_movements':distinct,
        'largest_unit_offset_movements':[r for r in groups if r['kind']=='unit'][:25],
        'largest_common_reference_building_movements':building_changes[:25],
        'building_reference':{'definition':'Unweighted mean of identical building population subtracted within each joint posterior draw.',
            'buildings':buildings,'diagnostics':[v['diagnostics'] for v in common]},
        'limitations':[shared.common.LIMITATION,'Floor representation AND induced prior change; this is not a pure execution comparison.',
            'Residuals are in sample and include unit effects. Improvement alone does not establish identification or justify model selection.',
            'Advertised floor labels are proxies, not physical height. High floors may concentrate in very few buildings.',
            'Curve intervals are pointwise conditional associations; between-fit shifts are descriptive, not paired posterior differences.']}
    for f in (a,b):
        if digest(f['root']/'fit/posterior.nc')!=f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result,movements,groups,building_changes


def render(result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':VERSION}):
        fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
        colors=['#4564a3','#b14e38'];labels=['Floor increments','Regularized spline']
        for i,curve in enumerate(result['curves']):
            rows=curve['points'];x=[r['floor'] for r in rows]
            for ax,kind,label,alpha in [(axes[i],'prior_log_effect','Prior 95%',.14),(axes[i],'log_effect','Posterior 95%',.35)]:
                values=[[r[kind][key] if r.get(kind) is not None else np.nan for r in rows] for key in ('lower_95','median','upper_95')]
                ax.fill_between(x,values[0],values[2],color=colors[i],alpha=alpha,label=label)
                ax.plot(x,values[1],color=colors[i],linestyle='--' if kind.startswith('prior') else '-')
            ax=axes[2];values=[[r['log_effect'][key] if r.get('log_effect') is not None else np.nan for r in rows] for key in ('lower_95','median','upper_95')]
            ax.plot(x,values[1],color=colors[i],label=labels[i]);ax.fill_between(x,values[0],values[2],color=colors[i],alpha=.18)
        for ax,title in zip(axes,[*labels,'Posterior comparison'],strict=True):
            ax.axhline(0,color='gray',lw=.7);ax.set(title=title,xlabel='Advertised floor label',ylabel='Log-price component relative to floor 2');ax.legend();ax.grid(alpha=.15)
        fig.suptitle('Floor curves: changed representation and prior; identical fitted observations')
        files={}
        for extension in ('png','svg'):
            stream=BytesIO();fig.savefig(stream,format=extension,dpi=160,metadata={'Date':None} if extension=='svg' else None);files['floor-curves.'+extension]=stream.getvalue()
        plt.close(fig)
    return files


def run(output,**kwargs):
    modules=(shared,shared.report,shared.source,shared.common,shared.laundry,shared.floors,execution,
        increment,spline,experiment,contrasts,elevator,publisher)
    paths=[Path(__file__),*[Path(m.__file__) for m in modules]];hashes={p.name:digest(p) for p in paths}
    result,movements,groups,buildings=build_comparison(**kwargs);files=render(result)
    files.update({'comparison.json':(canonical(result)+'\n').encode(),
        'movements.jsonl':''.join(canonical(r)+'\n' for r in movements).encode(),
        'residual-movements.jsonl':''.join(canonical(r)+'\n' for r in movements).encode(),
        'raw-group-movements.jsonl':''.join(canonical(r)+'\n' for r in groups).encode(),
        'common-reference-building-movements.jsonl':''.join(canonical(r)+'\n' for r in buildings).encode(),
        **{p.name:p.read_bytes() for p in paths}})
    if any(digest(p)!=hashes[p.name] for p in paths):raise ValueError('Comparison implementation changed')
    publisher._publish(output,files,{'version':VERSION,'fits':[f['bindings'] for f in result['fits']],'implementation_sha256':hashes})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','reference-dataset','dataset','output'):parser.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):run(**vars(parser.parse_args()))

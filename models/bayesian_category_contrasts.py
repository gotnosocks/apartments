"""Joint posterior contrasts between explicitly recorded amenity categories."""
from __future__ import annotations

import argparse
import itertools
import importlib.metadata
import json
from pathlib import Path

import arviz as az
import numpy as np
import pandas as pd
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report
from . import bayesian_feature_checks_v3 as checks
from . import bayesian_feature_design_v2 as loader
from . import bayesian_feature_model as feature

VERSION = 'bayesian-category-contrasts-v1'
HIGHLIGHTS = {('laundry_type','in_building','in_unit'), ('doorman_type','part_time','full_time')}
LIMITATIONS = [
    'Conditional posterior associations for recorded categories, not causal amenity upgrades or willingness to pay. Building, unit, date, area and all other encoded features remain fixed.',
    'Known category endpoints are compared directly. Unknown reporting is not a no-amenity category; no unknown-versus-known premium is calculated.',
    'Each contrast combines joint coefficient draws, preserving posterior covariance. Raw orthonormal basis coefficients are not category premiums.',
    'Endpoint support is observational coverage, not matched treatment groups. Shared-building/unit counts may reflect reporting differences, changes over time or source mistakes; overlap does not establish causality.',
    'All fitted current observations contribute to the posterior. Convergence gates concern numerical sampling, not identification or robustness to priors and omitted amenities.',
    'Intervals are 95% posterior credible intervals for conditional log-price contrasts and their transformed percentage changes. They are not predictive or transaction-price intervals.',
]


def support(frame):
    return {'rows':len(frame),'units':int(frame.unit_id.nunique()),'buildings':int(frame.building.nunique())}


def contrast_vector(design, data, field, before, after):
    meta=design.categories[field]
    if before not in meta['levels'] or after not in meta['levels'] or before == after:
        raise ValueError('Distinct known category endpoints required')
    a=data.iloc[[0]].copy();b=a.copy()
    a[field]=before;b[field]=after
    vector=(design.matrix(b)-design.matrix(a))[0]
    expected=np.zeros(len(design.features))
    basis=np.asarray(meta['basis'])
    delta=basis[meta['levels'].index(after)]-basis[meta['levels'].index(before)]
    for index,value in enumerate(delta):
        name=f'{field}.contrast_{index}'
        if abs(value)>1e-14 and name not in design.features:
            raise ValueError('Category contrast requires an unencoded basis column')
        if name in design.features:expected[design.features.index(name)]=value
    if not np.allclose(vector,expected,rtol=0,atol=1e-12) or not np.any(abs(vector)>1e-14):
        raise ValueError('Category endpoint change altered other features or is unencoded')
    return vector


def construct_contrasts(design,data):
    normalized=[feature.amenity.feature_record(row) for row in data.to_dict('records')]
    categories,contrasts,omitted=[],[],[]
    for field,meta in design.categories.items():
        values=np.array([feature.pricing._category(row.get(field)) for row in normalized])
        counts=[int(np.sum(values==level)) for level in meta['levels']]
        known=np.isin(values,meta['levels'])
        if sum(counts) and not np.allclose(np.array(counts)/sum(counts),meta['frequencies'],rtol=0,atol=1e-12):
            raise ValueError('Category frequencies differ from saved training design')
        categories.append({'field':field,'known':support(data.loc[known]),'unknown':support(data.loc[~known]),
                           'levels':[{'category':level,**support(data.loc[values==level])} for level in meta['levels']]})
        for first,second in itertools.combinations(meta['levels'],2):
            before,after=(second,first) if (field,second,first) in HIGHLIGHTS else (first,second)
            a,b=data.loc[values==before],data.loc[values==after]
            item={'field':field,'before':before,'after':after,'id':f'{field}:{before}->{after}',
                  'highlight':(field,before,after) in HIGHLIGHTS,
                  'support_before':support(a),'support_after':support(b),
                  'overlap':{'buildings':len(set(a.building)&set(b.building)),
                             'units':len(set(a.unit_id)&set(b.unit_id)),
                             'before_rows_in_shared_buildings':int(a.building.isin(set(b.building)).sum()),
                             'after_rows_in_shared_buildings':int(b.building.isin(set(a.building)).sum())}}
            if a.empty or b.empty:
                omitted.append({**item,'reason':'Unsupported endpoint'});continue
            vector=contrast_vector(design,data,field,before,after)
            contrasts.append({**item,'design_vector':vector.tolist(),
                              'nonzero_design_vector':{name:float(v) for name,v in zip(design.features,vector) if abs(v)>1e-14}})
    return categories,contrasts,omitted


def interval(values):
    lo,med,hi=np.quantile(values,[.025,.5,.975])
    return {'median':float(med),'lower_95':float(lo),'upper_95':float(hi),'probability_positive':float(np.mean(values>0))}


def calculate(beta,contrasts):
    if not contrasts:raise ValueError('No supported encoded category contrasts')
    vectors=np.asarray([item['design_vector'] for item in contrasts])
    if beta.ndim != 3 or not np.isfinite(beta).all() or beta.shape[2] != vectors.shape[1]:
        raise ValueError('Finite joint chain/draw/feature coefficient array required')
    draws=np.einsum('cdf,kf->cdk',beta,vectors)
    ds=xr.Dataset({'category_contrast':(('chain','draw','contrast'),draws)},
                  coords={'contrast':[item['id'] for item in contrasts]})
    diagnostics=az.summary(ds,kind='diagnostics',round_to='none')
    rows=[]
    for index,item in enumerate(contrasts):
        diag=diagnostics.loc['category_contrast['+item['id']+']']
        finite=np.isfinite(diag[['r_hat','ess_bulk','ess_tail']].to_numpy(float)).all()
        accepted=bool(finite and diag.r_hat<1.01 and diag.ess_bulk>=400 and diag.ess_tail>=400)
        values=draws[:,:,index].ravel()
        finite_value=lambda value:float(value) if np.isfinite(value) else None
        rows.append({**item,'diagnostics':{'max_rhat':finite_value(diag.r_hat),'ess_bulk':finite_value(diag.ess_bulk),
                     'ess_tail':finite_value(diag.ess_tail),'acceptable':accepted},
                     'log_effect':interval(values) if accepted else None,
                     'percent_effect':interval(100*np.expm1(values)) if accepted else None,
                     'status':'supported_converged' if accepted else 'withheld_derived_diagnostics'})
    return rows,diagnostics


def markdown(result):
    lines=['# Recorded-category Bayesian contrasts','',*[p+'\n' for p in LIMITATIONS],
           '| Feature | Before → after | Median percent [95% CrI] | Before rows / units / buildings | After support | Shared buildings / units |',
           '|---|---|---:|---|---|---|']
    for item in result['contrasts']:
        effect=item['percent_effect']
        value=f"{effect['median']:+.2f}% [{effect['lower_95']:+.2f}, {effect['upper_95']:+.2f}]" if effect else 'Withheld: derived diagnostics'
        counts=lambda key:' / '.join(str(item[key][k]) for k in ('rows','units','buildings'))
        lines.append(f"| {item['field']} | {item['before']} → {item['after']} | {value} | {counts('support_before')} | {counts('support_after')} | {item['overlap']['buildings']} / {item['overlap']['units']} |")
    return '\n'.join(lines)+'\n'


def verify_contrast_dependencies(experiment, dataset, protocol, manifests):
    """Verify the math used here without requiring an unchanged sampling launcher.

    V4/v5 category contrasts only multiply archived beta draws by reconstructed
    design differences. Source, posterior and protocol bundles are already bound
    by build_report; every transitive design dependency and saved design is then
    independently checked by source reconstruction. No sampler is rerun here.
    """
    if protocol['version'] not in (checks.V4_EXPERIMENT,checks.V5_EXPERIMENT):
        return checks.verify_implementation(protocol), None
    from . import bayesian_source_sensitivity as verification
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1, user_api='blas'):
        reconstructed = verification.verify_design(experiment, dataset, protocol, manifests)
    return verification.reconstruction_dependencies(protocol)[1], reconstructed


def run(experiment,dataset,output):
    experiment,dataset,output=map(Path,(experiment,dataset,output))
    modules=(report,checks,checks.common,loader,feature)
    paths=[Path(module.__file__) for module in modules]+[Path(__file__)]
    code={path.name:digest(path) for path in paths}
    verified,manifests=report.build_report(experiment,dataset,top=1)
    protocol=json.loads((experiment/'protocol/protocol.json').read_text())
    frozen,reconstructed=verify_contrast_dependencies(experiment,dataset,protocol,manifests)
    _,source=_verified_bundle(dataset,retain={'observations.jsonl'})
    data=pd.DataFrame(report.jsonl(source['observations.jsonl']))
    data.period=pd.to_datetime(data.period);data.square_feet=pd.to_numeric(data.square_feet,errors='coerce')
    if protocol['version'] in (checks.V4_EXPERIMENT,checks.V5_EXPERIMENT):
        from . import bayesian_source_sensitivity as verification
        path=Path(verification.__file__);paths.append(path);code[path.name]=digest(path)
    design=loader.load_design(experiment/'fit',data,protocol)
    categories,contrasts,omitted=construct_contrasts(design,data)
    with xr.open_dataset(experiment/'fit/posterior.nc',group='posterior',engine='h5netcdf') as p:
        if (p.sizes.get('chain')!=protocol['chains'] or p.sizes.get('draw')!=protocol['draws']
                or p['beta'].dims!=('chain','draw','feature') or p.feature.values.tolist()!=design.features):
            raise ValueError('Posterior beta dimensions or coordinate order differ from protocol/design')
        # Load only beta: all joint draws, without materializing unit or building posterior.
        beta=p['beta'].load().values
    results,diagnostics=calculate(beta,contrasts)
    result={'version':VERSION,'protocol_sha256':verified['protocol_sha256'],
            'source_observations_sha256':verified['source_observations_sha256'],
            'bindings':{kind:digest(path/'complete.json') for kind,path in
                        [('fit',experiment/'fit'),('protocol',experiment/'protocol'),('source',dataset)]},
            'posterior_sha256':manifests['fit_manifest']['files']['posterior.nc'],
            'chains':protocol['chains'],'draws_per_chain':protocol['draws'],'all_joint_beta_draws':True,
            'design_features':design.features,'categories':categories,'contrasts':results,'omitted':omitted,
            'design_reconstruction':reconstructed,
            'highlight_ids':[r['id'] for r in results if r['highlight']],
            'status':'all_supported_contrasts_converged' if all(r['diagnostics']['acceptable'] for r in results) else 'some_intervals_withheld',
            'limitations':LIMITATIONS,'implementation_sha256':code,
            'versions':{name:importlib.metadata.version(name) for name in ('numpy','pandas','arviz','xarray','h5netcdf')},
            'main_model_changed':False}
    if any(digest(p)!=code[p.name] for p in paths) or any(digest(p)!=protocol['implementation_sha256'][p.name] for p in frozen):
        raise ValueError('Implementation changed during contrast computation')
    publish_bundle(output,{'contrasts.json':canonical(result)+'\n','contrasts.md':markdown(result),
                           'derived-diagnostics.csv':diagnostics.to_csv(index_label='contrast'),
                           **{p.name:p.read_text() for p in paths}},
                   {'version':VERSION,'protocol_sha256':verified['protocol_sha256']})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.experiment,args.dataset,args.output)
    print(canonical({'status':result['status'],'contrasts':len(result['contrasts']),'output':str(args.output)}))

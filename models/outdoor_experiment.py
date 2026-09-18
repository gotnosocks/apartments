"""Matched outdoor-type contributions conditional on the interior research model."""
from __future__ import annotations

import argparse
from datetime import datetime,UTC
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import outdoor_evidence,pricing,corrections,research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from . import outdoor_model,interior_model,minimal_rent_model as baseline,amenity_rent_model,amenity_ablation
from . import outdoor_feature_audit

VERSION='advertised-outdoor-types-experiment-v1'
VARIANTS=('interior','reporting','types')
FIELDS=('private_outdoor_category','shared_outdoor_category')
SETTINGS_GRID={'standard':amenity_rent_model.SETTINGS,
 'weaker_groups':{**amenity_rent_model.SETTINGS,'building_penalty':2.,'unit_penalty':2.},
 'stronger_groups':{**amenity_rent_model.SETTINGS,'building_penalty':50.,'unit_penalty':40.}}


def records(data):return [json.loads(s) for s in data.decode().split('\n') if s.strip()]


def prepare(interior_dataset,outdoor_audit,output):
    dm,df=_verified_bundle(interior_dataset,retain={'observations.jsonl'})
    am,af=_verified_bundle(outdoor_audit,retain={'categories.jsonl'})
    if dm.get('dataset_version')!='advertised-interior-claims-v1' or am['dataset_manifest']!=dm['parent_dataset_manifest']:
        raise ValueError('Interior and outdoor evidence must bind the identical base cohort')
    rows=records(df['observations.jsonl']);categories=records(af['categories.jsonl'])
    by_id={r['audit_id']:r for r in categories}
    if len(by_id)!=len(categories) or len(rows)!=len(categories) or set(by_id)!={r['audit_id'] for r in rows}:
        raise ValueError('Outdoor category membership differs from interior cohort')
    enriched=[]
    for row in rows:
        cat=by_id[row['audit_id']]
        if cat['unit_id']!=row['unit_id'] or cat['source_listing_id']!=str(row['source_listing_id']):
            raise ValueError('Outdoor analytical identity mismatch')
        if any(field in row for field in FIELDS):raise ValueError('Already enriched outdoor rows')
        enriched.append({**row,**{field:cat[field] for field in FIELDS}})
    previous=_verified_bundle(output)[0] if (Path(output)/'complete.json').exists() else None
    interpreted_at=previous['interpreted_at'] if previous else datetime.now(UTC).isoformat()
    if corrections.instant(interpreted_at)>datetime.now(UTC):raise ValueError('Future interpretation clock')
    return publish_bundle(output,{'observations.jsonl':''.join(canonical(r)+'\n' for r in enriched),
        'support.json':canonical(am['report']['support'])+'\n'},
        {'version':VERSION,'dataset_version':'advertised-outdoor-types-v1','interior_manifest':dm,
         'outdoor_audit_manifest':am,'rows':len(rows),'interpreted_at':interpreted_at,
         'implementation_sha256':digest(__file__),
         'interpretation':'Same-advertisement union of positive reported structured outdoor types. Missing is unknown; unlisted types are not asserted absent; text areas not modeled.'})


def run(dataset,review,output,settings_grid=None):
    dm,df=_verified_bundle(dataset,retain={'observations.jsonl'})
    rm,rf=_verified_bundle(review,retain={'review.json'})
    if (dm.get('dataset_version')!='advertised-outdoor-types-v1' or rm.get('dataset_manifest')!=dm
        or json.loads(rf['review.json']).get('decision')!='proceed_exploratory'):
        raise ValueError('Verified dataset and matching source review required')
    rows=records(df['observations.jsonl']);train=pd.DataFrame(rows)
    train['period']=pd.to_datetime(train.period);train['log_rent']=np.log(train.asking_rent)
    if len(rows)<100 or train.duplicated(['unit_id','period']).any():raise ValueError('Insufficient or duplicate observations')
    grid=SETTINGS_GRID if settings_grid is None else settings_grid
    if not grid:raise ValueError('At least one matched settings configuration required')
    paths=[Path(m.__file__) for m in (outdoor_model,interior_model,baseline,amenity_rent_model,amenity_ablation,
        outdoor_evidence,outdoor_feature_audit,pricing,corrections,research_pipeline)]+[Path(__file__)]
    hashes={p.name:digest(p) for p in paths}
    protocol={'version':VERSION,'dataset_manifest':dm,'review_manifest':rm,'settings_grid':grid,'variants':list(VARIANTS),
        'iterations':20,'unit_effect':True,'implementation_sha256':hashes,
        'versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy')},
        'purpose':'Same-row residuals and conditional advertised-type contrasts; isolate values from reporting and vary group shrinkage. No physical absent-outdoor inference.'}
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**{p.name:p.read_text() for p in paths}},
                       {'version':VERSION,'protocol_sha256':ph})
        summaries=[];current=train.analysis_price_basis.eq('current_capture_gross_ask').to_numpy()
        for name,settings in grid.items():
            predictions={};results={}
            for variant in VARIANTS:
                target=root/name/variant
                if (target/'complete.json').exists():
                    fm,ff=_verified_bundle(target,retain={'model.json','result.json','log-fitted.json'})
                    if fm['protocol_sha256']!=ph:raise ValueError('Fit protocol differs')
                    fitted=outdoor_model.load_saved(json.loads(ff['model.json']))
                    pred=np.array(json.loads(ff['log-fitted.json']));result=json.loads(ff['result.json'])
                    if not np.allclose(pred,baseline.predict(fitted,train),rtol=0,atol=1e-11):raise ValueError('Saved coefficients disagree')
                else:
                    print(canonical({'phase':'fitting','settings':name,'variant':variant,'rows':len(rows)}),flush=True)
                    fitted=baseline.fit(train,settings,iterations=20,encoder_class=outdoor_model.encoder_class(variant))
                    change=fitted['robust_objective_relative_change']
                    if change is None or not np.isfinite(change) or change>1e-5:raise ValueError('Outdoor fit did not converge')
                    pred=baseline.predict(fitted,train)
                    saved={'encoder':fitted['encoder'].metadata(),'beta':fitted['beta'].tolist(),'center':fitted['center']}
                    replay=baseline.predict(outdoor_model.load_saved(saved),train)
                    if not np.allclose(pred,replay,rtol=0,atol=1e-11):raise ValueError('Saved model parity failed')
                    result={'metrics':baseline.metrics(train,pred),
                        'current_metrics':baseline.metrics(train[current],pred[current]) if current.any() else None,
                        'interior_contrasts':interior_model.contribution_contrasts(fitted),
                        'outdoor_contrasts':outdoor_model.category_contrasts(fitted),
                        'objective_relative_change':change,'solves':fitted['solves'],
                        'serialization_maximum_log_difference':float(max(abs(pred-replay)))}
                    publish_bundle(target,{'model.json':canonical(saved)+'\n','result.json':canonical(result)+'\n',
                        'log-fitted.json':canonical(pred.tolist())+'\n'},
                        {'version':VERSION,'protocol_sha256':ph,'variant':variant,'settings':name})
                if len(pred)!=len(rows) or not np.isfinite(pred).all():raise ValueError('Invalid fitted values')
                predictions[variant]=pred;results[variant]=result
            compared={}
            for reference in ('interior','reporting'):
                changes=np.exp(predictions['types'])-np.exp(predictions[reference])
                compared['types_minus_'+reference]={'median_absolute_fitted_change_dollars':float(np.median(abs(changes))),
                    'maximum_absolute_fitted_change_dollars':float(max(abs(changes))),
                    'mean_absolute_log_residual_change':float(np.mean(abs(train.log_rent-predictions['types'])-abs(train.log_rent-predictions[reference])))}
            table=[{k:r[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent','analysis_price_basis',*interior_model.FIELDS,*FIELDS)} |
                   {variant+'_fitted_rent':float(np.exp(predictions[variant][i])) for variant in VARIANTS} for i,r in enumerate(rows)]
            summary={'settings':name,'results':results,'comparisons':compared}
            publish_bundle(root/name/'comparison',{'result.json':canonical(summary)+'\n',
                'fitted-values.jsonl':''.join(canonical(r)+'\n' for r in table)}, {'version':VERSION,'protocol_sha256':ph})
            summaries.append(summary)
        if any(digest(p)!=hashes[p.name] for p in paths):raise ValueError('Implementation changed during experiment')
        return publish_bundle(root/'summary',{'results.json':canonical(summaries)+'\n'},
            {'version':VERSION,'protocol_sha256':ph,'rows':len(rows),'fits':len(grid)*len(VARIANTS)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');f=sub.add_parser('fit')
    for key in ('interior-dataset','outdoor-audit','output'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('dataset','review','output'):f.add_argument('--'+key,type=Path,required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    result=prepare(**args) if command=='prepare' else run(**args)
    print(canonical({'version':result['version'],'rows':result['rows']}))

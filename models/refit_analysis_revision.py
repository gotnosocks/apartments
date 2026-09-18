"""Apply an explicit cohort decision bundle and compare a same-specification refit."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime,UTC
import fcntl
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import robust_pricing,pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from . import amenity_ablation as ablation,amenity_rent_model as amenities,minimal_rent_model as baseline
from . import amenity_ablation_contrasts as contrasts

VERSION='reviewed-analysis-cohort-refit-v2'


def apply_decisions(rows,decisions):
    by_id={row['audit_id']:row for row in rows}
    if len(by_id)!=len(rows):
        raise ValueError('Duplicate analytical observation identity')
    edits={}
    for edit in decisions:
        key=edit['audit_id']
        if key not in by_id or key in edits or edit.get('action')!='quarantine':
            raise ValueError('Unknown/duplicate observation or unsupported decision action')
        row=by_id[key]
        if (edit.get('source_listing_id')!=str(row['source_listing_id']) or not edit.get('reasons')
                or not edit.get('evidence') or not edit.get('author')):
            raise ValueError('Decision lacks matching identity, reasons, evidence or author')
        edits[key]=edit
    return [r for r in rows if r['audit_id'] not in edits], [
        {'record':row,'decision':edits[row['audit_id']]} for row in rows if row['audit_id'] in edits]


def category_contrasts(model):
    enc=model.encoder;start=enc['offsets']['amenities'][0]
    result=[]
    for field,before,after in contrasts.CONTRASTS:
        levels=enc['amenity_categories'][field]
        item={'field':field,'before':before,'after':after}
        if before not in levels or after not in levels:
            result.append({**item,'status':'unsupported'});continue
        index={name:i for i,name in enumerate(enc['amenity_features'])}
        change=model.beta[start+index[f'{field}={after}']]-model.beta[start+index[f'{field}={before}']]
        result.append({**item,'status':'computed','log_change':change,'percent_change':float(100*np.expm1(change)),
            'training_counts':{value:enc['amenity_category_counts'][field][value] for value in (before,after)}})
    return result


def run(parent_model,dataset,decision_bundle,output):
    parent=robust_pricing.RobustPricingModel.load(parent_model)
    source,files=_verified_bundle(dataset,retain={'observations.jsonl'})
    decision_manifest,decision_files=_verified_bundle(decision_bundle,retain={'decisions.jsonl'})
    if source!=parent.artifact['training']['source_manifest'] or decision_manifest.get('dataset_manifest')!=source:
        raise ValueError('Parent model, dataset and decisions must bind the same cohort')
    if pricing._timestamp(decision_manifest['recorded_at'])>datetime.now(UTC):
        raise ValueError('Review decision knowledge timestamp is in the future')
    rows=[json.loads(s) for s in files['observations.jsonl'].decode().split('\n') if s.strip()]
    decisions=[json.loads(s) for s in decision_files['decisions.jsonl'].decode().split('\n') if s.strip()]
    kept,quarantined=apply_decisions(rows,decisions)
    if not quarantined:
        raise ValueError('No cohort revision supplied')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        revised=publish_bundle(root/'dataset',{
            'observations.jsonl':''.join(canonical(r)+'\n' for r in kept),
            'quarantined.jsonl':''.join(canonical(r)+'\n' for r in quarantined)},
            {**{k:v for k,v in source.items() if k not in ('files','historical_rows','current_rows')},
             'parent_dataset_manifest':source,'decision_manifest':decision_manifest,
             'as_of':max(source['as_of'],decision_manifest['recorded_at'],key=pricing._timestamp),
             'historical_rows':sum(r['analysis_price_basis']=='historical_initial_own_advertisement_ask' for r in kept),
             'current_rows':sum(r['analysis_price_basis']=='current_capture_gross_ask' for r in kept),
             'quarantined_rows':len(quarantined),
             'revision_knowledge_at':decision_manifest['recorded_at']})
        train=pd.DataFrame(kept);train['period']=pd.to_datetime(train.period)
        train['log_rent']=np.log(train.asking_rent)
        if len(train)<100 or train.period.nunique()<24:
            raise ValueError('Insufficient retained cohort')
        paths=[Path(m.__file__) for m in (ablation,amenities,baseline,contrasts,robust_pricing,pricing)]+[Path(__file__)]
        protocol={'version':VERSION,'parent_model_manifest':parent.manifest,'dataset_manifest':revised,
            'decision_manifest':decision_manifest,'settings':amenities.SETTINGS,'iterations':20,'unit_effect':True,
            'implementation_sha256':{p.name:digest(p) for p in paths}}
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**{p.name:p.read_text() for p in paths}},
            {'version':VERSION,'protocol_sha256':ph})
        if (root/'model/complete.json').exists():
            model=robust_pricing.RobustPricingModel.load(root/'model')
            if model.manifest.get('revision_protocol_sha256')!=ph:
                raise ValueError('Revision fit protocol differs')
        else:
            fitted=baseline.fit(train,amenities.SETTINGS,iterations=20,encoder_class=ablation.encoder_class('full'))
            change=fitted['robust_objective_relative_change']
            if change is None or not np.isfinite(change) or change>1e-5:
                raise ValueError('Revision optimizer did not converge')
            artifact=deepcopy(parent.artifact)
            artifact.update(encoder=fitted['encoder'].metadata(),coefficients=fitted['beta'].tolist(),center=fitted['center'])
            training=artifact['training'];current=[r for r in kept if r['analysis_price_basis']=='current_capture_gross_ask']
            training.update(rows=len(train),units=int(train.unit_id.nunique()),buildings=int(train.building.nunique()),
                start_month=str(train.period.min().date()),end_month=str(train.period.max().date()),
                latest_evidence_known_at=max((r['known_at'] for r in kept),key=pricing._timestamp),
                source_manifest=revised,membership_sha256=contrasts.membership(train[['unit_id','period','audit_id']]),
                knowledge_cutoff=max(training['knowledge_cutoff'],decision_manifest['recorded_at'],key=pricing._timestamp),
                unit_buildings=dict(train[['unit_id','building']].drop_duplicates().itertuples(index=False,name=None)),
                source_listing_ids=sorted(set(train.source_listing_id.astype(str))),
                current_capture_ids=sorted(str(r['capture_id']) for r in current),
                current_source_listing_ids=sorted(str(r['source_listing_id']) for r in current),
                layout_support={key:{str(float(v)):int(n) for v,n in train[key].value_counts().items()} for key in ('bedrooms','bathrooms')})
            artifact['analysis'].update(current_rows=len(current),historical_rows=len(kept)-len(current),
                revision='Explicit source-evidenced quarantine decisions; raw and parent data preserved.')
            artifact['limitations'].append('The cohort revision was informed by residual/source review; comparisons are descriptive sensitivity, not independent validation.')
            artifact['published_at']=datetime.now(UTC).isoformat()
            model=robust_pricing.RobustPricingModel(artifact)
            expected=np.exp(baseline.predict(fitted,train))
            actual=np.array([model.predict(row,row['period'])['predicted_rent'] for row in kept])
            if not np.allclose(expected,actual,rtol=1e-11,atol=1e-8):
                raise ValueError('Portable revision differs from scientific encoder')
            publish_bundle(root/'model',{'model.json':canonical(artifact)+'\n',
                'diagnostics.json':canonical({'objective_relative_change':change,'solves':fitted['solves'],
                    'parity_rows':len(train),'maximum_absolute_difference':float(np.max(abs(actual-expected)))})+'\n'},
                {'model_version':robust_pricing.VERSION,'revision_protocol_sha256':ph,
                 'runtime_sha256':digest(robust_pricing.__file__),'pricing_features_sha256':digest(pricing.__file__)})
            model=robust_pricing.RobustPricingModel.load(root/'model')
        old=np.array([parent.predict(row,row['period'])['predicted_rent'] for row in kept])
        new=np.array([model.predict(row,row['period'])['predicted_rent'] for row in kept])
        current=train.analysis_price_basis.eq('current_capture_gross_ask').to_numpy()
        comparison={'retained_rows':len(kept),'quarantined_rows':len(quarantined),
            'matched_retained_cohort':{'parent':baseline.metrics(train,np.log(old)),'revised':baseline.metrics(train,np.log(new))},
            'current_captures':{'rows':int(current.sum()),'parent':baseline.metrics(train[current],np.log(old[current])) if current.any() else None,
                                'revised':baseline.metrics(train[current],np.log(new[current])) if current.any() else None},
            'factor_contrasts':{'parent':category_contrasts(parent),'revised':category_contrasts(model)},
            'fitted_value_change':{'median_absolute_dollars':float(np.median(abs(new-old))),
                'median_absolute_percent':float(np.median(abs(new/old-1))*100),'maximum_absolute_dollars':float(max(abs(new-old)))},
            'interpretation':'Matched retained-cohort descriptive sensitivity; dropping suspect rows is not counted as model performance improvement.'}
        if any(digest(p)!=protocol['implementation_sha256'][p.name] for p in paths):
            raise ValueError('Implementation changed during refit')
        return publish_bundle(root/'comparison',{'report.json':canonical(comparison)+'\n'},
            {'version':VERSION,'protocol_sha256':ph,'parent_model_manifest':parent.manifest,'revised_model_manifest':model.manifest})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('parent-model','dataset','decision-bundle','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    print(canonical(run(args.parent_model,args.dataset,args.decision_bundle,args.output)))

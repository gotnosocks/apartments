"""Refit historical evidence plus current captures for fitted-value analysis.

Current apartments are intentionally included. This is descriptive estimation,
not an out-of-sample forecast or a new prospective validation result.
"""
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

from apartments import candidate_search, pricing, robust_pricing, corrections, research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrasts
from . import amenity_rent_model as amenities
from . import minimal_rent_model as baseline

VERSION='capture-updated-robust-analysis-v1'


def _records(frame):
    return frame.astype(object).where(pd.notna(frame),None).to_dict('records')


def current_rows(rows, *, as_of, max_age_days):
    selected,excluded,selection=candidate_search.select_candidates(rows,as_of=as_of,max_age_days=max_age_days)
    accepted=[]
    for row in selected:
        bedrooms=pricing._number(row.get('bedrooms'));bathrooms=pricing._number(row.get('bathrooms'))
        if (bedrooms is None or not 0<=bedrooms<=5 or bedrooms%1 or bathrooms is None
                or not 1<=bathrooms<=5 or (bathrooms*2)%1 or not 750<=row['rent']<=50000):
            excluded.append({'record':row,'reason':'outside_analysis_rent_or_layout_support'});continue
        if robust_pricing.month(row['collected_at'])!=robust_pricing.month(as_of):
            excluded.append({'record':row,'reason':'capture_outside_current_analysis_month'});continue
        size=pricing._number(row.get('square_feet'))
        accepted.append({**row,'audit_id':'capture:'+row['capture_id'],'building':row['building_id'],
            'bedrooms':bedrooms,'bathrooms':bathrooms,'square_feet':size if size is not None and 150<=size<=6000 else None,
            'asking_rent':float(row['rent']),'log_rent':float(np.log(row['rent'])),
            'price_at':row['collected_at'],'analysis_price_basis':'current_capture_gross_ask',
            'listing_ids':json.dumps([str(row['source_listing_id'])])})
    return accepted,excluded,selection


def run(historical_dataset,current_snapshot,output,*,as_of,max_age_days=1):
    cutoff=pricing._timestamp(as_of);origin=robust_pricing.month(cutoff)
    if cutoff>datetime.now(UTC):
        raise ValueError('Analysis knowledge cutoff is still in the future')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        historical,history_manifest,coverage=amenities.load_analytical(historical_dataset)
        current_manifest,files=_verified_bundle(current_snapshot,retain={'candidates.jsonl'})
        if current_manifest.get('snapshot_version') not in ('bounded-refreshed-candidates-v1','canonical-candidate-captures-v1'):
            raise ValueError('Verified capture-time candidate snapshot required')
        if pricing._timestamp(history_manifest['as_of'])>cutoff:
            raise ValueError('Historical dataset knowledge is later than analysis cutoff')
        rows=[json.loads(s) for s in files['candidates.jsonl'].decode().splitlines() if s.strip()]
        fresh,excluded,selection=current_rows(rows,as_of=cutoff,max_age_days=max_age_days)
        if not fresh:
            raise ValueError('No eligible current-month captures to fit')
        # Earlier months retain their own-advertisement historical attributes.
        # Current attributes are never propagated backward to historical prices.
        historical=historical[historical.period<pd.Timestamp(origin.date())].copy()
        historical['analysis_price_basis']='historical_initial_own_advertisement_ask'
        current=pd.DataFrame(fresh);current['period']=pd.Timestamp(origin.date())
        train=pd.concat([historical,current],ignore_index=True).sort_values(['period','unit_id']).reset_index(drop=True)
        if len(train)<100 or train.period.nunique()<24:
            raise ValueError('At least 100 observations and 24 months required')
        if pd.to_datetime(train.known_at,utc=True).max()>cutoff:
            raise ValueError('Training evidence is later than analysis knowledge cutoff')
        if train.groupby('unit_id').building.nunique().gt(1).any() or train.duplicated(['unit_id','period']).any():
            raise ValueError('Conflicting unit/building identity or duplicate unit-month')
        serialized=train.copy();serialized['period']=serialized.period.dt.strftime('%Y-%m-%d')
        dataset_manifest=publish_bundle(root/'dataset',{
            'observations.jsonl':''.join(canonical(r)+'\n' for r in _records(serialized)),
            'current-excluded.jsonl':''.join(canonical(r)+'\n' for r in excluded)},
            {'dataset_version':'historical-plus-current-capture-analysis-v1','as_of':cutoff.isoformat(),
             'historical_manifest':history_manifest,'current_snapshot_manifest':current_manifest,
             'historical_rows':len(historical),'current_rows':len(current),'current_selection':selection,
             'target_contract':'Earlier months: initial own-advertisement gross asks. Current month: latest eligible ACTIVE capture gross asks, one row per unit. No backward attribute filling.'})
        paths=[Path(m.__file__) for m in (baseline,amenities,ablation,contrasts,pricing,robust_pricing,
               candidate_search,corrections,research_pipeline)]+[Path(__file__)]
        protocol={'version':VERSION,'dataset_manifest':dataset_manifest,'analysis_month':origin.strftime('%Y-%m'),
            'as_of':cutoff.isoformat(),'max_age_days':float(max_age_days),'settings':amenities.SETTINGS,
            'unit_effect':True,'iterations':20,'train_rows':len(train),
            'train_sha256':contrasts.membership(train[['unit_id','period','audit_id']]),
            'implementation_sha256':{p.name:digest(p) for p in paths},
            'versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','duckdb')},
            'purpose':'Refit-before-analysis: factor contrasts, fitted residuals and same-apartment counterfactuals.'}
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**{p.name:p.read_text() for p in paths}},
                       {'version':VERSION,'protocol_sha256':ph})
        if (root/'model'/'complete.json').exists():
            model=robust_pricing.RobustPricingModel.load(root/'model')
            if model.manifest.get('analysis_protocol_sha256')!=ph:
                raise ValueError('Analysis model has a different protocol')
            return model.manifest
        fitted=baseline.fit(train,amenities.SETTINGS,iterations=20,encoder_class=ablation.encoder_class('full'))
        change=fitted['robust_objective_relative_change']
        if change is None or not np.isfinite(change) or change>1e-5:
            raise ValueError('Analysis refit did not converge')
        artifact={'version':robust_pricing.VERSION,'encoder':fitted['encoder'].metadata(),
            'coefficients':fitted['beta'].tolist(),'center':fitted['center'],
            'training':{'start_month':str(train.period.min().date()),'end_month':str(train.period.max().date()),
                'rows':len(train),'units':int(train.unit_id.nunique()),'buildings':int(train.building.nunique()),
                'knowledge_cutoff':cutoff.isoformat(),'latest_evidence_known_at':str(train.known_at.max()),
                'source_manifest':dataset_manifest,'membership_sha256':protocol['train_sha256'],
                'unit_buildings':dict(train[['unit_id','building']].drop_duplicates().itertuples(index=False,name=None)),
                'source_listing_ids':sorted(set(train.source_listing_id.astype(str))),
                'current_capture_ids':sorted(current.capture_id.astype(str)),
                'current_source_listing_ids':sorted(current.source_listing_id.astype(str)),
                'layout_support':{key:{str(float(value)):int(count) for value,count in train[key].value_counts().items()}
                                  for key in ('bedrooms','bathrooms')}},
            'analysis':{'mode':'refit_current_evidence_then_analyze','month':origin.strftime('%Y-%m'),
                'current_rows':len(current),'historical_rows':len(historical),
                'target':'Gross advertised asks; historical initial asks plus current-month capture asks.',
                'in_sample_residuals':'Intentional fitted diagnostics; current asks contribute to this fit.'},
            'validation':{'mode':'Descriptive analysis refit, not a new out-of-sample evaluation.',
                'max_serving_horizon_months':0,'pricing_month':origin.strftime('%Y-%m')},
            'limitations':['Current capture coverage is the supplied bounded sample, not the whole Chelsea market.',
                'Historical initial asks and current capture asks have different sampling rules; price reductions may influence current residuals.',
                'Building and unit effects can absorb feature premiums; contrasts depend on shrinkage and available variation.',
                'Conditional fitted contrasts are not causal effects, physical feasibility claims or personal willingness to pay.',
                'Historical attributes were often collected later; unverified effective times remain a limitation.']}
        portable=robust_pricing.RobustPricingModel(artifact)
        expected=np.exp(baseline.predict(fitted,train))
        actual=np.array([portable.predict(row,row['period'])['predicted_rent'] for row in _records(serialized)])
        if not np.allclose(actual,expected,rtol=1e-11,atol=1e-8):
            raise ValueError('Portable fitted values differ from scientific encoder')
        diagnostics={'objective_relative_change':change,'solves':fitted['solves'],'historical_source_coverage':coverage,
            'parity_rows':len(train),'maximum_absolute_dollar_difference':float(np.max(abs(actual-expected))),
            'maximum_relative_difference':float(np.max(abs(actual/expected-1))),
            'in_sample':baseline.metrics(train,np.log(actual))}
        artifact['published_at']=datetime.now(UTC).isoformat()
        if any(digest(p)!=protocol['implementation_sha256'][p.name] for p in paths):
            raise ValueError('Implementation changed during analysis fit')
        return publish_bundle(root/'model',{'model.json':canonical(artifact)+'\n','diagnostics.json':canonical(diagnostics)+'\n'},
            {'model_version':robust_pricing.VERSION,'analysis_protocol_sha256':ph,
             'runtime_sha256':digest(robust_pricing.__file__),'pricing_features_sha256':digest(pricing.__file__)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-dataset',type=Path,required=True)
    parser.add_argument('--current-snapshot',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--as-of',required=True);parser.add_argument('--max-age-days',type=float,default=1)
    args=parser.parse_args()
    print(canonical(run(args.historical_dataset,args.current_snapshot,args.output,as_of=args.as_of,max_age_days=args.max_age_days)))

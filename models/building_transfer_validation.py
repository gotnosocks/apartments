"""Time-ordered prediction bands with disjoint fit/calibration/evaluation buildings.

These are empirical development bands, not conformal coverage guarantees. Every
fold excludes its calibration and evaluation buildings from every point-model fit.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import corrections, research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrasts
from . import amenity_rent_model as amenities
from . import minimal_rent_model as baseline

VERSION='building-transfer-monthly-v1'
POLICIES=('row_weighted','building_balanced')
LEVELS=(80,95)


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def records(frame):
    return frame.astype(object).where(pd.notna(frame),None).to_dict('records')


def quantile(values, weights, probabilities):
    """Left-continuous inverse weighted empirical CDF, with no interpolation."""
    values=np.asarray(values,dtype=float);weights=np.asarray(weights,dtype=float)
    if len(values)==0 or values.shape!=weights.shape or not np.isfinite(values).all() or not np.isfinite(weights).all() or (weights<=0).any():
        raise ValueError('Finite residuals and positive weights required')
    probabilities=np.asarray(probabilities,dtype=float)
    if not np.isfinite(probabilities).all() or ((probabilities<0)|(probabilities>1)).any():
        raise ValueError('Probabilities must be between zero and one')
    order=np.argsort(values,kind='stable');cdf=np.cumsum(weights[order])/weights.sum()
    return values[order[np.minimum(np.searchsorted(cdf,probabilities,side='left'),len(values)-1)]].tolist()


def rules(history, origin, *, calibration_fold, min_rows=100, min_buildings=30, min_months=6):
    """No current/future target, evaluation building or training residual admitted."""
    selected=history.copy()
    if not selected.empty:
        if not selected.building.map(ablation.building_fold).eq(calibration_fold).all():
            raise ValueError('Calibration contains a building outside its reserved fold')
        dates=pd.to_datetime(selected.period)
        selected=selected[(dates<origin)&(dates>=origin-pd.DateOffset(months=12))].copy()
    counts={'rows':len(selected),'buildings':0 if selected.empty else int(selected.building.nunique()),
            'months':0 if selected.empty else int(selected.period.nunique())}
    if counts['rows']<min_rows or counts['buildings']<min_buildings or counts['months']<min_months:
        return {policy:{'status':'unavailable',**counts} for policy in POLICIES}
    residual=np.log(selected.asking_rent/selected.prediction).to_numpy()
    output={}
    for policy in POLICIES:
        weights=np.ones(len(selected)) if policy=='row_weighted' else 1/selected.groupby('building').building.transform('size').to_numpy()
        output[policy]={'status':'estimated',**counts,'start':str(selected.period.min()),'end':str(selected.period.max()),
            'quantiles':{str(level):quantile(residual,weights,[(1-level/100)/2,(1+level/100)/2]) for level in LEVELS}}
    return output


def add_bands(table, rule):
    table=table.copy()
    for policy in POLICIES:
        for level in LEVELS:
            for index,side in enumerate(('lower','upper')):
                table[f'{policy}_{level}_{side}']=(table.prediction*np.exp(rule[policy]['quantiles'][str(level)][index])
                    if rule[policy]['status']=='estimated' else np.nan)
    return table


def score(table):
    result={'rows':len(table),'buildings':int(table.building.nunique()),'intervals':{}}
    if not len(table):
        return result
    result['point']=baseline.metrics(table,np.log(table.prediction.to_numpy()))
    for policy in POLICIES:
        result['intervals'][policy]={}
        for level in LEVELS:
            lo=table[f'{policy}_{level}_lower'];hi=table[f'{policy}_{level}_upper'];has=lo.notna()&hi.notna()
            item={'available_rows':int(has.sum()),'unavailable_rows':int((~has).sum())}
            if has.any():
                actual=table.loc[has,'asking_rent'];lower=lo[has];upper=hi[has]
                covered=(lower<=actual)&(actual<=upper);width=upper-lower
                building=table.loc[has,'building'];balanced=covered.groupby(building).mean()
                item.update(coverage_percent=float(100*covered.mean()),
                    equal_building_coverage_percent=float(100*balanced.mean()),
                    buildings=int(building.nunique()),below_percent=float(100*(actual<lower).mean()),
                    above_percent=float(100*(actual>upper).mean()),median_width_dollars=float(width.median()),
                    median_width_percent_of_prediction=float(100*(width/table.loc[has,'prediction']).median()),
                    mean_interval_score_dollars=float((width+2/(1-level/100)*((lower-actual).clip(lower=0)+(actual-upper).clip(lower=0))).mean()))
            result['intervals'][policy][str(level)]=item
    return result


def partition(data, origin, fold):
    assignment=data['_building_fold'] if '_building_fold' in data else data.building.map(ablation.building_fold)
    calibration=(fold+1)%5
    train=data[(~assignment.isin((fold,calibration)))&(data.period<origin)]
    current=data.period.eq(origin)
    cal=data[current&assignment.eq(calibration)]
    test=data[current&assignment.eq(fold)]
    return train,cal,test


def _binding_check(manifest,binding):
    if any(manifest.get(k)!=v for k,v in binding.items()):
        raise ValueError('Fold/month membership or dependency mismatch')


def _check_table(table,expected):
    for key in ('audit_id','unit_id','building','asking_rent'):
        if table[key].tolist()!=expected[key].tolist():
            raise ValueError('Saved predictions differ from declared membership/targets')
    if table.period.tolist()!=expected.period.dt.strftime('%Y-%m-%d').tolist():
        raise ValueError('Saved prediction months differ')
    if not np.isfinite(table.prediction).all() or not (table.prediction>0).all():
        raise ValueError('Invalid saved prediction')


def _point_table(fitted,table,first_period):
    result=table[['unit_id','building','audit_id','period','asking_rent']].copy().reset_index(drop=True)
    result['natural_new_building']=result.period.eq(result.building.map(first_period))
    result['period']=result.period.dt.strftime('%Y-%m-%d')
    result['prediction']=np.exp(baseline.predict(fitted,table))
    if not np.isfinite(result.prediction).all() or not (result.prediction>0).all():
        raise ValueError('Invalid point prediction')
    return result


def run(dataset,output,*,start_year=2019,end_year=2024,folds=(0,1,2,3,4),
        min_rows=100,min_buildings=30,min_months=6,prepare_only=False,max_new_months=None):
    if not 2012<=start_year<=end_year<=2024:
        raise ValueError('Choose development evaluation years within 2012–2024')
    if len(set(folds))!=len(folds) or any(f not in range(5) for f in folds):
        raise ValueError('Invalid worker folds')
    if min(min_rows,min_buildings,min_months)<1 or (max_new_months is not None and max_new_months<1):
        raise ValueError('Positive support and work limits required')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    data,source,coverage=amenities.load_analytical(dataset)
    data=data[data.period<f'{end_year+1}-01-01'].copy()
    data['_building_fold']=data.building.map(ablation.building_fold)
    first_period=data.groupby('building').period.min()
    origins=pd.date_range(f'{start_year-1}-01-01',f'{end_year}-12-01',freq='MS')
    splits=[]
    for fold in range(5):
        for origin in origins:
            train,cal,test=partition(data,origin,fold)
            if min(len(train),len(cal),len(test))<1:
                raise ValueError('Empty fit/calibration/evaluation partition')
            splits.append({'fold':fold,'month':str(origin.date()),'calibration_fold':(fold+1)%5,
                'train_end':str(train.period.max().date()),
                **{name+'_rows':len(frame) for name,frame in [('train',train),('calibration',cal),('test',test)]},
                **{name+'_sha256':contrasts.membership(frame) for name,frame in [('train',train),('calibration',cal),('test',test)]}})
    paths=[Path(m.__file__) for m in (ablation,contrasts,amenities,baseline,amenities.pricing,corrections,research_pipeline)]+[Path(__file__)]
    code={p.name:p.read_text() for p in paths}
    protocol={'version':VERSION,'source_manifest':source,'coverage':coverage,'splits':splits,
        'start_year':start_year,'end_year':end_year,'settings':amenities.SETTINGS,'unit_effect':True,
        'iterations':20,'convergence_threshold':1e-5,'min_rows':min_rows,'min_buildings':min_buildings,'min_months':min_months,
        'fold_assignment':'Existing SHA256(building_id) first eight hex digits modulo five; no seed selection.',
        'partition':'Evaluation fold j, calibration fold (j+1)%5, training other three folds at strictly earlier price months.',
        'calibration':'Prior 12 months of held-out calibration-building one-month-ahead log(actual/prediction); no evaluation targets; no sparse fallback.',
        'policies':list(POLICIES),'quantile':'Inverse empirical CDF: equal row mass or equal total mass per building, evenly divided among its rows.',
        'levels':list(LEVELS),'warmup_year':start_year-1,
        'implementation_sha256':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in code.items()},
        'versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','duckdb')},
        'interpretation':'Retrospective development with later-collected attributes; no exchangeability, conformal, prospective, causal or serving-calibration claim.'}
    ph=_hash(protocol)
    publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**code},{'version':VERSION,'protocol_sha256':ph})
    if prepare_only:
        return {'phase':'prepared','fits':len(splits),'protocol_sha256':ph}
    new_months=0
    for fold in folds:
        foldroot=root/f'fold-{fold}';foldroot.mkdir(exist_ok=True)
        with (foldroot/'.run.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            history=pd.DataFrame();evaluations=[];chain=[];month_reports=[]
            for origin,split in zip(origins,[s for s in splits if s['fold']==fold]):
                directory=foldroot/origin.strftime('%Y-%m')
                train,cal,test=partition(data,origin,fold)
                binding={'version':VERSION,'protocol_sha256':ph,**split}
                if (directory/'fit'/'complete.json').exists():
                    fitmanifest,files=_verified_bundle(directory/'fit',retain={'diagnostics.json','calibration.jsonl','test.jsonl'})
                    _binding_check(fitmanifest,binding)
                    diagnostic=json.loads(files['diagnostics.json'])
                    caltable=pd.DataFrame(json.loads(s) for s in files['calibration.jsonl'].decode().splitlines())
                    testtable=pd.DataFrame(json.loads(s) for s in files['test.jsonl'].decode().splitlines())
                    _check_table(caltable,cal);_check_table(testtable,test)
                else:
                    print(canonical({'phase':'fitting','fold':fold,'month':origin.strftime('%Y-%m'),'train':len(train),'calibration':len(cal),'test':len(test)}),flush=True)
                    fitted=baseline.fit(train,amenities.SETTINGS,iterations=20,encoder_class=ablation.encoder_class('full'))
                    change=fitted['robust_objective_relative_change']
                    if change is None or not np.isfinite(change) or change>1e-5:
                        raise ValueError('Building-transfer fit did not converge')
                    diagnostic={'objective_relative_change':change,'solves':fitted['solves']}
                    caltable=_point_table(fitted,cal,first_period);testtable=_point_table(fitted,test,first_period)
                    saved={'amenities':{'encoder':fitted['encoder'].metadata(),'beta':fitted['beta'].tolist(),'center':fitted['center']}}
                    fitmanifest=publish_bundle(directory/'fit',{'models.json':canonical(saved)+'\n',
                        'diagnostics.json':canonical(diagnostic)+'\n',
                        'calibration.jsonl':''.join(canonical(r)+'\n' for r in records(caltable)),
                        'test.jsonl':''.join(canonical(r)+'\n' for r in records(testtable))},binding)
                if not np.isfinite(diagnostic['objective_relative_change']) or diagnostic['objective_relative_change']>1e-5:
                    raise ValueError('Saved fit did not converge')
                dependencies={**binding,'fit_manifest_sha256':_hash(fitmanifest),'prior_forecast_chain_sha256':_hash(chain)}
                rule=rules(history,origin,calibration_fold=(fold+1)%5,min_rows=min_rows,min_buildings=min_buildings,min_months=min_months)
                table=add_bands(testtable,rule)
                report={'fold':fold,'month':origin.strftime('%Y-%m'),'warmup':origin.year<start_year,'rules':rule,'metrics':score(table)}
                # Recompute inexpensive calibration even on replay. This verifies that
                # saved intervals still follow the exact earlier calibration chain.
                was_done=(directory/'forecast'/'complete.json').exists()
                forecast=publish_bundle(directory/'forecast',{'predictions.jsonl':''.join(canonical(r)+'\n' for r in records(table)),
                    'report.json':canonical(report)+'\n'},dependencies)
                new_months+=not was_done
                chain.append(_hash(forecast));history=pd.concat([history,caltable],ignore_index=True)
                if origin.year>=start_year:
                    evaluations.append(table);month_reports.append(report)
                (foldroot/'progress.json').write_text(canonical({'phase':'running','completed_months':len(chain),'total_months':len(origins),'last_month':str(origin.date())})+'\n')
                if max_new_months is not None and new_months>=max_new_months:
                    return {'phase':'paused_at_declared_limit','fold':fold,'completed_months':len(chain)}
            if any(digest(p)!=protocol['implementation_sha256'][p.name] for p in paths):
                raise ValueError('Implementation changed during building-transfer validation')
            evaluation=pd.concat(evaluations,ignore_index=True)
            report={'fold':fold,'months':month_reports,'pooled':score(evaluation),
                    'natural_new_building':score(evaluation[evaluation.natural_new_building])}
            publish_bundle(foldroot/'summary',{'report.json':canonical(report)+'\n',
                'predictions.jsonl':''.join(canonical(r)+'\n' for r in records(evaluation))},
                {'version':VERSION,'protocol_sha256':ph,'forecast_chain_sha256':_hash(chain)})
            (foldroot/'progress.json').write_text(canonical({'phase':'complete','completed_months':len(chain),'total_months':len(origins)})+'\n')
    complete=[fold for fold in range(5) if (root/f'fold-{fold}'/'summary'/'complete.json').exists()]
    if len(complete)<5:
        return {'phase':'partial','completed_folds':complete,'protocol_sha256':ph}
    tables=[];reports=[];manifests=[]
    for fold in range(5):
        manifest,files=_verified_bundle(root/f'fold-{fold}'/'summary',retain={'predictions.jsonl','report.json'})
        _binding_check(manifest,{'version':VERSION,'protocol_sha256':ph})
        tables.append(pd.DataFrame(json.loads(s) for s in files['predictions.jsonl'].decode().splitlines()))
        reports.append(json.loads(files['report.json']));manifests.append(_hash(manifest))
    table=pd.concat(tables,ignore_index=True)
    expected=data[(data.period>=f'{start_year}-01-01')&(data.period<f'{end_year+1}-01-01')]
    if table.audit_id.duplicated().any() or set(table.audit_id)!=set(expected.audit_id):
        raise ValueError('Five-fold evaluation rows do not match the source cohort exactly once')
    report={'version':VERSION,'fits':len(splits),'folds':reports,'pooled':score(table),
        'natural_new_building':score(table[table.natural_new_building]),
        'years':{str(year):score(table[table.period.str.startswith(str(year))]) for year in range(start_year,end_year+1)},
        'natural_new_building_years':{str(year):score(table[table.natural_new_building&table.period.str.startswith(str(year))]) for year in range(start_year,end_year+1)},
        'limitations':['All evaluation and calibration buildings excluded from each corresponding point-model training set.',
            'Calibration and evaluation folds rotate; pooled errors are dependent across folds and buildings.',
            'Only three building folds train each model. This does not directly calibrate the existing full-data serving fit.',
            'Balanced calibration weights choose a building-uniform target distribution, not a guarantee of conditional coverage.',
            'Natural new-building subset is defined by first observed price month in this archive, not construction date.',
            'Later-collected attributes and reused development years; no historical information-set or prospective final-test claim.',
            'No automatic promotion of these empirical bands to serving.']}
    return publish_bundle(root/'summary',{'report.json':canonical(report)+'\n'},
        {'version':VERSION,'protocol_sha256':ph,'fold_summary_sha256':manifests})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start-year',type=int,default=2019);parser.add_argument('--end-year',type=int,default=2024)
    parser.add_argument('--folds',type=int,nargs='*',default=[0,1,2,3,4])
    parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--max-new-months',type=int)
    args=parser.parse_args()
    print(canonical(run(args.dataset,args.output,start_year=args.start_year,end_year=args.end_year,folds=tuple(args.folds),
                        prepare_only=args.prepare_only,max_new_months=args.max_new_months)))

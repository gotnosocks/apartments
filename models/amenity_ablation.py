"""Frozen, matched-sample checks of amenities versus missingness patterns."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from . import amenity_rent_model as model
from . import minimal_rent_model as baseline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'chelsea-amenity-ablation-v2'
BLOCKS = {'laundry':('laundry_type',),'doorman':('doorman_type',),
          'hvac':('hvac_type',),'pets':('pet_rules',),
          'vertical':('listed_floor','physical_floor','elevator','physical_floor_x_elevator','floor_label_gap'),
          'exposures':('window_exposures','view_exposures')}
VARIANTS = ('baseline','missingness','full',*BLOCKS)


def encoder_class(variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown ablation variant')
    if variant == 'baseline':
        return baseline.Encoder

    class MaskedEncoder(model.AmenityEncoder):
        def __init__(self, train, unit_effect=True):
            super().__init__(train,unit_effect)
            self.ablation_variant = variant
            self.amenity_category_centers = {}
            for field, counts in self.amenity_category_counts.items():
                known = {value: count for value, count in counts.items() if value != '__unknown__'}
                total = sum(known.values())
                self.amenity_category_centers[field] = {value: count/total for value, count in known.items()}
            def enabled(name):
                if variant == 'full' or name.endswith('.unknown') or name.endswith('=__unknown__'):
                    return True
                field = name.split('=',1)[0].split('.',1)[0]
                return field in BLOCKS.get(variant,())
            self.amenity_active_columns = [enabled(name) for name in self.amenity_features]
    return MaskedEncoder


def building_fold(building):
    # Preserve the already-declared development fold assignment, now covering all five.
    return int(hashlib.sha256(str(building).encode()).hexdigest()[:8],16)%5


def split_data(data, *, years, folds, cross_years):
    for year in years:
        yield f'year-{year}',data[data.period < f'{year}-01-01'],data[(data.period >= f'{year}-01-01')&(data.period < f'{year+1}-01-01')]
    assignment = data.building.map(building_fold)
    for fold in folds:
        yield f'building-{fold}',data[assignment.ne(fold)],data[assignment.eq(fold)]
    for year in cross_years:
        for fold in folds:
            train = data[assignment.ne(fold)&data.period.lt(f'{year}-01-01')]
            test = data[assignment.eq(fold)&data.period.ge(f'{year}-01-01')&data.period.lt(f'{year+1}-01-01')]
            yield f'year-{year}-building-{fold}',train,test


def run(dataset,output,*,years=(),folds=(0,1,2,3,4),cross_years=(),
        variants=('baseline','missingness','full'),unit_effect=True,min_rows=100):
    if not variants or any(v not in VARIANTS for v in variants) or len(set(variants)) != len(variants):
        raise ValueError('Choose distinct supported variants')
    if not {'baseline','missingness','full'} <= set(variants):
        raise ValueError('Matched comparison requires baseline, missingness and full')
    if len(set(folds)) != len(folds) or any(f not in range(5) for f in folds):
        raise ValueError('Choose distinct building folds from zero to four')
    if any(y>=2025 or y<2011 for y in (*years,*cross_years)):
        raise ValueError('Development years must be 2011–2024; 2025+ are not untouched tests')
    if len(set(years)) != len(years) or len(set(cross_years)) != len(cross_years):
        raise ValueError('Duplicate temporal split')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data,source,coverage=model.load_analytical(dataset)
        data=data[data.period < '2025-01-01'].copy()
        splits=list(split_data(data,years=years,folds=folds,cross_years=cross_years))
        if not splits:
            raise ValueError('At least one evaluation split required')
        split_manifest=[]
        for name,train,test in splits:
            if min(len(train),len(test))<min_rows:
                raise ValueError(f'Insufficient rows: {name}')
            def membership(frame):
                return hashlib.sha256(canonical(sorted((r.unit_id,str(r.period),r.audit_id) for r in frame.itertuples())).encode()).hexdigest()
            split_manifest.append({'name':name,'train_rows':len(train),'test_rows':len(test),
                'train_sha256':membership(train),'test_sha256':membership(test),
                'train_buildings':int(train.building.nunique()),'test_buildings':int(test.building.nunique()),
                'train_end':str(train.period.max().date()),'test_start':str(test.period.min().date()),
                'overlapping_buildings':len(set(train.building)&set(test.building)),
                'overlapping_units':len(set(train.unit_id)&set(test.unit_id))})
        code={Path(path).name:digest(path) for path in (__file__,model.__file__,baseline.__file__,model.pricing.__file__)}
        protocol={'version':VERSION,'source_manifest':source,'coverage_before_2025_filter':coverage,
                  'development_rows':len(data),'settings':model.SETTINGS,'variants':list(variants),
                  'unit_effect':unit_effect,'splits':split_manifest,'implementation_sha256':code,
                  'versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','duckdb')},
                  'interpretation':'retrospective exploratory development; all encodings learned on each training partition',
                  'contrast':'actual amenity values versus explicit unknown indicators on exactly the same rows',
                  'categorical_encoding':'known-only training-frequency-centered contrasts; unknown indicators unchanged; unseen values have zero known contrast'}
        plan=root/'protocol.json'
        if plan.exists() and json.loads(plan.read_text())!=protocol:
            raise ValueError('Protocol changed; choose a new directory')
        if not plan.exists():plan.write_text(canonical(protocol)+'\n')
        summaries=[]
        for split_index,(name,train,test) in enumerate(splits):
            table=test[['unit_id','building','period','asking_rent','audit_id']].copy()
            metrics={};convergence={}
            for variant in variants:
                directory=root/name/variant
                if (directory/'complete.json').exists():
                    manifest,files=_verified_bundle(directory,retain={'result.json','predictions.json'})
                    if manifest.get('protocol_sha256')!=digest(plan):raise ValueError('Fit protocol mismatch')
                    result=json.loads(files['result.json']);pred=np.array(json.loads(files['predictions.json']))
                else:
                    print(canonical({'phase':'fitting','split':name,'variant':variant,'train':len(train),'test':len(test)}),flush=True)
                    fitted=baseline.fit(train,model.SETTINGS,unit_effect=unit_effect,iterations=12,encoder_class=encoder_class(variant))
                    change=fitted['robust_objective_relative_change']
                    if change is None or change>1e-5:raise ValueError(f'Objective not converged: {name}/{variant}')
                    log_pred=baseline.predict(fitted,test);pred=np.exp(log_pred)
                    result={'metrics':baseline.metrics(test,log_pred),'objective_relative_change':change,
                            'solves':fitted['solves'],'encoder':fitted['encoder'].metadata()}
                    saved={'amenities':{'encoder':result['encoder'],'beta':fitted['beta'].tolist(),'center':fitted['center']}}
                    publish_bundle(directory,{'result.json':canonical(result)+'\n',
                        'models.json':canonical(saved)+'\n','predictions.json':canonical(pred.tolist())+'\n'},
                        {'version':VERSION,'protocol_sha256':digest(plan),'split_sha256':split_manifest[split_index]['test_sha256']})
                if len(pred)!=len(test) or not np.isfinite(pred).all() or not (pred>0).all():
                    raise ValueError('Prediction validation failed')
                table[variant]=pred;metrics[variant]=result['metrics']
                convergence[variant]={'objective_relative_change':result['objective_relative_change'],'solves':result['solves']}
            comparisons={}
            for reference in ('baseline','missingness'):
                compared=table[['building','asking_rent']].copy()
                compared['baseline_rent']=table[reference];compared['amenity_rent']=table['full']
                comparisons['full_minus_'+reference]=model.paired_building_comparison(compared)
            summary={'split':name,'metrics':metrics,'comparisons':comparisons,'convergence':convergence}
            table['period']=table.period.dt.strftime('%Y-%m-%d')
            publish_bundle(root/name/'comparison',{'result.json':canonical(summary)+'\n',
                'predictions.jsonl':table.to_json(orient='records',lines=True)},
                {'version':VERSION,'protocol_sha256':digest(plan)})
            summaries.append(summary)
            (root/'progress.json').write_text(canonical({'phase':'running','completed_splits':[r['split'] for r in summaries]})+'\n')
        if any(digest(path)!=code[Path(path).name] for path in (__file__,model.__file__,baseline.__file__,model.pricing.__file__)):
            raise ValueError('Implementation changed during experiment')
        publish_bundle(root/'summary',{'results.json':canonical({'protocol':protocol,'results':summaries})+'\n'},
                       {'version':VERSION,'protocol_sha256':digest(plan)})
        (root/'progress.json').write_text(canonical({'phase':'complete','completed_splits':[r['split'] for r in summaries]})+'\n')
        return summaries


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--years',type=int,nargs='*',default=[])
    parser.add_argument('--folds',type=int,nargs='*',default=[0,1,2,3,4])
    parser.add_argument('--cross-years',type=int,nargs='*',default=[])
    parser.add_argument('--variants',choices=VARIANTS,nargs='+',default=['baseline','missingness','full'])
    parser.add_argument('--no-units',action='store_true')
    args=parser.parse_args()
    run(args.dataset,args.output,years=tuple(args.years),folds=tuple(args.folds),cross_years=tuple(args.cross_years),
        variants=tuple(args.variants),unit_effect=not args.no_units)

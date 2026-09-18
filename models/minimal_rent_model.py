"""Local, regularized asking-rent model of canonical StreetEasy rental units.

This is a robust penalized point estimate, not a posterior sampler or lease model.
Run with --dataset /path/to/completed-transform --output /path/to/new-model-run.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import duckdb
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import lsmr

RULE = 'canonical-initial-ask-v1'


def emit(phase, **values):
    print(json.dumps({'phase': phase, **values}, default=str), flush=True)


def load_source(root):
    root = Path(root)
    complete = json.loads((root/'complete.json').read_text())
    if complete.get('unit_association_rule') != 'canonical-url-v1':
        raise ValueError('A completed canonical-url-v1 transform is required')
    db = duckdb.connect(config={'memory_limit': '1GB', 'threads': '2'})
    try:
        for name in ['listing_observations', 'event_mentions', 'rental_unit_memberships']:
            db.read_parquet([str(p) for p in sorted((root/name).glob('*.parquet'))]).create_view(name)
        # Attributes come only from captures of this advertisement, never from
        # another listing that happens to mention it in propertyHistory.
        attrs = db.execute("""
            SELECT l.listing_id, m.unit_id, m.canonical_unit_url,
              min(l.bedrooms) bedrooms, min(l.bathrooms) bathrooms, min(l.square_feet) square_feet,
              count(*) capture_count,
              count(DISTINCT l.bedrooms)>1 OR count(DISTINCT l.bathrooms)>1 OR count(DISTINCT l.square_feet)>1 attribute_conflict,
              bool_or(coalesce(l.features_json ILIKE '%"FURNISHED"%',false)
                 OR coalesce(try_cast(json_extract_string(l.pricing_json,'$.furnishedRent') AS DOUBLE)>0,false)
                 OR coalesce(regexp_matches(lower(json_extract_string(l.raw_listing_json,'$.description')),
                    'blueground|fully furnished|comes furnished|furnished apartment'),false)) furnished,
              bool_or(coalesce(try_cast(json_extract_string(l.pricing_json,'$.leaseTermMonths') AS DOUBLE)<6,false)) short_term,
              bool_or(coalesce(try_cast(json_extract_string(l.pricing_json,'$.monthsFree') AS DOUBLE)>0,false)
                 OR coalesce(try_cast(json_extract_string(l.pricing_json,'$.netEffectiveRent') AS DOUBLE)>0,false)) concession,
              max(l.collected_at) collected_at
            FROM listing_observations l JOIN rental_unit_memberships m USING(listing_id)
            WHERE l.listing_type='rental'
            GROUP BY l.listing_id,m.unit_id,m.canonical_unit_url ORDER BY l.listing_id
        """).df()
        events = db.execute("""
            WITH own AS (
              SELECT DISTINCT l.listing_id, try_cast(e.event_date AS DATE) event_date, e.price
              FROM listing_observations l JOIN event_mentions e USING(snapshot_id)
              WHERE l.listing_type='rental' AND e.event_category='rental'
                AND e.event_listing_id=l.listing_id AND e.status='ACTIVE'
            ), first_events AS (
              SELECT * FROM own QUALIFY event_date=min(event_date) OVER(PARTITION BY listing_id)
            )
            SELECT listing_id,min(event_date) event_date,min(price) asking_rent,
              count(DISTINCT price)>1 OR count(price)!=count(*) price_conflict
            FROM first_events GROUP BY listing_id ORDER BY listing_id
        """).df()
        return attrs.merge(events, how='left', on='listing_id', validate='one_to_one')
    finally:
        db.close()


def prepare(root, start='2010-01-01', end=None):
    source = load_source(root)
    if end is None:
        latest_capture = pd.to_datetime(source.collected_at.max(), unit='s', utc=True).tz_localize(None)
        end = str((latest_capture.to_period('M').start_time-pd.Timedelta(days=1)).date())
    source['event_date'] = pd.to_datetime(source.event_date)
    source['building'] = source.canonical_unit_url.str.extract(r'/building/([^/]+)/', expand=False)
    source['exclusion_reason'] = ''
    counts = []
    def exclude(reason, condition):
        mask = source.exclusion_reason.eq('') & condition.fillna(True)
        source.loc[mask, 'exclusion_reason'] = reason
        counts.append({'reason': reason, 'listing_ids': int(mask.sum())})
    exclude('unresolved_identity', source.unit_id.isna() | source.building.isna())
    exclude('no_dated_own_active_event', source.event_date.isna())
    exclude('outside_date_window', ~source.event_date.between(pd.Timestamp(start), pd.Timestamp(end)))
    exclude('conflicting_initial_prices', source.price_conflict.fillna(True).astype(bool))
    exclude('invalid_or_extreme_initial_ask', ~source.asking_rent.between(750,50000) | ~np.isfinite(source.asking_rent))
    exclude('conflicting_attributes_within_listing', source.attribute_conflict)
    exclude('invalid_or_missing_layout', ~source.bedrooms.between(0,5) | source.bedrooms.mod(1).ne(0)
            | ~source.bathrooms.between(1,5) | source.bathrooms.mul(2).mod(1).ne(0))
    exclude('furnished', source.furnished)
    exclude('short_term', source.short_term)
    exclude('explicit_concession', source.concession)
    source['square_feet_invalid'] = source.square_feet.notna() & (~source.square_feet.between(150,6000) | ~np.isfinite(source.square_feet))
    source.loc[source.square_feet_invalid, 'square_feet'] = np.nan
    source['period'] = source.event_date.dt.to_period('M').dt.to_timestamp()
    good = source[source.exclusion_reason.eq('')].copy()
    groups = good.groupby(['unit_id','period'], sort=True)
    layout = groups.agg(beds=('bedrooms','nunique'), baths=('bathrooms','nunique'))
    inconsistent = layout[(layout.beds>1)|(layout.baths>1)].index
    bad = pd.MultiIndex.from_frame(source[['unit_id','period']]).isin(inconsistent)
    exclude('conflicting_layout_same_unit_month', pd.Series(bad,index=source.index))
    good = source[source.exclusion_reason.eq('')].copy()
    data = good.groupby(['unit_id','period'], as_index=False, sort=True).agg(
        asking_rent=('asking_rent','median'), bedrooms=('bedrooms','first'), bathrooms=('bathrooms','first'),
        square_feet=('square_feet','median'), building=('building','first'),
        canonical_unit_url=('canonical_unit_url','first'), source_listings=('listing_id','size'),
        listing_ids=('listing_id',lambda values: json.dumps(sorted(values.tolist()))))
    data['log_rent'] = np.log(data.asking_rent)
    coverage = {'dataset':str(Path(root).resolve()), 'selection_rule':RULE,'start':start,'end':end,
                'source_listing_ids':len(source),'included_listing_ids':len(good),
                'retained_percent':100*len(good)/len(source),'exclusions':counts,
                'model_observations':len(data),'units':int(data.unit_id.nunique()),
                'buildings':int(data.building.nunique()),
                'missing_sqft_observations':int(data.square_feet.isna().sum()),
                'invalid_sqft_kept_as_missing':int(good.square_feet_invalid.sum()),
                'earliest_month':str(data.period.min().date()),'latest_month':str(data.period.max().date())}
    if len(data)<100:
        raise ValueError('Too few eligible observations')
    return data, source, coverage


class Encoder:
    """All learned scales and category memberships use training observations only."""
    def __init__(self, train, unit_effect=True):
        self.unit_effect = unit_effect
        self.bedroom_encoding = 'incremental'
        self.size_medians = {str(int(k)):float(v) for k,v in train.groupby('bedrooms').square_feet.median().dropna().items()}
        self.size_default = float(train.square_feet.median()) if train.square_feet.notna().any() else 700.
        self.buildings = sorted(train.building.unique())
        self.units = sorted(train.unit_id.unique()) if unit_effect else []
        self.periods = pd.date_range(train.period.min(), train.period.max(),freq='MS')
        self.features = ['intercept',*[f'bedrooms_gt_{n}' for n in range(5)],'bathrooms_above_one','log_size_within_bedrooms','size_missing']
        self.offsets = {}
        offset=0
        for name,count in [('features',len(self.features)),('trend',len(self.periods)),('season',12),('building',len(self.buildings)),('unit',len(self.units))]:
            self.offsets[name]=(offset,offset+count);offset+=count
        self.n_parameters=offset

    def matrix(self, data):
        n=len(data);i=np.arange(n)
        size=data.square_feet.to_numpy(dtype=float)
        median=data.bedrooms.map(lambda x:self.size_medians.get(str(int(x)),self.size_default)).to_numpy()
        log_size=np.where(np.isfinite(size), np.log(np.where(np.isfinite(size),size,median)/median), 0)
        if self.bedroom_encoding == 'incremental':
            bedroom_columns=[data.bedrooms.gt(b).to_numpy(dtype=float) for b in range(5)]
        elif self.bedroom_encoding == 'categorical':
            bedroom_columns=[data.bedrooms.eq(b).to_numpy(dtype=float) for b in range(1,6)]
        else:
            raise ValueError('Unknown bedroom encoding')
        dense=np.column_stack([np.ones(n),*bedroom_columns,
                               data.bathrooms.to_numpy()-1,log_size,np.isnan(size).astype(float)])
        dates=pd.DatetimeIndex(data.period)
        months=(dates.year-self.periods[0].year)*12+dates.month-self.periods[0].month
        # Future forecasts hold the final smooth market level constant, while
        # applying the appropriate seasonal effect; no future prices enter fit.
        months=np.clip(months,0,len(self.periods)-1)
        trend=sparse.csr_matrix((np.ones(n),(i,months)),shape=(n,len(self.periods)))
        season=sparse.csr_matrix((np.ones(n),(i,dates.month-1)),shape=(n,12))
        blocks=[sparse.csr_matrix(dense),trend,season]
        for col,values in [('building',self.buildings),('unit',self.units)]:
            if not values:
                blocks.append(sparse.csr_matrix((n,0)));continue
            codes=data[col if col=='building' else 'unit_id'].map({x:j for j,x in enumerate(values)}).fillna(-1).to_numpy(dtype=int)
            valid=codes>=0
            blocks.append(sparse.csr_matrix((np.ones(valid.sum()),(i[valid],codes[valid])),shape=(n,len(values))))
        return sparse.hstack(blocks,format='csr')

    def penalty(self, settings):
        weights=np.zeros(self.n_parameters)
        a,b=self.offsets['features'];weights[a:b]=.1;weights[a]=1e-8
        a,b=self.offsets['trend'];weights[a:b]=1e-5
        a,b=self.offsets['season'];weights[a:b]=10
        a,b=self.offsets['building'];weights[a:b]=settings['building_penalty']
        a,b=self.offsets['unit'];weights[a:b]=settings['unit_penalty']
        ridge=sparse.diags(np.sqrt(weights),format='csr')
        a,b=self.offsets['trend'];n=b-a
        if n<3:return ridge
        diff=sparse.diags([np.ones(n-2),-2*np.ones(n-2),np.ones(n-2)],[0,1,2],shape=(n-2,n),format='csr')
        smooth=sparse.hstack([sparse.csr_matrix((n-2,a)),diff*np.sqrt(settings['trend_penalty']),sparse.csr_matrix((n-2,self.n_parameters-b))],format='csr')
        return sparse.vstack([ridge,smooth],format='csr')

    def metadata(self):
        return {'unit_effect':self.unit_effect,'bedroom_encoding':self.bedroom_encoding,'size_medians':self.size_medians,'size_default':self.size_default,
                'buildings':self.buildings,'units':self.units,'periods':self.periods.strftime('%Y-%m-%d').tolist(),
                'features':self.features,'offsets':self.offsets,'n_parameters':self.n_parameters}


def fit(train,settings,unit_effect=True,iterations=8):
    started=time.monotonic();enc=Encoder(train,unit_effect);x=enc.matrix(train);p=enc.penalty(settings)
    center=float(train.log_rent.median());y=train.log_rent.to_numpy()-center
    weights=np.ones(len(train));beta=np.zeros(x.shape[1]);solves=[];prior_objective=None;relative_change=None
    for iteration in range(iterations):
        w=np.sqrt(weights)
        design=sparse.vstack([x.multiply(w[:,None]),p],format='csr')
        rhs=np.concatenate([y*w,np.zeros(p.shape[0])])
        solution=lsmr(design,rhs,atol=1e-7,btol=1e-7,maxiter=2000,x0=beta)
        beta=solution[0];residual=y-x@beta
        solves.append({'stop_code':int(solution[1]),'iterations':int(solution[2]),'condition_estimate':float(solution[6])})
        if solution[1] not in (1,2,4,5):raise RuntimeError(f'Linear solver failed: {solves[-1]}')
        weights=np.minimum(1.,.20/np.maximum(np.abs(residual),1e-12))
        absolute=np.abs(residual)
        objective=float(np.where(absolute<=.20,.5*residual**2,.20*absolute-.5*.20**2).sum()+.5*np.square(p@beta).sum())
        relative_change=abs(objective-prior_objective)/max(1.,abs(prior_objective)) if prior_objective is not None else None
        prior_objective=objective
        if relative_change is not None and relative_change<1e-7:break
    return {'encoder':enc,'beta':beta,'center':center,'settings':settings,'seconds':time.monotonic()-started,
            'solves':solves,'weights':weights,'robust_objective_relative_change':relative_change}


def predict(model,data):
    return model['center']+model['encoder'].matrix(data)@model['beta']


def load_model(directory):
    directory=Path(directory)
    metadata=json.loads((directory/'encoder.json').read_text())
    enc=Encoder.__new__(Encoder)
    # Earlier saved models used exact-category indicators; preserve their predictions.
    enc.bedroom_encoding=metadata.get('bedroom_encoding','categorical')
    for key,value in metadata.items():setattr(enc,key,value)
    enc.periods=pd.DatetimeIndex(pd.to_datetime(metadata['periods']))
    with np.load(directory/'model.npz',allow_pickle=False) as values:
        return {'encoder':enc,'beta':values['beta'].copy(),'center':float(values['center'])}


def metrics(data,prediction):
    actual=data.asking_rent.to_numpy();pred=np.exp(prediction)
    errors=np.abs(pred/actual-1)*100
    return {'observations':len(data),'log_rmse':float(np.sqrt(np.mean((prediction-np.log(actual))**2))),
            'median_absolute_percent_error':float(np.median(errors)),
            'mean_absolute_percent_error':float(np.mean(errors)),
            'mean_absolute_dollar_error':float(np.mean(np.abs(pred-actual))),
            'within_10_percent':float(np.mean(errors<=10)*100),'within_20_percent':float(np.mean(errors<=20)*100),
            'median_signed_percent_error':float(np.median((pred/actual-1)*100))}


def comparison(train,test,model,contemporaneous=False):
    pred=predict(model,test)
    recent=train[train.period>=train.period.max()-pd.DateOffset(months=11)]
    medians=recent.groupby('bedrooms').asking_rent.median()
    baseline=test.bedrooms.map(medians).fillna(recent.asking_rent.median()).to_numpy()
    if contemporaneous:
        # A fair same-period baseline for historical unseen-unit validation.
        month_bed=train.groupby(['period','bedrooms']).asking_rent.median()
        year_bed=train.assign(year=train.period.dt.year).groupby(['year','bedrooms']).asking_rent.median()
        all_bed=train.groupby('bedrooms').asking_rent.median()
        baseline=np.array([month_bed.get((r.period,r.bedrooms),year_bed.get((r.period.year,r.bedrooms),all_bed.get(r.bedrooms,train.asking_rent.median()))) for r in test.itertuples()])
    last=train.sort_values('period').groupby('unit_id').asking_rent.last()
    seen=test.unit_id.isin(last.index).to_numpy();last_price=test.unit_id.map(last).to_numpy()
    table=test[['unit_id','building','period','bedrooms','asking_rent','listing_ids']].copy()
    table['predicted_rent']=np.exp(pred);table['bedroom_baseline']=baseline;table['last_unit_rent']=last_price
    table['seen_unit']=seen;table['seen_building']=test.building.isin(train.building.unique()).to_numpy()
    scores={'model':metrics(test,pred),'bedroom_baseline':metrics(test,np.log(baseline)),
            'seen_unit_count':int(seen.sum()),'unseen_unit_count':int((~seen).sum()),
            'seen_building_percent':float(table.seen_building.mean()*100)}
    if seen.any():
        scores['seen_unit_model']=metrics(test.iloc[np.flatnonzero(seen)],pred[seen])
        scores['last_unit_rent_baseline']=metrics(test.iloc[np.flatnonzero(seen)],np.log(last_price[seen]))
    if (~seen).any():scores['unseen_unit_model']=metrics(test.iloc[np.flatnonzero(~seen)],pred[~seen])
    return scores,table


def run(args):
    root=Path(args.dataset);output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    data,selection,coverage=prepare(root,args.start,args.end)
    data.to_parquet(output/'model_data.parquet',index=False)
    selection.to_parquet(output/'selection_audit.parquet',index=False)
    (output/'coverage.json').write_text(json.dumps(coverage,indent=2))
    emit('prepared',**coverage)
    # Tune only on 2025. The 2026 prices are a final untouched temporal test.
    train=data[data.period<'2025-01-01'];valid=data[(data.period>='2025-01-01')&(data.period<'2026-01-01')]
    if min(len(train),len(valid))<100:raise ValueError('Need sufficient pre-2025 and 2025 data')
    candidates=[]
    for unit_penalty in [2.,8.,32.]:
        for trend_penalty in [100.,1000.]:
            settings={'building_penalty':10.,'unit_penalty':unit_penalty,'trend_penalty':trend_penalty}
            model=fit(train,settings)
            scores=metrics(valid,predict(model,valid))
            result={**settings,**scores,'seconds':model['seconds']};candidates.append(result)
            emit('tuning',**result)
    best=min(candidates,key=lambda x:x['log_rmse'])
    settings={k:best[k] for k in ['building_penalty','unit_penalty','trend_penalty']}
    (output/'tuning.json').write_text(json.dumps(candidates,indent=2))
    train=data[data.period<'2026-01-01'];test=data[data.period>='2026-01-01']
    model=fit(train,settings);scores,table=comparison(train,test,model)
    table.to_parquet(output/'temporal_validation.parquet',index=False)
    temporal={'split':'Train through December 2025; test January–August 2026','scores':scores,'fit':{k:model[k] for k in ['seconds','solves','robust_objective_relative_change']}}
    emit('temporal_validation',**scores)
    # A simpler ablation checks that unit identity helps on the same held-out data.
    no_unit=fit(train,settings,unit_effect=False)
    scores_no_unit=metrics(test,predict(no_unit,test));temporal['without_unit_effect']=scores_no_unit
    emit('without_unit_effect',**scores_no_unit)
    # Entire units are withheld, keeping all dates for each unit on one side.
    held_units={u for u in data.unit_id.unique() if int(hashlib.sha256(u.encode()).hexdigest()[:8],16)%5==0}
    cold_train=data[~data.unit_id.isin(held_units)];cold_test=data[data.unit_id.isin(held_units)]
    # Fixed settings for this separate test; no held-out unit's prices are used
    # to select hyperparameters through the earlier 2025 tuning exercise.
    cold_settings={'building_penalty':10.,'unit_penalty':8.,'trend_penalty':1000.}
    cold_model=fit(cold_train,cold_settings);scores,cold_table=comparison(cold_train,cold_test,cold_model,contemporaneous=True)
    cold_table.to_parquet(output/'unseen_unit_validation.parquet',index=False)
    cold={'split':'Deterministic 20% of entire units withheld across all dates','scores':scores,'fixed_settings':cold_settings,
          'fit':{k:cold_model[k] for k in ['seconds','solves','robust_objective_relative_change']}}
    emit('unseen_unit_validation',**scores)
    model=fit(data,settings)
    fitted=predict(model,data)
    diagnostics=data.copy();diagnostics['fitted_rent']=np.exp(fitted)
    diagnostics['residual_percent']=100*(diagnostics.asking_rent/diagnostics.fitted_rent-1)
    diagnostics['robust_weight']=model['weights']
    diagnostics.to_parquet(output/'fit_diagnostics.parquet',index=False)
    np.savez_compressed(output/'model.npz',beta=model['beta'],center=model['center'])
    (output/'encoder.json').write_text(json.dumps(model['encoder'].metadata(),indent=2))
    enc=model['encoder'];a,b=enc.offsets['trend'];trend=model['beta'][a:b]
    a,b=enc.offsets['season'];season=model['beta'][a:b]
    reference=enc.periods.get_loc(pd.Timestamp('2022-01-01'))
    chart=pd.DataFrame({'period':enc.periods,'smooth_index':100*np.exp(trend-trend[reference]),
                        'index_with_seasonality':100*np.exp(trend+season[enc.periods.month-1]-trend[reference]-season[0])})
    chart=chart.merge(data.groupby('period').agg(observations=('unit_id','size'),raw_median=('asking_rent','median')).reset_index(),on='period',how='left')
    chart.to_parquet(output/'rent_index.parquet',index=False)
    a,b=enc.offsets['features']
    coefficients=pd.DataFrame({'term':enc.features,'log_coefficient':model['beta'][a:b]})
    coefficients['percent_difference']=100*np.expm1(coefficients.log_coefficient)
    coefficients.to_parquet(output/'coefficients.parquet',index=False)
    a,b=enc.offsets['building']
    buildings=pd.DataFrame({'building':enc.buildings,'log_effect':model['beta'][a:b]})
    buildings=buildings.merge(data.groupby('building').agg(observations=('unit_id','size'),units=('unit_id','nunique')).reset_index(),on='building')
    buildings.to_parquet(output/'building_effects.parquet',index=False)
    results={'coverage':coverage,'settings':settings,'bedroom_encoding':enc.bedroom_encoding,'temporal_validation':temporal,'unseen_unit_validation':cold,
             'in_sample':metrics(data,fitted),'fit':{k:model[k] for k in ['seconds','solves','robust_objective_relative_change']},
             'robustly_downweighted_observations':int((model['weights']<.999).sum()),
             'severely_downweighted_observations':int((model['weights']<.5).sum()),
             'runtime_seconds':time.monotonic()-started,'method':'Huber iteratively reweighted sparse penalized least squares on log initial asking rent',
             'uncertainty':'Point estimates only; no posterior or confidence intervals',
             'forecast_policy':'Hold the final fitted smooth trend constant and apply month-of-year seasonality',
             'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'training_sha256':hashlib.sha256((output/'model_data.parquet').read_bytes()).hexdigest(),
             'canonical_associations':json.loads((root/'canonical-units.json').read_text()),
             'versions':{x:importlib.metadata.version(x) for x in ['numpy','pandas','scipy','duckdb','pyarrow']}}
    (output/'results.json').write_text(json.dumps(results,indent=2))
    emit('complete',runtime_seconds=results['runtime_seconds'],output=str(output))
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',default='2010-01-01')
    parser.add_argument('--end',help='Last included date; default is the last complete capture month')
    run(parser.parse_args())


if __name__=='__main__':main()

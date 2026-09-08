"""Fit a pooled Chelsea asking-rent model from the local archive-derived database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

# Nutpie compiles the graph through Numba. Avoid PyTensor's unrelated C linker,
# which can select an unavailable Apple linker on machines without full Xcode.
os.environ.setdefault('PYTENSOR_FLAGS', 'cxx=')

import arviz as az
import duckdb
import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

FEATURES = ['bedrooms', 'bathrooms', 'log_sqft_z', 'bedrooms_missing',
            'bathrooms_missing', 'sqft_missing']


def prepare_data(db_path: Path, frequency='monthly', start=None):
    if frequency not in ('monthly', 'weekly'):
        raise ValueError('Frequency must be monthly or weekly')
    with duckdb.connect(str(db_path), read_only=True) as db:
        events = db.execute('''SELECT l.source_listing_id,l.building_slug,l.unit,
            l.bedrooms,l.bathrooms,l.square_feet,l.physical_floor,l.floor_inference,
            CAST(e.event_at AS DATE) AS event_date,e.price AS asking_rent,
            e.event_type,CAST(e.raw_json AS VARCHAR) AS event_json,
            l.unit_is_specific,l.is_furnished
            FROM listing_events e JOIN listings l USING(source,source_listing_id)
            WHERE e.source='streeteasy' ''').df()
        captures = db.execute('''SELECT source_listing_id, structured_json
            FROM captures WHERE source='streeteasy' ''').fetchall()
        names = dict(db.execute('''SELECT building_slug,
            coalesce(max(canonical_address),building_slug) FROM listings
            WHERE source='streeteasy' GROUP BY building_slug''').fetchall())
    if events.empty:
        raise ValueError('Import rental captures before fitting the model')
    events['event_date'] = pd.to_datetime(events.event_date)
    # Exclude a whole unit if any archived episode explicitly marks it furnished.
    # This conservative rule also removes its conventional rental history.
    furnished_ids = set(events.loc[events.is_furnished.fillna(False), 'source_listing_id'])
    evidence = (events.event_json.fillna('') + ' ' + events.event_type.fillna('')).str.lower()
    furnished_ids.update(events.loc[evidence.str.contains(r'blueground|\bfurnished\b', regex=True), 'source_listing_id'])
    for source_id, raw in captures:
        item = json.loads(raw)
        if any(str(feature).upper() == 'FURNISHED' for feature in item.get('home_features', [])):
            furnished_ids.add(source_id)
    coverage = {'archived_rental_units': int(events.source_listing_id.nunique()),
                'archived_rental_buildings': int(events.building_slug.nunique()),
                'raw_events': len(events), 'furnished_units_excluded': len(furnished_ids)}
    valid = events.asking_rent.gt(0) & events.event_date.notna() & events.unit_is_specific.fillna(True)
    if start is not None:
        valid &= events.event_date.ge(pd.Timestamp(start))
    coverage['invalid_or_outside_window_events'] = int((~valid).sum())
    coverage['furnished_events_excluded'] = int((valid & events.source_listing_id.isin(furnished_ids)).sum())
    events = events.loc[valid & ~events.source_listing_id.isin(furnished_ids)].copy()
    if events.empty:
        raise ValueError('No observations remain after the model exclusions')
    # Several captures repeat an event; count a price only once per unit/date.
    events = events.drop_duplicates(['source_listing_id', 'event_date', 'asking_rent'])
    coverage['unique_unit_date_prices'] = len(events)
    events.loc[events.floor_inference.eq('heuristic-first-digit'), 'physical_floor'] = np.nan
    if frequency == 'monthly':
        events['period'] = events.event_date.dt.to_period('M').dt.to_timestamp()
        freq = 'MS'
    else:
        events['period'] = events.event_date - pd.to_timedelta(events.event_date.dt.weekday, unit='D')
        freq = 'W-MON'
    data = events.groupby(['building_slug', 'unit', 'period'], as_index=False).agg(
        asking_rent=('asking_rent', 'median'), bedrooms=('bedrooms', 'first'),
        bathrooms=('bathrooms', 'first'), square_feet=('square_feet', 'first'),
        physical_floor=('physical_floor', 'first'), source_events=('asking_rent', 'size'))
    for col in ['bedrooms', 'bathrooms', 'square_feet', 'physical_floor']:
        data[col] = pd.to_numeric(data[col], errors='coerce')
    data.loc[data.square_feet.le(0), 'square_feet'] = np.nan
    for col in ['bedrooms', 'bathrooms']:
        data[col + '_missing'] = data[col].isna().astype(float)
        median = data[col].median()
        data[col] = data[col].fillna(median if pd.notna(median) else 0)
    data['sqft_missing'] = data.square_feet.isna().astype(float)
    group_median = data.groupby('bedrooms').square_feet.transform('median')
    overall = data.square_feet.median()
    data['square_feet_imputed'] = data.square_feet.fillna(group_median).fillna(overall if pd.notna(overall) else 700)
    log_size = np.log(data.square_feet_imputed)
    size_scale = float(log_size.std())
    if not np.isfinite(size_scale) or size_scale == 0:
        size_scale = 1.0
    data['log_sqft_z'] = (log_size - log_size.mean()) / size_scale
    data['log_rent'] = np.log(data.asking_rent)
    data['floor_level'] = data.physical_floor.fillna(-1).astype(int)
    data['unit_key'] = data.building_slug + '/' + data.unit.astype(str)
    periods = pd.date_range(data.period.min(), data.period.max(), freq=freq)
    for col, idx in [('building_slug', 'building_idx'), ('unit_key', 'unit_idx'), ('floor_level', 'floor_idx')]:
        values = sorted(data[col].unique())
        data[idx] = data[col].map(dict(zip(values, range(len(values))))).astype(int)
    data['period_idx'] = data.period.map(dict(zip(periods, range(len(periods))))).astype(int)
    coverage.update(modeled_units=int(data.unit_key.nunique()), modeled_buildings=int(data.building_slug.nunique()),
                    unit_period_observations=len(data), unknown_floor_observations=int(data.physical_floor.isna().sum()),
                    missing_size_observations=int(data.sqft_missing.sum()),
                    earliest_date=str(events.event_date.min().date()), latest_date=str(events.event_date.max().date()))
    data.attrs.update(coverage=coverage, names=names, excluded_furnished_units=sorted(furnished_ids),
                      size_log_mean=float(log_size.mean()), size_log_scale=size_scale)
    return data, periods


def fit_model(data, periods, frequency='monthly', draws=1000, tune=1000, chains=4, train_mask=None):
    buildings = sorted(data.building_slug.unique())
    units = sorted(data.unit_key.unique())
    floors = sorted(data.floor_level.unique())
    train = data if train_mask is None else data.loc[train_mask]
    coords = {'building': buildings, 'unit': units, 'floor': [str(x) for x in floors],
              'period': periods.strftime('%Y-%m-%d').tolist(),
              'step': np.arange(max(0, len(periods)-1)), 'feature': FEATURES}
    with pm.Model(coords=coords):
        alpha = pm.Normal('alpha', np.log(5000), 1)
        sigma_building = pm.HalfNormal('sigma_building', .5)
        building_z = pm.Normal('building_z', 0, 1, dims='building')
        building = pm.Deterministic('building_offset', (building_z-pt.mean(building_z))*sigma_building, dims='building')
        sigma_unit = pm.HalfNormal('sigma_unit', .4)
        unit_z = pm.Normal('unit_z', 0, 1, dims='unit')
        unit = pm.Deterministic('unit_effect', unit_z*sigma_unit, dims='unit')
        sigma_floor = pm.HalfNormal('sigma_floor', .15)
        floor_z = pm.Normal('floor_z', 0, 1, dims='floor')
        floor = pm.Deterministic('floor_effect', (floor_z-pt.mean(floor_z))*sigma_floor, dims='floor')
        sigma_rw = pm.HalfNormal('sigma_rw', .08 if frequency == 'monthly' else .04)
        step_z = pm.Normal('step_z', 0, 1, dims='step')
        trend = pm.Deterministic('trend', pt.concatenate([pt.zeros(1), pt.cumsum(step_z*sigma_rw)]), dims='period')
        beta = pm.Normal('beta', mu=[.15, .1, .3, 0, 0, 0], sigma=[.3, .3, .3, .3, .3, .3], dims='feature')
        mu = (alpha + trend[train.period_idx.to_numpy()] + building[train.building_idx.to_numpy()]
              + unit[train.unit_idx.to_numpy()] + floor[train.floor_idx.to_numpy()]
              + pt.dot(train[FEATURES].to_numpy(dtype=float), beta))
        sigma = pm.HalfNormal('sigma', .3)
        pm.StudentT('log_rent', nu=5, mu=mu, sigma=sigma, observed=train.log_rent.to_numpy(dtype=float))
        return pm.sample(draws=draws, tune=tune, chains=chains, cores=min(chains, 4),
                         nuts_sampler='nutpie', target_accept=.95, random_seed=150130,
                         progressbar=False, return_inferencedata=True)


def samples(posterior, variable):
    value = posterior[variable]
    return value.stack(sample=('chain', 'draw')).transpose('sample', ...).values


def predict(inference, data):
    p = inference.posterior
    return (samples(p, 'alpha')[:, None] + samples(p, 'trend')[:, data.period_idx.to_numpy()]
            + samples(p, 'building_offset')[:, data.building_idx.to_numpy()]
            + samples(p, 'unit_effect')[:, data.unit_idx.to_numpy()]
            + samples(p, 'floor_effect')[:, data.floor_idx.to_numpy()]
            + samples(p, 'beta') @ data[FEATURES].to_numpy(dtype=float).T)


def interval(values):
    return {'median': float(np.median(values)), 'lower_95': float(np.quantile(values, .025)),
            'upper_95': float(np.quantile(values, .975))}


def diagnostic_summary(inference):
    # Exclude anchored deterministic trend[0], whose variance is exactly zero.
    diag = az.summary(inference, var_names=['alpha','beta','sigma','sigma_rw','sigma_building',
                                           'sigma_unit','sigma_floor','building_z','unit_z','floor_z','step_z'], kind='diagnostics', round_to='none')
    return {'max_rhat': float(diag.r_hat.max()), 'min_ess_bulk': float(diag.ess_bulk.min()),
            'divergences': int(inference.sample_stats.diverging.sum().item())}


def save_outputs(inference, data, periods, frequency, output, validation=None):
    output.mkdir(parents=True, exist_ok=True)
    inference.to_netcdf(output / 'posterior.nc')
    data.to_parquet(output / 'training_data.parquet', index=False)
    p = inference.posterior
    trend = samples(p, 'trend')
    # Rebase to January 2022 if observed span includes it, to make old sparse tails
    # less dominant in the visual scale. The fit itself retains all history.
    base = int(periods.searchsorted(pd.Timestamp('2022-01-01')))
    base = min(base, len(periods)-1)
    index = 100*np.exp(trend-trend[:, base, None])
    counts = data.groupby('period').agg(observations=('unit_key','size'), units=('unit_key','nunique'))
    chart = pd.DataFrame({'period': periods, 'index_median': np.median(index,axis=0),
                          'index_lower': np.quantile(index,.025,axis=0), 'index_upper': np.quantile(index,.975,axis=0)})
    chart = chart.join(counts, on='period').fillna({'observations':0,'units':0})
    chart.to_parquet(output / 'index.parquet', index=False)
    buildings = sorted(data.building_slug.unique())
    offsets = samples(p, 'building_offset')
    rows = []
    for i, building in enumerate(buildings):
        group = data[data.building_slug.eq(building)]
        rows.append({'building_slug':building,'building_name':data.attrs['names'].get(building,building),
                     **interval(100*np.expm1(offsets[:,i])), 'units':group.unit_key.nunique(),'observations':len(group)})
    pd.DataFrame(rows).to_parquet(output / 'building_effects.parquet', index=False)
    beta = samples(p, 'beta')
    pd.DataFrame([{'term':name, **interval(100*np.expm1(beta[:,i]))}
                  for i,name in enumerate(FEATURES)]).to_parquet(output / 'coefficients.parquet', index=False)
    mu = predict(inference, data)
    diagnostic = data[['building_slug','unit','period','asking_rent']].copy()
    diagnostic['fitted_rent'] = np.exp(np.median(mu,axis=0))
    diagnostic['residual_percent'] = 100*(diagnostic.asking_rent/diagnostic.fitted_rent-1)
    diagnostic.to_parquet(output / 'observation_diagnostics.parquet', index=False)
    metadata = {**diagnostic_summary(inference), 'frequency':frequency,
                'observations':len(data),'units':data.unit_key.nunique(),
                'buildings':{b:data.attrs['names'].get(b,b) for b in buildings},
                'coverage':data.attrs['coverage'], 'index_base_period':str(periods[base].date()),
                'excluded_furnished_units':data.attrs['excluded_furnished_units'],
                'training_sha256':hashlib.sha256((output/'training_data.parquet').read_bytes()).hexdigest(),
                'size_log_scale':data.attrs['size_log_scale'],
                'assumptions':[
                    'All available imported rental history is used unless --start is supplied; this is not complete Chelsea coverage.',
                    'Any unit with explicit furnished or Blueground evidence is excluded, including earlier unfurnished history.',
                    'One median rent per unit and calendar period, after deduplicating unit/date/price events.',
                    'Building and unit effects are hierarchically pooled; building offsets are relative to the unweighted modeled-building mean.',
                    'Physical floors are categories; unknown and unsupported first-digit floor guesses form an explicit unknown category.',
                    'Bedrooms and bathrooms have linear log-rent slopes; size uses standardized log square feet with missing-value controls.',
                    'A shared Gaussian random walk models monthly/weekly changes. Student-t residuals reduce outlier influence.',
                    'No signed leases are observed. Histories are selectively available, sparse early periods have limited support, and repeated episodes may remain correlated.',
                    'Unit attributes come from the latest archived listing episode; historical renovations and changes of layout are not modeled.',
                    'Residual charts are in-sample diagnostics, not independent predictive validation.'],
                'validation':validation}
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps({**metadata['coverage'], **diagnostic_summary(inference)},indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=Path('data/apartments.duckdb'))
    parser.add_argument('--frequency',choices=['monthly','weekly'],default='monthly')
    parser.add_argument('--start',help='Optional ISO start date; default uses all history')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--draws',type=int,default=1000)
    parser.add_argument('--tune',type=int,default=1000)
    parser.add_argument('--chains',type=int,default=4)
    parser.add_argument('--validate-from',help='Also refit withholding prices from this date onward')
    parser.add_argument('--validation-draws',type=int,help='Override posterior draws for the withheld-price fit')
    parser.add_argument('--validation-tune',type=int,help='Override tuning draws for the withheld-price fit')
    args = parser.parse_args()
    data, periods = prepare_data(args.db,args.frequency,args.start)
    output = args.output or Path('data/model')/args.frequency
    print(json.dumps(data.attrs['coverage'],indent=2),flush=True)
    validation = None
    if args.validate_from:
        train_mask = data.period < pd.Timestamp(args.validate_from)
        if not train_mask.any() or train_mask.all():
            raise ValueError('Validation split needs both training and withheld periods')
        print('Fitting temporal price holdout...',flush=True)
        validation_draws = args.validation_draws or args.draws
        validation_tune = args.validation_tune or args.tune
        holdout = fit_model(data,periods,args.frequency,validation_draws,validation_tune,args.chains,train_mask)
        held = data.loc[~train_mask]
        predictions = np.exp(np.median(predict(holdout,held),axis=0))
        last_rent = data.loc[train_mask].sort_values('period').groupby('unit_key').asking_rent.last()
        baseline = held.unit_key.map(last_rent)
        seen = baseline.notna().to_numpy()
        comparison = held[['unit_key','period','asking_rent']].copy()
        comparison['predicted_rent'] = predictions
        comparison['last_observed_rent'] = baseline.to_numpy()
        output.mkdir(parents=True,exist_ok=True)
        comparison.to_parquet(output/'validation.parquet',index=False)
        validation = {'from':args.validate_from,'observations':len(held),'previously_seen_unit_observations':int(seen.sum()),
                      'draws_per_chain':validation_draws,'tune_per_chain':validation_tune,'chains':args.chains,
                      'median_absolute_percent_error':float(np.median(np.abs(predictions/held.asking_rent.to_numpy()-1))*100),
                      'seen_unit_model_median_absolute_percent_error':float(np.median(np.abs(predictions[seen]/held.asking_rent.to_numpy()[seen]-1))*100) if seen.any() else None,
                      'seen_unit_last_rent_median_absolute_percent_error':float(np.median(np.abs(baseline.to_numpy()[seen]/held.asking_rent.to_numpy()[seen]-1))*100) if seen.any() else None,
                      **diagnostic_summary(holdout),
                      'limitation':'Prices are withheld; latest archived covariates and full-data size scaling are retained. This is a retrospective price test, not a fully time-causal backtest.'}
        holdout.to_netcdf(output/'validation_posterior.nc')
        print(json.dumps(validation,indent=2),flush=True)
    print('Fitting all eligible history...',flush=True)
    inference = fit_model(data,periods,args.frequency,args.draws,args.tune,args.chains)
    save_outputs(inference,data,periods,args.frequency,output,validation)


if __name__ == '__main__':
    main()

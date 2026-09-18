"""Sequential monthly rent prediction, staleness and empirical interval validation.

Source event dates determine splits. Later collection/interpretation of historical
attributes means this is retrospective research, not a historical information-set
backtest. Interval coverage is measured, never assumed from nominal labels.
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

VERSION = 'chelsea-sequential-monthly-v1'
POLICIES = ('annual_frozen', 'monthly', 'monthly_recent')
STRATA = ('seen_unit', 'new_unit_seen_building', 'new_building')
LEVELS = (.8, .95)


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def familiarity(train, test):
    """Use the current monthly training set for matched strata across policies."""
    return np.where(test.unit_id.isin(set(train.unit_id)), 'seen_unit',
                    np.where(test.building.isin(set(train.building)),
                             'new_unit_seen_building', 'new_building'))


def earlier_history(history, origin, months):
    """Enforce the clock even if a caller supplies current/future outcomes."""
    if history.empty:
        return history.copy()
    dates = pd.to_datetime(history.period)
    return history[(dates < origin) & (dates >= origin-pd.DateOffset(months=months))].copy()


def recent_offset(history, origin, *, min_rows=100):
    recent = earlier_history(history, origin, 3)
    if recent.empty or len(recent) < min_rows or recent.period.nunique() < 3:
        return {'log_offset': 0., 'status': 'insufficient_prior_months_or_rows',
                'rows': len(recent), 'months': 0 if recent.empty else int(recent.period.nunique())}
    residual = np.log(recent.asking_rent/recent.monthly)
    # Equal weight per month avoids allowing the busiest month to set the shift.
    offset = float(residual.groupby(recent.period).median().mean())
    return {'log_offset': offset, 'status': 'estimated', 'rows': len(recent),
            'months': int(recent.period.nunique()),
            'start': str(recent.period.min()), 'end': str(recent.period.max())}


def interval_rules(history, origin, *, min_rows=100):
    """Past-policy residual quantiles, with explicit sparse-stratum fallback.

    All residuals are from prior out-of-time predictions. This is an empirical
    rolling quantile rule, without exchangeability or conformal coverage claims.
    """
    recent = earlier_history(history, origin, 12)
    rules = {}
    for policy in POLICIES:
        rules[policy] = {}
        for stratum in STRATA:
            group = recent if recent.empty else recent[recent.stratum.eq(stratum)]
            enough = lambda x: len(x) >= min_rows and x.period.nunique() >= 3
            scope = 'stratum'
            if not enough(group):
                group = recent
                scope = 'pooled_fallback'
            if not enough(group):
                rules[policy][stratum] = {'status': 'unavailable', 'rows': len(group),
                                         'months': 0 if group.empty else int(group.period.nunique())}
                continue
            residual = np.log(group.asking_rent/group[policy])
            rules[policy][stratum] = {
                'status': 'estimated', 'scope': scope, 'rows': len(group),
                'months': int(group.period.nunique()),
                'start': str(group.period.min()), 'end': str(group.period.max()),
                'quantiles': {str(int(level*100)): np.quantile(
                    residual, [(1-level)/2, (1+level)/2], method='linear').tolist()
                    for level in LEVELS}}
    return rules


def forecast_table(train, test, monthly_log, annual_log, history, origin, *, min_rows=100):
    """Pure forecast policy: target rents are retained for later scoring only."""
    table = test[['unit_id', 'building', 'audit_id', 'period', 'asking_rent']].copy().reset_index(drop=True)
    table['period'] = table.period.dt.strftime('%Y-%m-%d')
    table['stratum'] = familiarity(train, test)
    offset = recent_offset(history, origin, min_rows=min_rows)
    rules = interval_rules(history, origin, min_rows=min_rows)
    table['monthly'] = np.exp(monthly_log)
    table['annual_frozen'] = np.exp(annual_log)
    table['monthly_recent'] = np.exp(monthly_log+offset['log_offset'])
    if not np.isfinite(table[list(POLICIES)].to_numpy()).all() or (table[list(POLICIES)] <= 0).any().any():
        raise ValueError('Nonfinite or nonpositive prediction')
    for policy in POLICIES:
        table[policy+'_interval_scope'] = [rules[policy][s].get('scope', 'unavailable') for s in table.stratum]
        for level in LEVELS:
            label = str(int(level*100))
            for side, index in [('lower', 0), ('upper', 1)]:
                table[f'{policy}_{label}_{side}'] = [
                    float(pred*np.exp(rules[policy][s]['quantiles'][label][index]))
                    if rules[policy][s]['status'] == 'estimated' else None
                    for pred, s in zip(table[policy], table.stratum)]
    return table, {'recent_adjustment': offset, 'interval_rules': rules}


def score(table):
    """Keep unavailable interval denominators and tail misses visible."""
    result = {'rows': len(table), 'buildings': int(table.building.nunique()), 'policies': {}}
    for policy in POLICIES:
        entry = baseline.metrics(table, np.log(table[policy].to_numpy()))
        entry['mean_absolute_log_error'] = float(abs(np.log(table[policy]/table.asking_rent)).mean())
        entry['intervals'] = {}
        for level in LEVELS:
            label = str(int(level*100))
            lower, upper = table[f'{policy}_{label}_lower'], table[f'{policy}_{label}_upper']
            eligible = lower.notna() & upper.notna()
            n = int(eligible.sum())
            interval = {'nominal_percent': int(level*100), 'available_rows': n,
                        'unavailable_rows': len(table)-n}
            if n:
                actual = table.asking_rent[eligible]; lo = lower[eligible]; hi = upper[eligible]
                width = hi-lo
                # Proper interval score combines sharpness with tail misses.
                penalty = 2/(1-level)
                interval.update({
                    'coverage_percent': float(((lo <= actual) & (actual <= hi)).mean()*100),
                    'below_percent': float((actual < lo).mean()*100),
                    'above_percent': float((actual > hi).mean()*100),
                    'median_width_dollars': float(width.median()),
                    'median_width_percent_of_prediction': float((width/table[policy][eligible]).median()*100),
                    'mean_interval_score_dollars': float((width+penalty*(lo-actual).clip(lower=0)
                                                         +penalty*(actual-hi).clip(lower=0)).mean()),
                    'pooled_fallback_rows': int(table.loc[eligible,policy+'_interval_scope'].eq('pooled_fallback').sum())})
            entry['intervals'][label] = interval
        result['policies'][policy] = entry
    return result


def _records(table):
    return table.astype(object).where(pd.notna(table), None).to_dict('records')


def _check_binding(manifest, binding):
    if any(manifest.get(key) != value for key,value in binding.items()):
        raise ValueError('Checkpoint month, membership or dependency mismatch')


def run(dataset, output, *, start_year=2019, end_year=2024, min_rows=100,
        prepare_only=False, max_new_months=None):
    if not 2011 <= start_year <= end_year <= 2024:
        raise ValueError('Choose contiguous development years within 2011–2024')
    if min_rows < 1 or (max_new_months is not None and max_new_months < 1):
        raise ValueError('Row and optional month limits must be positive')
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data, source, coverage = amenities.load_analytical(dataset)
        data = data[data.period < f'{end_year+1}-01-01'].copy()
        origins = pd.date_range(f'{start_year}-01-01', f'{end_year}-12-01', freq='MS')
        splits = []
        for origin in origins:
            train, test = data[data.period < origin], data[data.period.eq(origin)]
            if min(len(train),len(test)) < min_rows:
                raise ValueError(f'Insufficient rows for {origin.date()}')
            splits.append({'month':str(origin.date()), 'train_rows':len(train), 'test_rows':len(test),
                           'train_sha256':contrasts.membership(train), 'test_sha256':contrasts.membership(test),
                           'train_end':str(train.period.max().date()),
                           'strata':{s:int((familiarity(train,test)==s).sum()) for s in STRATA}})
        paths = [Path(module.__file__) for module in
                 (ablation, amenities, baseline, amenities.pricing, contrasts, corrections, research_pipeline)] + [Path(__file__)]
        code = {p.name:p.read_text() for p in paths}
        protocol = {'version':VERSION, 'source_manifest':source, 'coverage':coverage,
                    'splits':splits, 'settings':amenities.SETTINGS, 'unit_effect':True,
                    'iterations':20, 'convergence_threshold':1e-5, 'min_rows':min_rows,
                    'policies':list(POLICIES), 'interval_levels':list(LEVELS),
                    'recent_adjustment':'mean of prior three monthly medians of monthly-model log(actual/prediction); three months and min_rows required, else zero',
                    'interval_rule':'prior 12 calendar months of out-of-time policy residuals; three months and min_rows per familiarity stratum, else pooled fallback or unavailable; linear empirical equal-tail quantiles',
                    'strata_basis':'current monthly training identities for all policies; annual frozen model may not know newly seen units/buildings',
                    'implementation_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in code.items()},
                    'versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','duckdb')},
                    'interpretation':'retrospective source-event-date evaluation using later-collected attributes; no historical information-set or guaranteed interval coverage claim'}
        protocol_hash = _hash(protocol)
        publish_bundle(root/'protocol', {'protocol.json':canonical(protocol)+'\n', **code},
                       {'version':VERSION, 'protocol_sha256':protocol_hash})
        if prepare_only:
            return {'phase':'prepared', 'months':len(splits), 'protocol_sha256':protocol_hash}
        history = pd.DataFrame()
        annual_fit = None; annual_manifest = None
        reports = []; forecast_manifests = []; new_months = 0
        for origin, split in zip(origins,splits):
            month = origin.strftime('%Y-%m')
            train, test = data[data.period < origin], data[data.period.eq(origin)]
            directory = root/month
            binding = {'version':VERSION, 'protocol_sha256':protocol_hash, **split}
            if (directory/'fit'/'complete.json').exists():
                fit_manifest, fit_files = _verified_bundle(directory/'fit', retain={'diagnostics.json'})
                _check_binding(fit_manifest,binding)
                diagnostic = json.loads(fit_files['diagnostics.json'])
                if diagnostic['objective_relative_change'] > 1e-5:
                    raise ValueError('Saved fit did not converge')
                fitted = None
            else:
                print(canonical({'phase':'fitting','month':month,'train':len(train),'test':len(test)}),flush=True)
                fitted = baseline.fit(train, amenities.SETTINGS, iterations=20,
                                      encoder_class=ablation.encoder_class('full'))
                change = fitted['robust_objective_relative_change']
                if change is None or not np.isfinite(change) or change > 1e-5:
                    raise ValueError('Monthly optimizer did not converge')
                diagnostic = {'objective_relative_change':change,'solves':fitted['solves']}
                saved = {'amenities':{'encoder':fitted['encoder'].metadata(),
                                     'beta':fitted['beta'].tolist(),'center':fitted['center']}}
                fit_manifest = publish_bundle(directory/'fit', {'models.json':canonical(saved)+'\n',
                    'diagnostics.json':canonical(diagnostic)+'\n'}, binding)
            if origin.month == 1:
                annual_fit = fitted or amenities.load_fit(directory/'fit')
                annual_manifest = fit_manifest
            dependencies = {**binding, 'fit_manifest_sha256':_hash(fit_manifest),
                            'annual_fit_manifest_sha256':_hash(annual_manifest),
                            'earlier_forecast_chain_sha256':_hash(forecast_manifests)}
            if (directory/'forecast'/'complete.json').exists():
                forecast_manifest, files = _verified_bundle(directory/'forecast',retain={'predictions.jsonl','report.json'})
                _check_binding(forecast_manifest,dependencies)
                table = pd.DataFrame(json.loads(line) for line in files['predictions.jsonl'].decode().split('\n') if line)
                report = json.loads(files['report.json'])
                if (table.audit_id.tolist() != test.audit_id.tolist()
                        or table.unit_id.tolist() != test.unit_id.tolist()
                        or table.period.tolist() != test.period.dt.strftime('%Y-%m-%d').tolist()
                        or table.asking_rent.tolist() != test.asking_rent.tolist()):
                    raise ValueError('Saved forecast rows differ from test membership/order/targets')
            else:
                fitted = fitted or amenities.load_fit(directory/'fit')
                table, rules = forecast_table(train,test,baseline.predict(fitted,test),
                                              baseline.predict(annual_fit,test),history,origin,min_rows=min_rows)
                report = {'month':month, 'annual_horizon_months':origin.month,
                          'monthly_horizon_months':1, 'fit_diagnostics':diagnostic,
                          **rules, 'metrics':score(table),
                          'strata':{s:score(table[table.stratum.eq(s)]) for s in STRATA if table.stratum.eq(s).any()}}
                forecast_manifest = publish_bundle(directory/'forecast', {
                    'predictions.jsonl':''.join(canonical(r)+'\n' for r in _records(table)),
                    'report.json':canonical(report)+'\n'}, dependencies)
                new_months += 1
            reports.append(report); forecast_manifests.append(_hash(forecast_manifest))
            history = pd.concat([history,table],ignore_index=True) if not history.empty else table.copy()
            (root/'progress.json').write_text(canonical({'phase':'running','completed_months':len(reports),
                'total_months':len(origins),'last_month':month})+'\n')
            if max_new_months is not None and new_months >= max_new_months and len(reports) < len(splits):
                return {'phase':'paused_at_declared_limit','completed_months':len(reports)}
        if any(digest(path) != protocol['implementation_sha256'][path.name] for path in paths):
            raise ValueError('Implementation changed during monthly evaluation')
        years = sorted({p[:4] for p in history.period})
        summary = {'version':VERSION, 'months':len(reports), 'monthly_reports':reports,
                   'pooled':score(history),
                   'years':{year:score(history[history.period.str.startswith(year)]) for year in years},
                   'strata':{s:score(history[history.stratum.eq(s)]) for s in STRATA if history.stratum.eq(s).any()},
                   'horizons':{str(m):score(history[pd.to_datetime(history.period).dt.month.eq(m)]) for m in range(1,13)},
                   'equal_month_mean_log_rmse':{policy:float(np.mean([r['metrics']['policies'][policy]['log_rmse'] for r in reports])) for policy in POLICIES},
                   'limitations':['Retrospective later-collected attributes and corrected identities; not historical information-set forecasting.',
                                  'Previously used development years; no untouched final-test claim.',
                                  'Prediction intervals are empirical sequential residual quantiles; serial/building dependence and market shifts can invalidate nominal coverage.',
                                  'Sparse familiarity strata use explicitly labeled pooled intervals or no interval.',
                                  'Monthly training uses reconstructed source-event dates; no current availability or signed-lease inference.']}
        manifest = publish_bundle(root/'summary', {'report.json':canonical(summary)+'\n'},
                                  {'version':VERSION, 'protocol_sha256':protocol_hash,
                                   'forecast_chain_sha256':_hash(forecast_manifests)})
        (root/'progress.json').write_text(canonical({'phase':'complete','completed_months':len(reports),'total_months':len(origins)})+'\n')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start-year',type=int,default=2019)
    parser.add_argument('--end-year',type=int,default=2024)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--max-new-months',type=int)
    args = parser.parse_args()
    print(canonical(run(args.dataset,args.output,start_year=args.start_year,end_year=args.end_year,
                        prepare_only=args.prepare_only,max_new_months=args.max_new_months)))

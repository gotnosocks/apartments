"""Verified, convergence-gated descriptive Bayesian rental research reports.

Consumes saved inference products only. No sampling, fitting or current-source
code imports are needed to inspect a frozen experiment.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments import reviewed_source_lineage, reviewed_lineage_cache
from . import bayesian_floor_elevator_contract as interaction_contract
from . import bayesian_floor_spline_contract as spline_contract

VERSION = 'verified-bayesian-feature-report-v2'
EXPERIMENT_VERSION = 'observable-bayesian-bathroom-experiment-v2'
EXPERIMENT_V3 = 'observable-bayesian-bathroom-experiment-v3'
EXPERIMENT_V4 = 'observable-bayesian-floor-experiment-v4'
EXPERIMENT_V5 = interaction_contract.EXPERIMENT
EXPERIMENT_SPLINE = spline_contract.EXPERIMENT
EXPERIMENT_VERSIONS = {EXPERIMENT_VERSION, EXPERIMENT_V3, EXPERIMENT_V4, EXPERIMENT_V5, EXPERIMENT_SPLINE}
DATASET_VERSIONS = {'reported-bathroom-counts-projection-v1', 'reviewed-bathroom-counts-projection-v1',
                    'reviewed-scope-composition-projection-v2', 'reviewed-capture-refreshed-analysis-v1'} | reviewed_source_lineage.VERSIONS
REQUIRED = {'summary.json', 'diagnostics.json', 'derived-diagnostics.json', 'bathroom-contrasts.json',
            'residuals.jsonl', 'coefficients.json', 'group-effects.jsonl', 'feature-design.json',
            'time-design.json', 'time-design.npz', 'posterior.nc'}
V3_REQUIRED = {'graph-configuration.json', 'residual-scales.json'}
V4_REQUIRED = {'floor-contrasts.json'}
V5_REQUIRED = {'interaction-design.json', 'floor-elevator-contrasts.json', 'floor-elevator-diagnostics.csv'}
FLOOR_INTERPRETATION = 'Joint floor-feature component contrasts, holding other encoded terms fixed. All retained draws; unconstrained signs. Not causal, not physical-height effects, and sparse overlap remains explicit.'
LIMITATIONS = [
    'Conditional posterior associations depend on the cohort, advertised source measurements, likelihood and priors. They are not causal renovation values or personal willingness to pay.',
    'The target is gross advertised asking rent, not a signed lease. Historical initial asks and current capture asks use different sampling rules. Historical attributes can have been collected after their price dates.',
    'Current observations deliberately contribute to the fit. Residuals are in-sample review signals, not independent predictions or automatic bargain scores.',
    'Endpoint counts describe observed support, not matched comparisons or independent replications. Repeated ads and units share information; scarce layouts remain prior-sensitive.',
    'Bathroom composition requires complete integer full/half counts, at least one full bath, scalar agreement and no unresolved flags. Unknown rows remain in the fit through a reporting indicator; missing evidence is not zero baths.',
    'Shared bathroom/toilet access, flexible bedrooms, regulation claims, basement position and bundled luxury amenities require source review. The posterior does not protect against omitted features or source errors.',
    'Building offsets and within-building unit offsets absorb unmodeled attributes. Their rankings depend on shrinkage and the chosen parameterization, and are not standalone market premiums.',
    'Intervals for fitted rent describe uncertainty in the latent conditional median asking rent. They are not posterior predictive intervals, transaction-price intervals or arithmetic mean rent.',
    'Passing diagnostics establishes numerical checks for this fit, not causal identification, a robust prior-sensitivity result or complete Chelsea market coverage.',
]


def jsonl(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def verify_reporting_recovery(protocol_hash, fit_manifest, recovery):
    """Reporting overrides preserve the sampled posterior and completed diagnostics."""
    files = fit_manifest['files']
    diagnostics = {'diagnostics.json', 'derived-diagnostics.json',
                   'parameter-diagnostics.csv', 'derived-diagnostics.csv'}
    code = {'recover_bayesian_reports.py', 'bayesian_report_cache.py', 'bayesian_feature_report.py'}
    if (recovery.get('version') != 'completed-diagnostics-report-recovery-v1'
            or recovery.get('protocol_sha256') != protocol_hash
            or recovery.get('posterior_sha256') != files['posterior.nc']
            or set(recovery.get('completed_diagnostic_sha256', {})) != diagnostics
            or any(files.get(k) != v for k, v in recovery['completed_diagnostic_sha256'].items())
            or set(recovery.get('implementation_sha256', {})) != code
            or any(files.get(k) != v for k, v in recovery['implementation_sha256'].items())
            or type(recovery.get('maximum_source_block_bytes')) is not int
            or not 0 < recovery['maximum_source_block_bytes'] <= 8*1024*1024):
        raise ValueError('Reporting recovery differs from inference products')
    return recovery


def verify_reporting_cache(protocol, protocol_hash, fit_manifest, cache):
    files = fit_manifest['files']
    if (cache.get('version') != 'bayesian-unit-report-cache-v1'
            or cache.get('protocol_sha256') != protocol_hash
            or cache.get('posterior_sha256') != files['posterior.nc']
            or cache.get('implementation_sha256') != files.get('bayesian_report_cache.py')
            or not isinstance(cache.get('implementation_sha256'), str)
            or cache.get('all_retained_draws') is not True
            or cache.get('sample_order') != 'chain_major_then_draw'
            or any(cache.get(k) != protocol[k] for k in ('chains', 'draws', 'units'))
            or type(cache.get('maximum_source_block_bytes')) is not int
            or not 0 < cache['maximum_source_block_bytes'] <= 8*1024*1024):
        raise ValueError('Reporting cache differs from inference products')
    return cache


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_interval(value):
    if not isinstance(value, dict) or any(not finite(value.get(k)) for k in ('median', 'lower_95', 'upper_95', 'probability_positive')):
        raise ValueError('Invalid posterior interval')
    if not value['lower_95'] <= value['median'] <= value['upper_95'] or not 0 <= value['probability_positive'] <= 1:
        raise ValueError('Invalid posterior interval ordering or probability')


def check_diagnostics(summary, parameters, derived):
    if summary.get('status') != 'exploratory_converged':
        raise ValueError('Research report requires exploratory_converged status; diagnostic-only fits are refused')
    if summary.get('diagnostics') != parameters or summary.get('derived_diagnostics') != derived:
        raise ValueError('Summary diagnostics differ from saved diagnostics')
    for kind, diag in [('parameter', parameters), ('derived', derived)]:
        required = ('max_rhat', 'min_ess_bulk', 'min_ess_tail', 'min_bfmi', 'divergences', 'maxdepth_reached', 'nonfinite_diagnostics')
        if (diag.get('acceptable') is not True or any(not finite(diag.get(k)) for k in required)
                or diag['max_rhat'] >= 1.01 or diag['min_ess_bulk'] < 400 or diag['min_ess_tail'] < 400
                or diag['min_bfmi'] < .3 or any(diag[k] != 0 for k in ('divergences', 'maxdepth_reached', 'nonfinite_diagnostics'))):
            raise ValueError(f'Unacceptable {kind} diagnostics')


def composition(row):
    try:
        full, half, total = (float(row[k]) for k in ('reported_full_bathrooms', 'reported_half_bathrooms', 'bathrooms'))
        evidence = row['bathroom_count_evidence']
    except (KeyError, TypeError, ValueError):
        return None
    if (not isinstance(evidence, dict) or evidence.get('flags') or not all(math.isfinite(v) for v in (full, half, total))
            or full < 1 or half < 0 or not full.is_integer() or not half.is_integer()
            or not math.isclose(total, full+.5*half, rel_tol=0, abs_tol=1e-8)):
        return None
    return int(full), int(half)


def support(rows):
    return {'rows': len(rows), 'units': len({r['unit_id'] for r in rows}),
            'buildings': len({r['building'] for r in rows})}


def verify_residual_scales(protocol, configuration, scales, rows):
    """Validate saved v3 scale summaries without importing or fitting its graph."""
    mode = protocol.get('residual_scale')
    if (mode not in ('shared', 'bedroom') or not isinstance(configuration, dict)
            or configuration != protocol.get('graph_configuration')
            or configuration.get('version') not in {'bayesian-feature-residual-graph-v3','bayesian-feature-residual-graph-v3-centered'}
            or configuration.get('residual_scale') != mode):
        raise ValueError('Residual graph configuration differs from protocol')
    for config_key, protocol_key in [('beta_prior_multiplier', 'prior_multiplier'),
            ('building_prior_scale', 'building_prior_scale'), ('unit_prior_scale', 'unit_prior_scale')]:
        value = configuration.get(config_key)
        expected = protocol.get(protocol_key)
        if not finite(value) or value <= 0 or not finite(expected) or value != expected:
            raise ValueError('Residual graph prior settings differ from protocol')
    if (not finite(configuration.get('student_t_nu')) or configuration['student_t_nu'] != 5
            or not finite(configuration.get('residual_sigma_prior_scale'))
            or configuration['residual_sigma_prior_scale'] != .25
            or configuration.get('residual_bedroom_offset_scale_prior') != (.3 if mode == 'bedroom' else None)):
        raise ValueError('Unsupported residual graph likelihood or scale priors')
    if protocol.get('residual_parameterization','noncentered') not in ('centered','noncentered'):
        raise ValueError('Unknown residual hierarchy parameterization')
    hierarchy = configuration.get('residual_bedroom_parameterization')
    centered = configuration['version'] == 'bayesian-feature-residual-graph-v3-centered'
    if ((centered and (mode != 'bedroom' or hierarchy != 'centered'))
            or (not centered and hierarchy is not None)
            or (mode == 'bedroom' and protocol.get('residual_parameterization', 'noncentered') != ('centered' if centered else 'noncentered'))):
        raise ValueError('Residual hierarchy parameterization differs from protocol')
    cells = defaultdict(list)
    if mode == 'bedroom':
        for row in rows:
            value = row.get('bedrooms')
            if not finite(value) or value < 0 or value > 2147483647 or int(value) != value:
                raise ValueError('Bedroom residual scales require valid source bedroom counts')
            cells[int(value)].append(row)
        if len(cells) < 2:
            raise ValueError('Bedroom residual scales require at least two source levels')
    levels = sorted(cells)
    counts = [len(cells[level]) for level in levels]
    if (configuration.get('residual_bedroom_levels') != levels
            or configuration.get('residual_bedroom_counts') != counts
            or any(type(v) is not int for key in ('residual_bedroom_levels','residual_bedroom_counts')
                   for v in configuration[key])):
        raise ValueError('Residual bedroom levels or counts differ from source')
    if (not isinstance(scales, dict) or scales.get('version') != 'bayesian-residual-scale-summary-v1'
            or scales.get('graph_configuration') != configuration
            or not finite(scales.get('student_t_nu')) or scales['student_t_nu'] != 5):
        raise ValueError('Residual scale summary configuration differs from protocol')
    def positive_interval(value):
        check_interval(value)
        if value['lower_95'] <= 0 or value['probability_positive'] != 1:
            raise ValueError('Residual scale intervals must be positive with probability one')
    positive_interval(scales.get('global_sigma'))
    items = scales.get('by_bedroom')
    if (not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
            or [item.get('bedrooms') for item in items] != levels):
        raise ValueError('Residual scale summary bedroom membership differs from source')
    for item in items:
        if (type(item['bedrooms']) is not int or item.get('support') != support(cells[item['bedrooms']])
                or any(type(v) is not int for v in item.get('support', {}).values())):
            raise ValueError('Residual scale support differs from source')
        positive_interval(item.get('sigma'))
    role = 'Shared observation scale' if mode == 'shared' else 'Geometric mean of bedroom-level scales (equal level weights)'
    units = 'Log advertised asking rent; Student-t scale, not its standard deviation.'
    interpretation = ('Separate conditional 95% posterior intervals. Residual variation is not latent conditional-median uncertainty. '
                      'Student-t standard deviation equals scale * sqrt(5/3); no mean or feature contribution changed by this summary.')
    if (scales.get('global_sigma_role') != role or scales.get('scale_units') != units
            or scales.get('interpretation') != interpretation):
        raise ValueError('Residual scale interpretation differs from its statistical definition')
    return scales


def verify_contrasts(contrasts, rows, summary):
    cells = defaultdict(list)
    for row in rows:
        counts = composition(row)
        if counts is not None:
            cells[(float(row['bedrooms']), *counts)].append(row)
    def cell(beds, counts):
        if len(counts) != 2:
            raise ValueError('Invalid bathroom state')
        return support(cells[(float(beds), *counts)])
    increments, seen = [], set()
    for item in contrasts['increments']:
        before, after = item['before_full_half'], item['after_full_half']
        a, b = cell(item['bedrooms'], before), cell(item['bedrooms'], after)
        if item['support_before'] != a or item['support_after'] != b or item['supported_endpoints'] != bool(a['rows'] and b['rows']):
            raise ValueError('Bathroom increment support differs from source')
        check_interval(item['log_effect']); check_interval(item['percent_effect'])
        key = (item['bedrooms'], *before, *after)
        if key not in seen and a['rows'] and b['rows'] and before[1] == after[1] == 0 and after[0] == before[0]+1:
            increments.append(item)
        seen.add(key)
    halves = []
    for item in contrasts['half_bath_increments']:
        before = (item['full_bathrooms'], item['before_half'])
        after = (item['full_bathrooms'], item['after_half'])
        a, b = cell(item['bedrooms'], before), cell(item['bedrooms'], after)
        if (item['support_before'] != a or item['support_after'] != b
                or item['supported_endpoints'] != bool(a['rows'] and b['rows'])
                or after[1] != before[1]+1):
            raise ValueError('Half-bath increment support differs from source')
        if item['encoded_contrast']:
            check_interval(item['log_effect']); check_interval(item['percent_effect'])
        elif item['log_effect'] is not None or item['percent_effect'] is not None:
            raise ValueError('Unencoded half-bath contrast has an interval')
        if a['rows'] and b['rows'] and item['encoded_contrast']:
            halves.append(item)
    balances = []
    if contrasts['balance'] != summary['bathroom_balance']:
        raise ValueError('Summary bathroom contrasts differ from saved contrasts')
    for item in contrasts['balance']:
        beds = item['bedrooms']
        expected = [cell(beds, (baths, 0)) for baths in (beds-1, beds, beds+1)]
        if item['support'] != expected:
            raise ValueError('Bathroom balance support differs from source')
        check_interval(item['difference'])
        p = item['probability_first_increment_larger']
        if not finite(p) or not 0 <= p <= 1 or p != item['difference']['probability_positive']:
            raise ValueError('Invalid balance probability')
        if all(s['rows'] for s in expected):
            balances.append(item)
    return {'full_bath_increments': increments, 'half_bath_increments': halves, 'net_balance': balances,
            'omitted_unsupported_or_unencoded': {'full_or_duplicate_saved': len(contrasts['increments'])-len(increments),
                'half': len(contrasts['half_bath_increments'])-len(halves), 'balance': len(contrasts['balance'])-len(balances)},
            'held_fixed': 'Building, unit, date, square footage and other observed features. Net balance compares full bathrooms minus bedrooms; a half bath does not eliminate a shortage of full baths.',
            'balance_scale': 'Difference of joint log increments: (-1 to 0) minus (0 to +1). Computed within posterior draws, preserving coefficient covariance; not a difference in percentage points.'}


def group_support(rows):
    return {**support(rows), 'advertisements': len({r['source_listing_id'] for r in rows}),
            'first_month': min(r['period'] for r in rows), 'last_month': max(r['period'] for r in rows),
            'median_asking_rent': statistics.median(float(r['asking_rent']) for r in rows)}


def group_rankings(groups, rows, top):
    source = {'building': defaultdict(list), 'unit': defaultdict(list)}
    for row in rows:
        source['building'][row['building']].append(row)
        source['unit'][row['unit_id']].append(row)
    seen, enriched = set(), []
    for item in groups:
        kind, identity = item['kind'], item['id']
        if kind not in source or identity not in source[kind] or (kind, identity) in seen:
            raise ValueError('Group effect membership differs from source')
        seen.add((kind, identity))
        check_interval(item['log_effect']); check_interval(item['percent_effect'])
        original = source[kind][identity]
        example = min(original, key=lambda r: r['audit_id'])
        enriched.append({**item, 'support': group_support(original),
                         'canonical_unit_url': example.get('canonical_unit_url') if kind == 'unit' else None,
                         'example_advertisement_url': 'https://streeteasy.com/rental/'+str(example['source_listing_id'])})
    if seen != {(kind, key) for kind, items in source.items() for key in items}:
        raise ValueError('Missing group effects')
    result = []
    for kind in ('building', 'unit'):
        for tail, sign in [('positive', 1), ('negative', -1)]:
            selected = sorted((r for r in enriched if r['kind'] == kind and sign*r['log_effect']['median'] > 0),
                              key=lambda r: (-sign*r['log_effect']['median'], r['id']))[:top]
            result.extend({**r, 'tail': tail, 'rank_in_tail': i+1} for i, r in enumerate(selected))
    return result


def residual_cases(residuals, rows, top):
    source = {r['audit_id']: r for r in rows}
    if len(source) != len(rows) or len(residuals) != len(rows):
        raise ValueError('Residual membership differs from source')
    seen = set()
    for item in residuals:
        row = source.get(item['audit_id'])
        if row is None or item['audit_id'] in seen or any(str(item[k]) != str(row[k]) for k in ('unit_id','building','period','source_listing_id')):
            raise ValueError('Residual identity differs from source')
        seen.add(item['audit_id'])
        fields = ('asking_rent','fitted_rent','latent_rent_lower_95','latent_rent_upper_95','residual_dollars','residual_log')
        if any(not finite(item.get(k)) for k in fields):
            raise ValueError('Invalid residual value')
        ask, fit = item['asking_rent'], item['fitted_rent']
        if (ask != float(row['asking_rent']) or fit <= 0 or ask <= 0
                or not 0 < item['latent_rent_lower_95'] <= fit <= item['latent_rent_upper_95']
                or not math.isclose(item['residual_dollars'], ask-fit, rel_tol=1e-10, abs_tol=1e-8)
                or not math.isclose(item['residual_log'], math.log(ask/fit), rel_tol=1e-10, abs_tol=1e-10)):
            raise ValueError('Residual target or arithmetic differs from source')
    cases = []
    for tail, sign in [('positive', 1), ('negative', -1)]:
        units = set()
        for item in sorted(residuals, key=lambda r: (-sign*r['residual_log'], r['audit_id'])):
            if sign*item['residual_log'] <= 0 or item['unit_id'] in units:
                continue
            units.add(item['unit_id'])
            row = source[item['audit_id']]
            cases.append({**item, 'tail': tail, 'source_record': row,
                          'advertisement_url': 'https://streeteasy.com/rental/'+str(item['source_listing_id'])})
            if len(units) == top:
                break
    current = [{**r, 'source_record': source[r['audit_id']],
                'advertisement_url': 'https://streeteasy.com/rental/'+str(r['source_listing_id'])}
               for r in residuals if source[r['audit_id']].get('analysis_price_basis') == 'current_capture_gross_ask']
    return cases, current


def coefficient_tables(coefficients, design):
    if [r['feature'] for r in coefficients] != design['features']:
        raise ValueError('Coefficient features differ from saved design')
    values, reporting, omitted = [], [], []
    for item in coefficients:
        check_interval(item)
        name = item['feature']
        if '.contrast_' in name:
            omitted.append(name)
            continue
        meta = design.get('numeric', {}).get(name)
        scale = 'Encoded threshold or log feature; interpret jointly with related columns.'
        if meta:
            scale = f"One training standard deviation ({meta['scale']:.8g} raw units); centered at {meta['center']:.8g}. This is not a per-floor or per-attribute-unit premium."
        if name.startswith('listed_floor_spline_'):
            scale = 'Regularized natural-spline basis coefficient; interpret joint floor contrasts, not individual basis coefficients as floor premiums.'
        if name.startswith('bedrooms_gt_'):
            scale = 'Bedroom threshold coefficient with within-bedroom area normalization held fixed; not a fixed-square-footage bedroom counterfactual.'
        if name == 'log_size_within_bedrooms':
            scale = 'One log unit of size relative to the training median for that bedroom count.'
        is_reporting = name.endswith('.unknown') or name in ('size_missing','bathroom_composition_unknown')
        if is_reporting:
            scale = 'Unknown/missing versus recorded evidence: a reporting association, not an amenity value.'
        (reporting if is_reporting else values).append({**item, 'encoded_unit': scale})
    return {'encoded_value_coefficients': values, 'reporting_coefficients': reporting,
            'omitted_category_basis_coefficients': omitted,
            'interpretation': 'Raw encoded log coefficients with 95% posterior intervals, not standalone physical premiums. Joint bathroom contrasts above are the interpretable price comparisons. Positive-only exposures have no varying magnitude coefficient; their unknown indicators describe reporting.'}


def verify_floor_contrasts(protocol, design, floors, rows, summary):
    """Bind floor endpoints, gaps, priors and diagnostic gates to source facts."""
    from apartments import pricing
    def value(row):
        normalized = pricing._normalize(row)
        return pricing._numeric_feature('listed_floor', normalized.get('listed_floor'))
    cells = defaultdict(list)
    for row in rows:
        observed = value(row)
        if observed is not None: cells[observed].append(row)
    levels = sorted(cells)
    scale = protocol.get('floor_increment_prior_scale')
    if (protocol.get('feature_design_version') != 'observed-listed-floor-increment-design-v1'
            or design.get('version') != protocol['feature_design_version']
            or not finite(scale) or scale <= 0 or design.get('floor_increment_prior_scale') != scale
            or any(obj.get('floor_levels') != levels or obj.get('floor_thresholds') != levels[:-1]
                   for obj in (protocol, design, floors))
            or floors.get('version') != 'joint-listed-floor-component-contrasts-v1'
            or floors.get('interpretation') != FLOOR_INTERPRETATION
            or floors.get('draws') != protocol['chains']*protocol['draws']
            or summary.get('floor_diagnostics') != floors.get('diagnostics')
            or 'listed_floor' in design['features']):
        raise ValueError('Floor design, source support, priors or diagnostics differ')
    expected_names = ['listed_floor_gt_'+format(k,'.17g') for k in levels[:-1]]
    if [n for n in design['features'] if n.startswith('listed_floor_gt_')] != expected_names:
        raise ValueError('Floor coefficient inventory differs from observed thresholds')
    pairs = list(zip(levels[:-1],levels[1:]))
    if len(levels)>2: pairs.append((levels[0],levels[-1]))
    items = floors.get('contrasts', [])
    if [(r.get('lower_floor'),r.get('upper_floor')) for r in items] != pairs:
        raise ValueError('Floor contrast endpoints differ from observed support')
    if pairs:
        diag = floors['diagnostics']
        check_diagnostics({'status':'exploratory_converged','diagnostics':diag,'derived_diagnostics':diag},diag,diag)
    elif floors['diagnostics'] != {'acceptable':True,'deterministic':True,'reason':'No varying observed floor contrast'}:
        raise ValueError('Invalid no-contrast floor diagnostics')
    for item, (low, high) in zip(items,pairs):
        for label, level in [('lower',low),('upper',high)]:
            if item.get('support_'+label) != {'level':level, **support(cells[level])}:
                raise ValueError('Floor endpoint counts differ from source')
        adjacent = levels.index(high) == levels.index(low)+1
        if item.get('kind') != ('adjacent_observed_levels' if adjacent else 'observed_range'):
            raise ValueError('Floor contrast kind differs')
        overlap = item.get('adjacent_overlap')
        if adjacent:
            if (not isinstance(overlap,dict)
                    or overlap.get('lower_supported_level') != low or overlap.get('upper_supported_level') != high
                    or overlap.get('shared_buildings') != len({r['building'] for r in cells[low]} & {r['building'] for r in cells[high]})
                    or overlap.get('shared_units') != len({r['unit_id'] for r in cells[low]} & {r['unit_id'] for r in cells[high]})):
                raise ValueError('Floor endpoint overlap differs from source')
        elif overlap is not None:
            raise ValueError('Unexpected adjacent overlap for range contrast')
        for kind in ('log_effect','percent_effect'): check_interval(item[kind])
        if item['log_effect']['probability_positive'] != item['percent_effect']['probability_positive']:
            raise ValueError('Floor sign probabilities disagree')
        for bound in ('lower_95','median','upper_95'):
            if not math.isclose(item['percent_effect'][bound],100*math.expm1(item['log_effect'][bound]),rel_tol=1e-10,abs_tol=1e-10):
                raise ValueError('Floor log and percentage intervals disagree')
    return floors


def build_report(experiment, dataset, top=5):
    if not isinstance(top, int) or not 1 <= top <= 50:
        raise ValueError('Choose 1–50 cases per tail')
    experiment, dataset = Path(experiment), Path(dataset)
    pm, pf = _verified_bundle(experiment/'protocol', retain={'protocol.json',
        'floor-block-parity.json', 'floor-block-parity-manifest.json'})
    protocol = json.loads(pf['protocol.json'])
    experiment_version = protocol.get('version')
    if experiment_version not in EXPERIMENT_VERSIONS or pm.get('version') != experiment_version:
        raise ValueError('Only supported Bayesian fits with derived diagnostics can be reported')
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    if pm.get('protocol_sha256') != ph or any(pm['files'].get(name) != value for name, value in protocol['implementation_sha256'].items()):
        raise ValueError('Invalid protocol or archived implementation binding')
    required = REQUIRED | (V3_REQUIRED if experiment_version in (EXPERIMENT_V3,EXPERIMENT_V4,EXPERIMENT_V5,EXPERIMENT_SPLINE) else set())
    if experiment_version in (EXPERIMENT_V4,EXPERIMENT_SPLINE): required |= V4_REQUIRED
    if experiment_version == EXPERIMENT_V5: required |= V5_REQUIRED
    from . import bayesian_disk_protocol as disk_protocol
    disk_execution = disk_protocol.verify_protocol(protocol)
    from . import bayesian_floor_execution as execution
    execution.verify_protocol(protocol)
    block_execution = execution.verify_archived_proof(protocol, pf)
    if disk_execution:
        if protocol['implementation_sha256'].get('bayesian_disk_protocol.py') != digest(Path(disk_protocol.__file__)):
            raise ValueError('Disk protocol verifier differs from archived implementation')
        required |= {'storage.json','trace-manifest.json'}
    fm, ff = _verified_bundle(experiment/'fit', retain=(required-{'posterior.nc','time-design.npz'})|{'reporting-recovery.json','reporting-cache.json','floor-report-recovery.json','pre-floor-summary.json','bayesian_feature_experiment_v4.py'})
    if fm.get('version') != experiment_version or fm.get('protocol_sha256') != ph or not required <= fm['files'].keys():
        raise ValueError('Fit protocol mismatch or missing inference products')
    if block_execution:
        expected_design = json.loads(pf['floor-block-parity.json']).get('design_sha256', {})
        actual_design = {name: sha for name, sha in fm['files'].items() if name.endswith('design.json')}
        if not expected_design or expected_design != actual_design:
            raise ValueError('Archived floor block proof differs from fitted design files')
    recovery = (verify_reporting_recovery(ph, fm, json.loads(ff['reporting-recovery.json']))
                if 'reporting-recovery.json' in ff else None)
    report_cache = (verify_reporting_cache(protocol, ph, fm, json.loads(ff['reporting-cache.json']))
                    if 'reporting-cache.json' in ff else None)
    if 'bayesian_report_cache.py' in fm['files'] and recovery is None and report_cache is None:
        raise ValueError('Missing reporting execution binding')
    if disk_execution:
        execution.verify_products(protocol,json.loads(ff['storage.json']),
            json.loads(ff['trace-manifest.json']),fm['files']['posterior.nc'])
    summary = json.loads(ff['summary.json'])
    floor_recovery = None
    if 'floor-report-recovery.json' in ff:
        from .recover_floor_report import verify_recovery
        floor_recovery = verify_recovery(protocol,ph,fm,json.loads(ff['floor-report-recovery.json']),
            (experiment/'protocol/bayesian_feature_experiment_v4.py').read_text(),
            ff['bayesian_feature_experiment_v4.py'].decode(),json.loads(ff['pre-floor-summary.json']),summary)
    if summary.get('protocol_sha256') != ph:
        raise ValueError('Summary protocol mismatch')
    parameters, derived = (json.loads(ff[name]) for name in ('diagnostics.json','derived-diagnostics.json'))
    check_diagnostics(summary, parameters, derived)
    sidecar = reviewed_source_lineage.reviewed_cohort_quarantine.SIDECAR
    elevator_sidecar = reviewed_source_lineage.elevator_corrections.SIDECAR
    floor_label_sidecar = reviewed_source_lineage.floor_label_projection.SIDECAR
    expanded_floor_sidecar = reviewed_source_lineage.expanded_floor_projection.SIDECAR
    direct_floor_sidecar = reviewed_source_lineage.direct_floor_projection.SIDECAR
    residual_scope_sidecar = reviewed_source_lineage.residual_scope_projection.SIDECAR
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl', sidecar, elevator_sidecar, floor_label_sidecar, expanded_floor_sidecar, residual_scope_sidecar, direct_floor_sidecar})
    if (sm.get('version') not in DATASET_VERSIONS or protocol.get('source_version') != sm.get('version')
            or digest(dataset/'complete.json') != protocol['source_manifest_sha256']
            or sm['files'].get('observations.jsonl') != protocol['source_observations_sha256']):
        raise ValueError('Source dataset does not match the fitted protocol')
    rows = jsonl(sf['observations.jsonl'])
    if sm['version'] in reviewed_source_lineage.VERSIONS:
        reviewed_lineage_cache.verified_bundle_lineage(sm, sf)
    if (len(rows) != protocol['rows'] or len({r['unit_id'] for r in rows}) != protocol['units']
            or len({r['building'] for r in rows}) != protocol['buildings']
            or sum(r.get('analysis_price_basis') == 'current_capture_gross_ask' for r in rows) != protocol['current_rows']
            or len({(r['unit_id'],r['period']) for r in rows}) != len(rows)):
        raise ValueError('Cohort counts or membership differ from protocol')
    noise = None
    if experiment_version in (EXPERIMENT_V3,EXPERIMENT_V4,EXPERIMENT_V5,EXPERIMENT_SPLINE):
        noise = verify_residual_scales(protocol, json.loads(ff['graph-configuration.json']),
                                       json.loads(ff['residual-scales.json']), rows)
    design, time_design = (json.loads(ff[name]) for name in ('feature-design.json','time-design.json'))
    if experiment_version == EXPERIMENT_V5:
        design = interaction_contract.merge_design(protocol, design,
            json.loads(ff['interaction-design.json']), rows, summary)
    if (design['spec'] != protocol['specification'] or design['support'] != summary['design_support']
            or design['support']['rows'] != len(rows)
            or set(time_design['buildings']) != {r['building'] for r in rows}
            or set(time_design['unit_ids']) != {r['unit_id'] for r in rows}):
        raise ValueError('Saved design differs from fitted cohort')
    known = sum(composition(r) is not None for r in rows)
    if design['support']['bathroom_composition_known'] != known:
        raise ValueError('Bathroom knownness differs from saved design')
    floors = (verify_floor_contrasts(protocol,design,json.loads(ff['floor-contrasts.json']),rows,summary)
              if experiment_version == EXPERIMENT_V4 else None)
    if experiment_version == EXPERIMENT_SPLINE:
        floors = spline_contract.verify_contrasts(protocol,design,json.loads(ff['floor-contrasts.json']),rows,summary)
    floor_elevator = (interaction_contract.verify_contrasts(protocol, design,
        json.loads(ff['floor-elevator-contrasts.json']), rows, summary, check_interval)
        if experiment_version == EXPERIMENT_V5 else None)
    contrasts = verify_contrasts(json.loads(ff['bathroom-contrasts.json']), rows, summary)
    coefficients = coefficient_tables(json.loads(ff['coefficients.json']), design)
    groups = group_rankings(jsonl(ff['group-effects.jsonl']), rows, top)
    residuals = jsonl(ff['residuals.jsonl'])
    cases, current = residual_cases(residuals, rows, top)
    median_error = statistics.median(abs(r['residual_log']) for r in residuals)
    if not math.isclose(median_error, summary['median_absolute_log_residual'], rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError('Summary residual metric differs from saved residuals')
    method = {k: protocol[k] for k in ('specification','likelihood','bathroom_policy','uncertainty','chains','draws','tune','prior_multiplier')}
    method.update(residual_scale=protocol['residual_scale'] if noise else 'shared',
                  building_prior_scale=protocol['building_prior_scale'] if noise else .35,
                  unit_prior_scale=protocol['unit_prior_scale'] if noise else .25)
    if experiment_version == EXPERIMENT_SPLINE:
        method.update({k:protocol[k] for k in spline_contract.FIELDS})
    elif floors is not None or floor_elevator is not None:
        method.update(feature_design_version=protocol['feature_design_version'],
                      floor_increment_prior_scale=protocol['floor_increment_prior_scale'])
    if floor_elevator is not None:
        method.update({k: protocol[k] for k in ('interaction_mode', 'interaction_prior_scale',
                                               'interaction_thresholds', 'interaction_policy')})
    return {'version': VERSION, 'experiment_version': experiment_version, 'status': summary['status'], 'protocol_sha256': ph,
            'reporting_recovery': recovery,
            'reporting_cache': report_cache,
            'floor_reporting_recovery': floor_recovery,
            'source_manifest_sha256': protocol['source_manifest_sha256'],
            'source_observations_sha256': protocol['source_observations_sha256'],
            'source_version': sm['version'], 'experiment': str(experiment.resolve()),
            'cohort': {'rows': len(rows), 'units': protocol['units'], 'buildings': protocol['buildings'],
                       'current_rows': protocol['current_rows'], 'bathroom_composition_known': known,
                       'bathroom_composition_unknown': len(rows)-known},
            'method': method, 'graph_configuration': noise['graph_configuration'] if noise else None,
            'residual_scales': noise, **({'floors':floors} if floors is not None else {}),
            **({'floor_elevator': floor_elevator} if floor_elevator is not None else {}),
            'diagnostics': {'parameters': parameters, 'derived': derived},
            'bathrooms': contrasts, 'coefficients': coefficients, 'group_rankings': groups,
            'residual_cases': cases, 'current_residuals': current,
            'median_absolute_log_residual': median_error, 'limitations': LIMITATIONS,
            'top_per_tail': top}, {'fit_manifest': fm, 'protocol_manifest': pm, 'source_manifest': sm}


def html_report(report):
    e = lambda value: escape(str(value), quote=True)
    def interval(value, percent=False):
        suffix = '%' if percent else ''
        return f"{value['median']:+.3f}{suffix} [{value['lower_95']:+.3f}, {value['upper_95']:+.3f}]"
    def counts(value):
        return f"{value['rows']:,} / {value['units']:,} / {value['buildings']:,}"
    def table(headers, rows):
        if not rows:
            return '<p>No supported, encoded comparisons available.</p>'
        def cell(value):
            text = e(value)
            return '<a href="'+text+'">'+text+'</a>' if str(value).startswith('https://streeteasy.com/rental/') else text
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    def heading(title, note=''):
        return '<h2>'+e(title)+'</h2>'+('<p>'+e(note)+'</p>' if note else '')
    c = report['cohort']; b = report['bathrooms']
    body = '<h1>Chelsea rental pricing: Bayesian feature research</h1>'
    body += '<p class="lede">Source-supported bathroom comparisons, group offsets and fitted residuals. All intervals below are 95% posterior credible intervals conditional on this model and its source data.</p>'
    body += '<p>'+e(f"{c['rows']:,} observations · {c['units']:,} units · {c['buildings']:,} buildings · {c['current_rows']} current captures. Bathroom composition known for {c['bathroom_composition_known']:,}; unknown or flagged for {c['bathroom_composition_unknown']:,}.")+'</p>'
    body += '<p><strong>Both parameter and derived diagnostics passed.</strong> This remains exploratory descriptive research. Report generation does not select the main model.</p>'
    body += heading('Residual variation', 'Residual-scale mode: '+report['method']['residual_scale']+'. Fitted-rent intervals remain uncertainty in the latent conditional median.')
    if report['residual_scales'] is not None:
        noise = report['residual_scales']
        body += '<p>'+e(noise['scale_units'])+' '+e(noise['interpretation'])+'</p>'
        body += table(['Scale','95% posterior interval','Support rows / units / buildings'],
            [[noise['global_sigma_role'],interval(noise['global_sigma']),f"{c['rows']:,} / {c['units']:,} / {c['buildings']:,}"]]
            +[[f"{r['bedrooms']} bedrooms",interval(r['sigma']),counts(r['support'])] for r in noise['by_bedroom']])
    else:
        body += '<p>This v2 experiment uses a shared Student-t residual scale. No saved residual-scale summary is supplied by its reporting contract.</p>'
    body += heading('Full-bath increments', b['held_fixed'])
    body += table(['Bedrooms','Full baths before → after','Price change, 95% CrI','Before rows / units / buildings','After rows / units / buildings'],
        [[r['bedrooms'], f"{r['before_full_half'][0]} → {r['after_full_half'][0]}", interval(r['percent_effect'],True),counts(r['support_before']),counts(r['support_after'])] for r in b['full_bath_increments']])
    body += heading('Half-bath increments','Full-bath count and other attributes held fixed. Unsupported or unencoded comparisons are omitted.')
    body += table(['Bedrooms','Full baths','Half baths before → after','Price change, 95% CrI','Before support','After support'],
        [[r['bedrooms'],r['full_bathrooms'],f"{r['before_half']} → {r['after_half']}",interval(r['percent_effect'],True),counts(r['support_before']),counts(r['support_after'])] for r in b['half_bath_increments']])
    body += heading('Does eliminating a full-bath shortage contribute more?', b['balance_scale'])
    body += table(['Bedrooms','Joint log-increment difference, 95% CrI','P(first increment larger)','Net −1 support','Net 0 support','Net +1 support'],
        [[r['bedrooms'],interval(r['difference']),f"{r['probability_first_increment_larger']:.1%}",*[counts(s) for s in r['support']]] for r in b['net_balance']])
    if report.get('floors') is not None:
        floors = report['floors']
        body += heading('Listed-floor component contrasts' if floors['version'] == spline_contract.CONTRAST else 'Listed-floor increments',floors['interpretation'])
        body += table(['Listed floor before → after','Component change, 95% CrI','Lower support','Upper support','Shared buildings at adjacent endpoints'],
            [[f"{r['lower_floor']:g} → {r['upper_floor']:g}",interval(r['percent_effect'],True),
              counts(r['support_lower']),counts(r['support_upper']),
              r['adjacent_overlap']['shared_buildings'] if r['adjacent_overlap'] is not None else 'Range contrast']
             for r in floors['contrasts']])
    if report.get('floor_elevator') is not None:
        joint = report['floor_elevator']
        body += heading('Listed floor by elevator access', joint['policy'])
        body += '<p>These intervals use every joint coefficient draw, including covariance. Endpoint support is not evidence of matched apartments; unknown access follows the midpoint convention.</p>'
        body += table(['Floor before → after','Elevator','Component change, 95% CrI','Before rows / units / buildings',
                       'After rows / units / buildings','Endpoint evidence'],
            [[f"{r['lower_floor']:g} → {r['upper_floor']:g}", 'Yes' if r['elevator'] else 'No',
              interval(r['percent_effect'],True),counts(r['support_before']),counts(r['support_after']),
              'Both observed' if r['supported_endpoints'] else 'Unobserved floor/access endpoint; model extrapolation']
             for r in joint['contrasts'] if r['kind'] == 'floor_change_at_known_access'])
        body += heading('Does the floor change differ with elevator access?',
            'Elevator minus no-elevator change in log rent. Percentage values describe the ratio of floor-change multipliers, not subtraction of percentage premiums.')
        body += table(['Floor before → after','Difference in log changes, 95% CrI','Ratio change, 95% CrI'],
            [[f"{r['lower_floor']:g} → {r['upper_floor']:g}",interval(r['log_effect']),interval(r['percent_effect'],True)]
             for r in joint['contrasts'] if r['kind'] == 'elevator_minus_no_elevator_floor_change'])
    body += heading('Encoded coefficients',report['coefficients']['interpretation'])
    for name,title in [('encoded_value_coefficients','Numeric/layout parameter diagnostics'),('reporting_coefficients','Reporting and missingness associations')]:
        body += '<h3>'+e(title)+'</h3>'+table(['Encoded feature','Log coefficient, 95% CrI','Encoded unit and interpretation'],
            [[r['feature'],interval(r),r['encoded_unit']] for r in report['coefficients'][name]])
    body += '<p>Category contrast-basis coefficients are omitted; they are not category premiums. No category before/after premium has been derived for this report.</p>'
    body += heading('Extreme building and unit offsets','Unit offsets are residual adjustments within building. These rankings absorb omitted attributes and depend on shrinkage. Support is observations / units / buildings, with repeated advertisements retained.')
    body += table(['Kind / tail','Group','Offset, 95% CrI','Support','Date coverage','Example source'],
        [[r['kind']+' / '+r['tail'],r['id'],interval(r['percent_effect'],True),counts(r['support']),r['support']['first_month']+' — '+r['support']['last_month'],r['example_advertisement_url']] for r in report['group_rankings']])
    body += heading('Large fitted residuals','Distinct units per tail. Inspect original source and price terms before proposing corrections; never replace asking prices with model estimates. Fitted intervals describe latent conditional-median uncertainty, not predictive uncertainty or mean rent.')
    def residual_table(items):
        return table(['Advertisement','Month','Ask','Fitted median [95% CrI]','Ask − fitted','Log residual'],
            [[r.get('advertisement_url'),r['period'],f"${r['asking_rent']:,.0f}",f"${r['fitted_rent']:,.0f} [${r['latent_rent_lower_95']:,.0f}, ${r['latent_rent_upper_95']:,.0f}]",f"${r['residual_dollars']:+,.0f}",f"{r['residual_log']:+.3f}"] for r in items])
    body += residual_table(report['residual_cases'])
    body += heading('Current captured apartments','These captured asking prices deliberately participate in the fit; availability is only known at the source capture time.')+residual_table(report['current_residuals'])
    body += heading('Diagnostic evidence')+table(['Family','Maximum R-hat','Minimum bulk ESS','Minimum tail ESS','Minimum BFMI','Divergences','Maximum-depth hits'],
        [[name,d['max_rhat'],d['min_ess_bulk'],d['min_ess_tail'],d['min_bfmi'],d['divergences'],d['maxdepth_reached']] for name,d in report['diagnostics'].items()])
    body += heading('Method, source policy and limitations')+'<ul>'+''.join('<li>'+e(s)+'</li>' for s in report['limitations'])+'</ul>'
    body += '<pre>'+e(json.dumps(report['method'],indent=2))+'</pre>'
    body += '<p>Protocol SHA-256: <code>'+e(report['protocol_sha256'])+'</code><br>Source observations SHA-256: <code>'+e(report['source_observations_sha256'])+'</code></p>'
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chelsea Bayesian rental research</title><style>body{max-width:1300px;margin:auto;padding:32px;font:16px/1.55 system-ui,sans-serif;color:#182331;background:#fafbfc}h1{font-size:2rem}h2{margin-top:2.5rem}p{max-width:1000px}.lede{font-size:1.15rem}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;background:white}th,td{padding:10px;border-bottom:1px solid #d6dee7;text-align:left;vertical-align:top}th{background:#eaf0f5}tr:nth-child(even){background:#f6f8fa}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}li{margin:.5rem 0}</style><body>'+body+'</body></html>\n'


def run(experiment, dataset, output, top=5):
    from . import bayesian_disk_protocol as disk_protocol
    from . import bayesian_floor_execution as execution
    report, provenance = build_report(experiment, dataset, top)
    return publish_bundle(output, {'report.json': canonical(report)+'\n', 'report.html': html_report(report),
        'bayesian_feature_report.py': Path(__file__).read_text(),
        'bayesian_floor_elevator_contract.py': Path(interaction_contract.__file__).read_text(),
        'bayesian_floor_spline_contract.py': Path(spline_contract.__file__).read_text(),
        'bayesian_floor_execution.py': Path(execution.__file__).read_text(),
        'bayesian_floor_block_graph.py': Path(execution.graph.__file__).read_text(),
        'reviewed_source_lineage.py': Path(reviewed_source_lineage.__file__).read_text(),
        'laundry_floor_split.py': Path(reviewed_source_lineage.laundry_floor_split.__file__).read_text(),
        'reviewed_cohort_quarantine.py': Path(reviewed_source_lineage.reviewed_cohort_quarantine.__file__).read_text(),
        'elevator_corrections.py': Path(reviewed_source_lineage.elevator_corrections.__file__).read_text(),
        'floor_label_projection.py': Path(reviewed_source_lineage.floor_label_projection.__file__).read_text(),
        'expanded_floor_projection.py': Path(reviewed_source_lineage.expanded_floor_projection.__file__).read_text(),
        'direct_floor_projection.py': Path(reviewed_source_lineage.direct_floor_projection.__file__).read_text(),
        'residual_scope_projection.py': Path(reviewed_source_lineage.residual_scope_projection.__file__).read_text(),
        'bayesian_disk_protocol.py': Path(disk_protocol.__file__).read_text()},
        {'version': VERSION, **provenance, 'top_per_tail': top, 'implementation_sha256': digest(__file__)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment','dataset','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--top',type=int,default=5)
    args=parser.parse_args()
    result=run(args.experiment,args.dataset,args.output,args.top)
    print(canonical({'output':str(args.output),'files':result['files']}))

"""Lightweight source and reporting contract for regularized floor splines."""
from __future__ import annotations

from collections import defaultdict
import math

EXPERIMENT = 'observable-bayesian-floor-spline-experiment-v5'
BEDROOM_TIME_EXPERIMENT = 'observable-bayesian-bedroom-time-experiment-v1'
STRUCTURE_EXPERIMENT = 'observable-bayesian-structure-experiment-v1'
ATTRIBUTE_EXPERIMENT = 'observable-bayesian-attribute-structure-experiment-v1'
DRIFT_EXPERIMENT = 'observable-bayesian-drift-experiment-v1'
EFFICIENT_STRUCTURE_EXPERIMENT = 'observable-bayesian-efficient-structure-experiment-v1'
# Experiments whose feature design is exactly this spline design; they may add
# location terms (see bayesian_location_terms) but share its floor contract.
FAMILY = frozenset({EXPERIMENT, BEDROOM_TIME_EXPERIMENT, STRUCTURE_EXPERIMENT, ATTRIBUTE_EXPERIMENT, DRIFT_EXPERIMENT, EFFICIENT_STRUCTURE_EXPERIMENT})
DESIGN = 'regularized-listed-floor-spline-design-v1'
# The attribute design is the spline design plus unit attribute columns.
ATTRIBUTE_DESIGN = 'unit-attribute-spline-design-v1'
DESIGNS = frozenset({DESIGN, ATTRIBUTE_DESIGN})
CONTRAST = 'joint-listed-floor-spline-component-contrasts-v1'
INTERPRETATION = 'Joint regularized natural-spline floor-component contrasts, holding other encoded terms fixed. Conditional associations, not causal or physical-height effects; shared smoothness and source support remain explicit.'
FIELDS = {'feature_design_version', 'floor_prior_scale', 'floor_levels', 'floor_knots',
          'floor_reference', 'floor_policy'}


def verify_metadata(protocol, design):
    """A spline must never inherit the old threshold prior/feature interpretation."""
    from .bayesian_feature_report import finite
    scale = protocol.get('floor_prior_scale')
    levels = protocol.get('floor_levels')
    if (protocol.get('version') not in FAMILY or protocol.get('feature_design_version') not in DESIGNS
            or design.get('version') != protocol.get('feature_design_version') or not finite(scale) or scale <= 0
            or not isinstance(levels,list) or len(levels) < 2 or any(not finite(v) for v in levels)
            or levels != sorted(set(levels))
            or any(design.get(k) != protocol.get(k) for k in FIELDS-{'feature_design_version'})
            or {'floor_increment_prior_scale','floor_thresholds'} & protocol.keys()
            or {'floor_increment_prior_scale','floor_thresholds'} & design.keys()):
        raise ValueError('Spline design metadata differs from protocol')
    knots = sorted({levels[0], levels[-1], *[v for v in (5.,10.,20.,35.) if levels[0] < v < levels[-1]]}) if levels else []
    reference = (2. if levels[0] <= 2 <= levels[-1] else levels[0]) if levels else None
    if (protocol.get('floor_knots') != knots or protocol.get('floor_reference') != reference
            or not isinstance(protocol.get('floor_policy'),dict) or not protocol['floor_policy']):
        raise ValueError('Spline knots, reference or policy differ from declared construction')
    names = design.get('features',[])
    expected = ['listed_floor_spline_'+str(i) for i in range(max(0,len(knots)-1))]
    if ([n for n in names if n.startswith('listed_floor_spline_')] != expected
            or 'listed_floor' in names or any(n.startswith('listed_floor_gt_') for n in names)):
        raise ValueError('Spline coefficient inventory differs from knot construction')
    if 'prior_scales' in design:
        priors = design['prior_scales']
        if len(priors) != len(names) or any(priors[names.index(n)] != scale for n in expected):
            raise ValueError('Spline coefficient priors differ from protocol')
    return True


def verify_contrasts(protocol, design, floors, rows, summary):
    from apartments import pricing
    from . import bayesian_feature_report as report
    verify_metadata(protocol,design)
    cells = defaultdict(list)
    for row in rows:
        value = pricing._numeric_feature('listed_floor',pricing._normalize(row).get('listed_floor'))
        if value is not None: cells[value].append(row)
    levels = sorted(cells)
    if (levels != protocol['floor_levels'] or floors.get('version') != CONTRAST
            or floors.get('interpretation') != INTERPRETATION
            or any(floors.get(k) != protocol[k] for k in FIELDS-{'feature_design_version'})
            or 'floor_thresholds' in floors
            or floors.get('draws') != protocol['chains']*protocol['draws']
            or summary.get('floor_diagnostics') != floors.get('diagnostics')):
        raise ValueError('Spline contrasts, source support or diagnostics differ')
    pairs = list(zip(levels[:-1],levels[1:]))
    if len(levels)>2: pairs.append((levels[0],levels[-1]))
    items = floors.get('contrasts',[])
    if [(v.get('lower_floor'),v.get('upper_floor')) for v in items] != pairs:
        raise ValueError('Spline contrast endpoints differ from observed support')
    diag = floors['diagnostics']
    if pairs:
        report.check_diagnostics({'status':'exploratory_converged','diagnostics':diag,'derived_diagnostics':diag},diag,diag)
    elif diag != {'acceptable':True,'deterministic':True,'reason':'No varying observed floor contrast'}:
        raise ValueError('Invalid no-contrast spline diagnostics')
    counts = [{'level':level,**report.support(cells[level])} for level in levels]
    support = design.get('floor_support',{})
    if (support.get('levels') != counts or support.get('known_rows') != sum(len(v) for v in cells.values())
            or support.get('unknown_rows') != len(rows)-sum(len(v) for v in cells.values())):
        raise ValueError('Spline floor support differs from source')
    for item,(low,high) in zip(items,pairs):
        for label,level in [('lower',low),('upper',high)]:
            if item.get('support_'+label) != {'level':level,**report.support(cells[level])}:
                raise ValueError('Spline endpoint counts differ from source')
        adjacent = levels.index(high) == levels.index(low)+1
        if item.get('kind') != ('adjacent_observed_levels' if adjacent else 'observed_range'):
            raise ValueError('Spline contrast kind differs')
        overlap = item.get('adjacent_overlap')
        if adjacent:
            if (not isinstance(overlap,dict) or overlap.get('lower_supported_level') != low
                    or overlap.get('upper_supported_level') != high
                    or overlap.get('shared_buildings') != len({r['building'] for r in cells[low]} & {r['building'] for r in cells[high]})
                    or overlap.get('shared_units') != len({r['unit_id'] for r in cells[low]} & {r['unit_id'] for r in cells[high]})):
                raise ValueError('Spline endpoint overlap differs from source')
        elif overlap is not None: raise ValueError('Unexpected adjacent overlap for spline range contrast')
        for kind in ('log_effect','percent_effect'): report.check_interval(item[kind])
        if item['log_effect']['probability_positive'] != item['percent_effect']['probability_positive']:
            raise ValueError('Spline contrast sign probabilities disagree')
        for bound in ('lower_95','median','upper_95'):
            if not math.isclose(item['percent_effect'][bound],100*math.expm1(item['log_effect'][bound]),rel_tol=1e-10,abs_tol=1e-10):
                raise ValueError('Spline log and percentage intervals disagree')
    return floors

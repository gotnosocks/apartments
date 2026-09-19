"""Numerical-runtime-free reader checks for the explicit v5 interaction model.

This reports metadata only. Actual analyses also reconstruct the design from
source and use the complete joint posterior; the base design alone is insufficient.
"""
import math

from apartments import pricing

EXPERIMENT = 'observable-bayesian-floor-elevator-experiment-v5'
DESIGN = 'lower-floor-elevator-interaction-design-v1'
BASE = 'observed-listed-floor-increment-design-v1'
CONTRAST = 'joint-lower-floor-elevator-contrasts-v1'
THRESHOLDS = [2., 3., 4.]
POLICY = ('Known no/yes elevator weights -0.5/+0.5; unknown zero. Thresholds 2, 3, 4 only; '
          'unknown floor contributes zero before centering. Pooled sum divided by sqrt(3), '
          'matching the separate model full-range interaction-difference prior variance. '
          'Base floor curve is the known-access midpoint; interaction saturates above 5. '
          'Advertised labels, not measured height; source conflicts remain separate.')


def source_values(rows):
    result = []
    for row in rows:
        normalized = pricing._normalize(row)
        result.append((pricing._numeric_feature('listed_floor', normalized.get('listed_floor')),
                       pricing._boolean(normalized.get('elevator'))))
    return result


def names(mode):
    if mode == 'pooled': return ['floor_elevator_pooled_2_to_5']
    if mode == 'separate': return ['floor_elevator_gt_2', 'floor_elevator_gt_3', 'floor_elevator_gt_4']
    raise ValueError('Unsupported interaction mode')


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def merge_design(protocol, base, interaction, rows, summary):
    mode = protocol.get('interaction_mode'); added = names(mode)
    scale = protocol.get('interaction_prior_scale')
    if (protocol.get('version') != EXPERIMENT or protocol.get('feature_design_version') != DESIGN
            or protocol.get('base_feature_design_version') != BASE or base.get('version') != BASE
            or protocol.get('interaction_thresholds') != THRESHOLDS or protocol.get('interaction_policy') != POLICY
            or not positive(scale) or not positive(protocol.get('floor_increment_prior_scale'))
            or not positive(protocol.get('prior_multiplier')) or interaction.get('version') != DESIGN
            or interaction.get('base_design_layout') != 'flat' or interaction.get('mode') != mode
            or interaction.get('thresholds') != THRESHOLDS or interaction.get('interaction_prior_scale') != scale
            or base.get('floor_increment_prior_scale') != protocol.get('floor_increment_prior_scale')):
        raise ValueError('Interaction protocol and base/extended design disagree')
    values = source_values(rows)
    levels = sorted({f for f, _ in values if f is not None})
    if (not rows or not {2.,3.,4.,5.} <= set(levels)
            or any(obj.get('floor_levels') != levels or obj.get('floor_thresholds') != levels[:-1]
                   for obj in (protocol, base))):
        raise ValueError('Floor support differs from interaction source')
    endpoints = [{'floor': f, 'elevator': bool(e), 'rows': sum(v == (f, e) for v in values)}
                 for f in (2.,3.,4.,5.) for e in (0.,1.)]
    if any(r['rows'] == 0 for r in endpoints) or interaction.get('endpoint_support') != endpoints:
        raise ValueError('Interaction endpoint support differs')
    sums = [0., 0., 0.]
    for f, e in values:
        if f is not None and e is not None:
            for i, threshold in enumerate(THRESHOLDS):
                if f > threshold: sums[i] += e-.5
    means = [value/len(rows) for value in sums]
    if mode == 'pooled': means = [sum(means)/math.sqrt(3)]
    saved_means = interaction.get('interaction_means', [])
    if (len(saved_means) != len(means) or any(type(v) not in (int,float) or not math.isfinite(v) for v in saved_means)
            or any(not math.isclose(x,y,rel_tol=0,abs_tol=1e-12) for x,y in zip(means,saved_means))):
        raise ValueError('Interaction centering differs from exact source')
    features = base['features']+added
    scales = base['prior_scales']+[scale]*len(added)
    support = {**base['support'], 'features': len(features), 'matrix_rank': len(features),
               'interaction_mode': mode, 'interaction_endpoint_support': endpoints}
    if (interaction.get('features') != features or interaction.get('prior_scales') != scales
            or interaction.get('support') != support or summary.get('design_support') != support
            or base['support']['rows'] != len(rows) or len(set(features)) != len(features)):
        raise ValueError('Interaction feature order, priors or support differ')
    # Metadata for summaries/coefficient tables only, never a mathematical loader.
    return {**base, 'version': DESIGN, 'features': features, 'prior_scales': scales,
            'means': base['means']+saved_means, 'support': support}


def verify_contrasts(protocol, design, joint, rows, summary, check_interval):
    mode = protocol['interaction_mode']; added = names(mode)
    if (joint.get('version') != CONTRAST or joint.get('interaction_mode') != mode
            or joint.get('policy') != POLICY or joint.get('all_joint_beta_draws') is not True
            or joint.get('all_contrasts_acceptable') is not True
            or summary.get('floor_elevator_contrasts_acceptable') is not True
            or joint.get('chains') != protocol['chains'] or joint.get('draws_per_chain') != protocol['draws']):
        raise ValueError('Joint interaction report is incomplete or failed diagnostics')
    values = source_values(rows); levels = protocol['floor_levels']
    def support(level, access):
        cell = [r for r, v in zip(rows, values) if v == (level, int(access))]
        return {'rows':len(cell), 'units':len({r['unit_id'] for r in cell}), 'buildings':len({r['building'] for r in cell})}
    def vector(low, high, access=None):
        value = dict.fromkeys(design['features'], 0.)
        if access is not None:
            for threshold in levels[:-1]:
                if low <= threshold < high: value['listed_floor_gt_'+format(threshold,'.17g')] = 1.
        weight = 1. if access is None else int(access)-.5
        delta = [weight if low <= k < high else 0. for k in THRESHOLDS]
        if mode == 'pooled': delta = [sum(delta)/math.sqrt(3)]
        value.update(zip(added,delta))
        return [value[k] for k in design['features']]
    expected = []
    pairs = list(zip(levels[:-1],levels[1:]))
    if len(levels)>2: pairs.append((levels[0],levels[-1]))
    for low, high in pairs:
        for access in (False, True):
            a,b = support(low,access),support(high,access)
            expected.append({'id':f'floor:{low:g}->{high:g}:elevator={int(access)}',
                'kind':'floor_change_at_known_access','lower_floor':low,'upper_floor':high,'elevator':access,
                'support_before':a,'support_after':b,'supported_endpoints':bool(a['rows'] and b['rows']),
                'design_vector':vector(low,high,access)})
    for low, high in [(2.,3.),(3.,4.),(4.,5.),(2.,5.)]:
        cells = [{'floor':f,'elevator':e,**support(f,e)} for f in (low,high) for e in (False,True)]
        expected.append({'id':f'interaction_difference:{low:g}->{high:g}',
            'kind':'elevator_minus_no_elevator_floor_change','lower_floor':low,'upper_floor':high,
            'support':cells,'supported_endpoints':all(c['rows']>0 for c in cells),'design_vector':vector(low,high)})
    actual = joint.get('contrasts', [])
    if len(actual) != len(expected): raise ValueError('Joint interaction contrast inventory differs')
    for wanted, item in zip(expected, actual):
        for key,value in wanted.items():
            if key == 'design_vector':
                other = item.get(key, [])
                if len(other) != len(value) or any(not math.isclose(x,y,rel_tol=0,abs_tol=1e-12) for x,y in zip(value,other)):
                    raise ValueError('Joint interaction design vector differs')
            elif item.get(key) != value: raise ValueError('Joint interaction semantics or support differ')
        prior = math.sqrt(sum((v*s)**2 for v,s in zip(wanted['design_vector'],design['prior_scales'])))*protocol['prior_multiplier']
        if not math.isclose(item.get('log_contrast_prior_sd', -1),prior,rel_tol=1e-12,abs_tol=1e-12):
            raise ValueError('Joint interaction contrast prior differs')
        d = item.get('diagnostics', {})
        if (d.get('acceptable') is not True or item.get('status') != 'supported_converged'
                or not all(positive(d.get(k)) for k in ('max_rhat','ess_bulk','ess_tail'))
                or d['max_rhat'] >= 1.01 or min(d['ess_bulk'],d['ess_tail']) < 400):
            raise ValueError('Joint interaction contrast diagnostics fail')
        check_interval(item['log_effect']); check_interval(item['percent_effect'])
        if item['log_effect']['probability_positive'] != item['percent_effect']['probability_positive']:
            raise ValueError('Joint interaction sign probabilities disagree')
    return joint

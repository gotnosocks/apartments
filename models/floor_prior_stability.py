"""Audit floor-contrast priors without fitting or changing a selected model.

Integer-step alternatives describe advertised labels, never physical height.
Only contrast priors are compared; intercept/missingness joint priors are not
asserted invariant when a cohort or its centering changes.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_floor_increment_design as floor
from .bayesian_feature_sensitivity import bound_bytes

VERSION = 'listed-floor-contrast-prior-stability-v1'


def covariance(levels, scale, policy):
    levels = np.asarray(levels, dtype=float)
    if (levels.ndim != 1 or len(levels) < 2 or not np.isfinite(levels).all()
            or (np.diff(levels) <= 0).any() or not np.isfinite(scale) or scale <= 0
            or isinstance(scale, (bool, np.bool_))):
        raise ValueError('Ordered distinct levels and finite positive scale required')
    if policy == 'observed_step':
        widths = np.ones(len(levels)-1)
    elif policy == 'integer_step':
        if not np.equal(levels, np.floor(levels)).all():
            raise ValueError('Integer-label prior requires integer floor labels')
        widths = np.diff(levels)
    else:
        raise ValueError('Unsupported floor prior policy')
    matrix = (levels[:, None] > levels[None, :-1]).astype(float)
    weighted = matrix*(scale*np.sqrt(widths))
    return weighted@weighted.T


def contrast_sd(cov, lower, upper):
    return float(np.sqrt(max(0., cov[lower, lower]+cov[upper, upper]-2*cov[lower, upper])))


def audit_priors(levels, scale):
    baseline = covariance(levels, scale, 'observed_step')
    distance = levels[-1]-levels[0]
    matched_scale = scale*np.sqrt((len(levels)-1)/distance)
    policies = [('observed_step', 'observed_step', scale),
                ('integer_step', 'integer_step', scale),
                ('integer_step_matched_range', 'integer_step', matched_scale)]
    matrices = {name: covariance(levels, value, policy) for name, policy, value in policies}
    # Expand every missing integer threshold, then marginalize their independent
    # Normal coefficients analytically. Observed-gap aggregation is exact for
    # these observed endpoint priors; it creates no within-gap data information.
    integer_thresholds = np.arange(levels[0], levels[-1])
    dense = (np.asarray(levels)[:, None] > integer_thresholds[None, :]).astype(float)*scale
    np.testing.assert_allclose(matrices['integer_step'], dense@dense.T, rtol=1e-13, atol=1e-14)
    pairs = [(i, i+1) for i in range(len(levels)-1)]+[(0, len(levels)-1)]
    contrasts = [{'lower_floor': levels[i], 'upper_floor': levels[j], 'label_distance': levels[j]-levels[i],
        'prior_log_sd': {name: contrast_sd(cov, i, j) for name, cov in matrices.items()}}
        for i, j in pairs]
    removals = []
    for removed in range(1, len(levels)-1):
        kept = [i for i in range(len(levels)) if i != removed]
        reduced = [levels[i] for i in kept]
        row = {'removed_level': levels[removed], 'lower_floor': levels[removed-1],
               'upper_floor': levels[removed+1], 'policies': {}}
        for name, policy, value in policies:
            new = covariance(reduced, value, policy)
            old_sd = contrast_sd(matrices[name], removed-1, removed+1)
            new_sd = contrast_sd(new, removed-1, removed)
            error = float(np.max(abs(new-matrices[name][np.ix_(kept, kept)])))
            if policy == 'integer_step' and error > 1e-12:
                raise ValueError('Integer-step marginal prior changed after an interior level was removed')
            row['policies'][name] = {'before_log_sd': old_sd, 'after_log_sd': new_sd,
                'relative_sd_change': new_sd/old_sd-1, 'maximum_retained_covariance_error': error}
        removals.append(row)
    return {'policies': [{'name': name, 'increment_log_sd': float(value),
                         'range_log_sd': contrast_sd(matrices[name], 0, len(levels)-1)}
                        for name, _, value in policies],
        'contrasts': contrasts, 'interior_level_removal': removals,
        'dense_integer_thresholds': integer_thresholds.tolist(),
        'integer_expansion_max_covariance_error': float(np.max(abs(matrices['integer_step']-dense@dense.T))),
        'observed_range_log_sd': contrast_sd(baseline, 0, len(levels)-1)}


def run(selection, output):
    selection = Path(selection)
    chosen = json.loads(selection.read_text())
    root, dataset = Path(chosen['experiment']), Path(chosen['dataset'])
    for directory, key in [(root/'fit', 'fit_manifest_sha256'), (root/'protocol', 'protocol_manifest_sha256'),
                           (dataset, 'source_manifest_sha256')]:
        if digest(directory/'complete.json') != chosen[key]: raise ValueError('Selected artifact changed')
    fm = json.loads((root/'fit/complete.json').read_text())
    pm = json.loads((root/'protocol/complete.json').read_text())
    protocol = json.loads(bound_bytes(root/'protocol', 'protocol.json', pm))
    design = json.loads(bound_bytes(root/'fit', 'feature-design.json', fm))
    fitted = json.loads(bound_bytes(root/'fit', 'floor-contrasts.json', fm))
    if (hashlib.sha256(canonical(protocol).encode()).hexdigest() != chosen['protocol_sha256']
            or protocol['source_manifest_sha256'] != chosen['source_manifest_sha256']
            or protocol['source_observations_sha256'] != chosen['source_observations_sha256']
            or design['version'] != floor.VERSION or protocol['implementation_sha256'][Path(floor.__file__).name] != digest(floor.__file__)):
        raise ValueError('Selected floor design, implementation or protocol differs')
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    if sm['files']['observations.jsonl'] != chosen['source_observations_sha256']:
        raise ValueError('Selected source observations differ')
    rows = [json.loads(s) for s in sf['observations.jsonl'].decode().split('\n') if s]
    data = pd.DataFrame(rows)
    values = floor.listed_floor_values(data)
    levels = np.unique(values[np.isfinite(values)]).tolist()
    if levels != design['floor_levels'] or levels != protocol['floor_levels']:
        raise ValueError('Saved and freshly measured floor levels differ')
    scale = design['floor_increment_prior_scale']*protocol['prior_multiplier']
    for k in levels[:-1]:
        if design['prior_scales'][design['features'].index(floor._name(k))]*protocol['prior_multiplier'] != scale:
            raise ValueError('Saved observed-floor increments do not share the specified prior')
    result = audit_priors(levels, scale)
    support = floor._support(data, values, levels)
    current = data.analysis_price_basis.eq('current_capture_gross_ask').to_numpy()
    result.update(version=VERSION, rows=len(rows), floor_levels=levels, support=support,
        current_rows=int(current.sum()), current_known_floor_rows=int((current & np.isfinite(values)).sum()),
        archived_fitted_floor_contrasts=fitted,
        fit_products_checked=['feature-design.json', 'floor-contrasts.json'],
        main_selection_changed=False, posterior_refitted=False,
        limitations=['Alternative prior calculations are not fitted effects, performance evidence or a selection decision.',
            'Label distance is not physical height; skipped floor numbering remains unresolved.',
            'Exact marginalization preserves the integer-step prior on observed endpoint contrasts, not identification of missing-floor increments.',
            'Matched-range scale is chosen once from the selected source and held fixed in all removal checks; recomputing it after each exclusion would reintroduce support dependence.',
            'Contrast-prior invariance does not guarantee invariance of the full joint prior after changing centering, intercept, missingness or group populations.',
            'Archived fitted contrast summaries are hash-checked against the selected fit; this audit does not reread or re-diagnose its posterior.'])
    files = {'audit.json': canonical(result)+'\n', Path(__file__).name: Path(__file__).read_text(),
             Path(floor.__file__).name: Path(floor.__file__).read_text()}
    publish_bundle(output, files, {'version': VERSION, 'selection_sha256': digest(selection),
        'fit_manifest_sha256': chosen['fit_manifest_sha256'], 'source_manifest_sha256': chosen['source_manifest_sha256'],
        'protocol_manifest_sha256': chosen['protocol_manifest_sha256']})
    print(canonical({k: result[k] for k in ('rows', 'floor_levels', 'policies', 'current_rows', 'current_known_floor_rows')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, default=Path('config/main-analysis.json'))
    parser.add_argument('--output', type=Path, required=True)
    run(**vars(parser.parse_args()))

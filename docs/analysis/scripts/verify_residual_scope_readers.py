"""Exercise residual-scope readers and audit the full-cohort design changes."""
import argparse
from pathlib import Path

import numpy as np

from apartments import bayesian_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner, bayesian_feature_report as report
from models import bayesian_floor_spline_design as floor, bayesian_floor_increment_design as floor_base
from models import residual_scope_fit_comparison as comparison


def compare_designs(designs, frames):
    a, b = designs
    if a.features != b.features or a.floor_levels != b.floor_levels or not np.array_equal(a.prior_scales, b.prior_scales):
        raise ValueError('Exclusions changed supported feature inventory or prior scales; review before fitting')
    if (a.floor_knots != b.floor_knots or a.floor_reference != b.floor_reference
            or a.floor_basis != b.floor_basis or a.floor_policy != b.floor_policy):
        raise ValueError('Spline construction, reference or basis changed')
    if {k: (v['levels'], v['basis']) for k, v in a.categories.items()} != {
            k: (v['levels'], v['basis']) for k, v in b.categories.items()}:
        raise ValueError('Category support or contrast basis changed')
    matrices = [d.matrix(frame) for d, frame in zip(designs, frames, strict=True)]
    ranks = [int(np.linalg.matrix_rank(matrix)) for matrix in matrices]
    if ranks != [len(a.features), len(b.features)]: raise ValueError('Feature design is rank deficient')
    # Source membership changes centering; do not claim identical numerical design.
    mean_changes = [{'feature': name, 'reference': float(x), 'candidate': float(y)}
                    for name, x, y in zip(a.features, a.means, b.means, strict=True) if x != y]
    numeric_changes = []
    for name in a.numeric:
        if a.numeric[name] == b.numeric[name]: continue
        item = {'feature': name, 'reference': a.numeric[name], 'candidate': b.numeric[name],
                'has_active_numeric_coefficient': name in a.features}
        if name in a.features:
            old_sd = a.prior_scales[a.features.index(name)]/a.numeric[name]['scale']
            new_sd = b.prior_scales[b.features.index(name)]/b.numeric[name]['scale']
            item.update(reference_log_prior_sd_per_raw_unit=float(old_sd),
                        candidate_log_prior_sd_per_raw_unit=float(new_sd),
                        raw_unit_prior_sd_relative_change=float(new_sd/old_sd-1))
        numeric_changes.append(item)
    return {'feature_counts': [len(d.features) for d in designs], 'features': a.features,
        'design_ranks': ranks, 'feature_inventory_and_coefficient_prior_scales_equal': True,
        'coefficient_prior_scales': a.prior_scales.tolist(),
        'floor_levels': b.floor_levels, 'floor_knots': b.floor_knots,
        'floor_reference': b.floor_reference, 'floor_prior_scale': b.floor_prior_scale,
        'floor_basis_equal': True, 'floor_policy': b.floor_policy,
        'floor_support': [d.floor_support for d in designs],
        'numeric_normalization_equal': a.numeric == b.numeric, 'centering_changes': mean_changes,
        'numeric_normalization_changes': numeric_changes,
        'categorical_contrast_bases_equal': True,
        'category_frequencies': [{k: v['frequencies'] for k, v in d.categories.items()} for d in designs],
        'size_reference': [{'medians': d.time.size_medians, 'default': d.time.size_default} for d in designs],
        'size_reference_equal': (a.time.size_medians == b.time.size_medians and
                                 a.time.size_default == b.time.size_default)}


def run(reference, candidate, evidence, output, policy=None):
    reference, candidate, evidence = map(Path, (reference, candidate, evidence))
    implementations = {p.name: p for p in runner.implementation_paths()}
    implementations.update({Path(m.__file__).name: Path(m.__file__) for m in
        (report, bayesian_evidence, comparison, floor, floor_base)})
    implementations[Path(__file__).name] = Path(__file__)
    code_before = {k: digest(p) for k, p in implementations.items()}
    input_before = {name: digest(path/'complete.json') for name, path in
        (('reference', reference), ('candidate', candidate), ('evidence', evidence))}
    policy_hash = digest(policy) if policy is not None else None
    print('Verifying exact reviewed-ad scope inverse and complete inherited source lineage', flush=True)
    original, kept, sidecar = comparison.verify_revision(reference, candidate, policy=policy)
    old_current = [r for r in original if r['analysis_price_basis'] == 'current_capture_gross_ask']
    new_current = [r for r in kept if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if old_current != new_current or len(new_current) != 172:
        raise ValueError('Expected unchanged 172 dated current-capture rows')
    print('Verifying retained literal evidence and fit loader membership', flush=True)
    mapping = bayesian_evidence.load_evidence(candidate, evidence)
    baseline = bayesian_evidence.load_evidence(reference, evidence)
    if set(mapping) != {r['audit_id'] for r in kept} or any(mapping[k] != baseline[k] for k in mapping):
        raise ValueError('Retained literal evidence changed')
    excluded = {r['observation']['audit_id'] for r in sidecar}
    if set(baseline)-set(mapping) != excluded: raise ValueError('Unexpected evidence membership loss')
    frames = [runner.load_data(p)[0] for p in (reference, candidate)]
    if [d.audit_id.tolist() for d in frames] != [[r['audit_id'] for r in rows] for rows in (original, kept)]:
        raise ValueError('Fit loader changed ordered membership')
    print('Auditing natural-spline feature design, rank and empirical normalization', flush=True)
    designs = [floor.FeatureDesign(d, 'full_half_balance', floor_prior_scale=.10) for d in frames]
    design_result = compare_designs(designs, frames)
    result = {'version': 'reviewed-residual-scope-reader-verification-v1', 'passed': True,
        'reference_rows': len(original), 'rows': len(kept), 'excluded_rows': len(sidecar),
        'units': frames[1].unit_id.nunique(), 'buildings': frames[1].building.nunique(),
        'unchanged_current_rows': len(new_current), 'literal_captures': sum(map(len, mapping.values())),
        'excluded_literal_captures': sum(len(baseline[k]) for k in excluded),
        'exact_inverse_parent_verified': True, 'full_ancestor_lineage_verified': True,
        'inherited_sidecars_byte_equal': True, 'retained_evidence_equal': True,
        'excluded_ads': sorted(r['observation']['source_listing_id'] for r in sidecar),
        'review_policy_sha256': policy_hash,
        **design_result,
        'main_selection_changed': False, 'fit_performed': False,
        'limitations': ['Reader and design validation only; no posterior or pricing inference.',
            'Centering/support counts can change when observations are excluded. The model must be refitted.',
            'Equal coefficient prior scales do not imply identical raw-unit priors when numeric normalization changes. '
            'The corresponding raw-unit prior changes are recorded explicitly. Category frequency centering can also '
            'alter joint priors involving missingness and the intercept even with unchanged pairwise contrast priors.']}
    if input_before != {name: digest(path/'complete.json') for name, path in
            (('reference', reference), ('candidate', candidate), ('evidence', evidence))}:
        raise ValueError('Input manifests changed during verification')
    if code_before != {k: digest(p) for k, p in implementations.items()}:
        raise ValueError('Reader implementations changed during verification')
    if policy is not None and digest(policy) != policy_hash:
        raise ValueError('Reviewed policy changed during verification')
    publish_bundle(output, {'verification.json': canonical(result)+'\n',
        Path(__file__).name: Path(__file__).read_text(), **{k: p.read_text() for k, p in implementations.items()}},
        {'version': result['version'], 'reference_manifest_sha256': digest(reference/'complete.json'),
         'candidate_manifest_sha256': digest(candidate/'complete.json'),
         'evidence_manifest_sha256': digest(evidence/'complete.json'), 'implementation_sha256': code_before})
    print(canonical({k: result[k] for k in ('version', 'passed', 'reference_rows', 'rows',
        'excluded_rows', 'unchanged_current_rows', 'feature_counts', 'design_ranks',
        'floor_knots', 'numeric_normalization_equal')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'evidence', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--policy', type=Path, help='Explicit cumulative policy; omitted preserves the original four-ad experiment')
    run(**vars(parser.parse_args()))

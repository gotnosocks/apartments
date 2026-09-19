"""Exercise reviewed quarantine readers and audit the full-cohort design changes."""
import argparse
import json
from pathlib import Path

import numpy as np

from apartments import bayesian_evidence, reviewed_cohort_quarantine as q, reviewed_source_lineage
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner, bayesian_feature_report as report
from models import bayesian_floor_increment_design as floor


def run(reference, candidate, evidence, output):
    reference, candidate, evidence = map(Path, (reference, candidate, evidence))
    implementations = {Path(m.__file__).name: Path(m.__file__) for m in
        (runner, report, bayesian_evidence, reviewed_source_lineage, q, floor)}
    code_before = {k: digest(p) for k, p in implementations.items()}
    sm, sf = _verified_bundle(candidate, retain={'observations.jsonl', q.SIDECAR})
    cm, cf = _verified_bundle(reference, retain={'observations.jsonl'})
    original, kept, sidecar = [report.jsonl(blob) for blob in
        (cf['observations.jsonl'], sf['observations.jsonl'], sf[q.SIDECAR])]
    if q.parent_rows(sm, kept, sidecar) != (cm, original):
        raise ValueError('Inverse quarantine differs from actual parent')
    old_current = [r for r in original if r['analysis_price_basis'] == 'current_capture_gross_ask']
    new_current = [r for r in kept if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if old_current != new_current: raise ValueError('Current rows changed')
    mapping = bayesian_evidence.load_evidence(candidate, evidence)
    baseline = bayesian_evidence.load_evidence(reference, evidence)
    if set(mapping) != {r['audit_id'] for r in kept} or any(mapping[k] != baseline[k] for k in mapping):
        raise ValueError('Retained literal evidence changed')
    excluded = {r['observation']['audit_id'] for r in sidecar}
    if set(baseline)-set(mapping) != excluded: raise ValueError('Unexpected evidence membership loss')
    frames = [runner.load_data(p)[0] for p in (reference, candidate)]
    if [d.audit_id.tolist() for d in frames] != [[r['audit_id'] for r in rows] for rows in (original, kept)]:
        raise ValueError('Fit loader changed ordered membership')
    designs = [floor.FeatureDesign(d, 'full_half_balance', floor_increment_prior_scale=.15) for d in frames]
    a, b = designs
    if a.features != b.features or a.floor_levels != b.floor_levels or not np.array_equal(a.prior_scales, b.prior_scales):
        raise ValueError('Exclusions changed supported feature inventory or prior scales; review before fitting')
    if {k: v['levels'] for k, v in a.categories.items()} != {k: v['levels'] for k, v in b.categories.items()}:
        raise ValueError('Category support changed')
    matrices = [d.matrix(frame) for d, frame in zip(designs, frames, strict=True)]
    ranks = [int(np.linalg.matrix_rank(matrix)) for matrix in matrices]
    if ranks != [len(a.features), len(b.features)]: raise ValueError('Feature design is rank deficient')
    # Source membership changes centering; do not claim identical numerical design.
    mean_changes = [{'feature': name, 'reference': float(x), 'candidate': float(y)}
                    for name, x, y in zip(a.features, a.means, b.means, strict=True) if x != y]
    result = {'version': 'reviewed-quarantine-reader-verification-v1', 'passed': True,
        'reference_rows': len(original), 'rows': len(kept), 'excluded_rows': len(sidecar),
        'units': frames[1].unit_id.nunique(), 'buildings': frames[1].building.nunique(),
        'unchanged_current_rows': len(new_current), 'literal_captures': sum(map(len, mapping.values())),
        'excluded_literal_captures': sum(len(baseline[k]) for k in excluded),
        'exact_inverse_parent_verified': True, 'retained_evidence_equal': True,
        'feature_counts': [len(d.features) for d in designs], 'design_ranks': ranks,
        'feature_inventory_and_priors_equal': True, 'floor_levels': b.floor_levels,
        'numeric_normalization_equal': a.numeric == b.numeric, 'centering_changes': mean_changes,
        'main_selection_changed': False, 'fit_performed': False,
        'limitations': ['Reader and design validation only; no posterior or pricing inference.',
            'Centering/support counts can change when observations are excluded. The model must be refitted.']}
    if code_before != {k: digest(p) for k, p in implementations.items()}:
        raise ValueError('Reader implementations changed during verification')
    publish_bundle(output, {'verification.json': canonical(result)+'\n',
        Path(__file__).name: Path(__file__).read_text(), **{k: p.read_text() for k, p in implementations.items()}},
        {'version': result['version'], 'reference_manifest_sha256': digest(reference/'complete.json'),
         'candidate_manifest_sha256': digest(candidate/'complete.json'),
         'evidence_manifest_sha256': digest(evidence/'complete.json'), 'implementation_sha256': code_before})
    print(canonical(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'evidence', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

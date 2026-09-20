"""Verify the real expanded source, unchanged nonfloor design, and literal evidence."""
import argparse
import json
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from apartments import expanded_floor_projection as projection
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as loader
from models.bayesian_floor_spline_design import FeatureDesign, knot_specification


def run(reference, dataset, evidence, output):
    reference, dataset, evidence, output = map(Path, (reference, dataset, evidence, output))
    before, bm = loader.load_data(reference)
    after, am = loader.load_data(dataset)
    _, files = _verified_bundle(dataset, retain={projection.SIDECAR, 'observations.jsonl'})
    rows, changes = ([json.loads(s) for s in files[name].decode().split('\n') if s.strip()]
                     for name in ('observations.jsonl', projection.SIDECAR))
    parent, restored = projection.parent_rows(am, rows, changes)
    assert parent == bm
    assert [r['audit_id'] for r in restored] == list(before.audit_id) == list(after.audit_id)
    source_columns = [c for c in before if c not in {'advertised_floor', 'listed_floor'}]
    assert before[source_columns].equals(after[source_columns])
    left, right = (FeatureDesign(frame, 'full_half_balance', floor_prior_scale=.10) for frame in (before, after))
    assert left.features == right.features
    indices = [i for i,n in enumerate(left.features)
               if not n.startswith('listed_floor_spline_') and n!='listed_floor.unknown']
    for a,b in ((left.means[indices], right.means[indices]),
                (left.prior_scales[indices], right.prior_scales[indices]),
                (left.matrix(before)[:,indices], right.matrix(after)[:,indices])):
        np.testing.assert_array_equal(a,b)
    assert left.floor_reference == right.floor_reference
    for design in (left,right):
        assert (design.floor_knots,design.floor_reference) == knot_specification(design.floor_levels)
    assert left.floor_knots[1:-1] == right.floor_knots[1:-1]
    np.testing.assert_array_equal(left.prior_scales, right.prior_scales)
    common_levels = sorted(set(left.floor_levels)&set(right.floor_levels))
    vectors = [np.asarray([d.contrast_vector(d.floor_reference, f) for f in common_levels])
               for d in (left,right)]
    covariances = [(v*d.prior_scales)@(v*d.prior_scales).T
                  for v,d in zip(vectors,(left,right),strict=True)]
    prior_sd = [np.sqrt(np.diag(c)) for c in covariances]
    prior_changes = [{'floor': f, 'before_log_sd':float(a), 'after_log_sd':float(b),
                      'sd_relative_change_percent':float(100*(b/a-1)) if a>0 else None}
                     for f,a,b in zip(common_levels,*prior_sd,strict=True)]
    previous = load_evidence(reference,evidence)
    updated = load_evidence(dataset,evidence)
    assert previous == updated
    result = {'version': 'expanded-floor-source-and-design-verification-v1',
        'rows': len(before), 'units': int(before.unit_id.nunique()), 'buildings': int(before.building.nunique()),
        'feature_columns': len(left.features), 'unchanged_nonfloor_columns': [left.features[i] for i in indices],
        'floor_knots_before': left.floor_knots, 'floor_knots_after': right.floor_knots,
        'floor_reference': left.floor_reference,
        'floor_prior_scale': .10, 'floor_levels_before': left.floor_levels, 'floor_levels_after': right.floor_levels,
        'floor_support_before': left.floor_support, 'floor_support_after': right.floor_support,
        'means_before': left.means.tolist(), 'means_after': right.means.tolist(),
        'unchanged_endpoint_prior_vectors': bool(np.array_equal(*vectors)),
        'common_endpoint_prior_sd': prior_changes,
        'common_endpoint_prior_covariance_before': covariances[0].tolist(),
        'common_endpoint_prior_covariance_after': covariances[1].tolist(),
        'unchanged_literal_captures': sum(map(len,updated.values())),
        'exact_parent_restored': True, 'all_nonfloor_values_and_encoding_unchanged': True,
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'reference_manifest_sha256': digest(reference/'complete.json'),
        'evidence_manifest_sha256': digest(evidence/'complete.json'),
        'interpretation': 'Floor measurement changes under the same spline construction policy. New upper-floor support moves the endpoint knot52→57, changing common-endpoint curve priors despite identical coefficient scales. Floor centering and missingness prevalence also change. This is not an identical joint prior over floor curves, intercept and cohort-centered contributions.'}
    publish_bundle(output, {'verification.json': canonical(result)+'\n',
        Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'source_manifest_sha256': result['source_manifest_sha256'],
         'reference_manifest_sha256': result['reference_manifest_sha256']})
    print(canonical({k: result[k] for k in ('version','rows','feature_columns','floor_knots_before','floor_knots_after','unchanged_literal_captures','exact_parent_restored')}), flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','dataset','evidence','output'): p.add_argument('--'+name,type=Path,required=True)
    with threadpool_limits(limits=1,user_api='blas'):
        run(**vars(p.parse_args()))

"""Verify the full-cohort experiment changes only the laundry category family."""
import argparse
from pathlib import Path
import tempfile

import numpy as np

from apartments import laundry_floor_split as split
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_increment_design as floor
from models.laundry_source_audit import records


def run(reference, candidate, output):
    paths = [Path(reference), Path(candidate)]
    bundles = [_verified_bundle(p, retain={'observations.jsonl'}) for p in paths]
    rows = [records(files['observations.jsonl']) for _, files in bundles]
    parent, restored = split.parent_rows(bundles[1][0], rows[1])
    assert parent == bundles[0][0] and restored == rows[0]
    data = [runner.load_data(p)[0] for p in paths]
    designs = [floor.FeatureDesign(d, 'full_half_balance', floor_increment_prior_scale=.15) for d in data]
    a, b = designs
    matrices = [d.matrix(frame) for d, frame in zip(designs, data, strict=True)]
    common = [n for n in a.features if not n.startswith('laundry_type.contrast_')]
    assert common == [n for n in b.features if not n.startswith('laundry_type.contrast_')]
    for name in common:
        i, j = a.features.index(name), b.features.index(name)
        np.testing.assert_array_equal(matrices[0][:, i], matrices[1][:, j])
        assert a.means[i] == b.means[j] and a.prior_scales[i] == b.prior_scales[j]
    for name in ('floor_levels', 'floor_thresholds', 'floor_support', 'floor_increment_prior_scale', 'numeric'):
        assert getattr(a, name) == getattr(b, name)
    assert {k: v for k, v in a.categories.items() if k != 'laundry_type'} == {
        k: v for k, v in b.categories.items() if k != 'laundry_type'}
    with tempfile.TemporaryDirectory() as tmp:
        targets = [Path(tmp)/name for name in ('reference', 'candidate')]
        for design, target in zip(designs, targets): design.save(target)
        time_hashes = [{p.name: digest(p) for p in target.glob('time-design.*')} for target in targets]
        assert time_hashes[0] == time_hashes[1]
    priors = []
    for design in designs:
        meta = design.categories['laundry_type']
        basis = np.asarray(meta['basis'])
        pair_sd = []
        for i, low in enumerate(meta['levels']):
            for j in range(i+1, len(meta['levels'])):
                sd = float(np.linalg.norm(basis[j]-basis[i])*.15)
                np.testing.assert_allclose(sd, np.sqrt(2)*.15, rtol=1e-14)
                pair_sd.append({'first': low, 'second': meta['levels'][j], 'log_prior_sd': sd})
        priors.append({'levels': meta['levels'], 'frequencies': meta['frequencies'], 'pairwise_priors': pair_sd})
    assert priors[0]['levels'] == ['in_building', 'in_unit']
    assert priors[1]['levels'] == ['in_building', 'in_unit', 'on_floor']
    changed = [r for r in rows[1] if split.FIELD in r]
    result = {'version': 'laundry-floor-split-design-verification-v1', 'passed': True,
        'rows': len(rows[0]), 'changed_rows': len(changed),
        'changed_units': len({r['unit_id'] for r in changed}), 'changed_buildings': len({r['building'] for r in changed}),
        'unchanged_current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in rows[0]),
        'identical_nonlaundry_columns': common, 'feature_counts': [len(d.features) for d in designs],
        'design_support': [d.support for d in designs], 'time_design_hashes': time_hashes[0],
        'laundry_priors': priors,
        'limitations': ['The joint laundry prior has an additional dimension and different category centering. Pairwise prior scales and every nonlaundry column/prior are unchanged.',
            'The new category measures explicitly reported access on the same floor versus unspecified building access. Generic building laundry may already be on the same floor.',
            'All 172 current rows remain unchanged; historical reporting associations can still affect their fitted estimates.']}
    publish_bundle(output, {'verification.json': canonical(result)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'datasets': [digest(p/'complete.json') for p in paths],
         'implementation_sha256': {p.name: digest(p) for p in [*runner.implementation_paths(), Path(floor.__file__)]}})
    print(canonical(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

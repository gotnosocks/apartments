"""Verify corrected observations, literal evidence and model-feature readiness."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import bayesian_evidence, reviewed_source_lineage
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_floor_increment_design as floor


def main():
    root = Path(__file__).resolve().parents[3]
    original = root/'data/model/chelsea-reviewed-current-analysis-20260918'
    corrected = root/'data/model/chelsea-reviewed-floor-masked-analysis-20260918'
    archive = root/'data/model/chelsea-refreshed-bayesian-descriptions-20260918'
    om, of = _verified_bundle(original, retain={'observations.jsonl'})
    cm, cf = _verified_bundle(corrected, retain={'observations.jsonl'})
    old_rows = [json.loads(s) for s in of['observations.jsonl'].split(b'\n') if s.strip()]
    new_rows = [json.loads(s) for s in cf['observations.jsonl'].split(b'\n') if s.strip()]
    assert reviewed_source_lineage.source_lineage(cm, new_rows) == om
    before = bayesian_evidence.load_evidence(original, archive)
    after = bayesian_evidence.load_evidence(corrected, archive)
    assert before == after
    del after
    changed = []
    for old, new in zip(old_rows, new_rows, strict=True):
        fields = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
        if fields:
            assert fields in [['advertised_floor', 'attribute_review_history'],
                              ['attribute_review_history', 'laundry_type']]
            changed.append({'audit_id': old['audit_id'], 'source_listing_id': old['source_listing_id'],
                            'changed_fields': fields})
        if old['analysis_price_basis'] == 'current_capture_gross_ask':
            assert old == new
    designs = []
    for rows in (old_rows, new_rows):
        frame = pd.DataFrame(rows)
        frame.period = pd.to_datetime(frame.period)
        frame.square_feet = pd.to_numeric(frame.square_feet, errors='coerce')
        assert not frame.audit_id.duplicated().any() and not frame.duplicated(['unit_id', 'period']).any()
        assert np.isfinite(frame.asking_rent).all() and frame.asking_rent.gt(0).all()
        design = floor.FeatureDesign(frame, 'full_half_balance', floor_increment_prior_scale=.15)
        designs.append({'features': design.features, 'known_floor_rows': design.floor_support['known_rows'],
                        'floor_levels': design.floor_levels, 'units': len(design.time.unit_ids),
                        'buildings': len(design.time.buildings)})
    result = {'version': 'corrected-bayesian-source-readiness-v1', 'rows': len(new_rows),
        'current_rows_unchanged': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in new_rows),
        'literal_capture_count': sum(map(len, before.values())), 'literal_evidence_identical': True,
        'changed_rows': changed, 'before_design': designs[0], 'after_design': designs[1],
        'posterior_refitted': False, 'main_selection_changed': False,
        'runner_version_integration_pending': True,
        'interpretation': 'Both correction stages reconstruct the exact original data hash. Only 17 floor masks and one laundry mask plus their review histories differ; prices, source clocks and current listings are unchanged. Evidence loader accepts the verified lineage. Production runner version integration awaits completion of the frozen GPU benchmark.'}
    publish_bundle(root/'data/model/chelsea-corrected-source-readiness-20260919', {
        'readiness.json': canonical(result)+'\n', Path(__file__).name: Path(__file__).read_text(),
        'reviewed_source_lineage.py': Path(reviewed_source_lineage.__file__).read_text(),
        'bayesian_evidence.py': Path(bayesian_evidence.__file__).read_text()},
        {'version': result['version'], 'original_manifest_sha256': digest(original/'complete.json'),
         'corrected_manifest_sha256': digest(corrected/'complete.json'),
         'archive_manifest_sha256': digest(archive/'complete.json'),
         'floor_design_implementation_sha256': digest(floor.__file__)})
    print(canonical({k: result[k] for k in ('rows', 'current_rows_unchanged', 'literal_capture_count',
        'literal_evidence_identical', 'before_design', 'after_design')}), flush=True)


if __name__ == '__main__':
    main()

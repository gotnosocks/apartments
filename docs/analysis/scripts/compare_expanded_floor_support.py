"""Repeat the fixed-cohort support audit before and after expanded floor labels."""
import json
from pathlib import Path

from apartments import pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import amenity_rent_model as amenity
from models.floor_elevator_support import summarize, ambiguity_sensitivity

SOURCES = {
    'reference': ('data/model/chelsea-label-floor-analysis-20260919',
                  '5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605'),
    'expanded': ('data/model/chelsea-expanded-label-floor-analysis-20260919',
                 'd244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717'),
}


def main():
    reports = {}
    for name, (location, expected) in SOURCES.items():
        path = Path(location)
        if digest(path/'complete.json') != expected:
            raise ValueError('Expected the fixed reviewed source manifests')
        _, files = _verified_bundle(path, retain={'observations.jsonl'})
        rows = []
        for line in files['observations.jsonl'].decode().split('\n'):
            if not line:
                continue
            row = json.loads(line)
            normalized = amenity.feature_record(row)
            rows.append({**{key: row[key] for key in ('audit_id', 'unit_id', 'building')},
                         'elevator': pricing._boolean(normalized.get('elevator')),
                         'floor': pricing._numeric_feature('listed_floor', normalized.get('listed_floor'))})
        reports[name] = {'source_manifest_sha256': expected,
                         'modeled_listed_floor': summarize(rows),
                         'opposing_elevator_claim_sensitivity': ambiguity_sensitivity(rows)}
    output = Path('data/model/chelsea-expanded-floor-elevator-support-20260919')
    publish_bundle(output, {'support.json': canonical(reports)+'\n'}, {
        'version': 'matched-expanded-floor-elevator-support-v1',
        'semantics': 'Support only; modeled listed floor combines explicit and label-derived claims. No physical-height inference, new fit, causal claim, or cohort edit.'})
    print(canonical({'manifest_sha256': digest(output/'complete.json')}), flush=True)


if __name__ == '__main__':
    main()

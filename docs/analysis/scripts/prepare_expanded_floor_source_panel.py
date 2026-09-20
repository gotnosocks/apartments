"""Publish a deterministic own-capture review panel without changing any model input."""
from collections import Counter
import json
from pathlib import Path

from apartments import expanded_floor_projection as projection
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import records_hash, sha

VERSION = 'expanded-floor-own-capture-review-panel-v1'
SOURCE = Path('data/model/chelsea-expanded-label-floor-analysis-20260919')
EVIDENCE = Path('data/model/chelsea-refreshed-bayesian-descriptions-20260918')
OUTPUT = Path('data/model/chelsea-expanded-floor-source-panel-20260919')
RULE = ('Take every newly inferred observation with floor above 52. For each named rule, '
    'rank buildings by descending newly inferred observation count, breaking ties by building ID. '
    'Take the first three buildings (or all if fewer). Within each building sort observations '
    'by candidate floor, integer source listing ID, then audit ID; select index (n-1)//2. '
    'Union selections by audit ID. Sort output by building, candidate floor, integer source listing ID, audit ID.')


def run():
    manifest, files = _verified_bundle(SOURCE, retain={'observations.jsonl', projection.SIDECAR})
    rows, changes = [[json.loads(line) for line in files[name].decode().split('\n') if line.strip()]
                     for name in ('observations.jsonl', projection.SIDECAR)]
    _, before = projection.parent_rows(manifest, rows, changes)
    mapping = load_evidence(SOURCE, EVIDENCE)
    by_audit = {row['audit_id']: (row, change) for row, change in zip(rows, changes, strict=True)}
    new = [row for old, row in zip(before, rows, strict=True)
           if old.get('listed_floor') is None and old.get('advertised_floor') is None
           and row.get('listed_floor') is not None]
    chosen = {row['audit_id']: ['all_new_support_above_52'] for row in new if row['listed_floor'] > 52}
    for rule in sorted({row[projection.FIELD]['rule'] for row in new}):
        candidates = [row for row in new if row[projection.FIELD]['rule'] == rule]
        buildings = Counter(row['building'] for row in candidates)
        for building in sorted(buildings, key=lambda key: (-buildings[key], key))[:3]:
            group = sorted([row for row in candidates if row['building'] == building],
                key=lambda row: (row['listed_floor'], int(row['source_listing_id']), row['audit_id']))
            representative = group[(len(group)-1)//2]
            chosen.setdefault(representative['audit_id'], []).append('rule_top_building_median_observation')
    panel = []
    for identity in chosen:
        row, change = by_audit[identity]
        panel.append({'observation': row, 'source_row_sha256': sha(row), 'selection': chosen[identity],
            'label_captures': change['original_change']['captures'], 'description_captures': mapping[identity]})
    panel.sort(key=lambda item: (item['observation']['building'], item['observation']['listed_floor'],
        int(item['observation']['source_listing_id']), item['observation']['audit_id']))
    files = {'panel.jsonl': ''.join(canonical(item)+'\n' for item in panel),
             Path(__file__).name: Path(__file__).read_text()}
    metadata = {'version': VERSION, 'source_manifest_sha256': digest(SOURCE/'complete.json'),
        'source_observations_sha256': manifest['files']['observations.jsonl'],
        'evidence_manifest_sha256': digest(EVIDENCE/'complete.json'), 'selection_rule': RULE,
        'newly_inferred_rows': len(new), 'panel_rows': len(panel),
        'above_52_rows': sum(item['observation']['listed_floor'] > 52 for item in panel),
        'panel_audit_ids_sha256': records_hash([item['observation']['audit_id'] for item in panel]),
        'model_inputs_changed': False, 'descriptions_are_review_inputs_not_automatic_confirmation': True}
    result = publish_bundle(OUTPUT, files, metadata)
    print(canonical({**metadata, 'panel_manifest_sha256': digest(OUTPUT/'complete.json')}), flush=True)
    return result


if __name__ == '__main__':
    run()

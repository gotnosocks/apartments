"""Record Ben's manual studio adjudication, with an exact-source overlay preview.

Does not overwrite a fitted dataset or claim to have refitted its posterior.
Replay reuses the ledger entry instead of appending a duplicate correction.
"""
import hashlib
import json
from pathlib import Path

from apartments.corrections import Overlay, append, canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / 'data/model/chelsea-reviewed-elevator-analysis-20260919'
REVIEW = ROOT / 'data/model/chelsea-laundry-dominant-building-raw-review-20260919'
LEDGER = ROOT / 'config/reviews/chelsea-thomas-eddy-studio-20260919.jsonl'
OUTPUT = ROOT / 'data/model/chelsea-thomas-eddy-studio-review-20260919'


def run():
    _, files = _verified_bundle(DATASET, retain={'observations.jsonl'})
    _, evidence = _verified_bundle(REVIEW, retain={'captures.jsonl'})
    rows = [json.loads(line) for line in files['observations.jsonl'].splitlines()]
    selected = [r for r in rows if r['source_listing_id'] == '3223153']
    if len(selected) != 1:
        raise ValueError('Expected exactly one reviewed advertisement observation')
    row = selected[0]
    captures = [json.loads(line) for line in evidence['captures.jsonl'].splitlines()
                if json.loads(line)['source_listing_id'] == '3223153']
    if (row['canonical_unit_url'] != 'https://streeteasy.com/building/the-thomas-eddy/2c'
            or row['bedrooms'] != 1 or row['capture_ids'] != [68524]
            or len(captures) != 1
            or captures[0]['property_details']['address']['displayUnit'] != '#2C'
            or captures[0]['property_details']['bedroomCount'] != 1
            or 'Beautiful Studio in Prime Chelsea!' not in captures[0]['raw_description']):
        raise ValueError('Reviewed source identity/count/description changed')
    version = hashlib.sha256(canonical(row).encode()).hexdigest()
    spec = {'target': {'source': 'streeteasy', 'source_listing_id': '3223153',
                       'version_id': version},
            'validity': {'all_time': True},
            'patch': [{'op': 'test', 'path': '/bedrooms', 'value': 1.0},
                      {'op': 'replace', 'path': '/bedrooms', 'value': 0.0}]}
    if not LEDGER.exists():
        append(LEDGER, author='Ben (manual review), recorded by Codex', edit=spec,
               reason='User manually reviewed Thomas Eddy 2C and confirmed it is a studio. '
                      'Correct the reviewed advertisement bedroom count; no physical change date inferred.',
               evidence=['User instruction: "Thomas Eddy 2C is a studio based on manual review, '
                         'you may record a correction"',
                         'docs/analysis/chelsea-laundry-residual-source-review-2026-09-19.md',
                         'raw_listing_sha256=' + captures[0]['raw_listing_sha256']])
    overlay = Overlay(LEDGER)
    if len(overlay.records) != 1 or any(overlay.active[0][k] != v for k, v in spec.items()):
        raise ValueError('Ledger differs from the manual adjudication')
    # A stable cutoff makes repeat publication byte-identical.
    overlay = Overlay(LEDGER, as_of=overlay.records[0]['recorded_at'])
    corrected, applied = overlay.apply(row, spec['target'], effective_at=row['price_at'])
    if corrected['bedrooms'] != 0 or len(applied) != 1:
        raise ValueError('Correction did not apply')
    if {k: v for k, v in corrected.items() if k != 'bedrooms'} != {
            k: v for k, v in row.items() if k != 'bedrooms'}:
        raise ValueError('Unexpected change outside bedroom count')
    summary = {'advertisement': '3223153', 'unit': 'Thomas Eddy 2C',
               'before_bedrooms': 1, 'corrected_bedrooms': 0,
               'status': 'correction_recorded_and_replay_verified_pending_dataset_projection_and_refit',
               'correction_id': applied[0]['id'], 'selected_fit_changed': False,
               'scope': 'Exact reviewed analytical row version; no propagation to other advertisements.'}
    publish_bundle(OUTPUT, {'review.json': canonical({'original': row, 'corrected': corrected,
                    'corrections': applied, 'source_captures': captures}) + '\n',
                    'summary.json': canonical(summary) + '\n',
                    'corrections.jsonl': LEDGER.read_text(),
                    Path(__file__).name: Path(__file__).read_text()},
                   {'version': 'manual-bedroom-adjudication-v1',
                    'source_manifest_sha256': digest(DATASET / 'complete.json'),
                    'source_review_manifest_sha256': digest(REVIEW / 'complete.json'),
                    'overlay': overlay.manifest})
    print(canonical(summary))


if __name__ == '__main__':
    run()

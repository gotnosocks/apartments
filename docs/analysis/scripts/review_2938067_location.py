"""Verify the manually reviewed Park Slope/Chelsea conflict in both own captures."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(inputs, archive, output):
    inputs, archive, output = map(Path, (inputs, archive, output))
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    if hashlib.sha256(files['cases.jsonl']).hexdigest() != '0f8bb602fb6b52c3277ecbbf1f0eda8e0070f67122f7735ca82cc11ec0fae46b':
        raise ValueError('Review is bound to the exact manually inspected cases')
    cases = [json.loads(s) for s in files['cases.jsonl'].decode().split('\n') if s]
    matches = [c for c in cases if c['observation']['source_listing_id'] == '2938067']
    assert len(matches) == 1
    case = matches[0]
    row = case['observation']
    assert row['building'] == '322-7-avenue-new_york'
    captures = case['descriptions']
    assert {d['capture_id'] for d in captures} == set(row['capture_ids']) == {45451, 122998}
    witnesses = []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for capture in captures:
            records = db.execute(
                'SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                [str(archive/'listing_observations/*.parquet'), capture['capture_id']],
            ).fetchall()
            assert len(records) == 1
            raw = records[0][0]
            assert hashlib.sha256(raw.encode()).hexdigest() == capture['raw_listing_sha256']
            listing = json.loads(raw)
            assert str(listing['id']) == '2938067'
            description = listing['description']
            assert description == capture['description']
            assert hashlib.sha256(description.encode()).hexdigest() == capture['description_sha256']
            address = listing['propertyDetails']['address']
            assert address == {'city': 'NEW YORK', 'displayUnit': '#3F',
                               'state': 'NY', 'street': '322 7th Avenue', 'zipCode': '10001'}
            spans = []
            for phrase in ('Gorgeous Park Slope 1 bedroom', 'across from the G/F train station',
                           '2 blocks to Prospect Park', 'Brooklyn Public Library'):
                start = description.index(phrase)
                spans.append({'start': start, 'end': start + len(phrase), 'text': phrase})
            witnesses.append({**capture, 'raw_listing_json': raw,
                              'structured_address': address, 'literal_spans': spans})
    finding = {
        'source_listing_id': '2938067', 'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
        'finding_kind': 'within_source_location_conflict',
        'proposed_action': 'quarantine_location_conflict', 'applied': False,
        'reason': 'Both own captures assign 322 7th Avenue, Manhattan ZIP 10001, while the full description repeatedly locates the offer in Park Slope near Prospect Park and Brooklyn Public Library. Quarantine this exact unresolved advertisement from location-dependent analysis; do not infer a replacement address or change price, floor, or sibling advertisements.',
        'selection_reasons': case['selection_reasons'], 'movement': case['movement'],
        'temporal_scope': 'Retrospective own-ad claims; physical location and effective dates unresolved.',
    }
    publish_bundle(output, {
        'finding.json': canonical(finding) + '\n',
        'raw-witnesses.jsonl': ''.join(canonical(w) + '\n' for w in witnesses),
        'reviewed-case.json': canonical(case) + '\n',
        Path(__file__).name: Path(__file__).read_text(),
    }, {'version': 'reviewed-2938067-location-v1', 'cases': 1, 'captures': 2,
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': manifest['source_manifest_sha256'],
        'comparison_manifest_sha256': manifest['comparison_manifest_sha256'],
        'source_or_model_changes': False})
    _verified_bundle(output)
    return {'output': str(output), 'manifest_sha256': digest(output/'complete.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'archive', 'output'):
        parser.add_argument('--' + name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

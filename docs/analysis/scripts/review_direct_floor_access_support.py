"""Freeze cached building access evidence for the reviewed floor additions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import duckdb

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


# Complete cached descriptions manually read; these are source claims, not
# permission to project a building-wide historical physical attribute.
WALKUPS = {'162-9-avenue-new_york': 'This charming walk-up',
           '322-west-22-street-new_york': 'This 4-story walk-up building',
           '421-west-22-street-new_york': 'This pre-war townhouse is a walk-up'}


def run(dataset, review, archive, output):
    dataset, review, archive, output = map(Path, (dataset, review, archive, output))
    if digest(dataset/'complete.json') != '2a92f7a593895bcb9389742ef1378ddaf729ef73a9325f96bff4e975d05699fd':
        raise ValueError('Reviewed floor source changed')
    if digest(review/'complete.json') != '8e604e097759247754d69d76149687980c93153ef66e67271035a544fabbac87':
        raise ValueError('Floor evidence review changed')
    _, files = _verified_bundle(dataset, retain={'direct-floor-changes.jsonl'})
    _, evidence = _verified_bundle(review, retain={'witnesses.jsonl'})
    records = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    changes = records(files['direct-floor-changes.jsonl'])
    unknown = [c for c in changes if c['before'].get('elevator') is None]
    ads = {c['case']['source_listing_id'] for c in unknown}
    descriptions = [w['capture'] for w in records(evidence['witnesses.jsonl'])
                    if w['capture']['source_listing_id'] in ads]
    for capture in descriptions:
        assert hashlib.sha256(capture['description'].encode()).hexdigest() == capture['description_sha256']
        assert not re.search(r'elevator|walk[ -]?up|flights?\b|stairs', capture['description'], re.I)
    buildings = sorted({c['before']['building'] for c in unknown})
    witnesses, findings = [], []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for building in buildings:
            found = db.execute('SELECT snapshot_id,raw_building_json FROM read_parquet(?) WHERE building_slug=?',
                [str(archive/'building_observations/*.parquet'), building]).fetchall()
            assert found
            for capture_id, raw in found:
                payload = json.loads(raw)
                assert payload['slug'] == building
                metadata = db.execute('SELECT url,body_hash,observed_at FROM read_parquet(?) WHERE snapshot_id=?',
                    [str(archive/'snapshots/*.parquet'), capture_id]).fetchall()
                assert len(metadata) == 1
                url, body_hash, observed_at = metadata[0]
                literal = WALKUPS.get(building)
                description = payload['description']
                span = None
                if literal:
                    start = description.index(literal)
                    span = {'start': start, 'end': start+len(literal), 'text': literal}
                witnesses.append({'building': building, 'snapshot_id': capture_id,
                    'source_url': url, 'source_observed_at_unix': observed_at,
                    'body_sha256': body_hash, 'raw_building_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                    'raw_building_json': raw, 'walkup_span': span})
            findings.append({'building': building,
                'affected_ads': sorted(c['case']['source_listing_id'] for c in unknown if c['before']['building'] == building),
                'finding': 'explicit_building_walkup_claim' if building in WALKUPS else 'no_reviewed_access_claim',
                'applied': False})
    summary = {'floor_additions': len(changes), 'floors': dict(Counter(str(c['case']['advertised_floor']) for c in changes)),
        'elevator_status': dict(Counter(str(c['before'].get('elevator')) for c in changes)),
        'price_bases': dict(Counter(c['before']['analysis_price_basis'] for c in changes)),
        'unknown_access_ads': len(ads), 'unknown_access_buildings': len(buildings),
        'building_captures_reviewed': len(witnesses), 'explicit_walkup_buildings': len(WALKUPS),
        'explicit_walkup_affected_ads': sum(len(f['affected_ads']) for f in findings if f['building'] in WALKUPS),
        'source_or_model_changes': False,
        'limitations': ['Cached building prose describes access but does not verify installation history or legal classification.',
            'Unresolved encoded amenity references and absent access text are not evidence of no elevator.',
            'No building-wide propagation or inferred elevator status applied; the running fit remains floor-only.']}
    assert len(changes) == 24 and len(ads) == 18 and len(buildings) == 6
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'findings.jsonl': ''.join(canonical(f)+'\n' for f in findings),
        'building-witnesses.jsonl': ''.join(canonical(w)+'\n' for w in witnesses),
        'unit-description-witnesses.jsonl': ''.join(canonical(c)+'\n' for c in descriptions),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'direct-floor-access-support-review-v1',
         'dataset_manifest_sha256': digest(dataset/'complete.json'),
         'review_manifest_sha256': digest(review/'complete.json')})
    _verified_bundle(output)
    print(canonical({**summary, 'manifest_sha256': digest(output/'complete.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'review', 'archive', 'output'):
        parser.add_argument('--'+name, required=True)
    run(**vars(parser.parse_args()))

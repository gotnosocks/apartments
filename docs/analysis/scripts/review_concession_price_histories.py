"""Bind four price-basis leads to all six exact raw own-ad capture histories."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(inputs, archive, output):
    inputs, archive, output = map(Path, (inputs, archive, output))
    expected = '52c6009ba76b7be937aca27b2623b770aa17cf026a09642a8985c86a2143a218'
    if digest(inputs/'complete.json') != expected:
        raise ValueError('Price review input differs')
    _, files = _verified_bundle(inputs, retain={'price-basis-leads.jsonl'})
    cases = [json.loads(l) for l in files['price-basis-leads.jsonl'].decode().split('\n') if l]
    witnesses, reviews = [], []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for case in cases:
            row = case['source_row']
            histories = []
            for cap in case['captures']:
                found = db.execute('SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                    [str(archive/'listing_observations/*.parquet'), cap['capture_id']]).fetchall()
                if len(found) != 1:
                    raise ValueError('Raw capture absent or duplicated')
                raw = found[0][0]
                if hashlib.sha256(raw.encode()).hexdigest() != cap['raw_listing_sha256']:
                    raise ValueError('Raw capture differs')
                listing = json.loads(raw)
                if str(listing['id']) != row['source_listing_id']:
                    raise ValueError('Own-ad identity differs')
                own = [h for h in listing['propertyHistory'] if str(h['listingId']) == row['source_listing_id']]
                if len(own) != 1:
                    raise ValueError('Own history absent or duplicated')
                events = own[0]['rentalEventsOfInterest']
                if not any(e.get('status') == 'ACTIVE' and e['date'] == row['price_at'][:10]
                           and e['price'] == row['asking_rent'] for e in events):
                    raise ValueError('Analytical initial active event missing')
                histories.append(events)
                witnesses.append({'capture': cap, 'raw_listing_json': raw,
                    'own_ad_events': events, 'analytical_initial_event_verified': True})
            if any(canonical(h) != canonical(histories[0]) for h in histories):
                raise ValueError('Own-ad histories disagree across captures')
            reviews.append({'source_row': row, 'own_ad_events': histories[0],
                'gross_quote': case['captured_description_gross_rent'],
                'capture_ids': [c['capture_id'] for c in case['captures']],
                'historical_concession_effective_date_verified': False,
                'source_or_model_changes': False})
    if len(reviews) != 4 or len(witnesses) != 6:
        raise ValueError('Review membership differs')
    publish_bundle(output, {'review.jsonl': ''.join(canonical(r)+'\n' for r in reviews),
        'raw-witnesses.jsonl': ''.join(canonical(w)+'\n' for w in witnesses),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'concession-own-ad-history-review-v1', 'input_manifest_sha256': expected,
         'cases': len(reviews), 'raw_captures': len(witnesses), 'source_or_model_changes': False})
    _verified_bundle(output)
    return {'cases': len(reviews), 'raw_captures': len(witnesses), 'manifest_sha256': digest(output/'complete.json')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'archive', 'output'):
        p.add_argument('--'+name, required=True)
    print(canonical(run(**vars(p.parse_args()))))

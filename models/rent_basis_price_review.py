"""Bind prioritized literal-price cases to original own-ad pricing and events.

Review packet only: a later captured quote is never assigned to an earlier date.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'literal-rent-basis-own-price-review-v1'


def own_event_review(row, capture_id, events):
    own = [e for e in events if e['snapshot_id'] == capture_id
           and str(e['event_listing_id']) == row['source_listing_id'] and e['event_category'] == 'rental']
    active = [e for e in own if e['status'] == 'ACTIVE']
    first_at = min((instant(e['event_date']) for e in active), default=None)
    initial = [e for e in active if instant(e['event_date']) == first_at]
    return {'own_rental_events': own, 'initial_active_events': initial,
            'initial_event_matches_analytical_target': bool(initial) and first_at == instant(row['price_at'])
                and all(e['price'] == row['asking_rent'] for e in initial)}


def run(audit, historical, archive, output):
    audit, historical, archive = map(Path, (audit, historical, archive))
    am, af = _verified_bundle(audit, retain={'cases.jsonl'})
    if am.get('version') != 'literal-rent-basis-source-audit-v1':
        raise ValueError('Expected verified literal rent-basis source audit')
    _, hf = _verified_bundle(historical, retain={'source-files.json'})
    inventory = json.loads(hf['source-files.json'])
    candidates = [json.loads(s) for s in af['cases.jsonl'].decode().split('\n') if s]
    selected, targets = [], {}
    for case in candidates:
        if case['source_record']['analysis_price_basis'] != 'historical_initial_own_advertisement_ask': continue
        # Include all positive target-net matches and all affirmative advertised-net statements,
        # including counterexamples where the historical target matches a quoted gross amount.
        target_net = case['classification'] in {'all_captures_match_explicit_net_only',
            'some_captures_match_explicit_net', 'target_matches_both_net_and_gross_quotes'}
        stated_net = any(not s['preceded_by_negation'] and not s['administrative_context']
            for c in case['captures'] for s in c['measurement']['advertised_net_statements'])
        if not (target_net or stated_net): continue
        selected.append(case)
        for capture in case['captures']:
            identity = capture['capture_id']
            if type(identity) is not int or identity in targets:
                raise ValueError('Historical review needs distinct integer capture identities')
            targets[identity] = (case['source_record'], capture)
    found = {}
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for relative, expected in sorted(inventory.items()):
            if not relative.startswith('listing_observations/') or not relative.endswith('.parquet'): continue
            path = archive/relative
            if not path.resolve().is_relative_to(archive.resolve()): raise ValueError('Invalid source path')
            matches = db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?) '
                'WHERE snapshot_id IN (SELECT unnest(?))', [str(path), list(targets)]).fetchall()
            if not matches: continue
            if digest(path) != expected: raise ValueError('Original listing shard differs')
            event_relative = 'event_mentions/'+path.name
            event_path = archive/event_relative
            if digest(event_path) != inventory.get(event_relative): raise ValueError('Original event shard differs')
            cursor = db.execute('SELECT * FROM read_parquet(?) WHERE snapshot_id IN (SELECT unnest(?)) '
                                'ORDER BY snapshot_id,event_date,episode_index,event_index',
                                [str(event_path), [i for i, _ in matches]])
            names = [d[0] for d in cursor.description]
            events = [dict(zip(names, r)) for r in cursor.fetchall()]
            for identity, raw in matches:
                if identity in found: raise ValueError('Duplicate original capture')
                row, capture = targets[identity]
                if hashlib.sha256(raw.encode()).hexdigest() != capture['raw_listing_sha256']:
                    raise ValueError('Original raw listing hash differs')
                payload = json.loads(raw)
                if str(payload['id']) != row['source_listing_id']: raise ValueError('Original ad identity differs')
                found[identity] = {'capture_id': identity, 'source_listing_id': row['source_listing_id'],
                    'audit_id': row['audit_id'], 'raw_listing_sha256': capture['raw_listing_sha256'],
                    'listing_shard': relative, 'listing_shard_sha256': expected,
                    'event_shard': event_relative, 'event_shard_sha256': inventory[event_relative],
                    'pricing': payload.get('pricing'), **own_event_review(row, identity, events)}
    if found.keys() != targets.keys(): raise ValueError('Missing original review captures')
    cases = [{**case, 'original_price_records': [found[c['capture_id']] for c in case['captures']]}
             for case in selected]
    summary = {'version': VERSION, 'cases': len(cases), 'captures': len(found),
        'by_classification': dict(sorted(Counter(c['classification'] for c in cases).items())),
        'initial_event_target_match_captures': sum(r['initial_event_matches_analytical_target'] for r in found.values()),
        'policy': 'All positive target-net matches and all affirmative advertised-net statements, including gross-target counterexamples. '
            'No residual-based selection. Every attached historical capture is verified against original raw listing and event shards. '
            'Event date labels and price-change timestamps remain distinct. No automatic correction, conversion or exclusion.'}
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases), Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'audit_manifest_sha256': digest(audit/'complete.json'),
         'historical_manifest_sha256': digest(historical/'complete.json'),
         'source_dataset_manifest_sha256': am['dataset_manifest_sha256']})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('audit', 'historical', 'archive', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

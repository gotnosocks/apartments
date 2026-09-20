"""Read-only coverage and canonical-identity audit; never makes site requests."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sqlite3

from apartments.granular_parse import parse_listing


def audit(data_dir):
    root = Path(data_dir).resolve()
    db = sqlite3.connect((root / 'archive.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('BEGIN')  # All database counters and evidence share one read snapshot.
    try:
        generation = db.execute('SELECT max(id) FROM generations').fetchone()[0]
        if generation is None:
            raise ValueError('Archive has no generation')
        policy = db.execute('SELECT value FROM metadata WHERE key=?',
                            (f'collection_policy:{generation}',)).fetchone()
        if not policy or policy[0] != 'rental-canonical-v1':
            raise ValueError('Archive does not use the rental-canonical collection policy')
        observations = db.execute('SELECT count(*),coalesce(sum(error IS NOT NULL),0),max(id),max(fetched) FROM observations WHERE generation=?',
                                  (generation,)).fetchone()
        states = dict(db.execute('SELECT state,count(*) FROM frontier JOIN scope_urls USING(generation,url) WHERE generation=? GROUP BY state', (generation,)))
        exclusions = dict(db.execute('SELECT reason,count(*) FROM collection_exclusions WHERE generation=? GROUP BY reason', (generation,)))
        aliases = Counter()
        for row in db.execute('SELECT reason FROM url_aliases WHERE generation=?', (generation,)):
            try:
                proof = json.loads(row[0])
            except (ValueError, TypeError):
                continue
            if isinstance(proof, dict) and proof.get('validation'):
                aliases[proof['validation']] += 1
        records = []
        # Report historical exclusions as an audit trail, and recompute their
        # current interpretation from the latest captured bytes and membership.
        for observation in db.execute('''SELECT o.* FROM observations o
            WHERE o.generation=? AND EXISTS(SELECT 1 FROM collection_exclusions e
                WHERE e.generation=o.generation AND e.url=o.url AND e.reason='captured_listing_not_eligible')
            AND o.id=(SELECT id FROM observations latest WHERE latest.generation=o.generation
                AND latest.url=o.url ORDER BY fetched DESC,id DESC LIMIT 1)
            ORDER BY o.url''', (generation,)):
            record = {'url': observation['url'], 'observation_id': observation['id'],
                      'body_hash': observation['body_hash']}
            if observation['error'] is not None or not observation['status'] or not (200 <= observation['status'] < 300 or observation['status'] == 304):
                records.append(dict(record, classification='latest_capture_failed'))
                continue
            digest = observation['body_hash']
            if not digest:
                records.append(dict(record, classification='missing_body'))
                continue
            try:
                body = gzip.decompress((root / 'bodies' / digest[:2] / (digest + '.gz')).read_bytes())
                parsed, events = parse_listing(body, observation['url'])
            except (OSError, ValueError, EOFError):
                records.append(dict(record, classification='unreadable_capture'))
                continue
            unit = parsed.get('canonical_unit_url')
            expected = sorted(r[0] for r in db.execute('''SELECT DISTINCT unit_url FROM collection_memberships
                WHERE generation=? AND listing_key=?''', (generation, f"rental:{parsed.get('listing_id')}:detail")))
            if not unit or parsed.get('canonical_unit_error'):
                classification = 'missing_canonical_unit'
            elif parsed.get('parse_status') != 'ok':
                classification = 'incomplete_listing_parse'
            elif parsed.get('listing_type') != 'rental' or not any(e['event_category'] == 'rental' for e in events):
                classification = 'not_verified_rental'
            elif not expected:
                classification = 'missing_unit_association'
            elif len(expected) > 1:
                classification = 'conflicting_unit_associations'
            elif expected != [unit]:
                classification = 'canonical_unit_mismatch'
            else:
                classification = 'association_now_supported'
            records.append(dict(record, classification=classification, canonical_unit_url=unit,
                                associated_unit_urls=expected,
                                parser_error=parsed.get('canonical_unit_error') or parsed.get('error')))
        return {'schema': 'rental-collection-audit-v1', 'generation': generation,
                'observations': observations[0], 'capture_errors': observations[1],
                'through_observation_id': observations[2], 'latest_capture_at': observations[3],
                'scoped_frontier': states, 'historical_exclusions': exclusions,
                'verified_reuse_by_validation': dict(aliases),
                'current_exclusion_interpretations': dict(Counter(r['classification'] for r in records)),
                'exclusion_evidence': records}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.data)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently replace an earlier audit artifact.
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'exclusion_evidence'}, indent=2))


if __name__ == '__main__':
    main()

"""Create two reviewed ad-specific scope decisions from verified literal evidence."""
import argparse
import json
from pathlib import Path

import duckdb

from apartments import reviewed_cohort_quarantine as lineage
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.reviewed_cohort_projection import DECISION_VERSION, rows

REVIEW = {
    '2675026': ('quarantine_unresolved_gross_price_basis',
        'The initial own-ad asking target equals the explicitly named net rent; structured concession fields are null. Quarantine the unresolved gross basis. Do not replace the initial price with the later gross quote.',
        'net_price_basis_and_divided_layout',
        'The gross rent is $3,100 with 1 month free on a 14-month lease term, the net rent is just $2,878!'),
    '970866': ('quarantine_explicit_short_term_offer',
        'The complete own-ad description affirmatively offers a short-term rental without establishing an ordinary long-term option or the quoted price for it. Quarantine this advertisement from the ordinary long-term cohort, retaining all other ads for the unit.',
        'short_term_product_and_missed_same_floor', 'AVAILABLE ON A SHORT-TERM BASIS'),
}


def initial_price_evidence(row, pricing, events):
    """Check the actual date-labelled ACTIVE event, separately from timestamps.

    Historical targets use event_mentions.event_date (e.g. 2019-03-12), not
    pricing.priceChanges.changedAt (which can be March 13 after UTC conversion).
    Neither timestamp is substituted for the other.
    """
    own = [e for e in events if str(e['event_listing_id']) == row['source_listing_id']
           and e['event_category'] == 'rental' and e['status'] == 'ACTIVE']
    prices = sorted(pricing['priceChanges'], key=lambda e: instant(e['changedAt']))
    first = min((instant(e['event_date']) for e in own), default=None)
    initial = [e for e in own if instant(e['event_date']) == first]
    if (first != instant(row['price_at']) or not initial or not prices
            or any(e['price'] != row['asking_rent'] for e in initial)
            or prices[0]['price'] != row['asking_rent'] or row['asking_rent'] != 2878
            or not any(e['price'] == 3100 for e in prices[1:])):
        raise ValueError('Initial net quote and later gross price evidence differ')
    return initial


def load_events(originals, historical, archive, expected_manifest):
    _, hf = _verified_bundle(historical, retain={'source-files.json'})
    if digest(historical/'complete.json') != expected_manifest:
        raise ValueError('Historical event inventory differs from raw review')
    inventory = json.loads(hf['source-files.json'])
    result = {}
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for capture_id, original in originals.items():
            if original['source_listing_id'] != '2675026': continue
            relative = 'event_mentions/'+Path(original['source_shard']).name
            path = archive/relative
            if digest(path) != inventory.get(relative):
                raise ValueError('Historical event shard differs')
            cursor = db.execute('SELECT * FROM read_parquet(?) WHERE snapshot_id=?', [str(path), capture_id])
            names = [d[0] for d in cursor.description]
            result[capture_id] = {'source_shard': relative, 'source_shard_sha256': inventory[relative],
                                  'events': [dict(zip(names, r)) for r in cursor.fetchall()]}
    return result


def run(reviewed_at, output):
    base = Path(__file__).resolve().parents[3]/'data/model'
    dataset = base/'chelsea-reviewed-floor-masked-analysis-20260918'
    candidates = base/'chelsea-laundry-dominant-building-review-candidates-20260919'
    review = base/'chelsea-laundry-dominant-building-source-review-20260919'
    raw = base/'chelsea-laundry-dominant-building-raw-review-20260919'
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    cm, cf = _verified_bundle(candidates, retain={'cases.jsonl'})
    rm, rf = _verified_bundle(review, retain={'decisions.jsonl'})
    xm, xf = _verified_bundle(raw, retain={'captures.jsonl'})
    if (cm['reference_dataset_sha256'] != digest(dataset/'complete.json')
            or rm['candidate_manifest_sha256'] != digest(candidates/'complete.json')
            or rm['raw_review_manifest_sha256'] != digest(raw/'complete.json')
            or xm['candidates_manifest_sha256'] != digest(candidates/'complete.json')):
        raise ValueError('Manual review/source lineage differs')
    source = {r['source_listing_id']: r for r in rows(sf['observations.jsonl']) if r['source_listing_id'] in REVIEW}
    cases = {c['source_record']['source_listing_id']: c for c in rows(cf['cases.jsonl'])}
    adjudicated = {r['source_listing_id']: r for r in rows(rf['decisions.jsonl'])}
    originals = {r['capture_id']: r for r in rows(xf['captures.jsonl'])}
    events = load_events(originals, base.parent/'exports/chelsea-serving-history-20260918-asof1600',
        Path('/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1'),
        xm['historical_manifest_sha256'])
    if source.keys() != REVIEW.keys(): raise ValueError('Reviewed advertisements absent from source')
    decisions = []
    for ad, (action, reason, finding, phrase) in REVIEW.items():
        row, case = source[ad], cases[ad]
        if adjudicated[ad]['finding'] != finding or adjudicated[ad]['audit_id'] != row['audit_id']:
            raise ValueError('Reviewed finding differs')
        evidence = []
        for capture in case['captures']:
            text = capture['description']; start = text.find(phrase)
            original = originals[capture['capture_id']]
            if (start < 0 or original['audit_id'] != row['audit_id'] or original['source_listing_id'] != ad
                    or original['raw_listing_sha256'] != capture['raw_listing_sha256']):
                raise ValueError('Positive scope evidence or raw capture binding differs')
            if ad == '2675026':
                event_source = events[capture['capture_id']]
                initial = initial_price_evidence(row, original['pricing'], event_source['events'])
            evidence.append({**capture, 'spans': [{'start': start, 'end': start+len(phrase), 'literal': phrase}],
                             'reviewed_original_pricing': original['pricing']})
            if ad == '2675026':
                evidence[-1]['initial_active_event_evidence'] = {**event_source, 'events': initial}
        decision = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
            'action': action, 'reason': reason, 'reviewer': 'codex', 'reviewed_at': reviewed_at,
            'source_row_sha256': lineage.sha(row), 'evidence': evidence,
            'adjudication_manifest_sha256': digest(review/'complete.json'),
            'raw_review_manifest_sha256': digest(raw/'complete.json')}
        decision['decision_id'] = lineage.sha(decision)
        lineage.validate_decision(row, decision, reviewed_at)
        decisions.append(decision)
    decisions.sort(key=lambda d: d['audit_id'])
    publish_bundle(output, {'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': DECISION_VERSION, 'reviewed_at': reviewed_at,
         'source_manifest_sha256': digest(dataset/'complete.json'),
         'source_observations_sha256': sm['files']['observations.jsonl'],
         'adjudication_manifest_sha256': digest(review/'complete.json'),
         'raw_review_manifest_sha256': digest(raw/'complete.json')})
    print(canonical({'decisions': len(decisions), 'source_listing_ids': list(REVIEW), 'output': str(output)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-at', required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(**vars(parser.parse_args()))

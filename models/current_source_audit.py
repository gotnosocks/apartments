"""Audit current asking-price wording and product scope against own raw listings."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

from apartments import granular_parse
from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import refresh_analysis_cohort as cohort

VERSION = 'current-own-listing-source-audit-v1'
PATTERNS = {
    'net_effective_wording': r'\bnet[ -]*effective\b',
    'scope_wording': r'\b(?:retail|commercial|office)\s+(?:space|storefront|lease|rental|loft)\b|\blive[ /-]*work\b',
    'product_wording': r'\b(?:furnished|short[ -]*term|months? free|income[ -]*restrict\w*|affordable|lottery|rent[ -]*stabili\w*)\b',
    'laundry_hookups': r'\bhook[ -]?ups?\b',
}
RENT = re.compile(r'\b(?:monthly\s+rent|rent)\s*:\s*\$\s*(\d[\d,]*(?:\.\d{2})?)(?!\d)', re.I)
APPROVAL = re.compile(r'Approval Standards:\s*Where applicable, approvals are based on the gross rent, not the net effective rent\.', re.I)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def inspect(row, payload):
    if str(payload.get('id')) != str(row['source_listing_id']):
        raise ValueError('Wrong advertisement in current source audit')
    pricing = payload.get('pricing') or {}; text = payload.get('description') or ''
    current = number(pricing.get('price')); cutoff = instant(row['collected_at'])
    events, invalid, future = [], [], []
    for index, event in enumerate(pricing.get('priceChanges') or []):
        try:
            at = instant(event['changedAt']); value = number(event['price'])
            if value is None:
                raise ValueError('Invalid price')
        except (ValueError, TypeError, KeyError):
            invalid.append({'index': index, 'event': event}); continue
        record = {'index': index, 'changed_at': at.isoformat(), 'price': value}
        (future if at > cutoff else events).append(record)
    events.sort(key=lambda e: (e['changed_at'], e['price'], e['index']))
    latest = [e for e in events if e['changed_at'] == events[-1]['changed_at']] if events else []
    latest_prices = {e['price'] for e in latest}
    latest_agrees = bool(latest_prices == {current})
    earlier_prices = {e['price'] for e in events if latest and e['changed_at'] < latest[0]['changed_at']}
    quotes = []
    for match in RENT.finditer(text):
        value = float(match.group(1).replace(',', ''))
        quotes.append({'source_path': '/description', 'start': match.start(), 'end': match.end(),
            'literal': match.group(), 'price': value, 'matches_current_structured_price': value == current,
            'matches_earlier_price_before_verified_current_change': bool(
                value != current and latest_agrees and value in earlier_prices)})
    findings = []
    approvals = [(m.start(), m.end()) for m in APPROVAL.finditer(text)]
    for family, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text, re.I):
            findings.append({'family': family, 'source_path': '/description',
                'start': match.start(), 'end': match.end(), 'literal': match.group(),
                'context': text[max(0, match.start()-100):min(len(text), match.end()+180)],
                'approval_standards_scope': family == 'net_effective_wording' and
                    any(a <= match.start() < match.end() <= b for a, b in approvals)})
    flags = []
    if current != row['asking_rent']: flags.append('structured_and_analytical_price_differ')
    if latest and not latest_agrees: flags.append('latest_visible_price_event_differs')
    if invalid: flags.append('invalid_price_events')
    if future: flags.append('price_events_after_capture')
    if any(not q['matches_current_structured_price'] for q in quotes):
        flags.append('description_rent_differs')
    return {'structured_price': current, 'analytical_price': row['asking_rent'],
        'pricing_fields': {k: pricing.get(k) for k in ('price', 'netEffectiveRent', 'monthsFree',
            'leaseTermMonths', 'furnishedRent', 'totalMonthlyPrice')},
        'own_price_changes': events, 'invalid_price_events': invalid, 'future_price_events': future,
        'latest_price_change_agrees': latest_agrees if latest else None,
        'description_rent_quotes': quotes, 'wording_findings': findings, 'flags': flags}


def run(dataset, collections, output):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl'})
    if dm.get('version') != cohort.VERSION:
        raise ValueError('Capture-refreshed analytical cohort required')
    rows = [r for r in cohort.records(df['observations.jsonl']) if r['analysis_price_basis'] == 'current_capture_gross_ask']
    evidence = {e['capture_id']: e for e in cohort.records(df['current-source-evidence.jsonl'])}
    if set(evidence) != {r['capture_id'] for r in rows} or len(evidence) != len(rows):
        raise ValueError('Current evidence coverage differs')
    sources, bindings = {}, []
    for collection in collections:
        _, _, paths, binding = cohort.load_collection(collection)
        if sources.keys() & paths.keys(): raise ValueError('Overlapping current capture identities')
        sources.update(paths); bindings.append(binding)
    if bindings != dm['collections']:
        raise ValueError('Collection evidence differs from cohort')
    reviews = []
    for row in sorted(rows, key=lambda r: r['audit_id']):
        e = evidence[row['capture_id']]; source = cohort.capture_evidence(row, sources[row['capture_id']])
        if {k: v for k, v in e.items() if k != 'audit_id'} != source or e['audit_id'] != row['audit_id']:
            raise ValueError('Saved current evidence differs from raw capture')
        sha = source['body_sha256']; root = sources[row['capture_id']]
        body = gzip.decompress((root / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha: raise ValueError('Current source body changed')
        parsed, _ = granular_parse.parse_listing(body, row['refresh_provenance']['requested_url'])
        payload = json.loads(parsed['raw_listing_json'])
        reviews.append({'audit_id': row['audit_id'], 'source_listing_id': row['source_listing_id'],
            'unit_id': row['unit_id'], 'canonical_unit_url': row['canonical_unit_url'],
            'source_row_sha256': cohort.hashed(row), 'source_evidence_sha256': cohort.hashed(e),
            'body_sha256': sha, 'raw_listing_sha256': source['raw_listing_sha256'],
            'collected_at': row['collected_at'], 'known_at': row['known_at'], **inspect(row, payload)})
    summary = {'current_rows': len(rows),
        'flags': dict(Counter(f for r in reviews for f in r['flags'])),
        'wording_families': dict(Counter(f for r in reviews for f in {x['family'] for x in r['wording_findings']})),
        'net_effective_findings': sum(x['family'] == 'net_effective_wording' for r in reviews for x in r['wording_findings']),
        'approval_standards_findings': sum(x['approval_standards_scope'] for r in reviews for x in r['wording_findings']),
        'description_rent_matches_earlier_ask': sum(q['matches_earlier_price_before_verified_current_change'] for r in reviews for q in r['description_rent_quotes']),
        'policy': 'Review evidence only. Own-advertisement pricing history is not independent corroboration. No inferred gross rent, source corrections, cohort exclusions, model fit or model promotion.'}
    return publish_bundle(output, {'review.jsonl': ''.join(canonical(r)+'\n' for r in reviews),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': VERSION, 'dataset_manifest_sha256': digest(Path(dataset)/'complete.json'),
         'dataset_observations_sha256': dm['files']['observations.jsonl'], 'summary': summary,
         'implementation_sha256': {Path(m.__file__).name: digest(m.__file__) for m in (cohort, granular_parse)}})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--collection', dest='collections', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    print(canonical(run(**vars(p.parse_args()))['summary']))

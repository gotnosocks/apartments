"""Bind Beatrice alias findings to own archived StreetEasy property histories."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

PAIRS = {'#PHA': {'1177683', '2894491'}, '#PHB': {'1177674', '1893537'}}


def run(inputs, historical, evidence, historical_evidence, archive, output, as_of):
    inputs, historical, evidence, historical_evidence, archive = map(Path, (inputs, historical, evidence, historical_evidence, archive))
    im, source = _verified_bundle(inputs, retain={'cases.jsonl'})
    hm, history = _verified_bundle(historical, retain={'source-files.json'})
    em, _ = _verified_bundle(evidence, retain=set())
    parent, _ = _verified_bundle(historical_evidence, retain=set())
    if (im['evidence_manifest_sha256'] != digest(evidence/'complete.json')
            or em['historical_evidence_manifest_sha256'] != digest(historical_evidence/'complete.json')
            or parent['historical_manifest'] != hm):
        raise ValueError('Alias review historical and description bindings differ')
    ids = set.union(*PAIRS.values())
    cases = [json.loads(line) for line in source['cases.jsonl'].decode().splitlines()]
    selected = [c for c in cases if c['observation']['source_listing_id'] in ids]
    if {c['observation']['source_listing_id'] for c in selected} != ids:
        raise ValueError('Alias-review listing membership differs')
    expected = {d['capture_id']: (c['observation'], d) for c in selected for d in c['descriptions']}
    if len(expected) != sum(len(c['descriptions']) for c in selected):
        raise ValueError('Duplicate selected source capture')
    inventory = json.loads(history['source-files.json'])
    paths = [archive/p for p in inventory if p.startswith('listing_observations/') and p.endswith('.parquet')]
    if any(not p.resolve().is_relative_to(archive.resolve()) for p in paths):
        raise ValueError('Archive path escapes bound root')
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        values = db.execute('SELECT snapshot_id,raw_listing_json,filename FROM read_parquet(?,filename=true) '
            'WHERE snapshot_id IN (SELECT unnest(?))', [[str(p) for p in paths], sorted(expected)]).fetchall()
    if len(values) != len(expected) or {v[0] for v in values} != set(expected):
        raise ValueError('Missing or duplicate archived alias capture')
    verified, records = {}, []
    for capture, raw, filename in sorted(values):
        row, item = expected[capture]
        path = Path(filename); relative = str(path.relative_to(archive))
        if relative not in verified:
            if digest(path) != inventory[relative]:
                raise ValueError('Alias source shard differs from historical export')
            verified[relative] = inventory[relative]
        if hashlib.sha256(raw.encode()).hexdigest() != item['raw_listing_sha256']:
            raise ValueError('Own captured raw listing hash differs')
        payload = json.loads(raw)
        address = payload['propertyDetails']['address']
        if str(payload['id']) != row['source_listing_id'] or str(payload['buildingId']) != '13264':
            raise ValueError('Alias listing or building identity differs')
        records.append({k: item[k] for k in ('capture_id', 'source_listing_id', 'body_sha256', 'raw_listing_sha256', 'source_collected_at')} |
            {'audit_id': row['audit_id'], 'unit_id': row['unit_id'], 'canonical_unit_url': row['canonical_unit_url'],
             'building_id': str(payload['buildingId']), 'address': address,
             'latest_listing_id': str(payload['latestListing']['id']),
             'property_history_listing_ids': [str(v['listingId']) for v in payload['propertyHistory']],
             'shard': relative})
    decisions = []
    for label, listing_ids in sorted(PAIRS.items()):
        captures = [r for r in records if r['source_listing_id'] in listing_ids]
        first = captures[0]
        if (any(r['address'] != first['address'] or r['address']['displayUnit'] != label for r in captures)
                or any(r['latest_listing_id'] != first['latest_listing_id'] for r in captures)
                or any(set(r['property_history_listing_ids']) != set(first['property_history_listing_ids']) for r in captures)
                or not listing_ids <= set(first['property_history_listing_ids'])):
            raise ValueError('Source property histories do not corroborate the proposed alias pair')
        urls = sorted({r['canonical_unit_url'] for r in captures})
        units = sorted({r['unit_id'] for r in captures})
        if len(urls) != 2 or len(units) != 2:
            raise ValueError('Expected two currently separate source URLs and analytical unit IDs')
        decisions.append({'display_unit': label, 'building_id': first['building_id'],
            'source_listing_ids': sorted(listing_ids), 'canonical_unit_urls': urls, 'analytical_unit_ids': units,
            'capture_ids': [r['capture_id'] for r in captures], 'latest_listing_id': first['latest_listing_id'],
            'shared_property_history_listing_ids': sorted(set(first['property_history_listing_ids'])),
            'status': 'source_supported_unit_alias_group_pending_projection',
            'decision': 'Record this pair as a source-supported identity linkage for the next reviewed identity projection. The same address and label are corroborated by mutual property-history membership and an identical latest-listing pointer across all selected own captures. Preserve each advertisement\'s attributes and dates; linkage does not resolve source bathroom conflicts or prove a renovation date.',
            'applied_to_frozen_floor_experiments': False, 'reviewed_at': as_of})
    return publish_bundle(output, {
        'source-captures.jsonl': ''.join(canonical(r)+'\n' for r in records),
        'decisions.jsonl': ''.join(canonical(r)+'\n' for r in decisions),
        'source-files.json': canonical(verified)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'source-supported-beatrice-unit-alias-review-v1', 'reviewed_at': as_of,
        'inputs_manifest_sha256': digest(inputs/'complete.json'),
        'historical_manifest_sha256': digest(historical/'complete.json'),
        'evidence_manifest_sha256': digest(evidence/'complete.json'),
        'historical_evidence_manifest_sha256': digest(historical_evidence/'complete.json'),
        'reviewed_captures': len(records), 'alias_groups': len(decisions),
        'source_paths': ['/buildingId', '/propertyDetails/address', '/latestListing/id', '/propertyHistory/*/listingId'],
        'source_assertion_not_independent_physical_verification': True,
        'analytical_identity_or_attribute_changes_applied': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'historical', 'evidence', 'historical-evidence', 'archive', 'output', 'as-of'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

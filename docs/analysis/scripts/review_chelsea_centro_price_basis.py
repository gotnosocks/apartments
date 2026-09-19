"""Record the own-history net/gross conflict found during floor-fit review."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(inputs, historical, archive, dataset, evidence, output, as_of):
    inputs, historical, archive, dataset, evidence = map(Path, (inputs, historical, archive, dataset, evidence))
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    if (manifest['source_manifest_sha256'] != digest(dataset/'complete.json')
            or manifest['evidence_manifest_sha256'] != digest(evidence/'complete.json')):
        raise ValueError('Price review dataset or description archive differs')
    cases = [json.loads(line) for line in files['cases.jsonl'].decode().splitlines()]
    selected = [c for c in cases if c['observation']['source_listing_id'] == '3091654']
    if len(selected) != 1:
        raise ValueError('Expected one exact Chelsea Centro source observation')
    case = selected[0]; row = case['observation']
    # Descriptions may be resolved React references. Revalidate their literal
    # hashes, capture identities and source/recovery/knowledge clocks.
    if load_evidence(dataset, evidence)[row['audit_id']] != case['descriptions']:
        raise ValueError('Price quote differs from verified own-capture evidence')
    expected = {c['capture_id']: c for c in case['descriptions']}
    _, source = _verified_bundle(historical, retain={'source-files.json'})
    inventory = json.loads(source['source-files.json'])
    paths = [archive/p for p in inventory if p.startswith('listing_observations/') and p.endswith('.parquet')]
    if any(not p.resolve().is_relative_to(archive.resolve()) for p in paths):
        raise ValueError('Historical source path escapes archive')
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        found = db.execute('SELECT snapshot_id,raw_listing_json,filename FROM read_parquet(?,filename=true) '
            'WHERE snapshot_id IN (SELECT unnest(?))', [[str(p) for p in paths], sorted(expected)]).fetchall()
    if len(found) != len(expected) or {r[0] for r in found} != set(expected):
        raise ValueError('Own source capture inventory differs')
    quote = 'bringing the net rent down to $4040 (actually gross rent is $4446)'
    records, shards = [], {}
    for capture, raw, filename in sorted(found):
        e = expected[capture]; path = Path(filename); relative = str(path.relative_to(archive))
        if digest(path) != inventory[relative] or hashlib.sha256(raw.encode()).hexdigest() != e['raw_listing_sha256']:
            raise ValueError('Own price source or shard differs')
        payload = json.loads(raw); pricing = payload['pricing']
        own = [h for h in payload['propertyHistory'] if str(h['listingId']) == '3091654']
        start = (e['description'] or '').find(quote)
        raw_description = payload.get('description')
        description_bound = (e['description_source'] == 'parsed_source' and raw_description == e['description']) or (
            e['description_source'] == 'verified_recovery' and isinstance(raw_description, str)
            and raw_description.startswith('$') and e['description_interpreted_at'] is not None)
        if (str(payload['id']) != '3091654' or len(own) != 1 or start < 0 or row['asking_rent'] != 4040
                or not description_bound):
            raise ValueError('Manual price review identity, quote or target differs')
        events = own[0]['rentalEventsOfInterest']
        active = sorted(h['date'] for h in events if h['status'] == 'ACTIVE')
        if (pricing['price'] != 4040 or pricing['netEffectiveRent'] is not None
                or any(v['price'] != 4040 for v in pricing['priceChanges'])
                or any(v['price'] != 4040 for v in events)
                or not active or active[0] != '2020-06-24'):
            raise ValueError('Own dated source does not establish the reviewed price-basis finding')
        records.append({k: e[k] for k in ('capture_id', 'body_sha256', 'raw_listing_sha256', 'description_sha256',
                                        'source_collected_at', 'description_source', 'description_interpreted_at')} |
            {'source_listing_id': '3091654', 'pricing_price': pricing['price'],
             'raw_description_reference': raw_description if e['description_source'] == 'verified_recovery' else None,
             'structured_net_effective_rent': pricing['netEffectiveRent'],
             'own_price_changes': pricing['priceChanges'], 'own_rental_events': events,
             'description_quote': {'source_path': '/description', 'offset_basis': 'verified_literal_description',
                                   'start': start, 'end': start+len(quote), 'literal': quote},
             'shard': relative})
        shards[relative] = inventory[relative]
    decision = {k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'canonical_unit_url', 'asking_rent', 'period')} | {
        'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
        'status': 'source_supported_net_headline_price_in_gross_ask_cohort',
        'reviewed_net_quote': 4040, 'reviewed_gross_quote': 4446,
        'first_own_active_event': '2020-06-24', 'reviewed_at': as_of,
        'recommendation': 'Quarantine this observation from the gross-ask analytical cohort in the next reviewed projection until an explicit dated gross-price and lease-assignment policy is applied. Preserve the raw advertised $4,040 and the separately quoted gross $4,446; never replace either with the model estimate. The source supports a net/gross distinction but is not an independent lease contract or proof of the gross quote on every historical date.',
        'numeric_replacement_or_quarantine_applied_to_frozen_fits': False}
    return publish_bundle(output, {
        'source-captures.jsonl': ''.join(canonical(r)+'\n' for r in records),
        'decision.json': canonical(decision)+'\n', 'source-files.json': canonical(shards)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'chelsea-centro-own-price-basis-review-v1', 'reviewed_at': as_of,
        'inputs_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'evidence_manifest_sha256': digest(evidence/'complete.json'),
        'historical_manifest_sha256': digest(historical/'complete.json'),
        'own_captures': len(records), 'price_or_cohort_changed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'historical', 'archive', 'dataset', 'evidence', 'output', 'as-of'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

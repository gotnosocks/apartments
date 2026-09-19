"""Bind the selected residual-review cases to original structured listing records."""
import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(candidates, historical, archive, output):
    candidates, historical, archive = map(Path, (candidates, historical, archive))
    _, cf = _verified_bundle(candidates, retain={'cases.jsonl'})
    _, hf = _verified_bundle(historical, retain={'source-files.json'})
    inventory = json.loads(hf['source-files.json'])
    cases = [json.loads(line) for line in cf['cases.jsonl'].decode().split('\n') if line]
    targets = {}
    for case in cases:
        for capture in case['captures']:
            if capture['capture_id'] in targets: raise ValueError('Duplicate review capture')
            targets[capture['capture_id']] = (case, capture)
    found = {}
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for relative, expected in sorted(inventory.items()):
            if not relative.startswith('listing_observations/') or not relative.endswith('.parquet'): continue
            path = archive/relative
            if not path.resolve().is_relative_to(archive.resolve()): raise ValueError('Invalid archive path')
            matches = db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?) WHERE snapshot_id IN (SELECT unnest(?))',
                                 [str(path), list(targets)]).fetchall()
            if not matches: continue
            if digest(path) != expected: raise ValueError('Source shard differs')
            for identity, raw in matches:
                if identity in found: raise ValueError('Duplicate archived review capture')
                case, capture = targets[identity]
                if hashlib.sha256(raw.encode()).hexdigest() != capture['raw_listing_sha256']:
                    raise ValueError('Raw capture hash differs')
                payload = json.loads(raw)
                if str(payload['id']) != case['source_record']['source_listing_id']:
                    raise ValueError('Raw advertisement identity differs')
                found[identity] = {'capture_id': identity, 'audit_id': case['source_record']['audit_id'],
                    'source_listing_id': str(payload['id']), 'raw_listing_sha256': capture['raw_listing_sha256'],
                    'source_shard': relative, 'source_shard_sha256': expected,
                    'property_details': payload.get('propertyDetails'), 'pricing': payload.get('pricing'),
                    'status': payload.get('status'), 'raw_description': payload.get('description')}
    if found.keys() != targets.keys(): raise ValueError('Missing original review capture')
    publish_bundle(output, {'captures.jsonl': ''.join(canonical(found[k])+'\n' for k in sorted(found)),
                           Path(__file__).name: Path(__file__).read_text()},
        {'version': 'laundry-residual-raw-source-review-v1', 'captures': len(found),
         'candidates_manifest_sha256': digest(candidates/'complete.json'),
         'historical_manifest_sha256': digest(historical/'complete.json')})
    print(canonical({'captures': len(found), 'output': str(output)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidates', 'historical', 'archive', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

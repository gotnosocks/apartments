"""Publish full-description adjudication of the 41 v8 floor-replay ads."""
import argparse
from collections import Counter
import hashlib
import gzip
import json
from pathlib import Path

import duckdb
from apartments.attribute_evidence import extract_attribute_evidence
from apartments.corrections import canonical
from apartments.granular_parse import parse_listing
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

REVIEWED_ADS = set('4127780 3959921 4352443 4996184 4573518 4165480 4750816 4943851 3809608 1483179 1432608 1334323 5048524 3203696 887089 3967693 4958250 4398107 2061666 3703592 4439603 998539 3332499 1773953 718952 3177548 776029 5093222 4747838 4034850 2971958 1246817 4404643 633450 4387279 5155202 5163034 2934738 4249220 3460328 1221531'.split())


def run(replay, archive, output):
    replay, archive, output = map(Path, (replay, archive, output))
    if digest(replay/'complete.json') != '2fb3123e121f3d14bff8de736517c3635ad6dc41f1e72588155a353e11bb8b73':
        raise ValueError('Manual review binds a different replay')
    manifest, files = _verified_bundle(replay, retain={'changes.jsonl'})
    if manifest['version'] != 'direct-floor-offer-replay-v1':
        raise ValueError('Expected direct-floor replay')
    records = [json.loads(l) for l in files['changes.jsonl'].decode().split('\n') if l]
    if len(records) != 60 or {r['capture']['source_listing_id'] for r in records} != REVIEWED_ADS:
        raise ValueError('Reviewed membership differs')
    findings, witnesses = {}, []
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for r in records:
            cap, row = r['capture'], r['source_row']
            text = cap['description']
            if hashlib.sha256(text.encode()).hexdigest() != cap['description_sha256']:
                raise ValueError('Description differs')
            if isinstance(cap['capture_id'], int):
                found = db.execute('SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                    [str(archive/'listing_observations/*.parquet'), cap['capture_id']]).fetchall()
            elif str(cap['capture_id']).startswith('refresh:'):
                body_hash = cap['body_sha256']
                path = Path('data/probes/chelsea-discovery-details-20260918/archive/bodies')/body_hash[:2]/(body_hash+'.gz')
                body = gzip.decompress(path.read_bytes())
                if hashlib.sha256(body).hexdigest() != body_hash:
                    raise ValueError('Refresh body differs')
                parsed, _ = parse_listing(body, 'https://streeteasy.com/rental/'+cap['source_listing_id'])
                found = [(parsed['raw_listing_json'],)]
            else:
                raise ValueError('Unsupported capture identity')
            if len(found) != 1 or hashlib.sha256(found[0][0].encode()).hexdigest() != cap['raw_listing_sha256']:
                raise ValueError('Raw capture differs')
            payload = json.loads(found[0][0])
            if str(payload['id']) != cap['source_listing_id']:
                raise ValueError('Own-ad identity differs')
            replayed = extract_attribute_evidence({**payload, 'description': text})
            floor = r['after']['attributes']['advertised_floor']
            disposition = ('corroborates_existing' if row['listed_floor'] == floor else
                           'label_description_conflict' if row['listed_floor'] is not None else
                           'previously_unknown_review_required')
            if replayed['attributes']['advertised_floor'] != floor:
                disposition = 'structured_description_conflict'
            findings[row['audit_id']] = {'source_row': row, 'advertised_description_floor': floor,
                'disposition': disposition, 'manual_scope_review': 'Full text identifies the offered dwelling; no reference/shared-space floor substitution found.',
                'existing_projection_status': row.get('expanded_floor_provenance', {}).get('status'),
                'source_or_model_changed': False}
            witnesses.append({**r, 'raw_listing_json': found[0][0],
                'complete_payload_floor': replayed['attributes']['advertised_floor'],
                'complete_payload_floor_conflicts': replayed['conflicts'].get('advertised_floor'),
                'manual_scope_review_passed': True})
    summary = {'reviewed_ads': len(REVIEWED_ADS), 'reviewed_captures': len(witnesses),
        'observations': len(findings), 'by_disposition': dict(Counter(f['disposition'] for f in findings.values())),
        'source_or_model_changed': False,
        'limitations': ['Manual claim-scope review is not verification of historical physical floors.',
            'Keep existing source masks and numbering disagreements; no coverage increase is applied.',
            'Repeated ads and captures are not independent evidence.']}
    publish_bundle(output, {'findings.jsonl': ''.join(canonical(v)+'\n' for _, v in sorted(findings.items())),
        'witnesses.jsonl': ''.join(canonical(w)+'\n' for w in witnesses),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': 'direct-floor-offer-full-review-v1', 'replay_manifest_sha256': digest(replay/'complete.json')})
    _verified_bundle(output)
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('replay', 'archive', 'output'):
        p.add_argument('--'+name, required=True)
    run(**vars(p.parse_args()))

"""Review unresolved detail-page unit identities using archived source associations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from apartments import granular_parse, unit_canonical
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'discovery-detail-identity-review-v1'


def identity_evidence(target, listing, memberships):
    if str(listing.get('id')) != target['source_listing_id']:
        raise ValueError('Wrong advertisement in identity evidence')
    byad = defaultdict(list)
    byunit = {}
    for member in memberships:
        byad[str(member['listing_id'])].append(member)
        if member['status'] == 'associated':
            url = member['canonical_unit_url']
            if (member['rule'] != 'canonical-url-v1'
                    or unit_canonical.canonical_unit_id(url) != member['unit_id']):
                raise ValueError('Historical unit association differs from canonical rule')
            byunit[member['unit_id']] = url
    histories = listing.get('propertyHistory') or []
    if not isinstance(histories, list):
        raise ValueError('Unresolved property history structure')
    # Source listing IDs can occur in sale histories too; only own rental-history
    # references are eligible for a rental-membership lookup.
    ids = sorted({str(h['listingId']) for h in histories
                  if isinstance(h, dict) and h.get('rentalEventsOfInterest') and h.get('listingId') is not None})
    matches = [dict(m) for identifier in ids for m in byad.get(identifier, []) if m['status'] == 'associated']
    candidates = sorted({m['unit_id'] for m in matches})
    expected_building = target.get('expected_building_path')
    building_conflicts = [m for m in matches if expected_building is not None
                          and '/'.join(urlsplit(m['canonical_unit_url']).path.split('/')[:3]) != expected_building]
    label = ((listing.get('propertyDetails') or {}).get('address') or {}).get('displayUnit')
    normalized = label.strip().removeprefix('#').strip().lower() if isinstance(label, str) else None
    label_candidates = []
    if expected_building and normalized and re.fullmatch(r'[a-z0-9_-]+', normalized):
        for unit, url in sorted(byunit.items()):
            if urlsplit(url).path == expected_building + '/' + normalized:
                label_candidates.append({'unit_id': unit, 'canonical_unit_url': url})
    status = ('history_building_conflict' if building_conflicts else 'multiple_history_units' if len(candidates) > 1
              else 'unique_history_unit_candidate' if len(candidates) == 1 else 'no_associated_history_unit')
    return {'status': status, 'display_unit': label, 'rental_history_listing_ids': ids,
        'associated_history_memberships': matches, 'history_unit_candidates': candidates,
        'building_conflicts': building_conflicts,
        'unresolved_history_listing_ids': [i for i in ids if any(m['status'] != 'associated' for m in byad.get(i, []))],
        'unseen_history_listing_ids': [i for i in ids if i not in byad],
        'label_only_candidates': label_candidates,
        'history_and_label_agree': bool(len(candidates) == 1 and not building_conflicts and
            any(c['unit_id'] == candidates[0] for c in label_candidates)),
        'policy': 'Review candidates only. Source history and label-only matches remain separate; attributes are not used to require or reject identity agreement.'}


def run(collection, historical, archive, output):
    import duckdb

    collection, historical, archive = map(Path, (collection, historical, archive))
    pm, pf = _verified_bundle(collection / 'plan', retain={'refresh-plan.json'})
    plan = json.loads(pf['refresh-plan.json'])
    sm, _ = _verified_bundle(collection / 'snapshot', retain=set())
    ph = hashlib.sha256(canonical(plan).encode()).hexdigest()
    if (plan.get('version') != 'bounded-discovery-detail-refresh-v1'
            or ph != pm.get('plan_sha256') or sm.get('plan_sha256') != ph
            or sm.get('report', {}).get('targets') != len(plan['targets'])):
        raise ValueError('Collection snapshot and plan differ')
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    inventory = json.loads(hf['source-files.json'])
    paths = [archive / p for p in inventory if p.startswith('rental_unit_memberships/') and p.endswith('.parquet')]
    if not paths:
        raise ValueError('Missing historical identity inventory')
    for path in paths:
        if not path.resolve().is_relative_to(archive.resolve()) or digest(path) != inventory[str(path.relative_to(archive))]:
            raise ValueError('Historical identity shard changed')
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        cursor = db.read_parquet([str(p) for p in paths]).execute()
        keys = [d[0] for d in cursor.description]
        members = [dict(zip(keys, row)) for row in cursor.fetchall()]
    reviews = []
    for index, target in enumerate(plan['targets']):
        if target['canonical_unit_url'] is not None:
            continue
        manifest, files = _verified_bundle(collection / 'results' / f'{index:04d}', retain={'result.json'})
        if (manifest.get('plan_sha256') != pm['plan_sha256'] or manifest.get('index') != index
                or manifest.get('target_sha256') != hashlib.sha256(canonical(target).encode()).hexdigest()):
            raise ValueError('Detail checkpoint differs from target')
        result = json.loads(files['result.json']); sha = result.get('body_sha256')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Missing verifiable detail response')
        body = gzip.decompress((collection / 'archive/bodies' / sha[:2] / (sha + '.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError('Detail body changed')
        parsed, _ = granular_parse.parse_listing(body, target['url'])
        literal = parsed['raw_listing_json']; listing = json.loads(literal)
        reviews.append({'source_listing_id': target['source_listing_id'], 'index': index,
            'collected_at': result['collected_at'], 'body_sha256': sha,
            'raw_listing_sha256': hashlib.sha256(literal.encode()).hexdigest(),
            'canonical_href': parsed.get('canonical_href'), 'parse_status': parsed.get('parse_status'),
            'collection_outcome': result['status'], 'collection_reason': result.get('reason'),
            'reported_status': listing.get('status'), 'reported_pricing': listing.get('pricing'),
            'reported_address': (listing.get('propertyDetails') or {}).get('address'),
            **identity_evidence(target, listing, members)})
    summary = {'version': VERSION, 'reviewed_targets': len(reviews),
        'outcomes': dict(Counter(r['status'] for r in reviews)),
        'history_and_label_agreement': sum(r['history_and_label_agree'] for r in reviews),
        'plan_manifest_sha256': digest(collection / 'plan/complete.json'),
        'snapshot_manifest_sha256': digest(collection / 'snapshot/complete.json'),
        'historical_manifest_sha256': digest(historical / 'complete.json'),
        'policy': 'No identity merges, corrected canonical links, new requests or analytical inclusion. Any accepted association needs a versioned identity policy and preserved source basis.'}
    return publish_bundle(output, {'summary.json': canonical(summary) + '\n',
        'reviews.jsonl': ''.join(canonical(r) + '\n' for r in reviews),
        'historical-identity-files.json': canonical({str(p.relative_to(archive)): digest(p) for p in paths}) + '\n',
        Path(__file__).name: Path(__file__).read_text(), 'granular_parse.py': Path(granular_parse.__file__).read_text(),
        'unit_canonical.py': Path(unit_canonical.__file__).read_text()}, {'version': VERSION, 'summary': summary})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('collection', 'historical', 'archive', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    print(canonical(run(**vars(p.parse_args()))['summary']))

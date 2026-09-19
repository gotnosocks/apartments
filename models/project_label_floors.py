"""Complete capture-specific unit-label floor extraction and publish an immutable projection."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from apartments import floor_label_projection as contract, granular_parse
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import sha


def records(data):
    return [json.loads(line) for line in data.decode().split('\n') if line.strip()]


def read_building_evidence(archive):
    """Bind fresh extraction to exact archived building and snapshot shards."""
    import duckdb
    from datetime import datetime, timezone
    paths = sorted(archive.glob('building_observations/*.parquet')) + sorted(archive.glob('snapshots/*.parquet'))
    inventory = {str(p.relative_to(archive)): digest(p) for p in paths}
    if not paths: raise ValueError('Building archive missing')
    snapshots, result = {}, {}
    with duckdb.connect(config={'threads':'1', 'memory_limit':'400MB'}) as db:
        for path in paths:
            if path.parent.name != 'snapshots': continue
            for ident, url, body, observed in db.execute('SELECT snapshot_id,url,body_hash,observed_at FROM read_parquet(?)', [str(path)]).fetchall():
                if ident in snapshots: raise ValueError('Duplicate archived snapshot')
                snapshots[ident] = {'snapshot_id': ident, 'source_url':url, 'body_sha256':body,
                    'source_collected_at':datetime.fromtimestamp(observed, timezone.utc).isoformat(),
                    'snapshot_shard':str(path.relative_to(archive))}
        for path in paths:
            if path.parent.name != 'building_observations': continue
            for ident, slug, raw in db.execute("SELECT snapshot_id,building_slug,raw_building_json FROM read_parquet(?) WHERE parse_status = 'ok'", [str(path)]).fetchall():
                payload = json.loads(raw)
                value = payload.get('floorCount')
                if type(value) not in (int,float) or not 0 < value < 200: continue
                if payload.get('slug') != slug or ident not in snapshots: raise ValueError('Building source identity differs')
                result.setdefault(slug, []).append({**snapshots[ident], 'floor_count':value,
                    'source_path':'/floorCount', 'raw_building_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                    'building_shard':str(path.relative_to(archive))})
    for values in result.values(): values.sort(key=lambda x:x['snapshot_id'])
    return result, inventory


def run(dataset, evidence, audit, review, refresh, output, archive, as_of):
    from datetime import datetime, timezone
    from apartments.corrections import instant
    if instant(as_of) > datetime.now(timezone.utc): raise ValueError('Interpretation clock is in the future')
    dataset, evidence, audit, review = map(Path, (dataset, evidence, audit, review))
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl', 'current-source-evidence.jsonl',
        'elevator-corrections.jsonl', 'quarantined.jsonl'})
    if dm['version'] != contract.PARENT: raise ValueError('Unexpected floor projection source')
    am, af = _verified_bundle(audit, retain={'captures.jsonl'})
    rm, rf = _verified_bundle(review, retain={'decisions.jsonl'})
    if am['version'] != 'unit-label-floor-research-v1' or rm['version'] != 'unit-label-floor-conflict-review-v1':
        raise ValueError('Unexpected label audit or review version')
    cached = {}
    for c in records(af['captures.jsonl']):
        key = (c['raw_listing_sha256'], str(c['source_listing_id']))
        if key in cached and cached[key]['literal'] != c['literal']: raise ValueError('Conflicting archived raw label')
        if c['candidate_floor'] != contract.candidate(c['literal']): raise ValueError('Archived label extraction differs')
        cached[key] = c
    reviews = records(rf['decisions.jsonl'])
    excluded = sorted({r['building'] for r in reviews})
    rows = records(df['observations.jsonl'])
    mapping = load_evidence(dataset, evidence)
    building_evidence, building_inventory = read_building_evidence(Path(archive))
    revised, changes = [], []
    counts = Counter()
    for index, row in enumerate(rows):
        captures = []
        for e in mapping[row['audit_id']]:
            old = cached.get((e['raw_listing_sha256'], str(e['source_listing_id'])))
            if old is not None:
                label = old['literal']; counts['reused_verified_raw_listing_labels'] += 1
            else:
                provenance = row.get('refresh_provenance')
                if not provenance: raise ValueError('Missing historical label in verified archive')
                body_sha = e['body_sha256']
                if provenance['body_sha256'] != body_sha: raise ValueError('Current capture body binding differs')
                paths = [Path(root)/'archive/bodies'/body_sha[:2]/(body_sha+'.gz') for root in refresh]
                path = next((p for p in paths if p.exists()), None)
                if path is None: raise ValueError('Frozen refresh body unavailable')
                body = gzip.decompress(path.read_bytes())
                if hashlib.sha256(body).hexdigest() != body_sha: raise ValueError('Refresh body hash differs')
                parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
                raw = parsed['raw_listing_json']
                if hashlib.sha256(raw.encode()).hexdigest() != e['raw_listing_sha256']:
                    raise ValueError('Refreshed raw listing hash differs')
                payload = json.loads(raw)
                if str(payload['id']) != str(row['source_listing_id']): raise ValueError('Refreshed ad identity differs')
                label = (payload.get('propertyDetails', {}).get('address') or {}).get('displayUnit')
                counts['newly_extracted_frozen_capture_labels'] += 1
            captures.append({**{k: e[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'capture_id',
                'raw_listing_sha256', 'body_sha256', 'source_collected_at', 'known_at')},
                'literal': label, 'candidate_floor': contract.candidate(label),
                'source_path': '/propertyDetails/address/displayUnit'})
        result = contract.project_row(row, captures, excluded, building_evidence.get(row['building'], []), as_of)
        revised.append(result)
        changes.append({'source_index': index, 'source_row_sha256': sha(row),
            'listed_floor_was_present': 'listed_floor' in row, 'before_listed_floor': row.get('listed_floor'),
            'captures': captures})
        counts[result['floor_label_provenance']['status']] += 1
    summary = {'rows': len(rows), **counts, 'excluded_buildings': len(excluded),
        'model_floor_distribution': dict(sorted(Counter(str(r.get('listed_floor') if r.get('listed_floor') is not None
            else r.get('advertised_floor')) for r in revised).items())),
        'policy': 'Own-capture positive 1–2 digit plus single letter labels, unanimous across captures. Preserve explicit claims; exclude every manually reviewed conflict building; withhold candidates above any captured building floor count and all two-digit candidates without a building count. Count compatibility is not an advertised-to-physical-floor mapping. No physical height, numeric-only label, penthouse or numbering offset inferred.'}
    files = {name: data.decode() for name, data in df.items() if name != 'observations.jsonl'}
    files.update({'observations.jsonl': ''.join(canonical(r)+'\n' for r in revised),
        contract.SIDECAR: ''.join(canonical(r)+'\n' for r in changes), 'summary.json': canonical(summary)+'\n',
        'building-source-files.json': canonical(building_inventory)+'\n',
        'project_label_floors.py': Path(__file__).read_text(),
        'floor_label_projection_contract.py': Path(contract.__file__).read_text()})
    for rel, expected in building_inventory.items():
        if digest(Path(archive)/rel) != expected: raise ValueError('Building source changed during extraction')
    manifest = publish_bundle(output, files, {'version': contract.VERSION, 'source_manifest': dm,
        'source_manifest_sha256': digest(dataset/'complete.json'), 'source_rows': len(rows),
        'interpreted_at': as_of, 'building_floor_evidence': building_evidence,
        'label_audit_manifest_sha256': digest(audit/'complete.json'), 'review_manifest_sha256': digest(review/'complete.json'),
        'evidence_manifest_sha256': digest(evidence/'complete.json'), 'excluded_buildings': excluded, 'summary': summary})
    contract.parent_rows(manifest, revised, changes)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'audit', 'review', 'output', 'archive'): p.add_argument('--'+name, required=True, type=Path)
    p.add_argument('--as-of', required=True)
    p.add_argument('--refresh', required=True, type=Path, action='append')
    print(canonical(run(**vars(p.parse_args()))['summary']))

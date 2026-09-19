"""Verify archived building locations for a complete retrospective rental cohort.

Research candidates only. Raw pages are read locally; no geocoding or scraping.
"""
import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import duckdb
import numpy as np

from apartments.corrections import canonical, instant
from apartments.research_pipeline import digest, publish_bundle
from streeteasy_archive import extract, flight
from . import current_spatial_features as spatial

VERSION = 'cohort-building-spatial-candidates-v1'


def verified_manifest(root):
    """Verify files by streaming hashes, avoiding multi-GB audit allocations."""
    root = Path(root)
    if (root/'complete.json').is_symlink(): raise ValueError('Symlink completion marker')
    manifest = json.loads((root/'complete.json').read_text())
    if not manifest.get('files'): raise ValueError('Incomplete artifact')
    for name, expected in manifest['files'].items():
        p = root/name
        if Path(name).name != name or p.is_symlink() or not p.is_file() or digest(p) != expected:
            raise ValueError('Artifact file differs: '+name)
    return manifest


def records(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip(): yield json.loads(line)


def check_listing(row, record):
    sid, listing, url, slug, raw_building, raw_listing = record
    if (type(sid) is not int or sid not in row['capture_ids']
            or listing != row['source_listing_id'] or raw_listing != listing
            or url != row['canonical_unit_url'] or slug != row['building']
            or urlsplit(url).path.split('/')[2] != slug or not raw_building):
        raise ValueError('Historical listing/capture/building identity differs')
    return {'capture_id': sid, 'audit_id': row['audit_id'], 'building': slug,
            'source_listing_id': listing, 'source_building_id': raw_building,
            'canonical_unit_url': url}


def bound_archived_building(building_id, url, decoded):
    """Resolve only spatial/address fields; preserve Flight text as literal text."""
    references = []
    def resolve(value, path, stack=()):
        if isinstance(value, flight.FlightText): return str(value)
        if isinstance(value, str) and re.fullmatch(r'\$[0-9a-fA-F]+', value):
            key = value[1:]
            if key not in decoded or key in stack:
                raise ValueError('Missing or cyclic spatial field reference')
            references.append({'source_path': path, 'reference': value, 'target_path': '/'+key})
            return resolve(decoded[key], '/'+key, (*stack, key))
        if isinstance(value, dict): return {k: resolve(v, path+'/'+k, stack) for k, v in value.items()}
        if isinstance(value, list): return [resolve(v, path+'/'+str(i), stack) for i, v in enumerate(value)]
        return value
    matches = [(p, obj) for p, obj in spatial.building_objects(decoded) if str(obj.get('id')) == building_id]
    hydrated = []
    try:
        for path, obj in matches:
            hydrated.append({k: resolve(obj[k], path+'/'+k) for k in
                ('id', 'slug', 'geoCenter', 'latitude', 'longitude', 'address') if k in obj})
    except ValueError as error:
        return {'status': 'unresolved_building_spatial_reference', 'source_building_id': building_id,
                'reason': str(error), 'field_references': references}
    result = spatial.bound_building({'buildingId': building_id}, url+'/_', hydrated)
    result['field_references'] = references
    if result['status'] == 'source_bound': result['source_paths'] = [p+'/geoCenter' for p, _ in matches]
    return result


def resolve_building(building, captures, expected_ids):
    result = {'building': building, 'location_captures': len(captures),
              'expected_source_building_ids': sorted(expected_ids)}
    valid = [r for r in captures if r['status'] == 'source_bound']
    variants = {(r['source_building_id'], r['latitude'], r['longitude']) for r in valid}
    if (not captures or len(valid) != len(captures) or len(variants) != 1
            or len(expected_ids) != 1 or {r['source_building_id'] for r in valid} != expected_ids):
        return {**result, 'status': 'missing_or_conflicting_location',
                'capture_statuses': dict(Counter(r['status'] for r in captures))}
    identity, lat, lon = next(iter(variants))
    streets = {r['street_candidate'] for r in valid}
    street = next(iter(streets)) if len(streets) == 1 and None not in streets else None
    return {**result, 'status': 'source_bound', 'source_building_id': identity,
        'latitude': lat, 'longitude': lon, 'street_candidate': street,
        'street_status': 'consistent_literal_street' if street is not None else 'missing_or_conflicting_street',
        'street_variants': sorted(streets, key=lambda x: '' if x is None else x)}


def feature_summary(buildings, rows):
    valid = [b for b in buildings if b['status'] == 'source_bound']
    if not valid: raise ValueError('No consistent locations')
    center = {k: float(np.mean([b[k] for b in valid])) for k in ('latitude', 'longitude')}
    streets = sorted({b['street_candidate'] for b in valid if b['street_candidate'] is not None})
    bmatrix = []
    for b in valid:
        b['relative_latitude_degrees'] = b['latitude']-center['latitude']
        b['relative_longitude_degrees'] = b['longitude']-center['longitude']
        bmatrix.append([b['relative_latitude_degrees'], b['relative_longitude_degrees'],
                        *[float(b['street_candidate'] == street) for street in streets]])
    matrix = np.asarray(bmatrix)
    indices = {b['building']: i for i, b in enumerate(valid)}
    covered = [r for r in rows if r['building'] in indices]
    # X = Z B exactly, where Z is the row-to-building incidence matrix. Check
    # without allocating the mostly-zero observations-by-buildings matrix.
    row_matrix = matrix[[indices[r['building']] for r in covered]]
    maximum_within_building_difference = 0.
    row_indices = defaultdict(list)
    for j, r in enumerate(covered): row_indices[r['building']].append(j)
    for building, i in indices.items():
        selected = row_indices[building]
        maximum_within_building_difference = max(maximum_within_building_difference,
                                                  float(np.max(abs(row_matrix[selected]-matrix[i]))))
    support = []
    for street in streets:
        members = [b['building'] for b in valid if b['street_candidate'] == street]
        support.append({'street': street, 'buildings': len(members),
                        'rows': sum(len(row_indices[b]) for b in members)})
    return {'coordinate_center': center, 'center_basis': 'Equal weight per source-consistent cohort building; offsets in degrees.',
        'covered_rows': len(covered), 'covered_units': len({r['unit_id'] for r in covered}),
        'covered_buildings': len(valid), 'covered_current_rows': sum(r['analysis_price_basis'] == 'current_capture_gross_ask' for r in covered),
        'street_support': support, 'street_candidates': len(streets),
        'single_building_streets': [r['street'] for r in support if r['buildings'] == 1],
        'candidate_columns': ['relative_latitude_degrees', 'relative_longitude_degrees', *['street:'+s for s in streets]],
        'candidate_matrix_rank': int(np.linalg.matrix_rank(matrix)),
        'maximum_within_building_feature_difference': maximum_within_building_difference,
        'additional_rank_given_building_indicators': 0}


def run(dataset, historical, archive, bodies, current_spatial, interpreted_at, output):
    dataset, historical, archive, bodies, current_spatial = map(Path, (dataset, historical, archive, bodies, current_spatial))
    instant(interpreted_at)
    dm, hm, cm = [verified_manifest(p) for p in (dataset, historical, current_spatial)]
    if cm['version'] != spatial.VERSION: raise ValueError('Expected verified current spatial evidence')
    if hm.get('dataset_version') != 'historical-own-advertisement-v1':
        raise ValueError('Expected original own-advertisement history')
    input_hashes = {p: digest(p/'complete.json') for p in (dataset, historical, current_spatial)}
    implementations = [Path(__file__), *(Path(m.__file__) for m in (spatial, extract, flight))]
    code_hashes = {p: digest(p) for p in implementations}
    rows = list(records(dataset/'observations.jsonl'))
    by_id = {r['audit_id']: r for r in rows}
    if len(by_id) != len(rows): raise ValueError('Duplicate cohort identity')
    history = [r for r in rows if r['analysis_price_basis'] == 'historical_initial_own_advertisement_ask']
    current = [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if len(history)+len(current) != len(rows): raise ValueError('Unsupported target price basis')
    originals = {r['audit_id']: r for r in records(historical/'observations.jsonl')}
    for row in history:
        old = originals[row['audit_id']]
        fixed = ('source_listing_id', 'unit_id', 'canonical_unit_url', 'capture_ids', 'price_at')
        if any(row[k] != old[k] for k in fixed) or row['asking_rent'] != old['rent']:
            raise ValueError('Historical source identity or target changed')
    inventory = json.loads((historical/'source-files.json').read_text())
    consumed = {}
    def checked(relative, expected=None):
        p = archive/relative
        if Path(relative).is_absolute() or not p.resolve().is_relative_to(archive.resolve()):
            raise ValueError('Invalid archive path')
        checksum = digest(p)
        if expected is not None and checksum != expected: raise ValueError('Historical source shard changed: '+relative)
        consumed[relative] = checksum
        return p
    checked('complete.json', inventory['complete.json'])
    targets = {}
    for r in history:
        for sid in r['capture_ids']:
            if type(sid) is not int or sid in targets: raise ValueError('Duplicate or noninteger historical capture')
            targets[sid] = r
    expected_ids = defaultdict(set)
    bindings, captures, seen = [], [], set()
    with duckdb.connect(config={'threads': '1', 'memory_limit': '400MB'}) as db:
        for relative, expected in sorted(inventory.items()):
            if not relative.startswith('listing_observations/'): continue
            p = checked(relative, expected)
            found = db.execute("SELECT snapshot_id,listing_id,canonical_unit_url,building_slug, "
                "json_extract_string(raw_listing_json,'$.buildingId'),json_extract_string(raw_listing_json,'$.id') "
                "FROM read_parquet(?) WHERE snapshot_id IN (SELECT unnest(?))", [str(p), list(targets)]).fetchall()
            for record in found:
                if record[0] in seen: raise ValueError('Duplicate archived capture')
                seen.add(record[0]); binding = check_listing(targets[record[0]], record)
                expected_ids[binding['building']].add(binding['source_building_id'])
                bindings.append({**binding, 'listing_shard': relative, 'listing_shard_sha256': expected})
        if seen != targets.keys(): raise ValueError('Missing historical listing capture')
        current_ids = {r['audit_id'] for r in current}
        for c in records(current_spatial/'captures.jsonl'):
            r = by_id.get(c['audit_id'])
            if r is None or r['audit_id'] not in current_ids: raise ValueError('Current spatial membership differs')
            if (any(c[k] != r[k] for k in ('source_listing_id', 'unit_id', 'building', 'known_at', 'collected_at'))
                    or c['raw_listing_sha256'] != r['source_raw_sha256']
                    or c['body_sha256'] != r['refresh_provenance']['body_sha256']
                    or instant(c['known_at']) > instant(interpreted_at)):
                raise ValueError('Current spatial identity differs')
            current_ids.remove(c['audit_id'])
            expected_ids[r['building']].add(c['source_building_id'])
            captures.append({**c, 'evidence_scope': 'verified_current_listing',
                             'upstream_manifest_sha256': digest(current_spatial/'complete.json')})
        if current_ids: raise ValueError('Incomplete current spatial coverage')
        snap = checked('snapshots/metadata.parquet', inventory['snapshots/metadata.parquet'])
        snapshots = {r[0]: dict(zip(('snapshot_id','url','body_hash','kind','observed_at'), r)) for r in
            db.execute('SELECT snapshot_id,url,body_hash,kind,observed_at FROM read_parquet(?) WHERE kind=\'building\'', [str(snap)]).fetchall()}
        total = 0
        for p in sorted((archive/'building_observations').glob('*.parquet')):
            relative = str(p.relative_to(archive)); checked(relative)
            cursor = db.execute('SELECT * FROM read_parquet(?) WHERE building_slug IN (SELECT unnest(?))',
                                [str(p), sorted(expected_ids)])
            columns = [d[0] for d in cursor.description]
            for values in cursor.fetchall():
                b = dict(zip(columns, values)); s = snapshots[b['snapshot_id']]
                slug = b['building_slug']; collected = datetime.fromtimestamp(s['observed_at'], UTC).isoformat()
                if urlsplit(s['url']).path.rstrip('/') != '/building/'+slug or instant(collected) > instant(interpreted_at):
                    raise ValueError('Building snapshot URL or interpretation clock differs')
                raw = json.loads(b['raw_building_json'])
                if (str(raw['id']) != b['building_id'] or raw['slug'] != slug
                        or spatial.coordinates(raw) != spatial.coordinates(b)):
                    raise ValueError('Exported building fields differ from raw building object')
                sha = s['body_hash']; body = gzip.decompress((bodies/sha[:2]/(sha+'.gz')).read_bytes())
                if hashlib.sha256(body).hexdigest() != sha: raise ValueError('Archived building body hash differs')
                decoded = flight.decode_records(extract.flight_text(extract._scripts(extract._selector(body))))
                measured = bound_archived_building(b['building_id'], s['url'], decoded)
                if measured['status'] == 'source_bound' and spatial.coordinates(measured) != spatial.coordinates(b):
                    measured = {'status': 'decoded_and_exported_coordinates_conflict', 'source_building_id': b['building_id']}
                captures.append({**measured, 'building': slug, 'capture_id': b['snapshot_id'],
                    'source_collected_at': collected, 'interpreted_at': interpreted_at, 'body_sha256': sha,
                    'source_url': s['url'], 'building_shard': relative, 'building_shard_sha256': consumed[relative],
                    'raw_building_sha256': hashlib.sha256(b['raw_building_json'].encode()).hexdigest(),
                    'evidence_scope': 'archived_building_page'})
                total += 1
                if total % 50 == 0: print(canonical({'phase': 'verified_building_pages', 'captures': total}), flush=True)
    by_building = defaultdict(list)
    for c in captures: by_building[c['building']].append(c)
    buildings = [resolve_building(b, by_building[b], expected_ids[b]) for b in sorted(expected_ids)]
    summary = {'version': VERSION, 'rows': len(rows), 'buildings': len(buildings), 'historical_listing_captures': len(bindings),
        'building_page_captures': total, 'current_listing_captures': len(current),
        'capture_statuses': dict(Counter(c['status'] for c in captures)),
        'building_statuses': dict(Counter(b['status'] for b in buildings)), **feature_summary(buildings, rows),
        'policy': 'Retrospective building-location research candidates. Every historical listing building ID and canonical URL is checked; archived building pages are decoded and body-hash verified. No source fields or main model changed.',
        'limitations': ['Building coordinates are not unit exposures, entrances, physical height or verified historical building footprints.',
            'Spatial and street columns are constant within building and lie in its indicator span; separating location from building effects depends on priors and structural assumptions.',
            'Street labels preserve literal ordinal/directional variants; aliases are not silently combined.',
            'Relative coordinates are degrees, not meters; the center uses equal building weights.',
            'No spatial posterior fit or accuracy improvement is claimed.']}
    for relative, expected in consumed.items():
        if digest(archive/relative) != expected: raise ValueError('Archive changed during research run')
    if (any(digest(p/'complete.json') != value for p, value in input_hashes.items())
            or any(digest(p) != value for p, value in code_hashes.items())):
        raise ValueError('Inputs or implementation changed during research run')
    files = {'captures.jsonl': ''.join(canonical(c)+'\n' for c in captures),
        'buildings.jsonl': ''.join(canonical(b)+'\n' for b in buildings),
        'listing-bindings.jsonl': ''.join(canonical(b)+'\n' for b in bindings),
        'summary.json': canonical(summary)+'\n', 'source-files.json': canonical(consumed)+'\n',
        **{Path(m.__file__).name: Path(m.__file__).read_text() for m in (spatial, extract, flight)},
        Path(__file__).name: Path(__file__).read_text()}
    publish_bundle(output, files, {'version': VERSION, 'interpreted_at': interpreted_at,
        'dataset_manifest_sha256': digest(dataset/'complete.json'), 'historical_manifest_sha256': digest(historical/'complete.json'),
        'current_spatial_manifest_sha256': digest(current_spatial/'complete.json')})
    print(canonical(summary), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','historical','archive','bodies','current_spatial','output'):
        parser.add_argument('--'+name.replace('_','-'), type=Path, required=True)
    parser.add_argument('--interpreted-at', required=True)
    run(**vars(parser.parse_args()))

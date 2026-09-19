"""Source-bound building coordinates and street candidates for spatial research."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from apartments import granular_parse
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from streeteasy_archive import extract, flight
from . import refresh_analysis_cohort as cohort

VERSION = 'current-building-spatial-candidates-v1'


def building_objects(value, path=''):
    if isinstance(value, dict):
        if 'geoCenter' in value:
            yield path, value
        for key, child in value.items():
            yield from building_objects(child, path+'/'+key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from building_objects(child, path+'/'+str(index))


def coordinates(value):
    if not isinstance(value, dict): return None
    lat, lon = value.get('latitude'), value.get('longitude')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lon)):
        return None
    return (float(lat), float(lon)) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def street_candidate(address):
    # No ordinal/directional alias reconciliation: preserve the literal street
    # after a simple house number, with only whitespace/case normalization.
    if not isinstance(address, str): return None
    match = re.fullmatch(r'\s*\d+[A-Za-z]?(?:[-–]\d+[A-Za-z]?)?\s+(.+?)\s*', address)
    return ' '.join(match[1].lower().split()) if match else None


def bound_building(listing, unit_url, decoded):
    building_id = str(listing.get('buildingId'))
    if building_id in {'None', ''}: raise ValueError('Own listing has no building ID')
    slug = urlsplit(unit_url).path.split('/')[2]
    matches = [{'path': path, 'object': obj} for path, obj in building_objects(decoded)
               if str(obj.get('id')) == building_id]
    if not matches: return {'status': 'missing_matching_building', 'source_building_id': building_id}
    if any(m['object'].get('slug') != slug for m in matches):
        return {'status': 'building_slug_conflict', 'source_building_id': building_id, 'matches': matches}
    values = []
    for match in matches:
        obj = match['object']; center = coordinates(obj.get('geoCenter'))
        direct = coordinates(obj)
        direct_present = 'latitude' in obj or 'longitude' in obj
        if center is None or (direct_present and (direct is None or center != direct)):
            return {'status': 'invalid_or_conflicting_coordinates', 'source_building_id': building_id}
        address = (obj.get('address') or {}).get('street')
        values.append((center, address))
    if len(set(values)) != 1:
        return {'status': 'conflicting_building_objects', 'source_building_id': building_id}
    point, address = values[0]
    return {'status': 'source_bound', 'source_building_id': building_id,
        'building_slug': slug, 'latitude': point[0], 'longitude': point[1],
        'building_street_address': address, 'street_candidate': street_candidate(address),
        'source_paths': [m['path']+'/geoCenter' for m in matches],
        'listing_street_address': (listing.get('propertyDetails', {}).get('address') or {}).get('street')}


def aggregate(captures):
    groups = defaultdict(list)
    for row in captures: groups[row['building']].append(row)
    buildings = []
    for building, rows in sorted(groups.items()):
        valid = [r for r in rows if r['status'] == 'source_bound']
        variants = {(r['source_building_id'], r['latitude'], r['longitude'], r['street_candidate']) for r in valid}
        result = {'building': building, 'captures': len(rows), 'units': len({r['unit_id'] for r in rows})}
        if len(valid) != len(rows) or len(variants) != 1:
            result['status'] = 'incomplete_or_conflicting_building_evidence'
        else:
            bid, lat, lon, street = next(iter(variants))
            result.update(status='source_bound', source_building_id=bid, latitude=lat, longitude=lon, street_candidate=street)
        buildings.append(result)
    valid = [b for b in buildings if b['status'] == 'source_bound']
    center = ({k: sum(b[k] for b in valid)/len(valid) for k in ('latitude', 'longitude')} if valid else None)
    for b in valid:
        b['relative_latitude_degrees'] = b['latitude'] - center['latitude']
        b['relative_longitude_degrees'] = b['longitude'] - center['longitude']
    return buildings, center


def run(dataset, collections, output):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    if dm.get('version') != cohort.VERSION: raise ValueError('Refreshed current cohort required')
    current = [r for r in cohort.records(df['observations.jsonl']) if r['analysis_price_basis'] == 'current_capture_gross_ask']
    sources, bindings = {}, []
    for collection in collections:
        _, _, paths, binding = cohort.load_collection(collection)
        if sources.keys() & paths.keys(): raise ValueError('Overlapping capture identities')
        sources.update(paths); bindings.append(binding)
    if bindings != dm['collections']: raise ValueError('Collection lineage differs')
    captures = []
    for row in sorted(current, key=lambda r: r['audit_id']):
        provenance = row['refresh_provenance']; sha = provenance['body_sha256']
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha): raise ValueError('Invalid body hash')
        body = gzip.decompress((sources[row['capture_id']] / 'archive/bodies' / sha[:2] / (sha+'.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha: raise ValueError('Raw body changed')
        parsed, _ = granular_parse.parse_listing(body, provenance['requested_url'])
        raw = parsed['raw_listing_json']; listing = json.loads(raw)
        if (str(listing['id']) != row['source_listing_id'] or parsed['canonical_unit_url'] != row['canonical_unit_url']
                or hashlib.sha256(raw.encode()).hexdigest() != row['source_raw_sha256']):
            raise ValueError('Own listing identity differs')
        decoded = flight.decode_records(extract.flight_text(extract._scripts(extract._selector(body))))
        captures.append({**{k: row[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'collected_at', 'known_at')},
            'body_sha256': sha, 'raw_listing_sha256': row['source_raw_sha256'],
            **bound_building(listing, row['canonical_unit_url'], decoded)})
    buildings, center = aggregate(captures)
    valid = [b for b in buildings if b['status'] == 'source_bound']
    summary = {'current_captures': len(captures), 'buildings': len(buildings),
        'capture_statuses': dict(Counter(r['status'] for r in captures)),
        'building_statuses': dict(Counter(r['status'] for r in buildings)),
        'street_candidates': dict(Counter(b['street_candidate'] for b in valid if b['street_candidate'])),
        'coordinate_center': center, 'center_basis': 'Equal weight per source-consistent observed building; degrees, not distance or a NYC geographic centroid.',
        'building_constant': True,
        'identifiability': 'Coordinate and street columns are constant within building and lie in the span of building indicators. Separating their contribution from building effects requires prior/structural assumptions; no within-building location contrast is available.',
        'policy': 'Research candidates only; no geocoding requests, unit-view inference, source corrections, model inputs changed or spatial fit.'}
    paths = [Path(__file__), *(Path(m.__file__) for m in (cohort, granular_parse, extract, flight))]
    return publish_bundle(output, {'captures.jsonl': ''.join(canonical(r)+'\n' for r in captures),
        'buildings.jsonl': ''.join(canonical(r)+'\n' for r in buildings),
        'summary.json': canonical(summary)+'\n', **{p.name: p.read_text() for p in paths}},
        {'version': VERSION, 'dataset_manifest_sha256': digest(Path(dataset)/'complete.json'),
         'summary': summary, 'implementation_sha256': {p.name: digest(p) for p in paths}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--collection', dest='collections', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))

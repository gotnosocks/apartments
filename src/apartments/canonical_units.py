"""Canonical-URL unit memberships derived from retained rental captures.

Source observations and history occurrences remain intact. Join memberships by
listing_id (or unit observations by snapshot_id) to analyze a unit's full history.
"""
from collections import defaultdict
from pathlib import Path
import hashlib
import json

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .unit_canonical import ASSOCIATION_RULE, canonical_unit_id, common_unit_page

SCHEMAS = {
    'rental_units': pa.schema([
        ('unit_id', pa.string()), ('canonical_unit_url', pa.string()),
        ('listing_count', pa.int64()), ('capture_count', pa.int64()), ('rule', pa.string()),
    ]),
    'rental_unit_memberships': pa.schema([
        ('listing_id', pa.string()), ('unit_id', pa.string()),
        ('canonical_unit_url', pa.string()), ('capture_count', pa.int64()),
        ('status', pa.string()), ('reason', pa.string()), ('rule', pa.string()),
    ]),
    'rental_unit_observations': pa.schema([
        ('snapshot_id', pa.int64()), ('listing_id', pa.string()), ('unit_id', pa.string()),
        ('canonical_unit_url', pa.string()), ('status', pa.string()), ('reason', pa.string()),
    ]),
}


def memberships(captures):
    """No labels, latest-listing pointers, attributes, or event data are required."""
    listings = defaultdict(list)
    for capture in captures:
        if capture['listing_id']:
            listings[capture['listing_id']].append(capture)
    pages = {lid: common_unit_page(c['canonical_unit_url'] for c in rows)
             for lid, rows in listings.items()}
    # Don't split an inconsistent listing between two units or implicitly bridge
    # their otherwise-consistent members. Keep the affected URLs unresolved.
    ambiguous_pages = {c['canonical_unit_url'] for lid, rows in listings.items()
                       if pages[lid] is None for c in rows if c['canonical_unit_url']}
    result = []
    for lid, rows in sorted(listings.items()):
        page = pages[lid]
        reason = ('Missing or conflicting canonical unit URLs across captures' if not page else
                  'Canonical unit URL is also used by a listing with conflicting captures'
                  if page in ambiguous_pages else None)
        result.append({'listing_id': lid, 'unit_id': canonical_unit_id(page) if not reason else None,
                       'canonical_unit_url': page, 'capture_count': len(rows),
                       'status': 'unresolved' if reason else 'associated', 'reason': reason,
                       'rule': ASSOCIATION_RULE})
    return result


def build_canonical_units(root):
    """Finalize a new transform; never rewrite a completed dataset."""
    root = Path(root)
    if (root / 'complete.json').exists():
        raise ValueError('Dataset is complete; choose a new output ID')
    db = duckdb.connect(config={'memory_limit': '512MB', 'threads': '2'})
    try:
        db.read_parquet([str(p) for p in sorted((root / 'listing_observations').glob('*.parquet'))]).create_view('listings')
        rows = db.execute("SELECT snapshot_id,listing_id,canonical_unit_url FROM listings WHERE listing_type='rental' ORDER BY snapshot_id").fetchall()
    finally:
        db.close()
    captures = [dict(zip(('snapshot_id', 'listing_id', 'canonical_unit_url'), row)) for row in rows]
    members = memberships(captures)
    by_listing = {row['listing_id']: row for row in members}
    units = {}
    for member in members:
        if member['unit_id']:
            unit = units.setdefault(member['unit_id'], {
                'unit_id': member['unit_id'], 'canonical_unit_url': member['canonical_unit_url'],
                'listing_count': 0, 'capture_count': 0, 'rule': ASSOCIATION_RULE})
            unit['listing_count'] += 1
            unit['capture_count'] += member['capture_count']
    observations = []
    for capture in captures:
        member = by_listing.get(capture['listing_id'], {})
        observations.append({**capture, 'unit_id': member.get('unit_id'),
                             'status': member.get('status', 'unresolved'),
                             'reason': member.get('reason') if member else 'Missing rental listing ID'})
    if len({c['snapshot_id'] for c in captures}) != len(captures):
        raise ValueError('Duplicate rental snapshot IDs')
    tables = {'rental_units': sorted(units.values(), key=lambda row: row['canonical_unit_url']),
              'rental_unit_memberships': members, 'rental_unit_observations': observations}
    digests = {}
    for name, output in tables.items():
        path = root / name / 'derived.parquet'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        pq.write_table(pa.Table.from_pylist(output, schema=SCHEMAS[name]), temporary, compression='zstd')
        temporary.replace(path)
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {'rule': ASSOCIATION_RULE,
               'source_evidence_sha256': hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
               'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'counts': {name: len(output) for name, output in tables.items()},
               'associated_listing_ids': sum(m['status'] == 'associated' for m in members),
               'unresolved_listing_ids': sum(m['status'] == 'unresolved' for m in members),
               'unresolved_captures': sum(o['status'] == 'unresolved' for o in observations),
               'multi_listing_units': sum(u['listing_count'] > 1 for u in units.values()),
               'listing_ids_in_multi_listing_units': sum(u['listing_count'] for u in units.values() if u['listing_count'] > 1),
               'output_sha256': digests}
    from .granular_export import write_json
    write_json(root / 'canonical-units.json', summary)
    return summary

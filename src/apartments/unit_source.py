"""Extract canonical unit pages from archived HTML; never fetch live listings."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .unit_canonical import Head, head_fields, unit_page
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

VERSION = 'canonical-unit-v1'


def extract(path, url):
    parser = Head()
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as stream:
        for _ in range(128):
            chunk=stream.read(8192); parser.feed(chunk)
            if parser.done or not chunk:
                break
    fields=head_fields(parser,url)
    return fields['canonical_unit_url'],fields['canonical_unit_error']


def snapshot_rows(root):
    db = duckdb.connect(config={'memory_limit':'512MB', 'threads':'2'})
    try:
        db.read_parquet([str(p) for p in (Path(root)/'listing_observations').glob('*.parquet')]).create_view('l')
        db.read_parquet([str(p) for p in (Path(root)/'snapshots').glob('*.parquet')]).create_view('s')
        return db.execute("SELECT l.snapshot_id,l.url,s.body_hash FROM l JOIN s USING(snapshot_id) WHERE listing_type='rental' AND l.url NOT LIKE '%/media_gallery%' ORDER BY l.snapshot_id").fetchall()
    finally:
        db.close()


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def build(root, bodies, output):
    rows = snapshot_rows(root)
    def read(row):
        sid, url, digest = row
        if not re.fullmatch(r'[0-9a-f]{64}', digest or ''):
            canonical, error = None, 'Invalid body hash'
        else:
            try:
                canonical, error = extract(Path(bodies)/digest[:2]/(digest+'.gz'), url)
            except (OSError, EOFError) as exc:
                canonical, error = None, type(exc).__name__
        return {'snapshot_id':sid, 'url':url, 'body_hash':digest, 'canonical_url':canonical, 'error':error}
    extracted = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for start in range(0, len(rows), 512):
            extracted.extend(pool.map(read, rows[start:start+512]))
            if start % 5120 == 0:
                print(f'Checked {len(extracted):,} of {len(rows):,} archived heads', flush=True)
    schema = pa.schema([('snapshot_id',pa.int64()), *[(k,pa.string()) for k in ('url','body_hash','canonical_url','error')]],
                       metadata={b'version':VERSION.encode(), b'dataset':Path(root).name.encode(), b'snapshots':fingerprint(rows).encode()})
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    pq.write_table(pa.Table.from_pylist(extracted, schema=schema), temporary, compression='zstd')
    temporary.replace(output)
    print(json.dumps({'captures':len(rows), 'canonical_unit_pages':sum(r['canonical_url'] is not None for r in extracted), 'output':str(output)}), flush=True)


class SourceEvidence:
    def __init__(self, service):
        self.pages = {}; self.digest = None; self.error = 'Canonical page evidence has not been built'
        columns = {r[0] for r in service.db.execute('DESCRIBE listing_observations').fetchall()}
        if {'canonical_href','canonical_unit_url','canonical_unit_error'}.issubset(columns):
            rows=service.db.execute("SELECT r.snapshot_id,l.canonical_href,l.canonical_unit_url,l.canonical_unit_error FROM rental r JOIN listing_observations l USING(snapshot_id) ORDER BY r.snapshot_id").fetchall()
            self.pages={sid:{'canonical_href':href,'canonical_url':url,'error':error} for sid,href,url,error in rows}
            self.digest=fingerprint(rows);self.error=None
        else:
            path = service.state/'unit-source-pages.parquet'
            if path.exists():
                metadata = pq.read_metadata(path).metadata or {}
                expected = snapshot_rows(service.root)
                table = pq.read_table(path)
                rows = table.to_pylist()
                observed = sorted((r['snapshot_id'],r['url'],r['body_hash']) for r in rows)
                if (metadata.get(b'version') != VERSION.encode() or metadata.get(b'dataset') != service.dataset.encode()
                    or metadata.get(b'snapshots') != fingerprint(expected).encode() or observed != expected):
                    raise ValueError('Canonical evidence does not match this dataset; rebuild it')
                self.pages = {r['snapshot_id']:r for r in rows}
                self.digest = hashlib.sha256(path.read_bytes()).hexdigest(); self.error = None
        self.latest = dict(service.db.execute("SELECT r.snapshot_id,json_extract_string(l.raw_listing_json,'$.latestListing.id') FROM rental r JOIN listing_observations l USING(snapshot_id)").fetchall())
        self.history = {}
        for sid, lid in service.db.execute("SELECT DISTINCT e.snapshot_id,e.event_listing_id FROM event_mentions e JOIN rental r USING(snapshot_id) WHERE event_category='rental'").fetchall():
            self.history.setdefault(sid, set()).add(lid)

    def assess(self, ids, catalog, canonical_members, history_members, corrected, reserved):
        ids = set(ids); captures = [c for lid in ids for c in catalog[lid]['captures']]
        sids = sorted(c['snapshot_id'] for c in captures)
        pages = {self.pages.get(sid, {}).get('canonical_url') for sid in sids}
        latest = {self.latest.get(sid) for sid in sids}
        labels = {(c['building_slug'],c['unit_label']) for c in captures}
        reasons = []
        if None in pages or len(pages) != 1:
            reasons.append('Missing or differing canonical unit pages')
        page = next(iter(pages)) if len(pages)==1 and None not in pages else None
        if page and canonical_members.get(page, set()) != ids:
            reasons.append('The canonical unit page also identifies listings outside this group')
        if any(not building or not label or not label.strip() or re.search(r'bedroom|studio|[0-9] *br|layout|floorplan',label,re.I) for building,label in labels):
            reasons.append('Unit label is missing or generic; review identity first')
        if len(labels) != 1:
            reasons.append('Building or unit labels differ')
        elif page:
            building, label = next(iter(labels)); parts = urlsplit(page).path.strip('/').split('/')
            if (unquote(parts[1]).casefold() != (building or '').casefold()
                or unquote(parts[2]).casefold() != (label or '').strip().lstrip('#').strip().casefold()):
                reasons.append('Canonical unit page disagrees with the building or unit label')
        if None in latest or len(latest) != 1 or not latest.issubset(ids):
            reasons.append('Latest listing references are missing, inconsistent, or outside this group')
        # Require complete agreement on the set of rental episodes in every capture.
        histories = [self.history.get(sid,set()) for sid in sids]
        if any(h != ids for h in histories):
            reasons.append('Property histories do not all identify exactly these rental listings')
        if any(not history_members.get(lid,set()).issubset(ids) for lid in ids):
            reasons.append('Another unit group references these listings in its property history')
        if set(sids) & corrected:
            reasons.append('Identity or source history has a review correction')
        if ids & reserved:
            reasons.append('Group includes a prior identity decision; review individually')
        return {'eligible':not reasons and len(ids)>1, 'reasons':reasons,
                'canonical_url':page, 'latest_listing_ids':sorted(x for x in latest if x),
                'snapshot_ids':sids, 'listing_ids':sorted(ids), 'rule':VERSION,
                'source_evidence_sha256':self.digest}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--dataset',required=True); parser.add_argument('--bodies',required=True); parser.add_argument('--output',required=True)
    args=parser.parse_args(); build(args.dataset,args.bodies,args.output)

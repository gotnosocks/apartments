"""Extract canonical unit pages from archived HTML; never fetch live listings."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .unit_canonical import Head, head_fields, unit_page
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

VERSION = 'canonical-unit-v1'
ASSOCIATION_RULE = 'shared-latest-v2'


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
        self.source_labels = {sid:(building,label) for sid,building,label in service.db.execute('SELECT snapshot_id,building_slug,unit_label FROM rental').fetchall()}
        self.history = {}
        for sid, lid in service.db.execute("SELECT DISTINCT e.snapshot_id,e.event_listing_id FROM event_mentions e JOIN rental r USING(snapshot_id) WHERE event_category='rental'").fetchall():
            self.history.setdefault(sid, set()).add(lid)

    def assess(self, ids, catalog, canonical_members, history_members, corrected, reserved,
               latest_members=None, latest_labels=None):
        ids = set(ids); captures = [c for lid in ids for c in catalog[lid]['captures']]
        sids = sorted(c['snapshot_id'] for c in captures)
        pages = {self.pages.get(sid, {}).get('canonical_url') for sid in sids} - {None}
        latest = {self.latest.get(sid) for sid in sids}
        labels = {(c['building_slug'],c['unit_label']) for c in captures}
        if latest_members is None or latest_labels is None:
            latest_members,latest_labels = {},{}
            for lid,listing in catalog.items():
                for c in listing['captures']:
                    target=self.latest.get(c['snapshot_id'])
                    if target:
                        latest_members.setdefault(target,set()).add(lid)
                        latest_labels.setdefault(target,set()).add((c['building_slug'],c['unit_label']))
        conflicts = [{'latest_listing_id':target,
                      'labels':sorted([list(pair) for pair in latest_labels.get(target,set())],key=lambda p:(p[0] or '',p[1] or '')),
                      'listing_ids':sorted(latest_members.get(target,set()))}
                     for target in sorted(x for x in latest if x) if len(latest_labels.get(target,set()))>1]
        reasons = []
        if conflicts:
            reasons.append('Shared latest listing ID appears under different building or unit labels')
        if len(labels)!=1:
            reasons.append('Building or unit labels differ')
        if any(not b or not u or not u.strip() or re.search(r'bedroom|studio|[0-9] *br|layout|floorplan',u,re.I) for b,u in labels):
            reasons.append('Unit label is missing or generic; review identity first')
        if None in latest or len(latest)!=1 or not latest.issubset(ids):
            reasons.append('Latest listing references are missing, inconsistent, or outside this group')
        elif latest_members.get(next(iter(latest)),set()) != ids:
            reasons.append('Shared latest listing also identifies listings outside this group')
        if set(sids)&corrected:
            reasons.append('Identity or latest-listing reference has a review correction')
        if ids&reserved:
            reasons.append('Group includes a prior identity decision; review individually')
        # Canonical and history coverage are explanatory evidence, not prerequisites
        # for the user's explicitly authorized shared-latest association rule.
        notes=[]
        if any(not self.pages.get(sid,{}).get('canonical_url') for sid in sids):
            notes.append('Some captures do not declare a canonical unit page')
        if len(pages)>1:
            notes.append('Captures declare different canonical unit pages')
        if any(self.history.get(sid,set()) != ids for sid in sids):
            notes.append('Property-history membership differs between captures or from this group')
        if any(not history_members.get(lid,set()).issubset(ids) for lid in ids):
            notes.append('Other listings include these rental IDs in their property history')
        return {'eligible':not reasons and len(ids)>1, 'reasons':reasons, 'notes':notes,
                'latest_label_conflicts':conflicts,
                'canonical_url':next(iter(pages)) if len(pages)==1 else None,
                'canonical_urls':sorted(pages), 'latest_listing_ids':sorted(x for x in latest if x),
                'latest_references':[[sid,self.latest.get(sid)] for sid in sids],
                'snapshot_ids':sids, 'listing_ids':sorted(ids), 'rule':ASSOCIATION_RULE,
                'source_evidence_sha256':self.digest}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--dataset',required=True); parser.add_argument('--bodies',required=True); parser.add_argument('--output',required=True)
    args=parser.parse_args(); build(args.dataset,args.bodies,args.output)

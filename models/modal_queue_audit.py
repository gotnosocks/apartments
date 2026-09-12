"""Bounded cloud queue audit and explicit, writer-locked building alias migration."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit
import uuid

import modal
ROOT = Path(__file__).resolve().parents[1]
volume = modal.Volume.from_name('chelsea-archive')
locks = modal.Dict.from_name('chelsea-scrape-locks')
image = (modal.Image.debian_slim(python_version='3.12').pip_install('parsel==1.10.0')
         .env({'PYTHONPATH': '/root/src'})
         .add_local_dir(ROOT/'src/streeteasy_archive', '/root/src/streeteasy_archive', ignore=['__pycache__'])
         .add_local_file(Path(__file__), '/root/modal_queue_audit.py'))


def safe_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
        raise ValueError('Invalid workspace ID')
    return value

app = modal.App('chelsea-queue-audit')


def grouped_summary(groups):
    duplicates = [rows for rows in groups.values() if len(rows) > 1]
    return {'groups': len(duplicates), 'urls': sum(map(len, duplicates)),
            'extra_urls': sum(len(rows)-1 for rows in duplicates),
            'pending_urls': sum(state == 'pending' for rows in duplicates for url, state in rows),
            'examples': duplicates[:15]}


def unit_url_audit(db, generation):
    rows = db.execute("""SELECT f.url,f.state FROM frontier f JOIN scope_urls s USING(generation,url)
                         WHERE f.generation=? AND f.kind='listing'""", (generation,)).fetchall()
    ids, labels = defaultdict(list), defaultdict(list)
    queries, states, paths = Counter(), Counter(), Counter()
    for url, state in rows:
        p = urlsplit(url)
        states[state] += 1
        paths[p.path.split('/')[1]+'|'+state] += 1
        if p.query:
            queries[state] += 1
        match = re.search(r'/(rental|sale)/(\d+)', p.path)
        if match:
            ids[(match[1], str(int(match[2])))].append((url, state))
        match = re.fullmatch(r'/building/([^/]+)/([^/]+)', p.path)
        if match:
            # Candidate detection only: 04C and 4C may be separate source labels.
            label = re.sub(r'(?<![0-9])0+(?=[0-9])', '', match[2].lower())
            labels[(match[1], label)].append((url, state))
    print(f'Audited {len(rows)} scoped listing URLs', flush=True)
    # This uses the small covering snapshot index, never the extracted JSON column.
    latest = db.execute("""SELECT url,body_hash,max(id) FROM snapshots WHERE generation=?
                           GROUP BY url""", (generation,)).fetchall()
    listing_states = dict(rows)
    bodies = defaultdict(list)
    for url, digest, snapshot_id in latest:
        if url in listing_states:
            bodies[digest].append((url, listing_states[url]))
    return {'at': time.time(), 'total': len(rows), 'states': dict(states),
            'path_states': dict(paths), 'query_states': dict(queries),
            'same_listing_id': grouped_summary(ids),
            'unit_label_candidates': grouped_summary(labels),
            'identical_latest_body_candidates': grouped_summary(bodies)}


@app.function(image=image, cpu=(1,1), memory=(2048,2048), timeout=1800,
              volumes={'/archive': volume}, retries=0, include_source=False)
def audit_or_migrate(workspace_id='chelsea-resume', apply=False, expected_retirements=-1):
    from streeteasy_archive.store import ArchiveStore
    safe_id(workspace_id)
    owner = str(uuid.uuid4())
    if not locks.put('writer', {'owner': owner, 'workspace': workspace_id,
                              'action': 'queue-audit-migration', 'started_at_epoch': time.time()},
                     skip_if_exists=True):
        raise RuntimeError('Archive writer active; stop the batch and await its commit first')
    committed = False
    store = None
    try:
        volume.reload()
        workspace = Path('/archive/crawls')/workspace_id
        if not (workspace/'archive.sqlite3').exists():
            raise ValueError('Archive workspace does not exist')
        store = ArchiveStore(workspace)
        generation = store.current_generation()
        preview = store.deduplicate_building_views(generation, dry_run=True)
        print(json.dumps({'migration_preview': preview}), flush=True)
        if apply and preview['superseded'] != expected_retirements:
            raise ValueError('Migration differs from reviewed dry run; refusing to apply')
        report = {'at': time.time(), 'generation': generation, 'preview': preview,
                  'units': unit_url_audit(store.db, generation) if not apply else None}
        report['scope_before'] = dict(store.db.execute('''SELECT f.state,count(*) FROM frontier f
            JOIN scope_urls s USING(generation,url) WHERE f.generation=? GROUP BY f.state''', (generation,)))
        if apply:
            report['applied'] = store.deduplicate_building_views(generation)
        report['scope_after'] = dict(store.db.execute('''SELECT f.state,count(*) FROM frontier f
            JOIN scope_urls s USING(generation,url) WHERE f.generation=? GROUP BY f.state''', (generation,)))
        report['building_states'] = [tuple(row) for row in store.db.execute("""SELECT f.state,count(*) FROM frontier f
            JOIN scope_urls s USING(generation,url) WHERE f.generation=? AND f.kind='building'
            GROUP BY f.state""", (generation,))]
        destination = workspace/'audits'
        destination.mkdir(exist_ok=True)
        (destination/('queue-alias-migration.json' if apply else 'queue-alias-preview.json')).write_text(json.dumps(report, indent=2))
        store.close(); store = None
        with sqlite3.connect(workspace/'archive.sqlite3') as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.close()
        print('Committing queue audit/migration', flush=True)
        volume.commit()
        committed = True
        return report
    finally:
        if store:
            store.close()
        if committed:
            locks.pop('writer')


@app.local_entrypoint()
def main(apply: bool=False, expected_retirements: int=-1):
    result = audit_or_migrate.remote(apply=apply, expected_retirements=expected_retirements)
    destination = Path('/tmp/chelsea-queue-alias-migration.json' if apply else '/tmp/chelsea-queue-alias-preview.json')
    destination.write_text(json.dumps(result, indent=2))
    print('Saved '+str(destination))
    print(json.dumps({key:value for key,value in result.items() if key != 'units'},indent=2))

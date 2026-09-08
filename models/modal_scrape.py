"""Optional bounded remote crawl. Setup: python models/modal_scrape.py setup-secret."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

import modal

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = 'chelsea-oxylabs'
volume = modal.Volume.from_name('chelsea-archive', create_if_missing=True)
locks = modal.Dict.from_name('chelsea-scrape-locks', create_if_missing=True)
app = modal.App('chelsea-remote-scrape')
image = (modal.Image.debian_slim(python_version='3.12')
         .pip_install('Scrapy==2.18.0', 'parsel==1.10.0', 'beautifulsoup4==4.14.3',
                      'requests==2.32.5', 'python-dotenv==1.2.1')
         .env({'PYTHONPATH':'/root/src', 'OMP_NUM_THREADS':'1'})
         .add_local_dir(ROOT/'src/streeteasy_archive', '/root/src/streeteasy_archive', ignore=['__pycache__'])
         .add_local_file(Path(__file__), '/root/modal_scrape.py'))


def safe_id(value):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
        raise ValueError('IDs may contain letters, digits, dash and underscore only')
    return value


def validate_budget(max_requests, concurrency, api_rps):
    if not 1 <= max_requests <= 10000:
        raise ValueError('Require a finite request budget from 1 to 10000')
    if not 1 <= concurrency <= 20 or not math.isfinite(api_rps) or not 0 < api_rps <= 50:
        raise ValueError('Concurrency must be 1–20 and API RPS positive and at most 50')


def credentials(values):
    username = values.get('OXYLABS_USERNAME') or values.get('OXYLABS_USER')
    password = values.get('OXYLABS_PASSWORD')
    if not username or not password:
        raise ValueError('Oxylabs username/password are missing')
    return {'OXYLABS_USERNAME':username, 'OXYLABS_PASSWORD':password}


def command(workspace, max_requests, concurrency, api_rps):
    import sys
    validate_budget(max_requests, concurrency, api_rps)
    return [sys.executable, '-m', 'streeteasy_archive.cli', '--data', str(workspace),
            'resume', '--transport', 'oxylabs', '--neighborhood', 'chelsea',
            '--include-unavailable', '--max-requests', str(max_requests),
            '--concurrency', str(concurrency), '--api-rps', str(api_rps), '--delay', '0']


def clone_snapshot(base, workspace, snapshot):
    """Bulk-copy a closed immutable snapshot; share raw bodies without copying them."""
    from streeteasy_archive.snapshot_copy import copy_closed_database
    if not (base/'complete.json').exists():
        raise ValueError('Snapshot upload is incomplete')
    marker = workspace/'origin.json'
    if marker.exists():
        if json.loads(marker.read_text())['snapshot'] != snapshot:
            raise ValueError('Workspace belongs to another snapshot')
        return
    if workspace.exists():
        raise ValueError('Incomplete workspace exists; inspect it or choose a new workspace ID')
    workspace.mkdir(parents=True)
    copy_closed_database(base/'archive.sqlite3', workspace/'archive.sqlite3')
    (workspace/'bodies').symlink_to('/archive/bodies', target_is_directory=True)
    marker.write_text(json.dumps({'snapshot':snapshot, 'created_at_epoch':time.time()}))


@app.function(image=image, cpu=(2,2), memory=(8192,8192), timeout=3600,
              max_containers=1, retries=0, volumes={'/archive':volume},
              secrets=[modal.Secret.from_name(SECRET_NAME)], include_source=False)
def resume(snapshot: str, workspace_id: str, max_requests: int=100,
           concurrency: int=5, api_rps: float=1):
    import sqlite3
    import subprocess
    import uuid
    safe_id(snapshot); safe_id(workspace_id)
    validate_budget(max_requests, concurrency, api_rps)
    owner = str(uuid.uuid4())
    # Dict atomic insertion protects across separate Modal apps and containers.
    if not locks.put('writer', {'owner':owner, 'workspace':workspace_id,
                                'started_at_epoch':time.time()}, skip_if_exists=True):
        raise RuntimeError('Remote archive writer lock exists; no automatic takeover')
    committed = False
    try:
        volume.reload()
        workspace = Path('/archive/crawls')/workspace_id
        workspace.parent.mkdir(parents=True, exist_ok=True)
        clone_snapshot(Path('/archive/snapshots')/snapshot, workspace, snapshot)
        volume.commit()
        log = workspace/f'run-{owner}.log'
        with log.open('wb') as output:
            try:
                process = subprocess.run(command(workspace,max_requests,concurrency,api_rps),
                                         stdout=output, stderr=subprocess.STDOUT, timeout=3300)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
        # Subprocess has exited; flush SQLite before committing remote files.
        with sqlite3.connect(workspace/'archive.sqlite3') as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            generation = db.execute('SELECT max(id) FROM generations').fetchone()[0]
            queue = dict(db.execute('SELECT state,count(*) FROM frontier WHERE generation=? GROUP BY state', (generation,)))
            state = db.execute('SELECT status,cooldown FROM generations WHERE id=?',(generation,)).fetchone()
        db.close()
        result = {'workspace':workspace_id, 'source_snapshot':snapshot,
                  'exit_code':code, 'queue':queue, 'state':state,
                  'log':str(log.relative_to('/archive')), 'max_requests':max_requests,
                  'concurrency':concurrency, 'api_rps':api_rps}
        (workspace/'last-run.json').write_text(json.dumps(result,indent=2))
        volume.commit()
        committed = True
        return result
    finally:
        # Hard timeout/crash/commit failure leaves the lock for explicit inspection.
        if committed:
            locks.pop('writer')



def publish_workspace(workspace, destination, snapshots, new_snapshot, seed_database=False):
    """Cloud-only immutable snapshot export, with readiness marker written last."""
    import shutil
    import sqlite3
    safe_id(new_snapshot)
    if destination.exists():
        raise ValueError('Snapshot ID already exists; never overwrite snapshots')
    origin = json.loads((workspace/'origin.json').read_text())
    run = json.loads((workspace/'last-run.json').read_text())
    original = snapshots/safe_id(origin['snapshot'])
    seed = original/'apartments.duckdb'
    if seed_database and (not seed.exists() or not (original/'prepared/metadata.json').exists()
                          or Path(str(seed)+'.wal').exists()):
        raise ValueError('Seed database must have a completed preparation and no active WAL')
    destination.mkdir(parents=True)
    from streeteasy_archive.snapshot_copy import checkpoint_database, copy_closed_database
    checkpoint_database(workspace/'archive.sqlite3')
    copy_closed_database(workspace/'archive.sqlite3', destination/'archive.sqlite3')
    if seed_database:
        shutil.copyfile(seed, destination/'apartments.duckdb')
    provenance = {'snapshot':new_snapshot, 'source_workspace':workspace.name,
                  'parent_snapshot':origin['snapshot'], 'created_at_epoch':time.time(),
                  'source_run':run, 'seeded_derived_database':seed_database,
                  'body_root':'/bodies'}
    (destination/'complete.json').write_text(json.dumps(provenance,indent=2))
    return provenance


@app.function(image=image, cpu=(2,2), memory=(8192,8192), timeout=3600,
              max_containers=1, retries=0, volumes={'/archive':volume}, include_source=False)
def publish_snapshot(workspace_id: str, new_snapshot: str, seed_database: bool=False):
    import uuid
    safe_id(workspace_id); safe_id(new_snapshot)
    owner = str(uuid.uuid4())
    if not locks.put('writer', {'owner':owner, 'workspace':workspace_id,
                                'action':'publish-snapshot', 'started_at_epoch':time.time()},
                     skip_if_exists=True):
        raise RuntimeError('Remote archive writer lock exists; no automatic takeover')
    committed = False
    try:
        volume.reload()
        root = Path('/archive/snapshots')
        result = publish_workspace(Path('/archive/crawls')/workspace_id,
                                   root/new_snapshot,root,new_snapshot,seed_database)
        volume.commit()
        committed = True
        return result
    finally:
        if committed:
            locks.pop('writer')


@app.local_entrypoint()
def main(snapshot: str='chelsea-20260908', workspace: str='chelsea-resume',
         max_requests: int=100, concurrency: int=5, api_rps: float=1,
         action: str='resume', new_snapshot: str='', seed_database: bool=False):
    safe_id(snapshot); safe_id(workspace)
    if action == 'publish-snapshot':
        safe_id(new_snapshot)
        result = publish_snapshot.remote(workspace,new_snapshot,seed_database)
    elif action == 'resume':
        validate_budget(max_requests, concurrency, api_rps)
        result = resume.remote(snapshot,workspace,max_requests,concurrency,api_rps)
    else:
        raise ValueError('Action must be resume or publish-snapshot')
    print(json.dumps(result,indent=2))


def setup_secret():
    from dotenv import dotenv_values
    values = credentials(dotenv_values(ROOT/'.env', interpolate=False))
    modal.Secret.objects.create(SECRET_NAME, values)
    print('Created named Modal secret; credential values were not printed.')


def clear_lock(owner):
    current = locks.get('writer', None)
    if not current or current['owner'] != owner:
        raise ValueError('Lock owner does not match; nothing changed')
    locks.pop('writer')
    print('Cleared the explicitly selected writer lock.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup-secret','show-lock','clear-lock'])
    parser.add_argument('--owner')
    args = parser.parse_args()
    if args.action == 'setup-secret':
        setup_secret()
    elif args.action == 'show-lock':
        print(json.dumps(locks.get('writer', None), indent=2))
    else:
        if not args.owner:
            parser.error('--owner is required; first stop the worker and inspect show-lock')
        clear_lock(args.owner)

"""Optional bounded remote crawl. Setup: python models/modal_scrape.py setup-secret."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

import modal

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAME = 'oxylabs'
volume = modal.Volume.from_name('chelsea-archive', create_if_missing=True)
locks = modal.Dict.from_name('chelsea-scrape-locks', create_if_missing=True)
runs = modal.Dict.from_name('chelsea-backfill-runs', create_if_missing=True)
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



def run_logged(args, log, timeout=3300):
    """Keep the durable batch log and stream the same progress to Modal."""
    import subprocess
    import threading
    def forward(pipe, output):
        for line in iter(pipe.readline, b''):
            output.write(line)
            output.flush()
            print(line.decode('utf-8', errors='replace'), end='', flush=True)
    with log.open('wb') as output:
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            reader = threading.Thread(target=forward, args=(process.stdout, output), daemon=True)
            reader.start()
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                code = 124
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                reader.join()
    return code


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


@app.function(image=image, cpu=(1,1), memory=(2048,2048), timeout=3600,
              nonpreemptible=True, max_containers=1, retries=0, volumes={'/archive':volume},
              secrets=[modal.Secret.from_name(SECRET_NAME)], include_source=False)
def resume(snapshot: str, workspace_id: str, max_requests: int=100,
           concurrency: int=10, api_rps: float=2):
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
        print('Opening resumable cloud archive: '+workspace_id, flush=True)
        clone_snapshot(Path('/archive/snapshots')/snapshot, workspace, snapshot)
        volume.commit()
        print(f'Starting crawl batch: budget={max_requests}, concurrency={concurrency}, api_rps={api_rps}', flush=True)
        with sqlite3.connect(workspace/'archive.sqlite3') as before_db:
            done_before = before_db.execute("SELECT count(*) FROM frontier f JOIN scope_urls s USING(generation,url) WHERE f.generation=(SELECT max(id) FROM generations) AND f.state='done'").fetchone()[0]
        before_db.close()
        log = workspace/f'run-{owner}.log'
        code = run_logged(command(workspace,max_requests,concurrency,api_rps), log)
        # Subprocess has exited; flush SQLite before committing remote files.
        with sqlite3.connect(workspace/'archive.sqlite3') as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            generation = db.execute('SELECT max(id) FROM generations').fetchone()[0]
            queue = dict(db.execute('SELECT state,count(*) FROM frontier WHERE generation=? GROUP BY state', (generation,)))
            scoped = dict(db.execute('SELECT f.state,count(*) FROM frontier f JOIN scope_urls s USING(generation,url) WHERE f.generation=? GROUP BY f.state', (generation,)))
            state = db.execute('SELECT status,cooldown FROM generations WHERE id=?',(generation,)).fetchone()
        db.close()
        result = {'workspace':workspace_id, 'source_snapshot':snapshot,
                  'exit_code':code, 'queue':queue, 'scope_queue':scoped, 'state':state,
                  'made_progress':scoped.get('done',0) > done_before,
                  'log':str(log.relative_to('/archive')), 'max_requests':max_requests,
                  'concurrency':concurrency, 'api_rps':api_rps}
        (workspace/'last-run.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)
        volume.commit()
        committed = True
        return result
    finally:
        # Hard timeout/crash/commit failure leaves the lock for explicit inspection.
        if committed:
            locks.pop('writer')


def continuation(result):
    """Completion refers to discovered scope only, never guaranteed NYC coverage."""
    if result['exit_code'] != 0 and not (result['exit_code'] == 124 and result.get('made_progress')):
        return 'needs_attention'
    queue = result['scope_queue']
    if queue.get('pending',0) or queue.get('inflight',0):
        return 'continue'
    if queue.get('deferred',0):
        return 'coverage_gaps'
    return 'queue_drained'


@app.function(image=image, cpu=(0.125,0.125), memory=(256,256), timeout=86400,
              nonpreemptible=True, max_containers=1, retries=0, include_source=False)
def finish_backfill(snapshot: str, workspace: str, total_budget: int=30000,
                    batch_size: int=750, concurrency: int=10, api_rps: float=2):
    """Cheap cloud controller; serial bounded workers survive laptop disconnects."""
    import uuid
    safe_id(snapshot); safe_id(workspace)
    if not 1 <= total_budget <= 30000:
        raise ValueError('Overall request budget must be 1–30000')
    validate_budget(batch_size,concurrency,api_rps)
    run_id = str(uuid.uuid4())
    report = {'run_id':run_id,'workspace':workspace,'status':'running',
              'allocated_requests':0,'total_budget':total_budget,'batches':[]}
    runs[run_id] = report
    runs['latest:'+workspace] = run_id
    print(json.dumps({'run_id':run_id,'workspace':workspace}),flush=True)
    try:
        previous_queue = None
        while report['allocated_requests'] < total_budget:
            if runs.get('stop-after-batch:'+workspace, False):
                report['status'] = 'stopped_at_batch_boundary'
                break
            budget = min(batch_size,total_budget-report['allocated_requests'])
            report['allocated_requests'] += budget
            runs[run_id] = report
            result = resume.remote(snapshot,workspace,budget,concurrency,api_rps)
            report['batches'].append(result)
            decision = continuation(result)
            if decision != 'continue':
                report['status'] = decision
                break
            if result['scope_queue'] == previous_queue:
                report['status'] = 'no_progress'
                break
            previous_queue = result['scope_queue']
            runs[run_id] = report
        else:
            report['status'] = 'budget_reached'
    except Exception as exc:
        report['status'] = 'failed'
        report['error_type'] = type(exc).__name__
        runs[run_id] = report
        raise
    runs[run_id] = report
    return report



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
         max_requests: int=100, concurrency: int=10, api_rps: float=2,
         action: str='resume', new_snapshot: str='', seed_database: bool=False,
         total_budget: int=30000, batch_size: int=750):
    safe_id(snapshot); safe_id(workspace)
    if action == 'finish':
        result = finish_backfill.remote(snapshot,workspace,total_budget,batch_size,concurrency,api_rps)
    elif action == 'publish-snapshot':
        safe_id(new_snapshot)
        result = publish_snapshot.remote(workspace,new_snapshot,seed_database)
    elif action == 'resume':
        validate_budget(max_requests, concurrency, api_rps)
        result = resume.remote(snapshot,workspace,max_requests,concurrency,api_rps)
    else:
        raise ValueError('Action must be resume, finish, or publish-snapshot')
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


def submit_backfill(snapshot='chelsea-20260908', workspace='chelsea-resume', total_budget=1000):
    """Submit to a deployed app; the laptop need not remain connected."""
    safe_id(snapshot); safe_id(workspace)
    if not 1 <= total_budget <= 30000:
        raise ValueError('Require a finite total budget from 1 to 30000')
    if locks.get('writer', None):
        raise RuntimeError('Writer already active; do not submit another controller')
    latest = runs.get('latest:'+workspace, None)
    if latest and runs.get(latest, {}).get('status') == 'running':
        raise RuntimeError('Controller reports running; verify its state before replacement')
    if runs.get('stop-after-batch:'+workspace, False):
        raise RuntimeError('Clear the batch stop flag before submitting')
    call = modal.Function.from_name('chelsea-remote-scrape', 'finish_backfill').spawn(
        snapshot, workspace, total_budget, 750, 10, 2)
    report = {'call_id':call.object_id, 'workspace':workspace, 'total_budget':total_budget,
              'submitted_at_epoch':time.time()}
    runs['submission:'+workspace] = report
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup-secret','show-lock','clear-lock','submit'])
    parser.add_argument('--owner')
    parser.add_argument('--total-budget', type=int, default=1000)
    args = parser.parse_args()
    if args.action == 'setup-secret':
        setup_secret()
    elif args.action == 'submit':
        print(json.dumps(submit_backfill(total_budget=args.total_budget), indent=2))
    elif args.action == 'show-lock':
        print(json.dumps(locks.get('writer', None), indent=2))
    else:
        if not args.owner:
            parser.error('--owner is required; first stop the worker and inspect show-lock')
        clear_lock(args.owner)

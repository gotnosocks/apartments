"""Private Modal RPC for the archive browser; no public HTTP endpoint is deployed."""
from __future__ import annotations

import json
from pathlib import Path
import time
import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App('chelsea-archive-browser')
volume = modal.Volume.from_name('chelsea-archive', create_if_missing=True)
locks = modal.Dict.from_name('chelsea-scrape-locks', create_if_missing=True)
image = (modal.Image.debian_slim(python_version='3.12')
         .pip_install('Flask==3.1.2', 'parsel==1.10.0')
         .env({'PYTHONPATH':'/root/src'})
         .add_local_dir(ROOT/'src/streeteasy_archive', '/root/src/streeteasy_archive', ignore=['__pycache__'])
         .add_local_file(Path(__file__), '/root/modal_cloud_browser.py'))


def safe_id(value):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
        raise ValueError('Invalid archive ID')
    return value


def active_archive(root):
    pointer = json.loads((root/'authoritative.json').read_text())
    parts = pointer['archive_path'].split('/')
    if len(parts) != 2 or parts[0] != 'crawls':
        raise ValueError('Invalid authoritative archive path')
    safe_id(parts[1])
    return root/pointer['archive_path'], pointer


def respond(root, path, query_string='', writer=None):
    """Route a read-only request through the existing Flask archive application."""
    from streeteasy_archive.web import create_app
    if (not isinstance(path, str) or not path.startswith('/') or '?' in path
            or '..' in path.split('/') or '\\' in path or len(path) > 1024
            or not isinstance(query_string, str) or len(query_string) > 8192):
        raise ValueError('Invalid browser request')
    if path != '/' and not path.startswith(('/api/', '/static/')):
        raise ValueError('Unsupported browser path')
    archive, pointer = active_archive(root)
    checkpoint = json.loads((root/'browser/checkpoint.json').read_text())
    web = create_app(root/'browser')
    with web.test_client() as client:
        response = client.get(path, query_string=query_string)
        if path == '/api/summary' and response.status_code == 200:
            value = response.get_json()
            value.update(storage_mode='cloud', archive_path=pointer['archive_path'],
                         cloud_committed_at=checkpoint.get('committed_at'),
                         writer_running=bool(writer), worker_lock=writer,
                         local_copy_role='backup')
            response.set_data(json.dumps(value))
        headers = {key:value for key,value in response.headers.items()
                   if key.lower() in {'content-type','content-security-policy','x-content-type-options',
                                      'referrer-policy','cache-control','content-disposition'}}
        body = response.get_data()
        if len(body) > 32*1024*1024:
            return {'status':413,'headers':{'Content-Type':'application/json'},
                    'body':b'{"error":"Response exceeds browser transfer limit"}'}
        return {'status':response.status_code, 'headers':headers, 'body':body}


@app.function(image=image, cpu=(1,1), memory=(2048,2048), timeout=120,
              min_containers=0, max_containers=1, scaledown_window=10,
              volumes={'/archive':volume}, include_source=False)
def read(path: str, query_string: str=''):
    # All SQLite connections close at request teardown before the next reload.
    volume.reload()
    return respond(Path('/archive'), path, query_string, locks.get('writer', None))


def initialize(root, snapshot, workspace):
    """Create the cloud working archive without modifying the historical snapshot."""
    import shutil
    safe_id(snapshot); safe_id(workspace)
    source = root/'snapshots'/snapshot
    if not (source/'complete.json').exists():
        raise ValueError('Source snapshot is incomplete')
    target = root/'crawls'/workspace
    if (root/'authoritative.json').exists():
        current, pointer = active_archive(root)
        if current != target:
            raise ValueError('Another authoritative archive is already selected')
        return pointer
    if target.exists():
        raise ValueError('Workspace already exists without authority marker; inspect before adopting')
    target.mkdir(parents=True)
    wal = source/'archive.sqlite3-wal'
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Immutable source unexpectedly has an active WAL')
    shutil.copyfile(source/'archive.sqlite3', target/'archive.sqlite3')
    (target/'bodies').symlink_to(root/'bodies', target_is_directory=True)
    (target/'origin.json').write_text(json.dumps({'snapshot':snapshot,'created_at_epoch':time.time()}))
    pointer = {'archive_path':f'crawls/{workspace}', 'source_snapshot':snapshot,
               'committed_at':time.time(), 'local_copy_role':'backup'}
    (root/'authoritative.json').write_text(json.dumps(pointer,indent=2))
    return pointer


@app.function(image=image, cpu=(2,2), memory=(2048,2048), timeout=1800,
              max_containers=1, retries=0, volumes={'/archive':volume}, include_source=False)
def activate(snapshot: str, workspace: str):
    import uuid
    owner = str(uuid.uuid4())
    if not locks.put('writer', {'owner':owner,'workspace':workspace,'action':'activate',
                                'started_at_epoch':time.time()}, skip_if_exists=True):
        raise RuntimeError('Cloud archive writer is active; inspect its lock first')
    committed = False
    try:
        volume.reload()
        result = initialize(Path('/archive'), snapshot, workspace)
        from streeteasy_archive.cloud_state import publish_browser_checkpoint
        publish_browser_checkpoint(Path('/archive')/result['archive_path'], Path('/archive'))
        volume.commit()
        committed = True
        return result
    finally:
        if committed:
            locks.pop('writer')


@app.local_entrypoint()
def main(snapshot: str='chelsea-20260908', workspace: str='chelsea-resume'):
    print(json.dumps(activate.remote(snapshot,workspace),indent=2))

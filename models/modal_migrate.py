"""Frozen, checksummed streaming export of the Modal archive for host migration."""
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import tarfile
import time

import modal

app = modal.App('chelsea-archive-migration')
volume = modal.Volume.from_name('chelsea-archive')
image = modal.Image.debian_slim(python_version='3.12').apt_install('zstd')
BASE = Path('/archive')
EXPORT = BASE / 'migrations/thelio-20260916'


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.partial')
    tmp.write_text(json.dumps(value))
    tmp.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


@app.function(image=image, cpu=1, memory=(1024,2048), timeout=1800, volumes={'/archive':volume}, max_containers=1)
def plan():
    volume.reload()
    EXPORT.mkdir(parents=True, exist_ok=True)
    if (EXPORT/'plan.json').exists():
        return json.loads((EXPORT/'plan.json').read_text())
    records = []
    totals = {}
    def add(path):
        # SQLite rebuilds its process coordination index; it is not durable data.
        # Keep database and WAL files, which can contain committed records.
        if path.name.endswith(".sqlite3-shm") and path.with_name(path.name[:-4]).is_file():
            return
        st = path.lstat()
        rel = path.relative_to(BASE).as_posix()
        rec = {'path':rel, 'size':st.st_size, 'mtime_ns':st.st_mtime_ns, 'mode':stat.S_IMODE(st.st_mode)}
        if path.is_symlink():
            original = os.readlink(path)
            target = (path.parent / original).resolve() if not original.startswith('/') else Path(original).resolve()
            try:
                target_relative = target.relative_to(BASE.resolve())
            except ValueError:
                # Older snapshots retained the SDK's internal path for this same volume.
                target_relative = target.relative_to(Path('/__modal/volumes')/volume.object_id)
            rec.update(type='symlink',target=os.path.relpath(BASE/target_relative,path.parent),original_target=original)
            rec['size'] = 0
        elif not stat.S_ISREG(st.st_mode):
            raise ValueError('Unsupported source file: '+rel)
        records.append(rec)
        root = rel.split('/')[0]
        totals.setdefault(root, {'files':0,'bytes':0})
        totals[root]['files'] += 1
        totals[root]['bytes'] += rec['size']
    for top in sorted(BASE.iterdir()):
        if top.name == 'migrations':continue
        if top.is_symlink() or top.is_file():add(top);continue
        for folder, dirs, files in os.walk(top, followlinks=False):
            for name in list(dirs):
                path=Path(folder)/name
                if path.is_symlink():add(path);dirs.remove(name)
            for name in files:add(Path(folder)/name)
    priority={'reviews':0,'datasets':1,'fits':2,'bodies':3,'snapshots':4,'crawls':5}
    records.sort(key=lambda r:(priority.get(r['path'].split('/')[0],9),r['path']))
    groups=[];batch=[];size=0
    (EXPORT/'jobs').mkdir(exist_ok=True);(EXPORT/'packs').mkdir(exist_ok=True)
    def flush():
        nonlocal batch,size
        if not batch:return
        ident=len(groups)
        write_json(EXPORT/'jobs'/f'{ident:05d}.json',batch)
        groups.append({'id':ident,'bytes':size,'files':len(batch)})
        batch=[];size=0
    previous=None
    for record in records:
        top=record['path'].split('/')[0]
        if batch and (size+record['size']>2*1024**3 or len(batch)>=5000 or previous!=top):flush()
        batch.append(record);size+=record['size'];previous=top
    flush()
    out={'version':1,'created_at':time.time(),'source':'chelsea-archive','total_files':len(records),'total_bytes':sum(r['size'] for r in records),'groups':groups,'by_root':totals}
    write_json(EXPORT/'plan.json',out);volume.commit()
    print(json.dumps(out),flush=True)
    return out


class HashReader:
    def __init__(self, stream, label=None):
        self.stream=stream;self.hash=hashlib.sha256();self.label=label
        self.bytes=0;self.started=self.last_log=time.time()
    def read(self,n=-1):
        value=self.stream.read(n);self.hash.update(value);self.bytes+=len(value)
        now=time.time()
        if self.label is not None and now-self.last_log>=30:
            print(json.dumps({'file':self.label,'uncompressed_bytes':self.bytes,'elapsed':round(now-self.started)}),flush=True)
            self.last_log=now
        return value


@app.function(image=image,cpu=(2,2),memory=(1024,2048),timeout=14400,volumes={'/archive':volume},max_containers=2,retries=0)
def pack(ident):
    volume.reload()
    ready=EXPORT/'packs'/f'{ident:05d}.ready.json'
    if ready.exists():return json.loads(ready.read_text())
    records=json.loads((EXPORT/'jobs'/f'{ident:05d}.json').read_text())
    name=EXPORT/'packs'/f'{ident:05d}.tar.zst'
    partial=name.with_suffix(name.suffix+'.partial')
    manifest=EXPORT/'packs'/f'{ident:05d}.manifest.jsonl'
    manifest_partial=manifest.with_suffix('.partial')
    started=time.time();last_log=started;bytes_done=0
    with partial.open('wb') as output,manifest_partial.open('w') as mf:
        proc=subprocess.Popen(['zstd','-3','-T2','--quiet','-c'],stdin=subprocess.PIPE,stdout=output)
        try:
            with tarfile.open(fileobj=proc.stdin,mode='w|',bufsize=1024*1024) as archive:
                for record in records:
                    source=BASE/record['path'];before=source.lstat()
                    if before.st_mtime_ns!=record['mtime_ns'] or (record.get('type')!='symlink' and before.st_size!=record['size']):raise RuntimeError('Source changed since freeze: '+record['path'])
                    info=tarfile.TarInfo(record['path']);info.mode=record['mode'];info.mtime=before.st_mtime
                    if record.get('type')=='symlink':
                        if os.readlink(source)!=record['original_target']:raise RuntimeError('Source symlink changed')
                        info.type=tarfile.SYMTYPE;info.linkname=record['target'];archive.addfile(info)
                        final={'path':record['path'],'type':'symlink','target':record['target']}
                    else:
                        info.size=record['size']
                        with source.open('rb') as raw:
                            reader=HashReader(raw, record["path"]);archive.addfile(info,reader)
                        after=source.stat()
                        if after.st_size!=before.st_size or after.st_mtime_ns!=before.st_mtime_ns:raise RuntimeError('Source mutated during export: '+record['path'])
                        final={'path':record['path'],'size':record['size'],'sha256':reader.hash.hexdigest()}
                        bytes_done+=record['size']
                    mf.write(json.dumps(final)+'\n')
                    if time.time()-last_log>30:
                        print(json.dumps({'group':ident,'uncompressed_bytes':bytes_done,'elapsed':round(time.time()-started)}),flush=True);last_log=time.time()
            proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('zstd failed')
        except BaseException:
            proc.kill();proc.wait();raise
    partial.replace(name);manifest_partial.replace(manifest)
    result={'id':ident,'files':len(records),'bytes':name.stat().st_size,'uncompressed_bytes':bytes_done,'sha256':sha256(name),'manifest_sha256':sha256(manifest),'seconds':time.time()-started}
    write_json(ready,result);volume.commit();print(json.dumps(result),flush=True)
    return result


@app.function(image=image,cpu=.25,memory=512,timeout=86400,volumes={'/archive':volume},max_containers=1,retries=0)
def run():
    planned=plan.remote()
    errors=[]
    for result in pack.map([g['id'] for g in planned['groups']],order_outputs=False,return_exceptions=True):
        if isinstance(result, Exception):
            errors.append(str(result));print(json.dumps({'pack_error':str(result)}),flush=True)
        else:
            print(json.dumps(result),flush=True)
    if errors:
        raise RuntimeError('Export incomplete; successful bundles retained: '+str(errors))
    volume.reload()
    ready=[json.loads((EXPORT/'packs'/f'{g["id"]:05d}.ready.json').read_text()) for g in planned['groups']]
    out={'completed_at':time.time(),'files':sum(r['files'] for r in ready),'bytes':sum(r['bytes'] for r in ready),'uncompressed_bytes':sum(r['uncompressed_bytes'] for r in ready)}
    write_json(EXPORT/'complete.json',out);volume.commit();return out


@app.function(image=image,cpu=.25,memory=512,timeout=120,volumes={'/archive':volume})
def status():
    volume.reload()
    planned=json.loads((EXPORT/'plan.json').read_text()) if (EXPORT/'plan.json').exists() else None
    ready=[json.loads(p.read_text()) for p in (EXPORT/'packs').glob('*.ready.json')] if (EXPORT/'packs').exists() else []
    return {'plan':planned,'completed_groups':len(ready),'compressed_bytes':sum(r['bytes'] for r in ready),'completed_uncompressed_bytes':sum(r['uncompressed_bytes'] for r in ready),'complete':(EXPORT/'complete.json').exists()}

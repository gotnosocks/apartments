"""Measure local bundle transfer sizes; compress only analytical input to a sink.

No upload, posterior reads/compression, fitting, bundle modification or stripped
bundle loading. Run against completed immutable input and baseline bundles.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import tarfile
import time
import zlib


class CountingSink:
    def __init__(self):
        self.bytes = 0
        self.hash = hashlib.sha256()

    def write(self, value):
        self.bytes += len(value)
        self.hash.update(value)
        return len(value)

    def flush(self):
        pass


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def inventory(path):
    path = Path(path)
    marker = path/'complete.json'
    if marker.is_symlink():
        raise ValueError('Symlinked manifest is not a portable bundle')
    manifest = json.loads(marker.read_text())
    records = []
    for name in ['complete.json', *sorted(manifest['files'])]:
        file = path/name
        if Path(name).name!=name or file.is_symlink() or not file.is_file():
            raise ValueError('Invalid bundle file: '+name)
        records.append({'name':name,'bytes':file.stat().st_size})
    return {'directory':str(path),'manifest_sha256':digest(marker),
            'manifest_version':manifest.get('version'),'files':records,
            'file_count_including_manifest':len(records),'bytes':sum(r['bytes'] for r in records),
            'content_integrity_checked':False}


def analytical_compression(path, measured, level):
    path = Path(path)
    manifest = json.loads((path/'complete.json').read_text())
    expected = {'complete.json':measured['manifest_sha256'], **manifest['files']}
    names = [r['name'] for r in measured['files']]
    # Verify all analytical bytes both before and after compression. The baseline
    # posterior is only stat'ed by inventory and is never read by this script.
    if any(digest(path/name)!=expected[name] for name in names):
        raise ValueError('Analytical source does not match its manifest')
    sink = CountingSink()
    started = time.monotonic()
    with gzip.GzipFile(filename='', mode='wb', fileobj=sink, compresslevel=level, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
            for name in names:
                info = tarfile.TarInfo('dataset/'+name)
                info.size = (path/name).stat().st_size
                info.mode = 0o644
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ''
                with (path/name).open('rb') as source:
                    archive.addfile(info, source)
    elapsed = time.monotonic()-started
    if (inventory(path)!=measured or any(digest(path/name)!=expected[name] for name in names)):
        raise ValueError('Analytical source changed during compression measurement')
    return {'format':'deterministic USTAR stream inside gzip; dataset/ prefix; zero timestamps and owners',
            'gzip_level':level,'bytes':sink.bytes,'sha256':sink.hash.hexdigest(),
            'compressed_fraction':sink.bytes/measured['bytes'],
            'uncompressed_to_compressed_ratio':measured['bytes']/sink.bytes,
            'compression_wall_seconds':elapsed,'wall_time_is_not_a_benchmark':True,
            'python':platform.python_version(),'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'source_hashes_verified_before_and_after':True,'archive_retained':False,
            'decompression_roundtrip_performed':False}


def run(dataset, experiment, output, level=6):
    if not 0<=level<=9:
        raise ValueError('Gzip level must be between zero and nine')
    input_bundle = inventory(dataset)
    fit = inventory(Path(experiment)/'fit')
    protocol = inventory(Path(experiment)/'protocol')
    declared = json.loads((Path(experiment)/'protocol/protocol.json').read_text())
    baseline_dataset = inventory(Path(declared['source_directory']))
    if baseline_dataset['manifest_sha256']!=declared['source_manifest_sha256']:
        raise ValueError('Baseline source manifest does not match fitted protocol')
    compression = analytical_compression(dataset,input_bundle,level)
    # Re-stat immutable baseline bundle membership; no posterior content hashing.
    if (fit!=inventory(Path(experiment)/'fit') or protocol!=inventory(Path(experiment)/'protocol')
            or baseline_dataset!=inventory(Path(declared['source_directory']))):
        raise ValueError('Baseline inventory changed during measurement')
    input_bundle['content_integrity_checked'] = True
    result = {'version':'local-modal-transfer-footprint-v1','analytical_input':input_bundle,
              'baseline_fit':fit,'baseline_protocol':protocol,'baseline_matching_dataset':baseline_dataset,
              'baseline_offline_closure':{'bytes':sum(v['bytes'] for v in (fit,protocol,baseline_dataset)),
                  'file_count_including_manifests':sum(v['file_count_including_manifest'] for v in (fit,protocol,baseline_dataset)),
                  'actual_stripped_bundle_load_performed':False},
              'analytical_input_compression':compression,
              'planning_combination':{'bytes':input_bundle['bytes']+fit['bytes']+protocol['bytes'],
                  'file_count_including_manifests':sum(v['file_count_including_manifest'] for v in (input_bundle,fit,protocol)),
                  'warning':'Size planning only: baseline posterior belongs to a different source dataset; this mixed set is not a valid analysis bundle.'},
              'posterior_read_or_compressed':False,'remote_activity':False,'stripped_bundle_load_performed':False,
              'measurement_script_sha256':digest(__file__)}
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as target:
        target.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),'input_bytes':input_bundle['bytes'],
                      'input_gzip_bytes':compression['bytes'],'baseline_fit_bytes':fit['bytes'],
                      'baseline_protocol_bytes':protocol['bytes']}))
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--level',type=int,default=6)
    run(**vars(parser.parse_args()))

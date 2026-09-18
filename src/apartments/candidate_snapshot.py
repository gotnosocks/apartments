"""Canonical, capture-dated search inputs from the immutable granular archive."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from . import analytical, attribute_evidence, corrections, historical_dataset as history
from .corrections import Overlay, canonical, instant
from .research_pipeline import _verified_bundle, digest, publish_bundle


def project_capture(capture, memberships, *, as_of, identity_known_at, overlay=None, recovery=None):
    cutoff=instant(as_of)
    collected=history._time(capture['collected_at']);parsed=history._time(capture['parsed_at'])
    if max(instant(collected),instant(parsed),instant(identity_known_at))>cutoff:
        return None,'not_known_at_cutoff'
    identities={(m.get('unit_id'),m.get('canonical_unit_url')) for m in memberships
                if m.get('status')=='associated' and m.get('rule')=='canonical-url-v1'}
    if len(identities)!=1:
        return None,'unresolved_identity'
    unit,url=next(iter(identities))
    match=re.fullmatch(r'https://streeteasy\.com/building/([^/]+)/([^/?#]+)',url or '')
    if not unit or not match or capture.get('canonical_unit_url')!=url:
        return None,'conflicting_canonical_url'
    original=json.loads(capture.get('raw_listing_json') or '{}');interpreted=deepcopy(original)
    clocks=[collected,parsed,identity_known_at]
    visible=recovery if recovery and instant(recovery['interpreted_at'])<=cutoff else None
    if visible:
        interpreted['description']=visible['resolved_description'];clocks.append(visible['interpreted_at'])
    evidence=attribute_evidence.extract_attribute_evidence(interpreted)
    attrs={k:capture.get(k) for k in ('bedrooms','bathrooms','square_feet')}
    attrs.update({k:v for k,v in evidence['attributes'].items() if k not in attrs and v is not None})
    for field in evidence.get('conflicts',{}):
        attrs[field]=None
    listing=str(capture['listing_id'])
    raw={'source':'streeteasy','source_listing_id':listing,'canonical_url':url,
         'captured_at':collected,'attributes':attrs,
         'home_features':json.loads(capture.get('features_json') or '[]'),
         'building_amenities':json.loads(capture.get('amenities_json') or '[]'),
         'archive_listing':interpreted}
    context={'source':'streeteasy','source_listing_id':listing,'episode_id':listing,
             'capture_id':str(capture['snapshot_id']),'version_id':str(capture['snapshot_id']),
             'building_slug':capture.get('building_slug') or '', 'unit':capture.get('unit_label') or ''}
    corrected,edits=overlay.apply(raw,context,effective_at=instant(collected)) if overlay else (raw,[])
    clocks.extend(e['recorded_at'] for e in edits)
    rent,price_path=analytical._price(corrected)
    flags=analytical._rental_flags(corrected)
    description=str((corrected.get('archive_listing') or {}).get('description') or '')
    if flags['furnished'] is None and history._description_furnished(description):
        flags['furnished']=True
    return {'unit_id':unit,'building_id':match[1],'canonical_unit_url':url,
            'source':'streeteasy','source_listing_id':listing,'capture_id':str(capture['snapshot_id']),
            'collected_at':collected,'known_at':max(clocks,key=instant),
            'listing_status':corrected.get('status') or (corrected.get('archive_listing') or {}).get('status'),
            'rent':rent,'price_basis':'gross_advertised_rent','price_path':price_path,
            **analytical.attributes(corrected),**flags,
            'source_raw_sha256':hashlib.sha256((capture.get('raw_listing_json') or '{}').encode()).hexdigest(),
            'attribute_evidence':evidence,'corrections':edits,
            'description_interpreted_at':visible['interpreted_at'] if visible else None,
            'attribute_time_basis':'capture-time evidence, with corrections effective at collection; not historical price-event attributes'},None


def build_snapshot(dataset, historical_reference, output, *, as_of, ledger=None, description_recovery=None):
    """Use a verified source inventory; never copy historical initial rent into search."""
    import duckdb
    root=Path(dataset);cutoff=instant(as_of)
    reference,content=_verified_bundle(historical_reference,retain={'source-files.json'})
    if reference.get('dataset_version')!='historical-own-advertisement-v1':
        raise ValueError('Verified canonical historical projection required for source inventory')
    files=json.loads(content['source-files.json'])
    if hashlib.sha256(canonical(files).encode()).hexdigest()!=reference['source_manifest_sha256']:
        raise ValueError('Source inventory hash mismatch')
    for name,expected in files.items():
        path=root/name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Invalid source inventory path')
        if digest(path)!=expected:
            raise ValueError('Archive source changed')
    complete=json.loads((root/'complete.json').read_text())
    if complete.get('unit_association_rule')!='canonical-url-v1':
        raise ValueError('Canonical URL memberships required')
    identity_known=history._time(complete['finished_at'])
    if instant(identity_known)>cutoff:
        raise ValueError('Identity mapping was unavailable at cutoff')
    overlay=Overlay(ledger,as_of=as_of) if ledger is not None else None
    paths=[Path(m.__file__) for m in (analytical,attribute_evidence,corrections,history)]+[Path(__file__)]
    implementation={p.name:digest(p) for p in paths}
    db=duckdb.connect(config={'memory_limit':'1GB','threads':'2'})
    records=[];excluded=[]
    try:
        tables=('listing_observations','rental_unit_memberships')+(('snapshots',) if description_recovery else ())
        for table in tables:
            shards=[str(root/name) for name in sorted(files) if name.startswith(table+'/') and name.endswith('.parquet')]
            if not shards:
                raise ValueError('Missing verified source shards: '+table)
            db.read_parquet(shards).create_view(table)
            if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]!=complete['counts'][table]:
                raise ValueError('Archive source row count mismatch')
        rm,recoveries=history._load_recoveries(description_recovery,db,files,root) if description_recovery else (None,{})
        members=defaultdict(list)
        cursor=db.execute('SELECT * FROM rental_unit_memberships');keys=[d[0] for d in cursor.description]
        for values in cursor.fetchall():
            row=dict(zip(keys,values));members[str(row['listing_id'])].append(row)
        cursor=db.execute("SELECT * FROM listing_observations WHERE listing_type='rental' ORDER BY listing_id,snapshot_id")
        keys=[d[0] for d in cursor.description]
        while batch:=cursor.fetchmany(256):
            for values in batch:
                capture=dict(zip(keys,values))
                row,reason=project_capture(capture,members[str(capture['listing_id'])],as_of=as_of,
                    identity_known_at=identity_known,overlay=overlay,recovery=recoveries.get(capture['snapshot_id']))
                if row:
                    records.append(row)
                else:
                    excluded.append({'capture_id':capture['snapshot_id'],'source_listing_id':capture['listing_id'],'reason':reason})
    finally:
        db.close()
    if any(digest(root/name)!=expected for name,expected in files.items()):
        raise ValueError('Archive changed during snapshot build')
    if any(digest(p)!=implementation[p.name] for p in paths):
        raise ValueError('Implementation changed during snapshot build')
    report={'captures':len(records),'quarantined':len(excluded),
            'status_counts':dict(sorted(Counter(str(r['listing_status']) for r in records).items())),
            'reasons':dict(sorted(Counter(r['reason'] for r in excluded).items())),
            'as_of':cutoff.isoformat(),'identity_known_at':identity_known,
            'limitations':['All captured advertisement statuses are retained; candidate selection must resolve each advertisement before combining units.',
                           'Prices come from current pricing.price in each captured advertisement, never its initial historical event.',
                           'Attributes and corrections describe the collection time; no physical change date is inferred.',
                           'Source-reported ACTIVE at capture does not guarantee current availability.']}
    return publish_bundle(output,{'candidates.jsonl':''.join(canonical(r)+'\n' for r in records),
                                  'quarantine.jsonl':''.join(canonical(r)+'\n' for r in excluded),
                                  'coverage.json':canonical(report)+'\n','source-files.json':canonical(files)+'\n'},
                          {'snapshot_version':'canonical-candidate-captures-v1','as_of':cutoff.isoformat(),
                           'source_manifest_sha256':reference['source_manifest_sha256'],
                           'description_recovery':rm,'overlay':overlay.manifest if overlay else None,
                           'implementation_sha256':implementation,'coverage':report})

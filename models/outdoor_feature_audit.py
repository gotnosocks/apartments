"""Audit structured outdoor scope and literal area wording on the fitted cohort."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from datetime import datetime,UTC
import gzip
import hashlib
import json
from pathlib import Path

from apartments import granular_parse,outdoor_evidence
from apartments.corrections import canonical,instant
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from . import interior_feature_audit as source_helpers
from .interior_feature_audit import checked_description,json_rows

VERSION='cohort-outdoor-evidence-v1'


def category(captures,scope):
    """Union positive reported types within the same advertisement, not absences.

    Changed type lists are retained as a review signal. Text remains review-only.
    Unknown codes block the category rather than being treated as understood.
    """
    present=False;types=set();unknown=set();reported_sets=set()
    allowed=outdoor_evidence.PRIVATE_TYPES if scope=='private' else outdoor_evidence.SHARED_TYPES
    for capture in captures:
        local=set()
        for assertion in capture['extraction']['assertions']:
            if assertion['attribute']==scope+'_outdoor' and assertion['value'] is True:present=True
            if assertion['attribute']==scope+'_type':
                value=assertion['value']
                if value in allowed:types.add(value);local.add(value)
                else:unknown.add(value)
        if local:reported_sets.add(tuple(sorted(local)))
    value=None if unknown else '+'.join(sorted(types)) if types else 'unspecified' if present else None
    return {'category':value,'reported_types':sorted(types),'unknown_type_codes':sorted(unknown),
            'reported_type_sets_changed':len(reported_sets)>1,'structured_positive':present,
            'scope':'Same-advertisement union of positive structured reports; no absent-type inference or cross-advertisement backfill.'}


def run(dataset,archive,historical,recovery,refresh,output):
    import duckdb
    dm,df=_verified_bundle(dataset,retain={'observations.jsonl'})
    hm,hf=_verified_bundle(historical,retain={'source-files.json'})
    rm,rf=_verified_bundle(recovery,retain={'accepted.jsonl'})
    fm,_=_verified_bundle(Path(refresh)/'snapshot')
    if dm.get('historical_manifest')!=hm or dm.get('current_snapshot_manifest')!=fm:
        raise ValueError('Sources do not bind the supplied fitted dataset')
    rows=json_rows(df['observations.jsonl']);by_id={r['audit_id']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('Duplicate analytical identities')
    inventory=json.loads(hf['source-files.json']);archive=Path(archive);paths={}
    for table in ('listing_observations','snapshots'):
        paths[table]=[archive/p for p in inventory if p.startswith(table+'/') and p.endswith('.parquet')]
        if not paths[table]:raise ValueError('Missing source table')
        for path in paths[table]:
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path)!=inventory[str(path.relative_to(archive))]:
                raise ValueError('Source shard hash mismatch')
    recovered={r['snapshot_id']:r for r in json_rows(rf['accepted.jsonl'])}
    targets={};current=[]
    for row in rows:
        if row['analysis_price_basis']=='current_capture_gross_ask':current.append(row)
        elif row['analysis_price_basis']=='historical_initial_own_advertisement_ask':
            for capture in row['capture_ids']:
                if capture in targets:raise ValueError('Duplicate source capture membership')
                targets[capture]=row
        else:raise ValueError('Unknown price basis')
    evidence=[];counts=Counter();seen=set()
    def consume(row,capture,raw,body_hash,collected_at,rec=None):
        description,raw_hash=checked_description(raw,body_hash,rec,row)
        observed=(datetime.fromtimestamp(collected_at,UTC) if isinstance(collected_at,(int,float)) else instant(collected_at))
        if observed>instant(row['known_at']):raise ValueError('Capture later than row knowledge clock')
        payload=json.loads(raw);payload['description']=description
        extraction=outdoor_evidence.extract(payload)
        counts['captures']+=1
        if description:counts['resolved_text_captures']+=1
        if extraction['assertions'] or extraction['description_candidates'] or extraction['warnings']:
            evidence.append({'audit_id':row['audit_id'],'source_listing_id':str(row['source_listing_id']),
                'unit_id':row['unit_id'],'building_id':row['building'],'canonical_unit_url':row['canonical_unit_url'],
                'period':row['period'],'known_at':row['known_at'],'capture_id':capture,
                'source_collected_at':observed.isoformat(),'body_sha256':body_hash,'raw_listing_sha256':raw_hash,
                'description_interpreted_at':rec['interpreted_at'] if rec else None,
                'description':description,'property_details':payload.get('propertyDetails'),
                'extraction':extraction,'status':'structured_advertised_claims_and_unreviewed_text_candidates'})
    with duckdb.connect(config={'threads':'2','memory_limit':'1GB'}) as db:
        for table in paths:db.read_parquet([str(p) for p in paths[table]]).create_view(table)
        cursor=db.execute('SELECT l.snapshot_id,l.listing_id,l.canonical_unit_url,l.raw_listing_json,s.body_hash,l.collected_at '
            'FROM listing_observations l JOIN snapshots s USING(snapshot_id) '
            'WHERE l.snapshot_id IN (SELECT unnest(?)) ORDER BY l.snapshot_id',[sorted(targets)])
        while batch:=cursor.fetchmany(128):
            for capture,listing,url,raw,body_hash,collected_at in batch:
                row=targets[capture]
                if capture in seen or str(listing)!=str(row['source_listing_id']) or url!=row['canonical_unit_url']:
                    raise ValueError('Source capture identity mismatch or duplicate')
                seen.add(capture);consume(row,capture,raw,body_hash,collected_at,recovered.get(capture))
    if seen!=set(targets):raise ValueError('Missing source captures')
    for row in sorted(current,key=lambda r:r['audit_id']):
        provenance=row['refresh_provenance'];sha=provenance['body_sha256']
        body=gzip.decompress((Path(refresh)/'archive/bodies'/sha[:2]/(sha+'.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('Current body hash mismatch')
        parsed,_=granular_parse.parse_listing(body,provenance['requested_url'])
        if str(parsed['listing_id'])!=str(row['source_listing_id']) or parsed['canonical_unit_url']!=row['canonical_unit_url']:
            raise ValueError('Current capture identity mismatch')
        consume(row,row['capture_id'],parsed['raw_listing_json'],sha,row['collected_at'])
    evidence.sort(key=lambda r:(r['audit_id'],str(r['capture_id'])))
    grouped=defaultdict(list)
    for capture in evidence:grouped[capture['audit_id']].append(capture)
    projected=[];support={}
    for row in rows:
        categories={scope:category(grouped.get(row['audit_id'],[]),scope) for scope in ('private','shared')}
        projected.append({'audit_id':row['audit_id'],'source_listing_id':str(row['source_listing_id']),
            'unit_id':row['unit_id'],'private_outdoor_category':categories['private']['category'],
            'shared_outdoor_category':categories['shared']['category'],'decisions':categories})
    for scope in ('private','shared'):
        field=scope+'_outdoor_category';known=[r for r in projected if r[field] is not None]
        support[scope]={'known_rows':len(known),'unknown_rows':len(rows)-len(known),
            'units':len({r['unit_id'] for r in known}),'buildings':len({by_id[r['audit_id']]['building'] for r in known}),
            'categories':dict(sorted(Counter(r[field] for r in known).items())),
            'changed_reported_type_sets':sum(r['decisions'][scope]['reported_type_sets_changed'] for r in projected)}
    report={'rows':len(rows),'captures':dict(counts),'evidence_captures':len(evidence),'support':support,
        'area_candidate_rows':len({r['audit_id'] for r in evidence if any(c['feature']=='outdoor_area' for c in r['extraction']['description_candidates'])}),
        'policy':'Structured positive types only for category projection. Empty arrays are unknown. Descriptions and outdoor areas remain review candidates, not modeled values.'}
    paths=[Path(__file__),Path(outdoor_evidence.__file__),Path(granular_parse.__file__),Path(source_helpers.__file__)]
    return publish_bundle(output,{'evidence.jsonl':''.join(canonical(r)+'\n' for r in evidence),
        'categories.jsonl':''.join(canonical(r)+'\n' for r in projected),'report.json':canonical(report)+'\n',
        **{p.name:p.read_text() for p in paths}}, {'version':VERSION,'dataset_manifest':dm,'historical_manifest':hm,
        'recovery_manifest':rm,'refresh_manifest':fm,'report':report,'implementation_sha256':{p.name:digest(p) for p in paths}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','archive','historical','recovery','refresh','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();print(canonical(run(**vars(args))['report']))

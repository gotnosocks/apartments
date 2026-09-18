"""Screen the fitted historical cohort for source-scope and initial-price issues.

Screens propose review cases, never automatically correct prices or exclude rows.
The thresholds are independent of fitted residual magnitude.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from apartments.corrections import canonical,instant
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle

VERSION='analysis-source-scope-screen-v1'
PATTERNS={
    'commercial_language':re.compile(r'\b(?:retail|commercial|office)\s+(?:space|storefront|lease|rental|loft)\b|\bcafe\s+and\s+retail\s+shop\b',re.I),
    'advertised_net_effective':re.compile(r'\b(?:advertis(?:e|ed|ing)|listed)\s+(?:rent|price)[^.\n]{0,50}\bnet[\s-]*effective\b|\b(?:rent|price)\s+(?:is\s+)?(?:advertised|listed)\s+(?:as\s+)?net[\s-]*effective\b',re.I)}


def screen(payload,price_at,asking_rent):
    findings=[];description=payload.get('description')
    if isinstance(description,str):
        for reason,pattern in PATTERNS.items():
            for match in pattern.finditer(description):
                findings.append({'reason':reason,'match':match.group(),'start':match.start(),'end':match.end(),
                    'context':description[max(0,match.start()-120):min(len(description),match.end()+180)]})
    events=[]
    for event in (payload.get('pricing') or {}).get('priceChanges') or []:
        try:
            date=instant(event['changedAt']);price=float(event['price'])
        except (ValueError,TypeError,KeyError):
            continue
        if math.isfinite(price) and price>0:
            events.append((date,price))
    events=sorted(set(events))
    if len(events)>=2:
        first,second=events[:2];seconds=(second[0]-first[0]).total_seconds()
        ratio=max(first[1],second[1])/min(first[1],second[1])
        if (first[0].date()==instant(price_at).date() and first[1]==asking_rent
                and 0<seconds<=300 and ratio>=5):
            findings.append({'reason':'rapid_large_initial_price_change','first_at':first[0].isoformat(),
                'first_price':first[1],'next_at':second[0].isoformat(),'next_price':second[1],
                'elapsed_seconds':seconds,'price_ratio':ratio})
    return findings


def run(dataset,archive,historical,recovery,output):
    import duckdb
    dataset=Path(dataset);archive=Path(archive)
    dm,df=_verified_bundle(dataset,retain={'observations.jsonl'})
    hm,hf=_verified_bundle(historical,retain={'source-files.json'})
    if dm.get('historical_manifest')!=hm:
        raise ValueError('Historical source differs from fitted analytical dataset')
    source_files=json.loads(hf['source-files.json']);paths={}
    for name in ('listing_observations','snapshots'):
        paths[name]=[archive/p for p in source_files if p.startswith(name+'/') and p.endswith('.parquet')]
        if not paths[name]:
            raise ValueError('Missing verified source shards')
        for path in paths[name]:
            if not path.resolve().is_relative_to(archive.resolve()) or digest(path)!=source_files[str(path.relative_to(archive))]:
                raise ValueError('Source shard differs from verified inventory')
    rows=[json.loads(s) for s in df['observations.jsonl'].decode().split('\n') if s.strip()]
    targets={}
    for row in rows:
        if row['analysis_price_basis']=='historical_initial_own_advertisement_ask':
            for capture in row['capture_ids']:
                if capture in targets:
                    raise ValueError('Capture belongs to multiple fitted observations')
                targets[capture]=row
    recovery_manifest,rf=_verified_bundle(recovery,retain={'accepted.jsonl'})
    recoveries={r['snapshot_id']:r for r in (json.loads(s) for s in rf['accepted.jsonl'].decode().split('\n') if s.strip())}
    flagged=[];seen=set();source_counts=Counter()
    with duckdb.connect(config={'threads':'2','memory_limit':'1GB'}) as db:
        db.read_parquet([str(p) for p in paths['listing_observations']]).create_view('listings')
        db.read_parquet([str(p) for p in paths['snapshots']]).create_view('snapshots')
        cursor=db.execute('SELECT l.snapshot_id,l.listing_id,l.canonical_unit_url,l.raw_listing_json,s.body_hash FROM listings l JOIN snapshots s USING(snapshot_id) WHERE l.snapshot_id IN (SELECT unnest(?)) ORDER BY l.snapshot_id',[sorted(targets)])
        while batch:=cursor.fetchmany(128):
            for capture,listing,url,raw,body_hash in batch:
                row=targets[capture];seen.add(capture)
                if str(listing)!=str(row['source_listing_id']) or url!=row['canonical_unit_url']:
                    raise ValueError('Source capture identity mismatch')
                raw_hash=hashlib.sha256(raw.encode()).hexdigest();payload=json.loads(raw)
                rec=recoveries.get(capture)
                if rec:
                    if (rec['original_raw_listing_sha256']!=raw_hash or rec['source_body_sha256']!=body_hash
                            or instant(rec['interpreted_at'])>instant(row['known_at'])):
                        raise ValueError('Description recovery differs from source/knowledge cutoff')
                    payload['description']=rec['resolved_description'];source_counts['recovered_descriptions']+=1
                source_counts['captures']+=1
                findings=screen(payload,row['price_at'],row['asking_rent'])
                if findings:
                    flagged.append({'audit_id':row['audit_id'],'unit_id':row['unit_id'],'source_listing_id':listing,
                        'canonical_unit_url':url,'price_at':row['price_at'],'asking_rent':row['asking_rent'],
                        'capture_id':capture,'body_sha256':body_hash,'raw_listing_sha256':raw_hash,
                        'description':payload.get('description'),'price_changes':(payload.get('pricing') or {}).get('priceChanges'),
                        'findings':findings,'status':'review_candidate_no_data_action'})
    if seen!=set(targets):
        raise ValueError('Source captures missing from audit')
    reason_ids=defaultdict(set)
    for row in flagged:
        for finding in row['findings']:
            reason_ids[finding['reason']].add(row['source_listing_id'])
    report={'version':VERSION,'historical_rows':len({r['audit_id'] for r in targets.values()}),
        'source_counts':dict(source_counts),'flagged_captures':len(flagged),
        'flagged_advertisements':len({r['source_listing_id'] for r in flagged}),
        'advertisements_by_reason':{k:len(v) for k,v in sorted(reason_ids.items())},
        'policy':'Review screens only; do not automatically exclude commercial keyword matches or replace prices.',
        'rapid_change_rule':'First price matches modeled initial ask and UTC calendar date; next distinct event within 300 seconds; multiplicative change at least fivefold.',
        'scope':'All historical observations in the supplied fitted cohort, independent of residual magnitude. Current capture rows are outside this historical audit.'}
    return publish_bundle(output,{'candidates.jsonl':''.join(canonical(r)+'\n' for r in flagged),
        'report.json':canonical(report)+'\n','screen.py':Path(__file__).read_text()},
        {'version':VERSION,'dataset_manifest':dm,'historical_manifest':hm,'recovery_manifest':recovery_manifest,
         'implementation_sha256':digest(__file__),'report':report})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','archive','historical','recovery','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    print(canonical(run(args.dataset,args.archive,args.historical,args.recovery,args.output)['report']))

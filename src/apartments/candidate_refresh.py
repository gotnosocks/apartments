"""Bounded Oxylabs refresh of a verified, explicitly selected advertisement set.

Responses are archived before parsing. Resume reuses durable responses, and an
interrupted request with no recorded response is an explicit uncertain failure,
not an automatic repeat charge. A new refresh requires a new output directory.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, UTC
import fcntl
import hashlib
import json
from pathlib import Path

from . import candidate_search, candidate_snapshot, granular_parse, attribute_evidence, unit_canonical
from . import analytical, historical_dataset, corrections, research_pipeline
from . import pricing, robust_pricing
from .corrections import canonical, Overlay
from .research_pipeline import _verified_bundle, digest, publish_bundle
from streeteasy_archive import oxylabs, capture as capture_utils
from streeteasy_archive import store, extract, flight, crawler
from streeteasy_archive.store import ArchiveStore
from streeteasy_archive.crawler import is_challenge

VERSION='bounded-candidate-refresh-v1'


def _code_paths():
    return [Path(m.__file__) for m in (candidate_search,candidate_snapshot,granular_parse,attribute_evidence,
        unit_canonical,analytical,historical_dataset,corrections,research_pipeline,oxylabs,capture_utils,
        store,extract,flight,crawler,pricing,robust_pricing)]+[Path(__file__)]


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _pause_if_blocked(root, result, completed, plan, ph):
    if result.get('reason') not in ('source_challenge','provider_auth_rejected','HTTP 401','HTTP 403','HTTP 429'):
        return None
    pause={'status':'paused_after_blocked_response','completed':completed,'targets':len(plan['targets']),
           'reason':result['reason'],'requires_review_before_new_collection':True}
    publish_bundle(root/'pause',{'pause.json':canonical(pause)+'\n'},{'version':plan['version'],'plan_sha256':ph})
    return pause


def prepare(snapshot, output, *, max_age_days=7, max_targets=50, ledger=None):
    if not isinstance(max_targets,int) or not 1<=max_targets<=100:
        raise ValueError('Choose a bounded target limit from 1 to 100')
    source,files=_verified_bundle(snapshot,retain={'candidates.jsonl'})
    if source.get('snapshot_version')!='canonical-candidate-captures-v1':
        raise ValueError('Verified canonical candidate snapshot required')
    overlay=Overlay(ledger,as_of=source['as_of']) if ledger is not None else None
    if source.get('overlay'):
        if overlay is None or overlay.manifest!=source['overlay']:
            raise ValueError('Use the same correction ledger/cutoff as the source snapshot')
    rows=(json.loads(line) for line in files['candidates.jsonl'].decode().split('\n') if line.strip())
    selected,_,selection=candidate_search.select_candidates(rows,as_of=source['as_of'],max_age_days=max_age_days)
    targets=[]
    for row in selected:
        url=row.get('canonical_unit_url')
        if unit_canonical.canonical_unit_id(url)!=row['unit_id']:
            raise ValueError('Candidate unit identity differs from canonical URL')
        for ad in row['active_advertisement_evidence']:
            listing=str(ad['source_listing_id'])
            if ad.get('source')!='streeteasy' or not listing.isdigit():
                raise ValueError('Only numeric StreetEasy rental advertisement IDs supported')
            targets.append({'unit_id':row['unit_id'],'canonical_unit_url':url,'source_listing_id':listing,
                            'url':'https://streeteasy.com/rental/'+listing,
                            'previous_capture':ad,'previous_record':row})
    targets=sorted(targets,key=lambda r:(r['unit_id'],r['source_listing_id']))
    if not targets or len(targets)>max_targets:
        raise ValueError(f'Found {len(targets)} targets; choose an explicit bounded selection (no silent truncation)')
    paths=_code_paths()
    plan={'version':VERSION,'snapshot_manifest':source,'selection':selection,'targets':targets,
          'max_targets':max_targets,'max_provider_submissions':3*len(targets),
          'transport':'oxylabs','api_submissions_per_second':1,'concurrency':1,'render':False,
          'overlay':overlay.manifest if overlay else None,
          'implementation_sha256':{p.name:digest(p) for p in paths},
          'scope':'Refresh previously source-active advertisements only; no discovery or request expansion.',
          'failure_policy':'No fallback to older candidates; failures remain explicit. No automatic retry of uncertain interrupted submissions.'}
    root=Path(output);ph=_hash(plan)
    publish_bundle(root/'plan',{'refresh-plan.json':canonical(plan)+'\n',
                              **{p.name:p.read_text() for p in paths}},
                   {'version':VERSION,'plan_sha256':ph})
    return plan,ph


def interpret(target, observation, body, plan_hash, *, interpreted_at, overlay=None):
    result={'url':target['url'],'unit_id':target['unit_id'],'source_listing_id':target['source_listing_id'],
            'observation_id':observation['id'],'body_sha256':observation['body_hash'],
            'collected_at':datetime.fromtimestamp(observation['fetched'],UTC).isoformat(),
            'interpreted_at':interpreted_at,'status':'failed','candidate':None}
    if observation['error']:
        return {**result,'reason':observation['error']}
    if not 200<=observation['status']<300:
        return {**result,'reason':'HTTP '+str(observation['status'])}
    if is_challenge(body):
        return {**result,'reason':'source_challenge'}
    try:
        parsed,_=granular_parse.parse_listing(body,target['url'])
    except (ValueError,TypeError,KeyError) as exc:
        return {**result,'reason':'parse_exception:'+type(exc).__name__}
    if parsed.get('listing_id')!=target['source_listing_id'] or parsed.get('listing_type')!='rental':
        return {**result,'reason':'advertisement_identity_or_type_mismatch'}
    if parsed.get('canonical_unit_url')!=target['canonical_unit_url'] or parsed.get('canonical_unit_error'):
        return {**result,'reason':'canonical_unit_mismatch'}
    # Current asking price does not require resolved historical events, but
    # conflicting listing objects or malformed history remain unsafe to choose.
    if parsed.get('parse_status')!='ok' and parsed.get('error')!='propertyHistory missing or unresolved':
        return {**result,'reason':'ambiguous_or_failed_parse'}
    unique='refresh:'+plan_hash[:16]+':'+str(observation['id'])
    parsed.update(snapshot_id=unique,collected_at=observation['fetched'],parsed_at=interpreted_at)
    membership={'unit_id':target['unit_id'],'canonical_unit_url':target['canonical_unit_url'],
                'status':'associated','rule':'canonical-url-v1'}
    row,reason=candidate_snapshot.project_capture(parsed,[membership],as_of=interpreted_at,
                                                 identity_known_at=interpreted_at,overlay=overlay)
    if reason:
        return {**result,'reason':reason}
    row['refresh_provenance']={'plan_sha256':plan_hash,'observation_id':observation['id'],
                               'body_sha256':observation['body_hash'],'requested_url':target['url'],
                               'parser_version':granular_parse.VERSION,'parse_status':parsed['parse_status'],
                               'history_warning':parsed.get('error')}
    # All statuses are retained. An inactive payload is a successful refresh,
    # not a failed request and not a reason to restore the older ACTIVE claim.
    changes={key:{'before':target['previous_record'].get(key),'after':row.get(key)}
             for key in ('listing_status','rent','bedrooms','bathrooms','square_feet','elevator',
                         'laundry_type','doorman_type','hvac_type','pet_policy','view_exposures','window_exposures')
             if target['previous_record'].get(key)!=row.get(key)}
    return {**result,'status':'parsed','candidate':row,'changes':changes}


async def execute_prepared(plan, ph, root, *, max_new_requests=None, fetch=None, ledger=None,
                           code_paths=None, interpreter=interpret):
    """Execute a validated, frozen plan while the caller holds the refresh lock."""
    root=Path(root)
    if max_new_requests is not None and (type(max_new_requests) is not int or max_new_requests<1):
        raise ValueError('Optional preflight limit must be a positive integer')
    code_paths=_code_paths() if code_paths is None else code_paths
    if {p.name:digest(p) for p in code_paths} != plan['implementation_sha256'] or _hash(plan)!=ph:
        raise ValueError('Prepared plan or implementation differs')
    if (root/'pause'/'complete.json').exists():
        manifest,files=_verified_bundle(root/'pause',retain={'pause.json'})
        if manifest.get('plan_sha256')!=ph:
            raise ValueError('Pause belongs to a different plan')
        return json.loads(files['pause.json'])
    overlay=Overlay(ledger,as_of=plan['snapshot_manifest']['as_of']) if ledger is not None else None
    archive=ArchiveStore(root/'archive')
    handler=None
    try:
        generation=archive.current_generation() or archive.new_generation('bounded-candidate-refresh')
        archive.enqueue(generation,[{'url':r['url'],'kind':'listing'} for r in plan['targets']])
        if fetch is None:
            from scrapy.settings import Settings
            handler=oxylabs.OxylabsDownloadHandler(Settings({'ARCHIVE_API_RPS':1,'ARCHIVE_OXYLABS_RENDER':False}))
            fetch=handler.download_request
        from scrapy import Request
        results=[];fresh=0
        for index,target in enumerate(plan['targets']):
            directory=root/'results'/f'{index:04d}'
            binding={'version':plan['version'],'plan_sha256':ph,'target_sha256':_hash(target),'index':index}
            if (directory/'complete.json').exists():
                manifest,files=_verified_bundle(directory,retain={'result.json'})
                if any(manifest.get(k)!=v for k,v in binding.items()):
                    raise ValueError('Refresh checkpoint target mismatch')
                result=json.loads(files['result.json'])
                if result.get('body_sha256') and hashlib.sha256(archive.get_body(result['body_sha256'])).hexdigest()!=result['body_sha256']:
                    raise ValueError('Archived body integrity failure')
                results.append(result)
                if pause:=_pause_if_blocked(root,result,len(results),plan,ph):
                    return pause
                continue
            existing=archive.db.execute('SELECT * FROM observations WHERE generation=? AND url=? ORDER BY id DESC LIMIT 1',
                                        (generation,target['url'])).fetchone()
            started=root/'requests'/f'{index:04d}'
            if existing is None and (started/'complete.json').exists():
                manifest,_=_verified_bundle(started)
                if any(manifest.get(k)!=v for k,v in binding.items()):
                    raise ValueError('Request intent target mismatch')
                result={'url':target['url'],'unit_id':target['unit_id'],'source_listing_id':target['source_listing_id'],
                        'status':'failed','reason':'interrupted_request_outcome_unknown','candidate':None,'body_sha256':None}
            else:
                if existing is None:
                    if max_new_requests is not None and fresh>=max_new_requests:
                        return {'status':'paused_at_declared_limit','completed':len(results),'targets':len(plan['targets'])}
                    publish_bundle(started,{'intent.json':canonical({'started_at':datetime.now(UTC).isoformat(),'url':target['url']})+'\n'},binding)
                    print(canonical({'phase':'fetching','index':index,'targets':len(plan['targets']),'url':target['url']}),flush=True)
                    fresh+=1
                    try:
                        response=await fetch(Request(target['url']))
                        metadata=capture_utils.capture_metadata(response.meta,'oxylabs')
                        archive.record(generation,target['url'],response.status,
                            response.meta.get('archive_response_headers',{}),body=bytes(response.body),
                            content_type='text/html',capture=metadata)
                    except (RuntimeError,ValueError,OSError) as exc:
                        # Provider exceptions can hold request objects; retain only the class.
                        auth_failure=any(str(exc).startswith('Oxylabs request failed (HTTP '+status) for status in ('401','403'))
                        archive.record(generation,target['url'],0,{},error='provider_auth_rejected' if auth_failure else 'transport_failure:'+type(exc).__name__,
                                       capture={'transport':'oxylabs'})
                    existing=archive.db.execute('SELECT * FROM observations WHERE generation=? AND url=? ORDER BY id DESC LIMIT 1',
                                                (generation,target['url'])).fetchone()
                observation=dict(existing)
                body=archive.get_body(observation['body_hash']) if observation['body_hash'] else b''
                if observation['body_hash'] and hashlib.sha256(body).hexdigest()!=observation['body_hash']:
                    raise ValueError('Archived body integrity failure')
                result=interpreter(target,observation,body,ph,interpreted_at=datetime.now(UTC).isoformat(),overlay=overlay)
            publish_bundle(directory,{'result.json':canonical(result)+'\n'},binding)
            results.append(result)
            (root/'progress.json').write_text(canonical({'completed':len(results),'targets':len(plan['targets']),'latest_status':result['status']})+'\n')
            if pause:=_pause_if_blocked(root,result,len(results),plan,ph):
                return pause
        from collections import Counter
        rows=[r['candidate'] for r in results if r['status']=='parsed']
        failures=[{k:v for k,v in r.items() if k!='candidate'} for r in results if r['status']!='parsed']
        report={'targets':len(results),'parsed':len(rows),'failed':len(failures),
                'listing_status_counts':dict(sorted(Counter(str(r['listing_status']) for r in rows).items())),
                'failure_reasons':dict(sorted(Counter(r['reason'] for r in failures).items())),
                'scope':plan['scope'],'max_provider_submissions':plan['max_provider_submissions'],
                'latest_known_at':max((r['known_at'] for r in rows),default=None),
                'limitations':['A bounded refresh of the chosen earlier advertisements, not a census or discovery of new units.',
                               'Failures do not fall back to old captures and do not prove a listing is inactive.',
                               'ACTIVE is source-reported at capture, not a guarantee of future availability.',
                               'Corrections use the frozen source-snapshot knowledge cutoff, applied at each new collection time; later review changes require a new projection.']}
        if plan.get('limitations') is not None:
            report['limitations']=plan['limitations']
        if any(digest(p)!=plan['implementation_sha256'][p.name] for p in code_paths):
            raise ValueError('Implementation changed during refresh')
        manifest=publish_bundle(root/'snapshot',{'candidates.jsonl':''.join(canonical(r)+'\n' for r in rows),
            'failures.jsonl':''.join(canonical(r)+'\n' for r in failures),'report.json':canonical(report)+'\n',
            'changes.jsonl':''.join(canonical({k:v for k,v in r.items() if k!='candidate'})+'\n' for r in results)},
            {'snapshot_version':'bounded-refreshed-candidates-v1','plan_sha256':ph,'report':report})
        return manifest
    finally:
        if handler:
            await handler.close()
        archive.close()


async def refresh(snapshot, output, *, max_age_days=7, max_targets=50, max_new_requests=None, fetch=None, ledger=None):
    if max_new_requests is not None and (type(max_new_requests) is not int or max_new_requests<1):
        raise ValueError('Optional preflight limit must be a positive integer')
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    with (root/'.refresh.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        plan,ph=prepare(snapshot,root,max_age_days=max_age_days,max_targets=max_targets,ledger=ledger)
        return await execute_prepared(plan,ph,root,max_new_requests=max_new_requests,fetch=fetch,ledger=ledger)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-age-days',type=float,default=7)
    parser.add_argument('--max-targets',type=int,default=50)
    parser.add_argument('--max-new-requests',type=int)
    parser.add_argument('--ledger',type=Path,default=Path('config/corrections.jsonl'))
    args=parser.parse_args()
    print(canonical(asyncio.run(refresh(args.snapshot,args.output,max_age_days=args.max_age_days,
        max_targets=args.max_targets,max_new_requests=args.max_new_requests,ledger=args.ledger))))

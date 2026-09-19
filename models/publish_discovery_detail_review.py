"""Verify completed detail collection and publish descriptive coverage/eligibility."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

from apartments import candidate_search
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'completed-discovery-detail-review-v1'


def run(collection, reference, output):
    collection, reference = Path(collection), Path(reference)
    pm, pf = _verified_bundle(collection/'plan', retain={'refresh-plan.json'})
    sm, sf = _verified_bundle(collection/'snapshot', retain={'candidates.jsonl','report.json'})
    _, rf = _verified_bundle(reference, retain={'observations.jsonl'})
    plan = json.loads(pf['refresh-plan.json']); report = json.loads(sf['report.json'])
    ph = hashlib.sha256(canonical(plan).encode()).hexdigest()
    if (pm.get('plan_sha256') != ph or sm.get('plan_sha256') != ph
            or report['targets'] != len(plan['targets'])):
        raise ValueError('Completed collection binding differs')
    candidates = [json.loads(l) for l in sf['candidates.jsonl'].decode().splitlines()]
    prior = [json.loads(l) for l in rf['observations.jsonl'].decode().splitlines()]
    results = []; inventory = []
    for index, target in enumerate(plan['targets']):
        manifest, files = _verified_bundle(collection/'results'/f'{index:04d}', retain={'result.json'})
        if (manifest.get('plan_sha256') != ph or manifest.get('index') != index
                or manifest.get('target_sha256') != hashlib.sha256(canonical(target).encode()).hexdigest()):
            raise ValueError('Result identity differs')
        result = json.loads(files['result.json']); sha = result.get('body_sha256')
        if sha:
            if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('Invalid body hash')
            body = gzip.decompress((collection/'archive/bodies'/sha[:2]/(sha+'.gz')).read_bytes())
            if hashlib.sha256(body).hexdigest() != sha:
                raise ValueError('Raw body changed')
        results.append(result)
        inventory.append({'index':index,'source_listing_id':target['source_listing_id'],
            'result_manifest_sha256':digest(collection/'results'/f'{index:04d}'/'complete.json'),
            'body_sha256':sha,'observation_id':result.get('observation_id'),'outcome':result['status'],
            'reason':result.get('reason')})
    if [r['candidate'] for r in results if r['status']=='parsed'] != candidates:
        raise ValueError('Snapshot differs from completed candidate records')
    dbpath=(collection/'archive/archive.sqlite3').resolve()
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.row_factory=sqlite3.Row
        transport=[dict(r) for r in db.execute('SELECT id,url,status,error,body_hash,capture_metadata,fetched FROM observations ORDER BY id')]
    byid={r['id']:r for r in transport}
    if set(byid)!={r['observation_id'] for r in results if r.get('observation_id') is not None}:
        raise ValueError('Unexpected or missing transport observations')
    for result in results:
        if result.get('observation_id') is not None:
            saved=byid[result['observation_id']]
            if saved['url']!=result['url'] or saved['body_hash']!=result['body_sha256']:
                raise ValueError('Transport and interpretation differ')
    attempts=[json.loads(r['capture_metadata']).get('provider',{}).get('submission_attempts') for r in transport]
    if any(not isinstance(n,int) or not 1<=n<=3 for n in attempts):
        raise ValueError('Provider attempt inventory is incomplete or outside the plan')
    selected, rejected, eligibility=candidate_search.select_candidates(candidates,as_of=report['latest_known_at'],max_age_days=7)
    old_units={r['unit_id'] for r in prior}; old_ads={str(r['source_listing_id']) for r in prior}
    old_buildings={r['building'] for r in prior}
    current={str(r['source_listing_id']) for r in prior if r['analysis_price_basis']=='current_capture_gross_ask'}
    collected={t['source_listing_id'] for t in plan['targets']}
    summary={'version':VERSION,'collection':report,'transport':{'observations':len(transport),
        'HTTP_statuses':dict(Counter(str(r['status']) for r in transport)),
        'provider_submissions':sum(attempts),'retry_submissions':sum(n-1 for n in attempts),
        'first_capture':datetime.fromtimestamp(min(r['fetched'] for r in transport),UTC).isoformat(),
        'last_capture':datetime.fromtimestamp(max(r['fetched'] for r in transport),UTC).isoformat()},
        'snapshot_units':len({r['unit_id'] for r in candidates}),
        'snapshot_buildings':len({r['building_id'] for r in candidates}),
        'eligible_units':len(selected),'eligibility':eligibility,
        'eligibility_rejections':dict(Counter(r['reason'] for r in rejected)),
        'eligible_units_seen_in_reference':sum(r['unit_id'] in old_units for r in selected),
        'eligible_buildings_unseen_in_reference':sorted({r['building_id'] for r in selected}-old_buildings),
        'captured_advertisements_seen_in_reference':len(collected&old_ads),
        'prior_current_advertisements_not_in_this_pass':sorted(current-collected),
        'bindings':{'plan':digest(collection/'plan/complete.json'),'snapshot':digest(collection/'snapshot/complete.json'),
            'reference':digest(reference/'complete.json')},
        'limitations':['Eligibility uses the existing seven-day, unfurnished, standard-lease, no-concession selection at the latest capture knowledge clock; it does not establish market coverage.',
            'Identity failures retain raw pages but do not supply canonical candidate rows.',
            'Unseen earlier current advertisements are not declared inactive.',
            'No new analytical cohort, model fit or main-model promotion occurs in this review.']}
    return publish_bundle(output,{'review.json':canonical(summary)+'\n',
        'verified-results.jsonl':''.join(canonical(r)+'\n' for r in inventory),
        'eligible.jsonl':''.join(canonical(r)+'\n' for r in selected),
        'eligibility-rejections.jsonl':''.join(canonical(r)+'\n' for r in rejected),
        Path(__file__).name:Path(__file__).read_text(),'candidate_search.py':Path(candidate_search.__file__).read_text()},
        {'version':VERSION,'summary':summary})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('collection','reference','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))['summary']))

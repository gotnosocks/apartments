"""Closed literal review of floor-relevant opposing elevator claims; no projection."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import duckdb

from apartments import attribute_evidence, bayesian_evidence, pricing
from apartments import reviewed_cohort_quarantine as quarantine
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models.rent_basis_price_review import own_event_review

VERSION = 'floor-relevant-access-conflict-review-v1'
SOURCE = Path('data/model/chelsea-reviewed-elevator-analysis-20260919')
DESCRIPTIONS = Path('data/model/chelsea-refreshed-bayesian-descriptions-20260918')
SUPPORT = Path('data/model/chelsea-reviewed-elevator-floor-support-20260919')
HISTORY = Path('data/exports/chelsea-historical-20260918-v4')
ARCHIVE = Path('/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1')
OUTPUT = Path('data/model/chelsea-floor-access-conflict-review-20260919')
REVIEWED_AT = '2026-09-19T11:24:42Z'
POSITIVE_ADS = {'1218638','1306285','1374305','1600856','1623996','1683383','1724746',
    '1749571','1792035','1849993','1959994','1980010','2005111','2102258','2138736',
    '2508409','2538342','3193768','3428430','3815436'}
NEGATIVE_ANCHORS = {'4912875','1359089','2573624','2022952','4714469','3038235','4067869'}
NOTES = {
 '142-west-17-street-new_york': 'Earlier positive claims include literal elevator copy; later descriptions explicitly say walk-up. No installation/removal date or building-wide truth is established.',
 '180-7-avenue-new_york': 'The positive advertisement describes one flight on the second floor. Stair access alone does not establish elevator absence. Preserve its original structured assertion and opposing walk-up evidence separately.',
 '222-west-16-street-new_york': 'Three positive advertisements reuse closely similar elevator/laundry copy while other descriptions explicitly say walk-up and laundry off-site. The positive copy also gives floor 9 for label 4H and floor 3 for label 6A. These are source/identity review signals, not verified replacement floors or independent confirmations.',
 '259-west-15-street-new_york': 'The lone positive advertisement literally says ELEVATOR and third floor; other advertisements describe three-flight walk-up duplexes. No extraction reversal or universal building value is justified.',
 '327-west-14-street-new_york': 'Positive text advertises elevator plus laundry; a later full-floor advertisement explicitly says no elevator. Preserve source identity and temporal ambiguity; do not infer removal.',
 '340-west-17-street-new_york': 'Positive claims include elevator copy and structured claims without that text. Advertisement 3193768 has structured address 340 but literal address 344, and a target matching a dollar-sign-free net quote. Recommend a separate gross-basis quarantine review; do not remap its unit or elevator by majority vote.',
 '350-west-18-street-new_york': 'The sole positive advertisement has no literal elevator statement. Walk-up descriptions occur both before and after it, including a 2023 fourth-floor case. One structured positive claim does not establish an installation date.',
}


def spans(text, pattern):
    return [{'start':m.start(),'end':m.end(),'literal':m.group()} for m in re.finditer(pattern,text,re.I)]


def price_recommendation(row, captures):
    if (str(row['source_listing_id']) != '3193768' or row['asking_rent'] != 2379
            or row['building'] != '340-west-17-street-new_york'):
        raise ValueError('Closed price review identity or target differs')
    evidence=[]
    for item in captures:
        capture,original=item['capture'],item['original']
        if (original['pricing']['price'] != 2379 or not original['events']['initial_event_matches_analytical_target']
                or original['listingAddress'] != '340 West 17th Street #2A'
                or original['raw_listing_sha256'] != capture['raw_listing_sha256']):
            raise ValueError('Original reviewed price/address evidence differs')
        text=capture['description']
        literals=['$2,595 monthly rent | Net monthly cost with 1-month free 2,379',
                  '344 West 17th Street']
        reviewed=[]
        for literal in literals:
            start=text.find(literal)
            if start<0:raise ValueError('Manually reviewed quote differs')
            reviewed.append({'start':start,'end':start+len(literal),'literal':literal})
        evidence.append({**capture,'spans':reviewed,'reviewed_original_pricing':original['pricing'],
            'initial_active_event_evidence':original['events']['initial_active_events'],
            'structured_listing_address':original['listingAddress']})
    decision={**{k:row[k] for k in ('audit_id','unit_id','source_listing_id')},
        'source_row_sha256':quarantine.sha(row),'reviewed_at':REVIEWED_AT,'reviewer':'codex',
        'action':'quarantine_unresolved_gross_price_basis','recommendation_only':True,
        'reason':'Both attached captures show $2,595 monthly rent and net monthly cost 2,379. '
            'The $2,379 analytical target matches captured price and the earliest own ACTIVE event. '
            'The later description does not establish an event-specific gross replacement. '
            'Structured 340 West 17th Street #2A also conflicts with literal 344 West 17th Street. '
            'Recommend exclusion from the gross-ask cohort; do not replace price, unit identity or elevator value.',
        'evidence':evidence}
    decision['decision_id']=quarantine.sha(decision)
    quarantine.validate_decision(row,decision,REVIEWED_AT)
    return decision


def run():
    bindings={str(p):digest(p/'complete.json') for p in (SOURCE,DESCRIPTIONS,SUPPORT,HISTORY)}
    sm,sf=_verified_bundle(SOURCE,retain={'observations.jsonl'})
    support_manifest,support_files=_verified_bundle(SUPPORT,retain={'support.json'})
    if support_manifest['dataset_manifest_sha256'] != bindings[str(SOURCE)]:raise ValueError('Support source differs')
    rows=[json.loads(line) for line in sf['observations.jsonl'].decode().splitlines()]
    opposing=set(json.loads(support_files['support.json'])['opposing_claim_building_sensitivity']['excluded_building_ids'])
    buildings={r['building'] for r in rows if r['building'] in opposing and pricing._normalize(r).get('listed_floor') is not None}
    if buildings != NOTES.keys():raise ValueError('Closed building inventory differs')
    building_rows=[r for r in rows if r['building'] in buildings]
    positive={str(r['source_listing_id']) for r in building_rows if r.get('elevator') is True}
    if positive != POSITIVE_ADS:raise ValueError('Closed positive advertisement inventory differs')
    selected=[r for r in building_rows if str(r['source_listing_id']) in POSITIVE_ADS|NEGATIVE_ANCHORS]
    if len(selected)!=27:raise ValueError('Reviewed case coverage differs')
    evidence=bayesian_evidence.load_evidence(SOURCE,DESCRIPTIONS)
    targets={}
    for row in selected:
        for capture in evidence[row['audit_id']]:
            identity=capture['capture_id']
            if type(identity) is not int or identity in targets:raise ValueError('Historical capture identity differs')
            targets[identity]=(row,capture)
    _,hf=_verified_bundle(HISTORY,retain={'source-files.json'})
    inventory=json.loads(hf['source-files.json']);found={};shards={}
    with duckdb.connect(config={'threads':'1','memory_limit':'300MB'}) as db:
        for relative,expected in sorted(inventory.items()):
            if not relative.startswith('listing_observations/') or not relative.endswith('.parquet'):continue
            path=ARCHIVE/relative
            if not path.resolve().is_relative_to(ARCHIVE.resolve()):raise ValueError('Invalid archive path')
            matches=db.execute('SELECT snapshot_id,raw_listing_json FROM read_parquet(?) WHERE snapshot_id IN (SELECT unnest(?))',
                [str(path),list(targets)]).fetchall()
            if not matches:continue
            if digest(path)!=expected:raise ValueError('Listing shard changed')
            er='event_mentions/'+path.name;ep=ARCHIVE/er
            if digest(ep)!=inventory[er]:raise ValueError('Event shard changed')
            shards[relative]=expected;shards[er]=inventory[er]
            cur=db.execute('SELECT * FROM read_parquet(?) WHERE snapshot_id IN (SELECT unnest(?)) ORDER BY snapshot_id,event_date,episode_index,event_index',
                [str(ep),[cid for cid,_ in matches]])
            names=[d[0] for d in cur.description];events=[dict(zip(names,r)) for r in cur.fetchall()]
            for identity,raw in matches:
                if identity in found:raise ValueError('Repeated raw capture')
                row,capture=targets[identity]
                if hashlib.sha256(raw.encode()).hexdigest()!=capture['raw_listing_sha256']:raise ValueError('Raw payload hash differs')
                payload=json.loads(raw)
                if str(payload['id'])!=row['source_listing_id']:raise ValueError('Raw ad differs')
                interpreted=deepcopy(payload);interpreted['description']=capture['description']
                extracted=attribute_evidence.extract_attribute_evidence(interpreted)
                claims=[c for c in extracted['evidence'] if c['attribute']=='elevator']
                for c in claims:
                    if c['source_path']=='/description' and capture['description'][c['start']:c['end']]!=c['literal']:
                        raise ValueError('Elevator claim span differs')
                found[identity]={'capture':capture,'original':{'raw_listing_sha256':capture['raw_listing_sha256'],
                    'listing_shard':relative,'listing_shard_sha256':expected,'event_shard':er,'event_shard_sha256':inventory[er],
                    **{k:payload.get(k) for k in ('listingAddress','buildingId','urlPath','pricing','propertyDetails')},
                    'events':own_event_review(row,identity,events)},
                    'elevator_replay':{'value':extracted['attributes']['elevator'],'claims':claims,
                        'conflicts':extracted['conflicts'].get('elevator',[])}}
    if found.keys()!=targets.keys():raise ValueError('Missing reviewed original capture')
    cases=[{'observation':r,'review':NOTES[r['building']],
            'selection':'all_positive_claims' if r['elevator'] is True else 'reviewed_negative_anchor',
            'captures':[found[c['capture_id']] for c in evidence[r['audit_id']]],'source_patch_applied':False}
           for r in selected]
    price_case=next(c for c in cases if c['observation']['source_listing_id']=='3193768')
    recommendation=price_recommendation(price_case['observation'],price_case['captures'])
    summary={'version':VERSION,'buildings':len(buildings),'building_history_rows':len(building_rows),
        'reviewed_observations':len(cases),'reviewed_captures':len(found),'positive_observations':len(positive),
        'negative_anchor_observations':len(NEGATIVE_ANCHORS),'gross_basis_quarantine_recommendations':1,
        'elevator_replay_transitions':dict(Counter(str(r['elevator'])+'->'+str(found[c['capture_id']]['elevator_replay']['value'])
            for r,c in targets.values())),
        'source_rows_changed':0,'main_selection_changed':False,'notes':NOTES,
        'limitations':['Closed review of all positive claims and one negative anchor per floor-relevant conflicting building; not all 42 conflicting buildings or all negative/unknown advertisements.',
            'Capture dates, historical price dates and interpretation dates remain distinct. Opposing reports do not establish physical access changes.',
            'Absence of elevator text is not absence of an elevator. Structured assertions and literal text remain separate.',
            'The gross-basis recommendation is exact-row and unapplied. No address, floor, elevator or price is inferred from majority claims or model residuals.']}
    for p,h in bindings.items():
        if digest(Path(p)/'complete.json')!=h:raise ValueError('Input bundle changed')
    for rel,h in shards.items():
        if digest(ARCHIVE/rel)!=h:raise ValueError('Original shard changed during review')
    publish_bundle(OUTPUT,{'summary.json':canonical(summary)+'\n',
        'cases.jsonl':''.join(canonical(c)+'\n' for c in cases),
        'recommendations.jsonl':canonical(recommendation)+'\n',
        Path(__file__).name:Path(__file__).read_text()},
        {'version':VERSION,'reviewed_at':REVIEWED_AT,'input_manifests':bindings,'original_shards':shards,
         'extractor_version':attribute_evidence.VERSION,'extractor_sha256':digest(attribute_evidence.__file__)})
    print(canonical(summary),flush=True)


if __name__=='__main__':run()

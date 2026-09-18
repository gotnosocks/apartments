"""Source-bound bathroom and alternative seed-phrase screen; no feature inference."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re

from apartments import granular_parse
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .interior_feature_audit import json_rows

VERSION = 'bathroom-research-evidence-v1'
PATTERNS = {
    'full_bath': r'\bfull\s+bath(?:room)?s?\b',
    'half_bath': r'\bhalf[ -]+bath(?:room)?s?\b|\b(?:1/2|½)\s*bath(?:room)?s?\b',
    'powder_room': r'\bpowder\s+rooms?\b',
    'ensuite': r'\ben[ -]?suite\b',
    'jack_and_jill': r'\bjack\s*(?:and|&)\s*jill\b',
    'bath_access': r'\b(?:shared|hall|hallway|guest|private|attached|adjoining)\s+bath(?:room)?s?\b',
    'bath_fixtures': r'\b(?:double|dual)\s+(?:sink|vanit)(?:s|y|ies)?\b|\b(?:separate|walk[ -]in|steam)\s+showers?\b|\bsoaking\s+tubs?\b',
    'split_bedrooms': r'\bsplit[ -]+bedrooms?\b|\bbedrooms?\s+(?:are\s+)?(?:at|on)\s+opposite\b',
    'railroad': r'\brailroad\b|\bwalk[ -]through\s+bedrooms?\b',
    'flex_layout': r'\bconvertible\b|\bflex\b|\bpressuri[sz]ed\s+walls?\b|\btemporary\s+walls?\b',
    'home_office': r'\bhome[ -]+office\b|\bwindowless\b|\bden\b',
    'privacy_noise': r'\bsoundproof\w*\b|\bnoise\b|\bquiet\b|\binterior[ -]+facing\b',
    'light_obstruction': r'\b(?:open|unobstructed|protected)\s+(?:city\s+)?views?\b|\bobstruct\w*\b|\bair\s+shaft\b',
}


def screen(text):
    if not text:
        return []
    results = []
    for family, pattern in PATTERNS.items():
        for m in re.finditer(pattern, text, re.I):
            start, end = max(0, m.start()-130), min(len(text), m.end()+170)
            context = text[start:end]
            flags = []
            for flag, expression in {
                'building_or_shared_context': r'\b(?:building|amenit\w*|residents|shared|lounge|fitness|gym)\b',
                'planned_or_conditional': r'\b(?:can be|could|potential|planned|will be|convertible|convert|flex)\b',
                'negative_or_exclusion_wording': r'\b(?:not|no|without|except|excluding)\b',
                'non_bath_ensuite_context': r'\ben[ -]?suite\s+(?:laundry|washer|dryer|kitchen|office)\b',
            }.items():
                if re.search(expression, context, re.I): flags.append(flag)
            results.append({'family': family, 'start': m.start(), 'end': m.end(), 'literal': m.group(),
                            'context_start': start, 'context_end': end, 'context': context, 'flags': flags})
    return sorted(results, key=lambda r: (r['start'], r['family']))


def reported_bathrooms(payload):
    details = payload.get('propertyDetails') or {}
    return {name: {'present': name in details, 'value': details.get(name)}
            for name in ('fullBathroomCount', 'halfBathroomCount', 'bathroomCount')}


def valid_count(field):
    value = field['value']
    return field['present'] and isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 and value == int(value)


def consensus(captures):
    pairs = {(r['bathroom_fields']['fullBathroomCount']['value'], r['bathroom_fields']['halfBathroomCount']['value'])
             for r in captures if all(valid_count(r['bathroom_fields'][k]) for k in ('fullBathroomCount', 'halfBathroomCount'))}
    complete = all(all(valid_count(r['bathroom_fields'][k]) for k in ('fullBathroomCount', 'halfBathroomCount')) for r in captures)
    if complete and len(pairs) == 1:
        full, half = next(iter(pairs))
        return {'status': 'consistent_explicit_counts', 'reported_full_bathrooms': full, 'reported_half_bathrooms': half}
    return {'status': 'conflicting_reported_counts' if len(pairs)>1 else 'incomplete_explicit_counts',
            'reported_full_bathrooms': None, 'reported_half_bathrooms': None}


def run(dataset, descriptions, archive, historical, refresh, output):
    import duckdb
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, ef = _verified_bundle(descriptions, retain={'evidence.jsonl'})
    hm, hf = _verified_bundle(historical, retain={'source-files.json'})
    if em.get('dataset_manifest') != dm or em.get('historical_manifest') != hm:
        raise ValueError('Description archive does not bind dataset or historical inventory')
    rows = json_rows(df['observations.jsonl']); by_id = {r['audit_id']: r for r in rows}
    evidence = json_rows(ef['evidence.jsonl'])
    if len(by_id) != len(rows) or {e['audit_id'] for e in evidence} != set(by_id):
        raise ValueError('Invalid cohort membership')
    by_capture = {}
    for e in evidence:
        r = by_id[e['audit_id']]
        if any(str(e[k]) != str(r[k]) for k in ('source_listing_id', 'canonical_unit_url', 'unit_id')):
            raise ValueError('Description identity mismatch')
        key = e['capture_id']
        if key in by_capture: raise ValueError('Duplicate capture identity')
        by_capture[key] = e
        if e['description'] is not None and hashlib.sha256(e['description'].encode()).hexdigest() != e['description_sha256']:
            raise ValueError('Description hash mismatch')
    inventory = json.loads(hf['source-files.json']); archive = Path(archive)
    paths = [archive / p for p in inventory if p.startswith('listing_observations/') and p.endswith('.parquet')]
    if not paths: raise ValueError('Missing source table')
    for p in paths:
        if not p.resolve().is_relative_to(archive.resolve()) or digest(p) != inventory[str(p.relative_to(archive))]:
            raise ValueError('Source shard hash mismatch')
    output_captures = []; seen = set(); field_inventory = Counter()
    def consume(capture, listing, url, raw):
        e = by_capture[capture]
        if capture in seen or str(listing) != e['source_listing_id'] or url != e['canonical_unit_url'] or hashlib.sha256(raw.encode()).hexdigest() != e['raw_listing_sha256']:
            raise ValueError('Raw source identity or hash mismatch')
        seen.add(capture); payload = json.loads(raw)
        def walk(value, path=''):
            if isinstance(value, dict):
                for key, val in value.items():
                    child = path + '/' + key
                    if 'bath' in key.lower(): field_inventory[child] += 1
                    walk(val, child)
            elif isinstance(value, list):
                for val in value: walk(val, path+'/*')
        walk(payload)
        output_captures.append({**e, 'bathroom_fields': reported_bathrooms(payload), 'findings': screen(e['description'])})
    historical_ids = [c for c,e in by_capture.items() if e['analysis_price_basis'] == 'historical_initial_own_advertisement_ask']
    with duckdb.connect(config={'threads':'2','memory_limit':'1GB'}) as db:
        db.read_parquet([str(p) for p in paths]).create_view('source')
        result = db.execute('SELECT snapshot_id, listing_id, canonical_unit_url, raw_listing_json FROM source WHERE snapshot_id IN (SELECT unnest(?)) ORDER BY snapshot_id', [historical_ids])
        while batch := result.fetchmany(128):
            for args in batch: consume(*args)
    for e in evidence:
        if e['analysis_price_basis'] != 'current_capture_gross_ask': continue
        r = by_id[e['audit_id']]; provenance = r['refresh_provenance']; sha = e['body_sha256']
        if provenance['body_sha256'] != sha: raise ValueError('Current source mismatch')
        body = gzip.decompress((Path(refresh)/'archive/bodies'/sha[:2]/(sha+'.gz')).read_bytes())
        if hashlib.sha256(body).hexdigest() != sha: raise ValueError('Current body hash mismatch')
        parsed,_ = granular_parse.parse_listing(body, provenance['requested_url'])
        consume(e['capture_id'], parsed['listing_id'], parsed['canonical_unit_url'], parsed['raw_listing_json'])
    if seen != set(by_capture): raise ValueError('Missing raw source captures')
    output_captures.sort(key=lambda e: (e['audit_id'], str(e['capture_id'])))
    grouped = defaultdict(list); features = defaultdict(set); flags = defaultdict(set)
    for e in output_captures:
        grouped[e['audit_id']].append(e)
        for f in e['findings']:
            features[f['family']].add(e['audit_id'])
            for flag in f['flags']: flags[flag].add(e['audit_id'])
    projections = []; pairs = Counter(); status = Counter(); differences = []
    for audit_id, captures in sorted(grouped.items()):
        row = by_id[audit_id]; result = consensus(captures); status[result['status']] += 1
        if result['status'] == 'consistent_explicit_counts':
            full, half = result['reported_full_bathrooms'], result['reported_half_bathrooms']
            pairs[(row['bedrooms'], full, half)] += 1
            if full+.5*half != row['bathrooms']: differences.append(audit_id)
        projections.append({'audit_id':audit_id,'unit_id':row['unit_id'],'building_id':row['building'],
                            'source_listing_id':row['source_listing_id'],'bedrooms':row['bedrooms'],
                            'analysis_bathrooms':row['bathrooms'],**result,'capture_ids':[c['capture_id'] for c in captures]})
    support = {family: {'candidate_rows':len(ids),'units':len({by_id[i]['unit_id'] for i in ids}),
                       'buildings':len({by_id[i]['building'] for i in ids})} for family,ids in sorted(features.items())}
    samples = []
    for family in PATTERNS:
        candidates = [e for e in output_captures if any(f['family']==family for f in e['findings'])]
        candidates.sort(key=lambda e: hashlib.sha256((family+e['audit_id']+str(e['capture_id'])).encode()).hexdigest())
        units = set()
        for e in candidates:
            if e['unit_id'] in units: continue
            units.add(e['unit_id']); samples.append({k:v for k,v in e.items() if k not in ('description','findings')} | {'family':family,'findings':[f for f in e['findings'] if f['family']==family]})
            if len(units) == 5: break
    summary = {'version':VERSION,'rows':len(rows),'captures':len(evidence),'explicit_count_status':dict(status),
               'source_field_capture_inventory':dict(sorted(field_inventory.items())),
               'bed_full_half_support':[{'bedrooms':b,'full':f,'half':h,'rows':n} for (b,f,h),n in sorted(pairs.items())],
               'scalar_disagreement_audit_ids':differences,'phrase_support':support,'advisory_flag_rows':{k:len(v) for k,v in sorted(flags.items())},
               'policy':'Reported counts remain source claims. Phrase hits are review candidates, not model features; absence is unknown. Never derive full/half from scalar bathrooms. Same-advertisement capture does not establish historical validity.'}
    lines = ['# Bathroom and alternative seed-phrase evidence audit','',f'{len(rows):,} fitted rows; {len(evidence):,} verified captures.','',canonical(dict(status)),'',summary['policy'],'','| Phrase family | Rows | Units | Buildings |','|---|---:|---:|---:|']
    lines += [f"| {k} | {v['candidate_rows']} | {v['units']} | {v['buildings']} |" for k,v in support.items()]
    return publish_bundle(output, {'captures.jsonl':''.join(canonical(e)+'\n' for e in output_captures),
        'reported-counts.jsonl':''.join(canonical(e)+'\n' for e in projections),
        'review-sample.jsonl':''.join(canonical(e)+'\n' for e in samples),'summary.json':canonical(summary)+'\n',
        'report.md':'\n'.join(lines)+'\n','audit.py':Path(__file__).read_text()},
        {'version':VERSION,'dataset_manifest':dm,'description_manifest':em,'historical_manifest':hm,'summary':summary,
         'implementation_sha256':{p.name:digest(p) for p in (Path(__file__),Path(granular_parse.__file__))}})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','descriptions','archive','historical','refresh','output'): parser.add_argument('--'+key,type=Path,required=True)
    print(canonical(run(**vars(parser.parse_args()))['summary']))

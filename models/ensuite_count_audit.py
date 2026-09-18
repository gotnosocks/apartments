"""Source-bound en-suite count research screen; no physical attribute inference."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
from pathlib import Path
import re

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from .interior_feature_audit import json_rows

VERSION='ensuite-count-research-screen-v2'
ENSUITE=r'\ben[ -]?suite\b'
PATTERNS={
 'numeric_phrase':r'\b(?:one|two|three|four|five|six|\d+)\b[^.!?\n]{0,75}'+ENSUITE,
 'distributed_access':r'\b(?:both|each|every|all)\b[^.!?\n]{0,150}\b(?:en[ -]?suite|bath(?:room)?s?)\b',
 'primary_access':r'\b(?:primary|master)\b[^.!?\n]{0,120}'+ENSUITE,
 'hall_guest_access':r'\b(?:hall|hallway|guest|shared)\s+(?:full\s+)?bath(?:room)?s?\b',
 'negated_ensuite':r'\b(?:no|not|without)\b[^.!?\n]{0,55}'+ENSUITE,
 'planned_ensuite':r'\b(?:can|could|potential|convert\w*|future|planned|proposed)\b[^.!?\n]{0,180}'+ENSUITE,
 'ambiguous_subject':ENSUITE+r'\s+(?:(?:primary|master)\s+)?(?:bedrooms?|laundry|washer|dryer|kitchen|office)\b',
}
STRATA=[('ambiguous_or_conditional',('negated_ensuite','planned_ensuite','ambiguous_subject')),
        ('numeric_phrase',('numeric_phrase',)),('distributed_access',('distributed_access',)),
        ('primary_access',('primary_access',)),('hall_guest_access',('hall_guest_access',))]
SEED='ensuite-count-independent-review-v1'


def screen(description):
    if not description:return []
    result=[]
    for family,pattern in PATTERNS.items():
        for m in re.finditer(pattern,description,re.I):
            start=max(0,m.start()-160);end=min(len(description),m.end()+300)
            result.append({'family':family,'start':m.start(),'end':m.end(),'literal':m.group(),
                'context_start':start,'context_end':end,'context':description[start:end]})
    return sorted(result,key=lambda r:(r['start'],r['family']))


def select(candidates,excluded_units,per_stratum=6):
    seen=set(excluded_units);selected=[]
    for stratum,families in STRATA:
        options=[c for c in candidates if any(f['family'] in families for f in c['count_candidates'])]
        options.sort(key=lambda c:hashlib.sha256((SEED+stratum+c['audit_id']+str(c['capture_id'])).encode()).hexdigest())
        count=0
        for c in options:
            if c['unit_id'] in seen:continue
            seen.add(c['unit_id']);selected.append({**c,'selection_stratum':stratum});count+=1
            if count==per_stratum:break
        if count!=per_stratum:raise ValueError('Insufficient distinct-unit stratum support: '+stratum)
    return selected


def run(descriptions,bathroom_audit,prior_review,output):
    dm,df=_verified_bundle(descriptions,retain={'evidence.jsonl'})
    bm,bf=_verified_bundle(bathroom_audit,retain={'captures.jsonl','reported-counts.jsonl'})
    pm,pf=_verified_bundle(prior_review,retain={'review.jsonl'})
    if bm.get('description_manifest')!=dm or pm.get('audit_manifest')!=bm:raise ValueError('Source lineage mismatch')
    descriptions_rows=json_rows(df['evidence.jsonl']);bath_captures=json_rows(bf['captures.jsonl'])
    bath_by_key={(c['audit_id'],c['capture_id']):c for c in bath_captures}
    if len(bath_by_key)!=len(bath_captures):raise ValueError('Duplicate bathroom source capture')
    by_audit={r['audit_id']:r for r in json_rows(bf['reported-counts.jsonl'])}
    prior=json_rows(pf['review.jsonl']);excluded={r['unit_id'] for r in prior}
    candidates=[];family_rows=defaultdict(set);seen=set()
    for c in descriptions_rows:
        key=(c['audit_id'],c['capture_id']);b=bath_by_key.get(key)
        if key in seen or b is None:raise ValueError('Duplicate or unmatched description capture')
        seen.add(key)
        if any(c[k]!=b[k] for k in ('unit_id','source_listing_id','canonical_unit_url','description_sha256','description','raw_listing_sha256','body_sha256')):
            raise ValueError('Capture source identity/hash mismatch')
        text=c['description']
        if text is not None and hashlib.sha256(text.encode()).hexdigest()!=c['description_sha256']:raise ValueError('Description hash mismatch')
        findings=screen(text)
        if findings:
            r=by_audit[c['audit_id']]
            candidates.append({**c,'bathroom_fields':b['bathroom_fields'],
              'reported_count_consensus':{k:r[k] for k in ('bedrooms','analysis_bathrooms','reported_full_bathrooms','reported_half_bathrooms','status')},
              'count_candidates':findings,'status':'unreviewed_count_candidate_not_model_attribute'})
            for f in findings:family_rows[f['family']].add(c['audit_id'])
    if seen!=set(bath_by_key):raise ValueError('Incomplete description inventory')
    candidates.sort(key=lambda c:(c['audit_id'],str(c['capture_id'])))
    sample=select(candidates,excluded)
    summary={'source_rows':len(by_audit),'source_captures':len(seen),'candidate_rows':len({c['audit_id'] for c in candidates}),
      'candidate_captures':len(candidates),'family_candidate_rows':{k:len(family_rows[k]) for k in PATTERNS},
      'review_cases':len(sample),'excluded_prior_review_units':len(excluded),
      'selection':{'seed':SEED,'distinct_units_per_stratum':6,'strata':[[name,list(families)] for name,families in STRATA]},
      'policy':'Candidates only. Numeric/distributed wording is not an exact count. Unmentioned is unknown; no physical feature promotion.'}
    return publish_bundle(output,{'candidates.jsonl':''.join(canonical(c)+'\n' for c in candidates),
      'review-sample.jsonl':''.join(canonical(c)+'\n' for c in sample),'summary.json':canonical(summary)+'\n','audit.py':Path(__file__).read_text()},
      {'version':VERSION,'description_manifest':dm,'bathroom_audit_manifest':bm,'prior_review_manifest':pm,
       'summary':summary,'implementation_sha256':{Path(__file__).name:digest(Path(__file__))}})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('descriptions','bathroom-audit','prior-review','output'):p.add_argument('--'+name,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))['summary']))

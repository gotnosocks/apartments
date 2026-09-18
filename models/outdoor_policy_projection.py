"""Keep the cohort fixed while requiring explicit private-type text corroboration."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from datetime import datetime,UTC
from pathlib import Path

from apartments import outdoor_corroboration,outdoor_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle,digest,publish_bundle
from .outdoor_experiment import records

VERSION='private-outdoor-corroboration-policy-v1'


def run(structured_dataset,evidence,output):
    dm,df=_verified_bundle(structured_dataset,retain={'observations.jsonl'})
    em,ef=_verified_bundle(evidence,retain={'evidence.jsonl'})
    if dm.get('dataset_version')!='advertised-outdoor-types-v1' or dm['outdoor_audit_manifest']!=em:
        raise ValueError('Structured projection and outdoor evidence do not bind')
    grouped=defaultdict(list)
    for capture in records(ef['evidence.jsonl']):grouped[capture['audit_id']].append(capture)
    rows=records(df['observations.jsonl']);enriched=[];decisions=[]
    for row in rows:
        captures=grouped.get(row['audit_id'],[])
        allowed=set(row.get('capture_ids') or [])|{row.get('capture_id')}
        for c in captures:
            if c['unit_id']!=row['unit_id'] or c['source_listing_id']!=str(row['source_listing_id']) or c['capture_id'] not in allowed:
                raise ValueError('Corroboration capture identity mismatch')
        result=outdoor_corroboration.corroborate(captures)
        codes=result['private_types']
        original=row['private_outdoor_category']
        asserted={a['value'] for c in captures for a in c['extraction']['assertions'] if a['attribute']=='private_type'}
        if not set(codes)<=asserted:
            raise ValueError('Corroboration cannot invent a structured private type')
        value='+'.join(sorted(codes)) if codes else None
        enriched.append({**row,'structured_private_outdoor_category':original,'private_outdoor_category':value})
        if captures:decisions.append({'audit_id':row['audit_id'],'source_listing_id':str(row['source_listing_id']),
            'structured_private_outdoor_category':original,'structured_category_unresolved':original is None,
            'private_outdoor_category':value,**result})
    support={'known_private_rows':sum(r['private_outdoor_category'] is not None for r in enriched),
        'structured_known_private_rows':sum(r['structured_private_outdoor_category'] is not None for r in enriched),
        'categories':dict(sorted(Counter(r['private_outdoor_category'] for r in enriched if r['private_outdoor_category'] is not None).items())),
        'shared_policy':'Unchanged structured shared categories.',
        'interpretation':'Corroborated types are positive claims, not an exhaustive inventory. Missing corroboration does not imply physical absence.'}
    previous=_verified_bundle(output)[0] if (Path(output)/'complete.json').exists() else None
    interpreted_at=previous['interpreted_at'] if previous else datetime.now(UTC).isoformat()
    paths=[Path(__file__),Path(outdoor_corroboration.__file__),Path(outdoor_evidence.__file__)]
    return publish_bundle(output,{'observations.jsonl':''.join(canonical(r)+'\n' for r in enriched),
        'decisions.jsonl':''.join(canonical(r)+'\n' for r in decisions),'support.json':canonical(support)+'\n',
        **{p.name:p.read_text() for p in paths}},
        {**{k:v for k,v in dm.items() if k not in ('files','interpreted_at','implementation_sha256','interpretation')},
         'structured_projection_manifest':dm,'policy_version':VERSION,'interpreted_at':interpreted_at,'support':support,
         'interpretation':support['interpretation'],'implementation_sha256':{p.name:digest(p) for p in paths}})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('structured-dataset','evidence','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();result=run(args.structured_dataset,args.evidence,args.output)
    print(canonical(result['support']))

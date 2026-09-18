"""Expose explicitly reported full/half counts without repairing source claims."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from .bathroom_evidence_audit import valid_count
from .interior_feature_audit import json_rows

VERSION = 'reported-bathroom-counts-projection-v1'


def field_consensus(captures, name):
    fields = [c['bathroom_fields'][name] for c in captures]
    values = {f['value'] for f in fields if valid_count(f)}
    if len(values)>1: return None, 'conflicting_capture_values'
    if not fields or not all(valid_count(f) for f in fields): return None, 'missing_or_invalid_capture_value'
    return next(iter(values)), 'consistent_explicit_count'


def project(row, captures):
    result = dict(row)
    full, fs = field_consensus(captures,'fullBathroomCount')
    half, hs = field_consensus(captures,'halfBathroomCount')
    flags=[]
    if full is not None and full == 0: flags.append('reported_no_full_bathroom_review_required')
    if half is not None and half > 1: flags.append('multiple_reported_half_bathrooms_review_required')
    if full is not None and half is not None and full+.5*half != row['bathrooms']:
        flags.append('reported_counts_disagree_with_analytical_scalar')
    result.update(reported_full_bathrooms=full, reported_half_bathrooms=half,
                  bathroom_count_evidence={'version':VERSION,'full_status':fs,'half_status':hs,
                      'flags':flags,'capture_ids':[c['capture_id'] for c in captures],
                      'meaning':'Explicit source reports, not verified physical counts; flags require review; missing is unknown, never zero.'})
    return result


def run(dataset, audit, output):
    dm, df = _verified_bundle(dataset,retain={'observations.jsonl'})
    am, af = _verified_bundle(audit,retain={'captures.jsonl'})
    if am.get('dataset_manifest') != dm: raise ValueError('Audit dataset binding mismatch')
    rows=json_rows(df['observations.jsonl']); captures=json_rows(af['captures.jsonl']); grouped=defaultdict(list)
    by_id={r['audit_id']:r for r in rows}
    if len(by_id)!=len(rows): raise ValueError('Duplicate cohort identity')
    seen=set()
    for c in captures:
        r=by_id.get(c['audit_id'])
        if r is None or any(str(c[k])!=str(r[k]) for k in ('unit_id','source_listing_id','canonical_unit_url')):
            raise ValueError('Capture identity mismatch')
        if c['capture_id'] in seen: raise ValueError('Duplicate capture identity')
        seen.add(c['capture_id']); grouped[c['audit_id']].append(c)
    if set(grouped)!=set(by_id): raise ValueError('Incomplete cohort coverage')
    results=[project(r,grouped[r['audit_id']]) for r in rows]
    flags=Counter(f for r in results for f in r['bathroom_count_evidence']['flags'])
    summary={'rows':len(results),'known_full_rows':sum(r['reported_full_bathrooms'] is not None for r in results),
             'known_half_rows':sum(r['reported_half_bathrooms'] is not None for r in results),
             'flagged_rows':sum(bool(r['bathroom_count_evidence']['flags']) for r in results),'flags':dict(flags),
             'unchanged_source_fields':True,'policy':'No corrections, exclusions, scalar reconstruction, or text inference. Reported counts are not verified physical counts. Review source-quality flags before fitting.'}
    return publish_bundle(output,{'observations.jsonl':''.join(canonical(r)+'\n' for r in results),
        'summary.json':canonical(summary)+'\n','projection.py':Path(__file__).read_text()},
        {'version':VERSION,'dataset_manifest':dm,'audit_manifest':am,'summary':summary,
         'implementation_sha256':{Path(__file__).name:digest(Path(__file__))}})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('dataset','audit','output'):p.add_argument('--'+key,type=Path,required=True)
    print(canonical(run(**vars(p.parse_args()))['summary']))

"""Apply source-bound scope quarantines and composition masks without repairing values."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical, instant
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'reviewed-scope-composition-projection-v2'
DECISION_VERSION = 'source-reviewed-scope-composition-decisions-v1'
SOURCE_VERSION = 'reviewed-bathroom-counts-projection-v1'
IDENTITY = ('audit_id', 'source_listing_id', 'unit_id', 'canonical_unit_url')
ACTIONS = {'quarantine_nonresidential', 'quarantine_location_conflict', 'mask_bathroom_composition'}
MASK_FLAG = 'reviewed_bathroom_composition_conflict'


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rows(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def validate_decision(row, decision, captures):
    if (decision.get('action') not in ACTIONS or not isinstance(decision.get('reason'), str)
            or not decision['reason'].strip()):
        raise ValueError('Unknown action or missing review reason')
    if (decision.get('decision_id') != sha({k:v for k,v in decision.items() if k != 'decision_id'})
            or decision.get('source_projection_row_sha256') != sha(row)
            or any(str(decision.get(k)) != str(row.get(k)) for k in IDENTITY)):
        raise ValueError('Decision identity or source row binding mismatch')
    interpreted = instant(decision['interpreted_at'])
    if interpreted < instant(row['known_at']):
        raise ValueError('Review predates source knowledge')
    evidence = decision.get('evidence')
    expected = {str(c) for c in row['bathroom_count_evidence']['capture_ids']}
    if (not isinstance(evidence, list) or not evidence
            or len({str(e['capture_id']) for e in evidence}) != len(evidence)
            or {str(e['capture_id']) for e in evidence} != expected):
        raise ValueError('Every exact advertisement capture must be reviewed once')
    for e in evidence:
        original = captures.get((row['audit_id'], str(e['capture_id'])))
        if original is None:
            raise ValueError('Evidence capture absent from verified source audit')
        for key in (*IDENTITY, 'body_sha256', 'raw_listing_sha256', 'description_sha256',
                    'description', 'source_collected_at', 'known_at'):
            if e.get(key) != original.get(key):
                raise ValueError('Evidence differs from audited capture: '+key)
        if any(str(e.get(k)) != str(row.get(k)) for k in IDENTITY):
            raise ValueError('Evidence belongs to a different advertisement or unit')
        text = e['description']
        if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != e['description_sha256']:
            raise ValueError('Description hash mismatch')
        if interpreted < max(instant(e['known_at']), instant(e['source_collected_at'])):
            raise ValueError('Review predates capture knowledge')
        spans = e.get('spans')
        if not isinstance(spans, list) or not spans:
            raise ValueError('Literal review evidence required')
        for span in spans:
            start, end = span.get('start'), span.get('end')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or text[start:end] != span.get('literal')):
                raise ValueError('Invalid source evidence span')


def apply_decision(row, decision, captures):
    validate_decision(row, decision, captures)
    if decision['action'].startswith('quarantine_'):
        return None
    result = deepcopy(row)
    evidence = result['bathroom_count_evidence']
    if MASK_FLAG not in evidence['flags']:
        evidence['flags'].append(MASK_FLAG)
    evidence['composition_status'] = 'reviewed_composition_conflict_unknown'
    history = result.setdefault('research_review_history', [])
    if not isinstance(history, list) or any(h.get('decision_id') == decision['decision_id'] for h in history):
        raise ValueError('Invalid or already applied review history')
    history.append({'decision_id':decision['decision_id'], 'action':decision['action'],
                    'reason':decision['reason'], 'interpreted_at':decision['interpreted_at'],
                    'source_projection_row_sha256':decision['source_projection_row_sha256'],
                    'before_bathroom_count_evidence':deepcopy(row['bathroom_count_evidence'])})
    if any(result.get(k) != v for k,v in row.items() if k not in {'bathroom_count_evidence','research_review_history'}):
        raise ValueError('Original analytical field changed')
    return result


def run(projection, decisions, audit, output):
    projection, decisions, audit = map(Path, (projection, decisions, audit))
    pm,pf = _verified_bundle(projection, retain={'observations.jsonl'})
    dm,df = _verified_bundle(decisions, retain={'decisions.jsonl'})
    am,_ = _verified_bundle(audit, retain=set())
    if (pm.get('version') != SOURCE_VERSION or dm.get('version') != DECISION_VERSION
            or dm.get('source_manifest_sha256') != digest(projection/'complete.json')
            or dm.get('source_observations_sha256') != pm['files']['observations.jsonl']
            or dm.get('audit_manifest_sha256') != digest(audit/'complete.json')):
        raise ValueError('Review/source/audit lineage mismatch')
    source = rows(pf['observations.jsonl']); edits = rows(df['decisions.jsonl'])
    by_id = {d['audit_id']:d for d in edits}
    if (len(by_id) != len(edits) or len({r['audit_id'] for r in source}) != len(source)
            or not set(by_id) <= {r['audit_id'] for r in source}):
        raise ValueError('Duplicate or unknown review identity')
    captures = {}
    with (audit/'captures.jsonl').open() as stream:
        for line in stream:
            if not line.strip():
                continue
            capture = json.loads(line)
            if capture['audit_id'] in by_id:
                key = (capture['audit_id'],str(capture['capture_id']))
                if key in captures:
                    raise ValueError('Duplicate audited capture')
                captures[key] = capture
    if digest(audit/'captures.jsonl') != am['files']['captures.jsonl']:
        raise ValueError('Source audit changed during review')
    kept,quarantined,changes = [],[],[]
    for row in source:
        decision = by_id.get(row['audit_id'])
        if decision is None:
            kept.append(row)
            continue
        result = apply_decision(row, decision, captures)
        if result is None:
            quarantined.append({'observation':row, 'decision_id':decision['decision_id'],
                'action':decision['action'], 'reason':decision['reason'], 'interpreted_at':decision['interpreted_at']})
        else:
            kept.append(result)
        changes.append({'audit_id':row['audit_id'], 'source_listing_id':row['source_listing_id'],
            'decision_id':decision['decision_id'], 'action':decision['action'],
            'before_bathroom_count_evidence':row['bathroom_count_evidence'],
            'after_bathroom_count_evidence':result['bathroom_count_evidence'] if result is not None else None})
    current = lambda rr: {r['audit_id'] for r in rr if r.get('analysis_price_basis') == 'current_capture_gross_ask'}
    if current(source) != current(kept):
        raise ValueError('This research overlay must preserve the refreshed current cohort')
    info = {'source_rows':len(source), 'rows':len(kept), 'quarantined_rows':len(quarantined),
        'masked_rows':sum(d['action']=='mask_bathroom_composition' for d in edits),
        'action_counts':dict(sorted(Counter(d['action'] for d in edits).items())),
        'current_rows':len(current(kept)), 'original_retained_counts_prices_and_analytical_fields_preserved':True,
        'policy':'Named advertisements only. No numeric repairs, inferred addresses, physical change dates or propagation to other advertisements. Quarantined observations retained separately.'}
    files = {'observations.jsonl':''.join(canonical(r)+'\n' for r in kept),
        'quarantined.jsonl':''.join(canonical(r)+'\n' for r in quarantined),
        'changes.jsonl':''.join(canonical(r)+'\n' for r in changes),
        'decisions.jsonl':df['decisions.jsonl'].decode(), 'summary.json':canonical(info)+'\n',
        'research_scope_overlay.py':Path(__file__).read_text()}
    return publish_bundle(output, files, {'version':VERSION, 'source_manifest':pm,
        'source_manifest_sha256':digest(projection/'complete.json'), 'decisions_manifest':dm,
        'audit_manifest_sha256':digest(audit/'complete.json'), 'summary':info,
        'implementation_sha256':digest(__file__)})


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('projection','decisions','audit','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    print(canonical(run(**vars(args))['summary']))

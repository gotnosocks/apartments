"""Preserve literal witnesses for the sparse floor/elevator interaction tail."""
import json
from pathlib import Path

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

SOURCE = Path('data/model/chelsea-reviewed-elevator-analysis-20260919')
DESCRIPTIONS = Path('data/model/chelsea-refreshed-bayesian-descriptions-20260918')
SUPPORT = Path('data/model/chelsea-reviewed-elevator-floor-support-20260919')
POLICY = {
    '2094316': (6., 'located on the 6th floor', 'Retain the literal advertised sixth-floor claim; the description also explicitly calls the building a walk-up. Other advertisements in this building contain opposing elevator claims, so this case cannot independently adjudicate building access.'),
    '2300836': (6., 'on the 6th floor of a walk-up building', 'Retain the literal advertised sixth-floor and walk-up claims. One unit is not independent evidence for a general upper-floor walk-up premium.'),
    '4582906': (4., 'located on the 4th floor of this elevator building', 'Unresolved floor/identity conflict with advertisement 4930926 in the same source unit. Literal source claim is fourth floor; no physical move or replacement floor is inferred.'),
    '4930926': (6., 'located on the 6th floor of this elevator building', 'Unresolved floor/identity conflict with advertisement 4582906 in the same source unit. Literal source claim is sixth floor; bedroom count also changes from one to three. No physical move or replacement floor is inferred.'),
}


def run():
    manifest, files = _verified_bundle(SOURCE, retain={'observations.jsonl'})
    support_manifest, support_files = _verified_bundle(SUPPORT, retain={'support.json', 'explicit-observations.jsonl'})
    if support_manifest['dataset_manifest_sha256'] != digest(SOURCE/'complete.json'):
        raise ValueError('Interaction support belongs to another source')
    rows = [json.loads(line) for line in files['observations.jsonl'].decode().split('\n') if line]
    evidence = load_evidence(SOURCE, DESCRIPTIONS)
    selected = [r for r in rows if str(r['source_listing_id']) in POLICY]
    if len(selected) != 4 or {str(r['source_listing_id']) for r in selected} != POLICY.keys():
        raise ValueError('Reviewed advertisement inventory differs')
    cases = []
    for row in selected:
        floor, phrase, decision = POLICY[str(row['source_listing_id'])]
        if row['advertised_floor'] != floor:
            raise ValueError('Reviewed advertised floor differs')
        captures = []
        for capture in evidence[row['audit_id']]:
            text = capture['description'] or ''
            start = text.find(phrase)
            if start < 0: raise ValueError('Missing reviewed literal floor claim')
            captures.append({**capture, 'reviewed_span': {'start': start, 'end': start+len(phrase), 'literal': phrase}})
        cases.append({'observation': row, 'captures': captures, 'review': decision,
                      'source_patch_applied': False})
    conflict = [r for r in selected if str(r['source_listing_id']) in ('4582906', '4930926')]
    if len({r['unit_id'] for r in conflict}) != 1:
        raise ValueError('Previously reviewed source unit identity changed')
    summary = {'version': 'floor-interaction-witness-review-v1', 'observations': len(cases),
        'captures': sum(len(r['captures']) for r in cases),
        'interpretation': 'Literal source review only. Advertised floor is not verified physical height. The two source floor claims within one unit remain conflicting evidence, not useful repeated-unit treatment variation. No source edits or model changes.'}
    publish_bundle(Path('data/model/chelsea-floor-interaction-witness-review-20260919'),
        {'cases.jsonl': ''.join(canonical(r)+'\n' for r in cases), 'summary.json': canonical(summary)+'\n',
         Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'dataset_manifest_sha256': digest(SOURCE/'complete.json'),
         'description_manifest_sha256': digest(DESCRIPTIONS/'complete.json'),
         'support_manifest_sha256': digest(SUPPORT/'complete.json')})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    run()

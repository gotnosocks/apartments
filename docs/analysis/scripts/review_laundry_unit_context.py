"""Preserve same-unit context without inferring physical renovation dates."""
import json
from pathlib import Path

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run():
    base = Path(__file__).resolve().parents[3]/'data/model'
    source = base/'chelsea-reviewed-floor-masked-analysis-20260918'
    descriptions = base/'chelsea-refreshed-bayesian-descriptions-20260918'
    reviewed = base/'chelsea-laundry-dominant-building-source-review-20260919'
    _, files = _verified_bundle(source, retain={'observations.jsonl'})
    _, rf = _verified_bundle(reviewed, retain={'decisions.jsonl'})
    chosen = {'3223153', '2675026', '970866'}
    decisions = [json.loads(s) for s in rf['decisions.jsonl'].decode().split('\n') if s]
    units = {r['unit_id'] for r in decisions if r['source_listing_id'] in chosen}
    if len(units) != 3: raise ValueError('Reviewed context units changed')
    rows = [r for r in (json.loads(s) for s in files['observations.jsonl'].decode().split('\n') if s) if r['unit_id'] in units]
    evidence = load_evidence(source, descriptions)
    rows.sort(key=lambda r: (r['unit_id'], r['period'], r['audit_id']))
    context = [{'source_record': row, 'captures': evidence[row['audit_id']]} for row in rows]
    result = {'version': 'laundry-reviewed-unit-context-v1', 'units': len(units), 'observations': len(rows),
        'interpretation': 'Separate advertisements preserve their own reported counts and dates. Studio/divided/junior-bedroom wording and count changes do not establish a physical renovation interval. Do not forward-fill a chosen count across the unit history.'}
    publish_bundle(base/'chelsea-laundry-reviewed-unit-context-20260919',
        {'summary.json': canonical(result)+'\n', 'context.jsonl': ''.join(canonical(r)+'\n' for r in context),
         Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'source_manifest_sha256': digest(source/'complete.json'),
         'descriptions_manifest_sha256': digest(descriptions/'complete.json'),
         'review_manifest_sha256': digest(reviewed/'complete.json')})
    print(canonical(result), flush=True)


if __name__ == '__main__': run()

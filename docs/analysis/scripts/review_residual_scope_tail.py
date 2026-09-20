"""Publish manually reviewed residual findings with exact prior-review reuse."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import duckdb

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


FINDINGS = {
    '831056': (2, 'insufficient_unit_specific_description',
        'Generic London Terrace building marketing does not explain the $18,000 initial ask.',
        'Review own price history and unit identity; no supported replacement price.', []),
    '2833618': (0, 'location_and_access_review',
        'Raw address is 160 West 24th Street #5H, building 13058; prose says a block from McGolrick Park and only two flights up. Raw amenities include elevator/doorman. Resolve location and access evidence before changing identity or floor.',
        'Check address/place association and possible copied prose; preserve the $1,950 own-ad price. Two flights does not establish an advertised floor.',
        ['only 2 flights up', 'A block away from McGolrick Park']),
    '1670174': (0, 'bathroom_conflict_and_retrospective_timing',
        'Raw composition reports one full bath and zero half baths; prose describes a powder room plus a separate shower bathroom. Same-ad prices rise from $2,395 to $3,700 to $5,950. Captured luxury-duplex attributes may not describe the initial price event.',
        'Review attribute/price timing and bathroom composition; test an explicitly defined temporal sensitivity. Do not overwrite the supported initial ask with the later price. Interior duplex levels are not building-floor evidence.',
        ['sleek powder room off entryway', 'spacious glass-walled walk-in shower']),
    '3591788': (1, 'furnished_term_service_bundle',
        'Own prose offers designer-furnished residences for 2–12 month stays with room service available. It also explicitly describes a second-floor unit, while the analytical floor is unknown.',
        'Review capture-scoped furnished/term/service features and explicit-floor extraction. Restaurant amenities alone do not make this residential offer commercial; service availability does not establish inclusion in rent.',
        ['minimum 2-12 month stays', 'chic designer furnishings', 'daily room service available', 'charming second floor unit']),
}


def records(blob):
    return [json.loads(line) for line in blob.decode().split('\n') if line.strip()]


def run(inputs, previous_inputs, previous_review, archive, output):
    inputs, previous_inputs, previous_review, archive, output = map(
        Path, (inputs, previous_inputs, previous_review, archive, output))
    im, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    _, old_files = _verified_bundle(previous_inputs, retain={'cases.jsonl'})
    _, review_files = _verified_bundle(previous_review, retain={'queue.jsonl'})
    cases = records(files['cases.jsonl'])
    old = {r['source_row']['audit_id']: r for r in records(old_files['cases.jsonl'])}
    reviews = {r['audit_id']: r for r in records(review_files['queue.jsonl'])}
    assert len(cases) == 15 and [r['rank'] for r in cases] == list(range(1, 16))
    assert len({r['source_row']['unit_id'] for r in cases}) == 15
    queue, witnesses = [], []
    reused = 0
    with duckdb.connect(config={'threads': '1', 'memory_limit': '300MB'}) as db:
        for case in cases:
            row = case['source_row']
            ad, audit = row['source_listing_id'], row['audit_id']
            assert hashlib.sha256(canonical(row).encode()).hexdigest() == case['source_row_sha256']
            if audit in old:
                assert canonical(old[audit]['source_row']) == canonical(row)
                assert canonical(old[audit]['captures']) == canonical(case['captures'])
                finding = deepcopy(reviews[audit])
                assert finding['source_row_sha256'] == case['source_row_sha256']
                finding['review_reuse'] = {
                    'method': 'Exact canonical source row and every capture unchanged',
                    'prior_inputs_manifest_sha256': digest(previous_inputs/'complete.json'),
                    'prior_review_manifest_sha256': digest(previous_review/'complete.json'),
                    'prior_rank': finding['rank'],
                }
                reused += 1
            else:
                priority, kind, finding_text, action, phrases = FINDINGS[ad]
                literals = []
                for capture in case['captures']:
                    description = capture['description']
                    assert hashlib.sha256(description.encode()).hexdigest() == capture['description_sha256']
                    spans = []
                    for phrase in phrases:
                        start = description.index(phrase)
                        spans.append({'start': start, 'end': start+len(phrase), 'text': phrase})
                    literals.append({'capture_id': capture['capture_id'],
                        'description_sha256': capture['description_sha256'], 'spans': spans})
                    matches = db.execute(
                        'SELECT raw_listing_json FROM read_parquet(?) WHERE snapshot_id=?',
                        [str(archive/'listing_observations/*.parquet'), capture['capture_id']]).fetchall()
                    assert len(matches) == 1
                    raw = matches[0][0]
                    assert hashlib.sha256(raw.encode()).hexdigest() == capture['raw_listing_sha256']
                    assert str(json.loads(raw)['id']) == ad
                    witnesses.append({'source_listing_id': ad, 'capture_id': capture['capture_id'],
                        'raw_listing_sha256': capture['raw_listing_sha256'], 'raw_listing_json': raw})
                finding = {'priority': priority, 'kind': kind, 'finding': finding_text,
                    'next_action': action, 'literal_evidence': literals,
                    'source_row_sha256': case['source_row_sha256'],
                    'review_reuse': None}
            finding.update({k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'analysis_price_basis')})
            finding.update(rank=case['rank'], residual=case['residual'], applied_to_source_or_model=False)
            queue.append(finding)
    assert reused == 11 and len(witnesses) == 5
    publish_bundle(output, {
        'queue.jsonl': ''.join(canonical(r)+'\n' for r in queue),
        'raw-witnesses.jsonl': ''.join(canonical(r)+'\n' for r in witnesses),
        Path(__file__).name: Path(__file__).read_text(),
    }, {'version': 'reviewed-residual-scope-tail-v1',
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'source_manifest_sha256': im['dataset_manifest_sha256'],
        'fit_manifest_sha256': im['fit_manifest_sha256'],
        'cases': len(queue), 'exact_prior_reviews_reused': reused,
        'new_full_description_reviews': 4, 'raw_witnesses': len(witnesses),
        'source_or_model_changes': False,
        'temporal_scope': 'Captured retrospective same-ad wording; historical attribute effective dates unverified'})
    _verified_bundle(output)
    return {'output': str(output), 'manifest_sha256': digest(output/'complete.json'),
        'cases': len(queue), 'reused': reused, 'new': 4}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'previous-inputs', 'previous-review', 'archive', 'output'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))

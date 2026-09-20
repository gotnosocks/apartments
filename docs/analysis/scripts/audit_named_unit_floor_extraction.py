"""Replay all archived descriptions before/after the named-unit floor rule.

This audits the interpretation only. It does not rebuild observations or replace
label-derived floors in a frozen analytical dataset.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from apartments import attribute_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

OLD_SHA = '4fbc1b5b7f15061206d708ad8775190dd4bf9f3930fe072422a75b4ba0c3789a'
REVIEWED = {'4810936': 2, '4817705': 3, '4902655': 2, '4968706': 3}


def without_floor(result):
    result = deepcopy(result)
    result.pop('version')
    result['attributes'].pop('advertised_floor')
    result['evidence'] = [e for e in result['evidence'] if e['attribute'] != 'advertised_floor']
    result['conflicts'].pop('advertised_floor', None)
    return result


def run(dataset, evidence, reference_implementation, output):
    dataset, evidence, reference_implementation, output = map(Path,
        (dataset, evidence, reference_implementation, output))
    if digest(reference_implementation) != OLD_SHA or attribute_evidence.VERSION != 'attribute-evidence-v7':
        raise ValueError('Expected exact reviewed v6 implementation and candidate v7')
    namespace = {}
    exec(compile(reference_implementation.read_text(), str(reference_implementation), 'exec'), namespace)
    old_extract = namespace['extract_attribute_evidence']
    code = Path(attribute_evidence.__file__)
    before_hashes = [digest(dataset/'complete.json'), digest(evidence/'complete.json'), digest(code)]
    _, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, ef = _verified_bundle(evidence, retain={'evidence.jsonl'})
    rows = {r['audit_id']: r for r in (json.loads(line) for line in sf['observations.jsonl'].splitlines())}
    cache, changed, found, scanned, in_cohort = {}, [], set(), 0, 0
    for line in ef['evidence.jsonl'].splitlines():
        item = json.loads(line)
        text = item.get('description')
        if text is not None and (not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != item['description_sha256']):
            raise ValueError('Description hash or shape differs')
        row = rows.get(item['audit_id'])
        if row is not None:
            if any(canonical(row[k]) != canonical(item[k]) for k in ('unit_id', 'source_listing_id')):
                raise ValueError('Evidence source identity differs')
            if canonical(item['capture_id']) not in {canonical(c) for c in row.get('capture_ids', [row.get('capture_id')])}:
                raise ValueError('Capture is not attached to the analytical observation')
            in_cohort += 1
        scanned += 1
        if text not in cache:
            a, b = old_extract({'description': text}), attribute_evidence.extract_attribute_evidence({'description': text})
            if without_floor(a) != without_floor(b):
                raise ValueError('An unrelated attribute, evidence item or warning changed')
            cache[text] = (a, b)
        a, b = cache[text]
        if {k:v for k,v in a.items() if k != 'version'} == {k:v for k,v in b.items() if k != 'version'}:
            continue
        ad = item['source_listing_id']
        claims = [e for e in b['evidence'] if e['attribute'] == 'advertised_floor']
        if (row is None or ad not in REVIEWED or a['attributes']['advertised_floor'] is not None
                or b['attributes']['advertised_floor'] != REVIEWED[ad] or len(claims) != 1
                or claims[0].get('rule') != attribute_evidence.NAMED_UNIT_FLOOR_RULE):
            raise ValueError('New floor claim exceeds the four fully reviewed advertisements')
        claim = claims[0]
        if text[claim['start']:claim['end']] != claim['literal']:
            raise ValueError('Original-text evidence offsets differ')
        found.add(ad)
        changed.append({'capture': item, 'source_row': row,
            'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
            'before': a, 'after': b})
    if found != REVIEWED.keys() or len(changed) != 8:
        raise ValueError('Expected exactly eight captures across four reviewed ads')
    if before_hashes != [digest(dataset/'complete.json'), digest(evidence/'complete.json'), digest(code)]:
        raise ValueError('Input or candidate implementation changed during replay')
    summary = {'version': 'named-unit-floor-description-replay-v1', 'passed': True,
        'all_archive_captures': scanned, 'source_attached_captures': in_cohort,
        'out_of_cohort_captures': scanned-in_cohort, 'distinct_description_inputs': len(cache),
        'changed_captures': len(changed), 'changed_ads': sorted(found),
        'changed_captures_by_ad': dict(Counter(r['capture']['source_listing_id'] for r in changed)),
        'all_other_attributes_evidence_conflicts_warnings_equal': True,
        'selected_source_or_fit_changed': False,
        'limitations': ['Description-only replay; structured-field conflict behavior is tested separately.',
            'Four recovered explicit claims disagree with existing label proxies; no new known-floor coverage is asserted.',
            'No historical effective dates, physical floors or building-wide numbering offsets are inferred.',
            'The separately reviewed forth-floor misspelling remains unrecognized.']}
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changed),
        'attribute_evidence_v6.py': reference_implementation.read_text(),
        'attribute_evidence_v7.py': code.read_text(), Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'source_manifest_sha256': before_hashes[0],
         'evidence_manifest_sha256': before_hashes[1], 'old_implementation_sha256': OLD_SHA,
         'new_implementation_sha256': before_hashes[2]})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'reference-implementation', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

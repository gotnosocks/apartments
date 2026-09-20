"""Measure the v8 direct-offer floor rules without projecting source values."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from apartments import attribute_evidence as current
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from docs.analysis.scripts.audit_named_unit_floor_extraction import without_floor


def run(dataset, evidence, reference_implementation, output):
    dataset, evidence, reference_implementation, output = map(Path,
        (dataset, evidence, reference_implementation, output))
    ns = {}
    exec(compile(reference_implementation.read_text(), str(reference_implementation), 'exec'), ns)
    if ns['VERSION'] != 'attribute-evidence-v7' or current.VERSION != 'attribute-evidence-v8':
        raise ValueError('Expected v7 to v8 comparison')
    code = Path(current.__file__)
    hashes = [digest(p) for p in [dataset/'complete.json', evidence/'complete.json', reference_implementation, code]]
    _, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, ef = _verified_bundle(evidence, retain={'evidence.jsonl'})
    rows = {r['audit_id']: r for r in map(json.loads, sf['observations.jsonl'].splitlines())}
    cache, changes, count = {}, [], 0
    for line in ef['evidence.jsonl'].splitlines():
        cap = json.loads(line); text = cap.get('description'); row = rows.get(cap['audit_id'])
        if text is not None and hashlib.sha256(text.encode()).hexdigest() != cap['description_sha256']:
            raise ValueError('Description differs')
        if row is not None and (any(row[k] != cap[k] for k in ('source_listing_id', 'unit_id'))
                or cap['capture_id'] not in row.get('capture_ids', [row.get('capture_id')])):
            raise ValueError('Source/capture identity differs')
        count += 1
        if text not in cache:
            a = ns['extract_attribute_evidence']({'description': text})
            b = current.extract_attribute_evidence({'description': text})
            if without_floor(a) != without_floor(b):
                raise ValueError('Nonfloor interpretation changed')
            cache[text] = a, b
        a, b = cache[text]
        if {k:v for k,v in a.items() if k != 'version'} != {k:v for k,v in b.items() if k != 'version'}:
            changes.append({'capture': cap, 'source_row': row, 'before': a, 'after': b})
    if hashes != [digest(p) for p in [dataset/'complete.json', evidence/'complete.json', reference_implementation, code]]:
        raise ValueError('Replay input changed')
    summary = {'archive_captures': count, 'distinct_descriptions': len(cache), 'changed_captures': len(changes),
        'changed_ads': len({r['capture']['source_listing_id'] for r in changes}),
        'changed_captures_by_ad': dict(Counter(r['capture']['source_listing_id'] for r in changes)),
        'nonfloor_interpretations_unchanged': True, 'source_or_fit_changed': False,
        'limitation': 'Description-only interpretation replay; new matches need manual scope review before projection.'}
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'attribute_evidence_v7.py': reference_implementation.read_text(), 'attribute_evidence_v8.py': code.read_text(),
        'audit_named_unit_floor_extraction.py': Path(without_floor.__code__.co_filename).read_text(),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'direct-floor-offer-replay-v1', 'source_manifest_sha256': hashes[0],
         'evidence_manifest_sha256': hashes[1], 'old_implementation_sha256': hashes[2], 'new_implementation_sha256': hashes[3]})
    _verified_bundle(output)
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'reference-implementation', 'output'):
        p.add_argument('--'+name, required=True)
    run(**vars(p.parse_args()))

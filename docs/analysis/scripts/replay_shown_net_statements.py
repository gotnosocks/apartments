"""Compare the v6 shown-net statement rules with the saved v5 measurement."""
import argparse
import importlib.util
import json
from pathlib import Path

from apartments import rent_basis_measurement as current
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(baseline, dataset, evidence, output):
    baseline, dataset, evidence, output = map(Path, (baseline, dataset, evidence, output))
    spec = importlib.util.spec_from_file_location('rent_basis_v5', baseline)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    if previous.VERSION != 'literal-rent-basis-measurement-v5':
        raise ValueError('Expected saved v5 baseline')
    _, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    _, ef = _verified_bundle(evidence, retain={'evidence.jsonl'})
    rows = {r['audit_id']: r for r in map(json.loads, sf['observations.jsonl'].splitlines())}
    changes, count, skipped = [], 0, 0
    for line in ef['evidence.jsonl'].splitlines():
        cap = json.loads(line)
        row = rows.get(cap['audit_id'])
        if row is None:
            skipped += 1
            continue
        if cap['source_listing_id'] != row['source_listing_id'] or cap['unit_id'] != row['unit_id']:
            raise ValueError('Evidence identity differs')
        before = previous.measure(cap['description'], row['asking_rent'])
        after = current.measure(cap['description'], row['asking_rent'])
        count += 1
        for key in before.keys()-{'version', 'advertised_net_statements'}:
            if before[key] != after[key]:
                raise ValueError('Unexpected nonstatement measurement change')
        if before['advertised_net_statements'] != after['advertised_net_statements']:
            changes.append({'capture': cap, 'source_row': row, 'before': before, 'after': after})
    summary = {'checked_captures': count, 'out_of_cohort_captures': skipped,
        'changed_captures': len(changes),
        'changed_ads': len({r['capture']['source_listing_id'] for r in changes}),
        'amount_and_target_match_changes': 0, 'source_or_model_changes': False}
    publish_bundle(output, {'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'summary.json': canonical(summary)+'\n', 'baseline.py': baseline.read_text(),
        'rent_basis_measurement.py': Path(current.__file__).read_text(),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': 'shown-net-statement-replay-v1', 'source_manifest_sha256': digest(dataset/'complete.json'),
         'evidence_manifest_sha256': digest(evidence/'complete.json')})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'dataset', 'evidence', 'output'):
        p.add_argument('--'+name, required=True)
    print(canonical(run(**vars(p.parse_args()))))

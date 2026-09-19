"""Select source review cases using accepted residuals before the new fit completes."""
import argparse
from pathlib import Path

from apartments import bayesian_evidence, laundry_floor_split as split
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_report as report
from models import bayesian_feature_sensitivity as common

BUILDINGS = ('the-thomas-eddy', '101-west-23-street-new_york')


def select_cases(rows, residuals):
    by_id = {r['audit_id']: r for r in residuals}
    if len(by_id) != len(residuals) or set(by_id) != {r['audit_id'] for r in rows}:
        raise ValueError('Review residual/source coverage differs')
    selected, used = [], set()
    for building in BUILDINGS:
        for category in ('on_floor', 'in_building'):
            subset = [r for r in rows if r['building'] == building and r['laundry_type'] == category]
            for direction, reverse in [('highest_signed_residual', True), ('lowest_signed_residual', False)]:
                ordered = sorted(subset, key=lambda r: (by_id[r['audit_id']]['residual_log'], r['audit_id']), reverse=reverse)
                row = next((r for r in ordered if r['unit_id'] not in used), None)
                if row is None: raise ValueError('Insufficient distinct units in review stratum')
                used.add(row['unit_id'])
                residual = by_id[row['audit_id']]
                if any(row[k] != residual[k] for k in ('source_listing_id', 'unit_id', 'building', 'asking_rent', 'period')):
                    raise ValueError('Review residual target differs')
                selected.append({'selection': direction, 'candidate_category': category,
                                 'source_record': row, 'accepted_residual': residual})
    return selected


def run(reference, reference_dataset, candidate_dataset, descriptions, output):
    reference, reference_dataset, candidate_dataset = map(Path, (reference, reference_dataset, candidate_dataset))
    verified, provenance = report.build_report(reference, reference_dataset)
    residuals = report.jsonl(common.bound_bytes(reference/'fit', 'residuals.jsonl', provenance['fit_manifest']))
    cm, cf = _verified_bundle(candidate_dataset, retain={'observations.jsonl'})
    rm, rf = _verified_bundle(reference_dataset, retain={'observations.jsonl'})
    rows = report.jsonl(cf['observations.jsonl'])
    parent, restored = split.parent_rows(cm, rows)
    if parent != rm or restored != report.jsonl(rf['observations.jsonl']):
        raise ValueError('Exact review parent differs')
    cases = select_cases(rows, residuals)
    evidence = bayesian_evidence.load_evidence(candidate_dataset, descriptions)
    for case in cases:
        case['captures'] = evidence[case['source_record']['audit_id']]
        if not case['captures']: raise ValueError('No review source capture')
    summary = {'version': 'laundry-dominant-building-residual-review-candidates-v1',
        'cases': len(cases), 'buildings': list(BUILDINGS),
        'selection': 'Accepted-model signed residual extremes in each building and candidate laundry category, with eight distinct units. Selected before reading candidate-fit results.',
        'status': 'source_review_candidates_not_adjudicated', 'main_model_changed': False,
        'reference_protocol_sha256': verified['protocol_sha256']}
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases), Path(__file__).name: Path(__file__).read_text()},
        {'version': summary['version'], 'reference_fit_sha256': digest(reference/'fit/complete.json'),
         'reference_dataset_sha256': digest(reference_dataset/'complete.json'),
         'candidate_dataset_sha256': digest(candidate_dataset/'complete.json'),
         'descriptions_sha256': digest(Path(descriptions)/'complete.json')})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'reference_dataset', 'candidate_dataset', 'descriptions', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    run(**vars(parser.parse_args()))

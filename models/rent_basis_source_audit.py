"""Screen every verified description for literal net/gross target relationships."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from apartments import bayesian_evidence, rent_basis_measurement as measurement
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'literal-rent-basis-source-audit-v1'


def classify(captures):
    positive = lambda c: [a for a in c['measurement']['amounts']
        if a['equals_analytical_target'] and not a['preceded_by_negation'] and not a['administrative_context']]
    matches = [{a['basis_label'] for a in positive(c)} for c in captures]
    union = set().union(*matches)
    if 'net' in union and 'gross' in union: return 'target_matches_both_net_and_gross_quotes'
    if matches and all(m == {'net'} for m in matches): return 'all_captures_match_explicit_net_only'
    if 'net' in union: return 'some_captures_match_explicit_net'
    if 'gross' in union: return 'target_matches_explicit_gross'
    if 'legal' in union: return 'target_matches_explicit_legal'
    if any(not s['preceded_by_negation'] and not s['administrative_context']
           for c in captures for s in c['measurement']['advertised_net_statements']):
        return 'advertised_net_statement_without_target_amount_match'
    if any(c['measurement']['mentions'] for c in captures): return 'net_mention_without_target_amount_match'
    return 'other_labelled_rent_amount'


def run(dataset, evidence, output):
    dataset, evidence = Path(dataset), Path(evidence)
    sm, sf = _verified_bundle(dataset, retain={'observations.jsonl'})
    rows = [json.loads(s) for s in sf['observations.jsonl'].decode().split('\n') if s]
    descriptions = bayesian_evidence.load_evidence(dataset, evidence)
    cases, coverage = [], Counter()
    for row in rows:
        captures = []
        for capture in descriptions[row['audit_id']]:
            measured = measurement.measure(capture['description'], row['asking_rent'])
            coverage['captures'] += 1
            coverage['with_description'] += measured['description_available']
            captures.append({**capture, 'measurement': measured})
        if not any(c['measurement']['mentions'] or c['measurement']['amounts'] for c in captures): continue
        cases.append({'source_record': row, 'source_row_sha256':
            hashlib.sha256(canonical(row).encode()).hexdigest(),
            'classification': classify(captures), 'captures': captures,
            'status': 'literal_evidence_review_candidate_no_data_action'})
    summary = {'version': VERSION, 'measurement_version': measurement.VERSION,
        'source_rows': len(rows), 'coverage': dict(coverage), 'candidate_rows': len(cases),
        'candidate_units': len({c['source_record']['unit_id'] for c in cases}),
        'candidate_captures': sum(len(c['captures']) for c in cases),
        'by_classification': dict(sorted(Counter(c['classification'] for c in cases).items())),
        'current_by_classification': dict(sorted(Counter(c['classification'] for c in cases
            if c['source_record']['analysis_price_basis'] == 'current_capture_gross_ask').items())),
        'policy': 'Literal quotes and exact target equality only. Every attached capture participates, including missing descriptions. '
                  'A captured description may postdate the initial historical price; quote equality is not proof of its economic basis. '
                  'No replacement prices, inferred concessions or automatic exclusions.',
        'research_prompts': ['Which number does the headline represent?',
            'Does a net-rent statement concern the initial price or a later offer?',
            'Is a gross/net mention an approval requirement rather than an advertised quote?'],
        'limitations': ['Experimental bounded English-language patterns, not exhaustive natural-language interpretation.',
            'Money extraction requires a dollar sign; words, unlabelled numbers and complex sentence structures remain unresolved.',
            'Negation and administrative-context flags are conservative local heuristics, not semantic adjudication.',
            'Development examples include residual-review findings; this is not an independent accuracy evaluation.']}
    paths = [Path(__file__), Path(measurement.__file__), Path(bayesian_evidence.__file__)]
    publish_bundle(output, {'summary.json': canonical(summary)+'\n',
        'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases), **{p.name: p.read_text() for p in paths}},
        {'version': VERSION, 'dataset_manifest_sha256': digest(dataset/'complete.json'),
         'source_observations_sha256': sm['files']['observations.jsonl'],
         'evidence_manifest_sha256': digest(evidence/'complete.json'),
         'implementation_sha256': {p.name: digest(p) for p in paths}})
    print(canonical(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'evidence', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))

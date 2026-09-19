"""Verify source-review notes against the selected fit and literal captures."""
import json
from pathlib import Path

from .bayesian_evidence import load_evidence
from .research_pipeline import _verified_bundle, digest


def load_source_review(experiment, dataset, review, *, evidence):
    experiment, dataset, review, evidence = map(Path, (experiment, dataset, review, evidence))
    manifest, files = _verified_bundle(review, retain={'cases.jsonl', 'summary.json'})
    if (manifest.get('version') != 'current-residual-source-case-review-v1'
            or manifest.get('fit_manifest_sha256') != digest(experiment/'fit/complete.json')
            or manifest.get('dataset_manifest_sha256') != digest(dataset/'complete.json')
            or manifest.get('descriptions_manifest_sha256') != digest(evidence/'complete.json')):
        raise ValueError('Source review differs from selected fit, dataset or description archive')
    _, source_files = _verified_bundle(dataset, retain={'observations.jsonl'})
    source = {r['audit_id']: r for line in source_files['observations.jsonl'].decode().splitlines()
              if (r := json.loads(line))}
    fit_manifest = json.loads((experiment/'fit/complete.json').read_text())
    path = experiment/'fit/residuals.jsonl'
    if path.is_symlink() or digest(path) != fit_manifest['files']['residuals.jsonl']:
        raise ValueError('Reviewed residual file differs from selected fit')
    residuals = {r['audit_id']: r for line in path.read_text().splitlines() if (r := json.loads(line))}
    captures = load_evidence(dataset, evidence)
    summary = json.loads(files['summary.json'])
    cases = [json.loads(line) for line in files['cases.jsonl'].decode().splitlines() if line.strip()]
    if summary.get('version') != manifest['version'] or summary.get('cases') != len(cases):
        raise ValueError('Source review coverage differs')
    notes = {}
    for case in cases:
        identity = case['residual']['audit_id']
        row = source.get(identity)
        if (identity in notes or row is None or identity not in residuals
                or row.get('analysis_price_basis') != 'current_capture_gross_ask'
                or case['joint_posterior_detail']['source_record'] != row
                or case['source_listing_id'] != row['source_listing_id']
                or any(case['residual'].get(k) != v for k, v in residuals[identity].items())
                or case['source_captures'] != captures.get(identity)):
            raise ValueError('Source review case, residual or literal capture binding differs')
        kind, message = case['review_kind'], case['review_reason']
        if not isinstance(kind, str) or not kind.strip() or not isinstance(message, str) or not message.strip():
            raise ValueError('A named source review and explanation are required')
        notes[identity] = {'kind': kind, 'message': message,
            'interpretation_limited': kind in {'bedroom_count_conflict', 'known_bathroom_conflict_and_private_terrace'}}
    return notes

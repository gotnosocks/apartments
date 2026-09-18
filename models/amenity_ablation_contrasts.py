"""Replay a verified amenity ablation and report supported categorical contrasts.

These are conditional regularized point estimates, not causal effects or
coefficient uncertainty intervals. Never modifies a fitted experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from . import amenity_rent_model as model
from . import minimal_rent_model as baseline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'amenity-contrast-replay-v1'
CONTRASTS = (
    ('laundry_type', 'in_building', 'in_unit'),
    ('doorman_type', 'part_time', 'full_time'),
    ('pet_rules', 'not_allowed', 'allowed_restrictions_unknown'),
    ('pet_rules', 'not_allowed', 'approval_required'),
    ('hvac_type', 'room_ac', 'central_ac'),
)


def membership(frame):
    records = sorted((r.unit_id, str(r.period), r.audit_id) for r in frame.itertuples())
    return hashlib.sha256(canonical(records).encode()).hexdigest()


def category_contrast(fitted, train, field, before, after):
    """Contrast known levels using the exact saved column mask and centering."""
    encoder = fitted['encoder']
    levels = encoder.amenity_categories[field]
    categories = pd.Series([model.pricing._category(model.feature_record(row).get(field))
                            for row in train.to_dict('records')], index=train.index)
    groups = {}
    support = {}
    for level in (before, after):
        rows = train[categories.eq(level)]
        groups[level] = (set(rows.unit_id), set(rows.building))
        support[level] = {'unit_months': len(rows), 'units': int(rows.unit_id.nunique()),
                          'buildings': int(rows.building.nunique())}
    result = {'field': field, 'from': before, 'to': after,
              'support': support,
              'buildings_with_both': len(groups[before][1] & groups[after][1]),
              'units_with_both': len(groups[before][0] & groups[after][0]),
              'interpretation': 'conditional regularized association, holding other encoded inputs fixed; not causal'}
    if before == '__unknown__' or after == '__unknown__':
        raise ValueError('This report compares known amenity values, not missingness')
    if before not in levels or after not in levels or not all(support[v]['unit_months'] for v in (before, after)):
        return {**result, 'status': 'unsupported_category', 'log_difference': None, 'percent_difference': None}
    start, _ = encoder.offsets['amenities']
    names = encoder.amenity_features
    mask = getattr(encoder, 'amenity_active_columns', [True] * len(names))
    coefficients = {}
    for level in (before, after):
        index = names.index(f'{field}={level}')
        coefficients[level] = float(fitted['beta'][start+index]) * float(mask[index])
    difference = coefficients[after] - coefficients[before]
    # Training-known category centering subtracts the same vector from both
    # rows, and their unknown indicator is zero. The saved mask applies first.
    pair = pd.concat([train.iloc[:1], train.iloc[:1]], ignore_index=True)
    pair[field] = [before, after]
    predictions = baseline.predict(fitted, pair)
    encoded_difference = float(predictions[1] - predictions[0])
    if not np.isclose(difference, encoded_difference, rtol=1e-10, atol=1e-12):
        raise ValueError('Categorical coefficient contrast disagrees with saved encoder prediction')
    return {**result, 'status': 'estimated', 'log_difference': difference,
            'percent_difference': float(np.expm1(difference) * 100),
            'encoded_prediction_log_difference': encoded_difference,
            'centering_cancellation_error': abs(encoded_difference-difference),
            'effective_coefficients': coefficients,
            'uncertainty': 'Not estimated; support counts are not uncertainty intervals'}


def run(dataset, experiment, output, *, split='year-2024'):
    match = re.fullmatch(r'year-(\d{4})', split)
    if not match:
        raise ValueError('A temporal year-YYYY split is required')
    year = int(match.group(1))
    root = Path(experiment)
    protocol_bytes = (root/'protocol.json').read_bytes()
    protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()
    protocol = json.loads(protocol_bytes)
    if protocol.get('version') != 'chelsea-amenity-ablation-v2':
        raise ValueError('Centered amenity ablation v2 is required')
    directory = root/split/'full'
    fit_manifest, files = _verified_bundle(directory, retain={'predictions.json'})
    if fit_manifest.get('protocol_sha256') != protocol_hash:
        raise ValueError('Fit protocol hash mismatch')
    expected = next((record for record in protocol['splits'] if record['name'] == split), None)
    if expected is None or fit_manifest.get('split_sha256') != expected['test_sha256']:
        raise ValueError('Fit split identity mismatch')
    code_paths = [Path(__file__).with_name('amenity_ablation.py'), Path(model.__file__),
                  Path(baseline.__file__), Path(model.pricing.__file__)]
    code_hashes = {path.name: digest(path) for path in code_paths}
    if code_hashes != protocol['implementation_sha256']:
        raise ValueError('Current replay implementation differs from the fitted protocol')
    versions = {name: importlib.metadata.version(name) for name in protocol['versions']}
    if versions != protocol['versions']:
        raise ValueError('Replay library versions differ from the fitted protocol')
    data, source, _ = model.load_analytical(dataset)
    if source != protocol['source_manifest']:
        raise ValueError('Analytical source manifest does not match fitted protocol')
    data = data[data.period < '2025-01-01'].copy()
    train = data[data.period < f'{year}-01-01']
    test = data[(data.period >= f'{year}-01-01') & (data.period < f'{year+1}-01-01')]
    if (len(train) != expected['train_rows'] or len(test) != expected['test_rows']
            or membership(train) != expected['train_sha256'] or membership(test) != expected['test_sha256']):
        raise ValueError('Analytical train/test membership does not match fitted split')
    fitted = model.load_fit(directory)
    encoder = fitted['encoder']
    if getattr(encoder, 'ablation_variant', None) != 'full' or not hasattr(encoder, 'amenity_category_centers'):
        raise ValueError('Saved fit lacks the full centered amenity encoder')
    if encoder.unit_effect != protocol['unit_effect']:
        raise ValueError('Saved unit-effect setting differs from protocol')
    stored = np.asarray(json.loads(files['predictions.json']), dtype=float)
    replay = np.exp(baseline.predict(fitted, test))
    if (stored.shape != replay.shape or not np.isfinite(stored).all()
            or not np.isfinite(replay).all() or not (stored > 0).all()
            or not (replay > 0).all() or not np.allclose(stored, replay, rtol=1e-12, atol=1e-8)):
        raise ValueError('Saved-model predictions do not reproduce persisted held-out predictions')
    report = {'version': VERSION, 'split': split, 'training_rows': len(train),
              'heldout_rows': len(test), 'unit_effect': encoder.unit_effect,
              'replay': {'verified': True, 'rtol': 1e-12, 'atol_dollars': 1e-8,
                         'maximum_absolute_dollar_error': float(np.max(np.abs(stored-replay))),
                         'maximum_relative_error': float(np.max(np.abs(stored-replay)/stored))},
              'contrasts': [category_contrast(fitted, train, *contrast) for contrast in CONTRASTS],
              'limitations': ['Regularized point contrasts have no coefficient uncertainty estimates.',
                  'Building and unit effects can confound amenity coefficients; shared-building support does not remove that confounding.',
                  'Support counts are training unit-months, canonical source units, and canonical building identities.',
                  'Historical advertisement attributes were collected later; this is retrospective source-evidence modeling.',
                  'Changes compare known levels at fixed other inputs; willingness to pay is not inferred.']}
    if (hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest() != protocol_hash
            or any(digest(path) != code_hashes[path.name] for path in code_paths)
            or _verified_bundle(directory)[0] != fit_manifest):
        raise ValueError('Fit protocol or implementation changed during reporting')
    return publish_bundle(output, {'report.json': canonical(report)+'\n',
                                   'source-manifest.json': canonical(source)+'\n',
                                   'fit-manifest.json': canonical(fit_manifest)+'\n'},
                          {'version': VERSION, 'protocol_sha256': protocol_hash,
                           'source_manifest_sha256': hashlib.sha256(canonical(source).encode()).hexdigest(),
                           'implementation_sha256': digest(__file__),
                           'replay_implementation_sha256': code_hashes, 'versions': versions,
                           'training_membership_sha256': expected['train_sha256'],
                           'test_membership_sha256': expected['test_sha256']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', default='year-2024')
    args = parser.parse_args()
    manifest = run(args.dataset, args.experiment, args.output, split=args.split)
    print(canonical(manifest))

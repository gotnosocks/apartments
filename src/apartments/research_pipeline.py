"""Verified artifact boundaries for the analytical, pricing and search stages."""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import tempfile

from .corrections import canonical


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _verified_bundle(root, retain=()):
    """Fail closed on unfinished, tampered, or externally referenced outputs."""
    root = Path(root)
    if (root / 'complete.json').is_symlink():
        raise ValueError('Completion marker must not be a symlink')
    manifest = json.loads((root / 'complete.json').read_text())
    if not manifest.get('files'):
        raise ValueError('Bundle has no artifact hashes')
    contents = {}
    for name, expected in manifest['files'].items():
        if Path(name).name != name or (root / name).is_symlink() or not (root / name).is_file():
            raise ValueError(f'Invalid artifact path: {name}')
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Artifact integrity failure: {name}')
        if name in retain:
            contents[name] = data
    return manifest, contents


def read_bundle(root):
    return _verified_bundle(root)[0]


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def publish_bundle(root, files, metadata):
    """Deterministic, locked publication; identical reruns verify and reuse."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(Path(name).name != name or name in {'complete.json', 'plan.json', '.build.lock'} for name in files):
        raise ValueError('Invalid publication filename')
    manifest = {**metadata, 'files': {
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}}
    with (root / '.build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (root / 'complete.json').exists():
            if read_bundle(root) != manifest:
                raise ValueError('Run identity changed; choose a new output directory')
            return manifest
        plan = root / 'plan.json'
        if plan.exists():
            if json.loads(plan.read_text()) != manifest:
                raise ValueError('Partial run identity changed; choose a new output directory')
        elif any(p.name != '.build.lock' for p in root.iterdir()):
            raise ValueError('Output directory contains unrelated files')
        outputs = {'plan.json': canonical(manifest) + '\n', **files,
                   'complete.json': canonical(manifest) + '\n'}
        for name, content in outputs.items():
            with tempfile.NamedTemporaryFile('w', dir=root, encoding='utf-8',
                                             prefix='.partial-', delete=False) as temp:
                temp.write(content)
                temp_path = Path(temp.name)
            temp_path.replace(root / name)
    return manifest


def fit_dataset(dataset, output, *, holdout_fraction=.2, ridge=1.0):
    from . import pricing
    source, verified = _verified_bundle(dataset, retain={'observations.jsonl'})
    if source.get('dataset_version') not in {'dated-analytical-v1','historical-own-advertisement-v1'}:
        raise ValueError('A verified dated or own-advertisement analytical dataset is required')
    if 'observations.jsonl' not in source['files']:
        raise ValueError('Analytical observations are not verified')
    rows = (json.loads(line) for line in verified['observations.jsonl'].decode().split('\n') if line.strip())
    model = pricing.fit_pricing_model(rows,
                                      holdout_fraction=holdout_fraction, ridge=ridge)
    if source['dataset_version'] == 'historical-own-advertisement-v1':
        model.report['evaluation_basis'] = 'retrospective reconstructed advertisement price dates; attributes collected later'
        model.report['limitations'] = model.report['limitations'] + [
            'observed_at is a source price-date alias in this historical input, not collection time.',
            'Temporal validation does not represent historically available information.']
    else:
        model.report['evaluation_basis'] = 'contemporary collection-time asking-rent observations'
    if not model.report['converged']:
        raise ValueError('Pricing optimizer did not converge; no model published')
    return publish_bundle(output, {
        'model.json': canonical(model.to_dict()) + '\n',
        'report.json': canonical(model.report) + '\n',
        'analytical-manifest.json': canonical(source) + '\n',
    }, {'model_version': pricing.VERSION,
        'source_manifest_sha256': hashlib.sha256(canonical(source).encode()).hexdigest(),
        'implementation_sha256': digest(pricing.__file__),
        'pipeline_sha256': digest(__file__),
        'settings': {'holdout_fraction': holdout_fraction, 'ridge': ridge}})


def rank_candidates(candidates, preferences, output, *, unknown_policy='exclude',
                    budget=None, model_bundle=None):
    """Candidates are an explicitly selected snapshot, never claimed live inventory."""
    from . import pricing
    if budget is not None:
        import math
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError('Budget must be finite and positive')
    # Read each input once so its digest describes the bytes actually consumed.
    candidate_bytes = Path(candidates).read_bytes()
    preference_bytes = Path(preferences).read_bytes()
    rows = [json.loads(line) for line in candidate_bytes.decode().split('\n') if line.strip()]
    weights = json.loads(preference_bytes)
    if not isinstance(weights, dict):
        raise ValueError('Preferences must be an object of monthly dollar values')
    ranked = pricing.rank_apartments(rows, weights, unknown_policy=unknown_policy)
    over_budget = sum(r['rent'] > budget for r in ranked) if budget is not None else 0
    if budget is not None:
        ranked = [r for r in ranked if r['rent'] <= budget]
    model_manifest = None
    if model_bundle is not None:
        model_manifest, verified = _verified_bundle(model_bundle, retain={'model.json'})
        if 'model.json' not in model_manifest['files']:
            raise ValueError('Model file is not verified')
        data = json.loads(verified['model.json'])
        if data.get('version') != pricing.VERSION:
            raise ValueError('Unsupported pricing artifact version')
        model = pricing.PricingModel(data['encoder'], data['coefficients'],
                                    data['report'], data['residual_log_std'])
        for row in ranked:
            row['market_comparison'] = model.predict(row['record'])
            row['market_comparison']['asking_minus_predicted'] = row['rent'] - row['market_comparison']['predicted_rent']
    return publish_bundle(output, {
        'rankings.jsonl': ''.join(canonical(row) + '\n' for row in ranked),
        'preferences.json': canonical(weights) + '\n',
    }, {'ranking_version': 'preference-frontier-v1',
        'candidates_sha256': hashlib.sha256(candidate_bytes).hexdigest(),
        'preferences_sha256': hashlib.sha256(preference_bytes).hexdigest(),
        'implementation_sha256': digest(pricing.__file__), 'pipeline_sha256': digest(__file__),
        'unknown_policy': unknown_policy, 'budget': budget,
        'input_candidates': len(rows), 'over_budget': over_budget,
        'eligible': sum(r['eligible'] for r in ranked),
        'frontier': sum(r['pareto_efficient'] for r in ranked),
        'model_manifest': model_manifest,
        'limitations': ['Candidate file is a supplied snapshot; current availability is not verified.',
                        'Willingness to pay is supplied by the user, not inferred from market coefficients.']})

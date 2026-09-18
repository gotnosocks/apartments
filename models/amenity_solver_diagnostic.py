"""Independent fixed-objective numerical verification of saved amenity fits.

Refinement outputs are diagnostics only: they do not replace fitted experiments,
select hyperparameters, estimate sampling uncertainty, or imply causal effects.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import lsmr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_ablation_contrasts as contrasts
from . import amenity_rent_model as model
from . import minimal_rent_model as baseline

VERSION = 'amenity-solver-diagnostic-v2'


def objective_gradient(x, p, y, beta, *, delta=.2):
    """Huber objective and negative gradient, including the exact saved penalty."""
    residual = np.asarray(y - x @ beta)
    absolute = abs(residual)
    penalized = p @ beta
    objective = float(np.where(absolute <= delta, .5*residual**2,
                               delta*absolute-.5*delta**2).sum() + .5*sum(penalized**2))
    negative_gradient = np.asarray(x.T @ np.clip(residual, -delta, delta) - p.T @ penalized).ravel()
    scale = np.sqrt(np.asarray(x.power(2).sum(axis=0) + p.power(2).sum(axis=0)).ravel())
    scaled = np.divide(negative_gradient, scale, out=np.zeros_like(negative_gradient), where=scale > 0)
    return {'objective': objective, 'gradient_inf': float(max(abs(negative_gradient), default=0.)),
            'gradient_l2': float(np.linalg.norm(negative_gradient)),
            'column_scaled_gradient_inf': float(max(abs(scaled), default=0.)),
            'negative_gradient': negative_gradient}


def refine(x, p, y, beta, *, steps=12, atol=1e-10, btol=1e-10, maxiter=20000, delta=.2, progress=None):
    """Perform a fixed number of tight weighted solves; never early-exit on loss."""
    if steps < 1 or maxiter < 1 or min(atol, btol, delta) <= 0:
        raise ValueError('Positive numerical diagnostic settings required')
    x, p = sparse.csr_matrix(x), sparse.csr_matrix(p)
    y, beta = np.asarray(y, dtype=float), np.array(beta, dtype=float, copy=True)
    history = []
    for step in range(steps):
        residual = y - x @ beta
        root_weights = np.sqrt(np.minimum(1., delta / np.maximum(abs(residual), 1e-12)))
        design = sparse.vstack([x.multiply(root_weights[:, None]), p], format='csr')
        rhs = np.concatenate([y*root_weights, np.zeros(p.shape[0])])
        solved = lsmr(design, rhs, atol=atol, btol=btol, maxiter=maxiter, x0=beta)
        if solved[1] not in (1, 2, 4, 5):
            raise RuntimeError(f'Tight LSMR failed: stop={solved[1]}, iterations={solved[2]}')
        prior = beta
        beta = solved[0]
        stationarity = objective_gradient(x, p, y, beta, delta=delta)
        record = {'step': step+1, **{k:v for k,v in stationarity.items() if k != 'negative_gradient'},
                  'lsmr_stop_code': int(solved[1]), 'lsmr_iterations': int(solved[2]),
                  'lsmr_condition_estimate': float(solved[6]),
                  'coefficient_step_inf': float(max(abs(beta-prior), default=0.))}
        history.append(record)
        if progress:
            progress(record)
    return beta, history


def _contrast_vector(encoder, field, before, after):
    levels = encoder.amenity_categories[field]
    if before not in levels or after not in levels:
        return None
    vector = np.zeros(encoder.n_parameters)
    start = encoder.offsets['amenities'][0]
    mask = getattr(encoder, 'amenity_active_columns', [True] * len(encoder.amenity_features))
    for level, sign in ((before, -1), (after, 1)):
        position = encoder.amenity_features.index(f'{field}={level}')
        vector[start + position] = sign * float(mask[position])
    return vector


def prediction_change(original, refined):
    difference = np.asarray(refined) - np.asarray(original)
    percent = 100*np.expm1(difference)
    dollars = np.exp(refined)-np.exp(original)
    return {'rows': len(difference), 'max_absolute_log_change': float(max(abs(difference), default=0.)),
            'mean_absolute_log_change': float(np.mean(abs(difference))),
            'max_absolute_percent_change': float(max(abs(percent), default=0.)),
            'mean_absolute_percent_change': float(np.mean(abs(percent))),
            'max_absolute_dollar_change': float(max(abs(dollars), default=0.)),
            'mean_absolute_dollar_change': float(np.mean(abs(dollars)))}


def _verify_implementation(root, protocol, protocol_hash, *, current_paths=None):
    """Verify executed code live, and non-executed producer code as archived data."""
    expected = protocol['implementation_sha256']
    allowed = {'amenity_ablation.py', 'amenity_ablation_contrasts.py',
               'amenity_rent_model.py', 'minimal_rent_model.py', 'pricing.py',
               'amenity_sensitivity.py'}
    required = {'amenity_ablation.py', 'amenity_rent_model.py', 'minimal_rent_model.py', 'pricing.py'}
    sensitivity = protocol['version'] in {'amenity-shrinkage-sensitivity-v1', 'amenity-shrinkage-sensitivity-v2'}
    if sensitivity:
        required |= {'amenity_ablation_contrasts.py', 'amenity_sensitivity.py'}
    if not required.issubset(expected) or not set(expected).issubset(allowed):
        raise ValueError('Unsupported or incomplete implementation inventory')
    if current_paths is None:
        current_paths = {name:Path(__file__).with_name(name) for name in allowed}
        current_paths['pricing.py'] = Path(model.pricing.__file__)
    live = {name:Path(current_paths[name]) for name in expected if name != 'amenity_sensitivity.py'}
    if any(digest(path) != expected[name] for name,path in live.items()):
        raise ValueError('Executed fit implementation changed')
    producer = {}
    if sensitivity:
        archive = Path(root)/'implementation'
        path = archive/'amenity_sensitivity.py'
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing or invalid producer snapshot')
        if protocol['version'] == 'amenity-shrinkage-sensitivity-v2':
            archived, _ = _verified_bundle(archive)
            if archived.get('protocol_sha256') != protocol_hash or archived.get('version') != protocol['version']:
                raise ValueError('Producer snapshot bundle protocol mismatch')
            if any(archived['files'].get(name) != value for name,value in expected.items()):
                raise ValueError('Producer snapshot bundle implementation mismatch')
            kind = 'checksummed_bundle'
            bundle_hash = digest(archive/'complete.json')
        else:
            kind, bundle_hash = 'protocol_hash_bound_flat_snapshot', None
        if digest(path) != expected['amenity_sensitivity.py']:
            raise ValueError('Producer snapshot hash mismatch')
        producer = {'name':'amenity_sensitivity.py', 'path':'implementation/amenity_sensitivity.py',
                    'sha256':expected['amenity_sensitivity.py'], 'kind':kind,
                    'bundle_manifest_sha256':bundle_hash, 'executed':False}
    return {'live_implementation_sha256':{name:digest(path) for name,path in live.items()},
            'producer_snapshot':producer}


def run(dataset, experiment, output, *, split='year-2024', specification='full', steps=12):
    year_match = re.fullmatch(r'year-(\d{4})', split)
    if not year_match:
        raise ValueError('Diagnostic supports temporal year-YYYY splits')
    year = int(year_match[1])
    root, directory = Path(experiment), Path(experiment)/split/specification
    protocol_hash = digest(root/'protocol.json')
    protocol = json.loads((root/'protocol.json').read_text())
    fit_manifest, artifacts = _verified_bundle(directory, retain={'result.json', 'predictions.json'})
    if fit_manifest.get('protocol_sha256') != protocol_hash:
        raise ValueError('Saved fit protocol hash mismatch')
    result = json.loads(artifacts['result.json'])
    if protocol['version'] == 'chelsea-amenity-ablation-v2' and specification == 'full':
        settings = protocol['settings']
        units = protocol['unit_effect']
    elif protocol['version'] in {'amenity-shrinkage-sensitivity-v1', 'amenity-shrinkage-sensitivity-v2'}:
        spec = next((s for s in protocol['specifications'] if s['name'] == specification), None)
        if spec is None or result['specification'] != spec:
            raise ValueError('Sensitivity specification does not match saved protocol')
        settings, units = spec['settings'], spec['unit_effect']
    else:
        raise ValueError('Unsupported full amenity fit protocol')
    expected = next((s for s in protocol['splits'] if s['name'] == split), None)
    if expected is None:
        raise ValueError('Missing saved split')
    replay_provenance = _verify_implementation(root, protocol, protocol_hash)
    versions = {name: importlib.metadata.version(name) for name in protocol['versions']}
    if versions != protocol['versions']:
        raise ValueError('Numerical library versions changed')
    data, source, _ = model.load_analytical(dataset)
    if source != protocol['source_manifest']:
        raise ValueError('Analytical source manifest mismatch')
    train = data[data.period < f'{year}-01-01']
    test = data[(data.period >= f'{year}-01-01') & (data.period < f'{year+1}-01-01')]
    if (len(train) != expected['train_rows'] or len(test) != expected['test_rows']
            or contrasts.membership(train) != expected['train_sha256']
            or contrasts.membership(test) != expected['test_sha256']):
        raise ValueError('Saved training/test membership mismatch')
    fitted = model.load_fit(directory)
    enc, beta = fitted['encoder'], fitted['beta']
    if enc.unit_effect != units or getattr(enc, 'ablation_variant', None) != 'full':
        raise ValueError('Saved full encoder settings mismatch')
    if not np.isclose(fitted['center'], float(train.log_rent.median()), atol=1e-12, rtol=0):
        raise ValueError('Saved outcome center disagrees with training data')
    x, p = enc.matrix(train), enc.penalty(settings)
    xtest = enc.matrix(test)
    y = train.log_rent.to_numpy()-fitted['center']
    original_test = fitted['center'] + xtest @ beta
    stored = np.array(json.loads(artifacts['predictions.json']))
    if stored.shape != original_test.shape or not np.allclose(stored, np.exp(original_test), rtol=1e-12, atol=1e-8):
        raise ValueError('Saved test predictions fail exact replay')
    original = objective_gradient(x, p, y, beta)
    controls = {'steps': steps, 'atol': 1e-10, 'btol': 1e-10, 'maxiter': 20000, 'delta': .2}
    print(canonical({'specification':specification, 'phase':'original_stationarity',
                     **{k:v for k,v in original.items() if k != 'negative_gradient'}}), flush=True)
    refined, history = refine(x, p, y, beta, **controls,
        progress=lambda row: print(canonical({'specification':specification, **row}), flush=True))
    final = objective_gradient(x, p, y, refined)
    comparisons = []
    for field, before, after in contrasts.CONTRASTS:
        vector = _contrast_vector(enc, field, before, after)
        if vector is None:
            comparisons.append({'field':field,'from':before,'to':after,'status':'unsupported'})
            continue
        # Independently cross-check the contrast vector against encoded rows.
        pair = train.iloc[[0, 0]].copy()
        pair[field] = [before, after]
        encoded = enc.matrix(pair)
        if not np.allclose((encoded[1]-encoded[0]).toarray().ravel(), vector, rtol=0, atol=1e-12):
            raise ValueError('Category contrast does not match saved encoder')
        old, new = float(vector @ beta), float(vector @ refined)
        comparisons.append({'field':field,'from':before,'to':after,'status':'estimated',
                            'original_log_contrast':old,'refined_log_contrast':new,
                            'absolute_log_contrast_change':abs(new-old),
                            'original_percent_contrast':float(100*np.expm1(old)),
                            'refined_percent_contrast':float(100*np.expm1(new)),
                            'absolute_percentage_point_change':float(100*abs(np.expm1(new)-np.expm1(old)))})
    report = {'version':VERSION,'split':split,'specification':specification,'settings':settings,
              'controls':controls,'saved_center':fitted['center'],'training_rows':len(train),
              'test_rows':len(test),'parameters':len(beta),
              'original':{k:v for k,v in original.items() if k != 'negative_gradient'},
              'refined':{k:v for k,v in final.items() if k != 'negative_gradient'},
              'relative_objective_decrease':(original['objective']-final['objective'])/max(1.,abs(original['objective'])),
              'history':history,'contrasts':comparisons,
              'train_prediction_change':prediction_change(fitted['center']+x@beta,fitted['center']+x@refined),
              'test_prediction_change':prediction_change(original_test,fitted['center']+xtest@refined),
              'limitations':['Numerical verification of one fixed encoder, outcome center and penalized objective only.',
                  'Refinement is not a replacement model or a hyperparameter selection procedure.',
                  'Contrast changes are numerical sensitivity, not statistical uncertainty or causal effects.',
                  'Stationarity scales depend on design units; both unscaled and column-normalized norms are reported.']}
    implementation = {**replay_provenance['live_implementation_sha256'],
                      Path(__file__).name:digest(__file__), 'amenity_ablation_contrasts.py':digest(contrasts.__file__)}
    if digest(root/'protocol.json') != protocol_hash or _verified_bundle(directory)[0] != fit_manifest:
        raise ValueError('Saved fit changed during diagnostics')
    if _verify_implementation(root, protocol, protocol_hash) != replay_provenance:
        raise ValueError('Source or producer snapshot changed during diagnostics')
    return publish_bundle(output, {'report.json':canonical(report)+'\n',
        'refinement.json':canonical({'beta':refined.tolist(),'center':fitted['center'],
                                    'interpretation':'diagnostic only; original model unchanged'})+'\n',
        'source-manifest.json':canonical(source)+'\n', 'fit-manifest.json':canonical(fit_manifest)+'\n'},
        {'version':VERSION,'protocol_sha256':protocol_hash,'controls':controls,
         'source_manifest_sha256':hashlib.sha256(canonical(source).encode()).hexdigest(),
         'training_membership_sha256':expected['train_sha256'],'test_membership_sha256':expected['test_sha256'],
         'implementation_sha256':implementation,'replay_provenance':replay_provenance,'versions':versions})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--split', default='year-2024')
    parser.add_argument('--specification', default='full')
    parser.add_argument('--steps', type=int, default=12)
    args = parser.parse_args()
    run(args.dataset,args.experiment,args.output,split=args.split,specification=args.specification,steps=args.steps)

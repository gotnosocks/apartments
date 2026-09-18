"""Bounded posterior checks using the fitted shared or bedroom-specific noise."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_checks_v2 as common
from . import bayesian_feature_design_v2 as ordered_design
from . import bayesian_feature_graph_v3 as graph
from . import bayesian_feature_report as report

VERSION = 'bayesian-feature-posterior-checks-v3'
V2_EXPERIMENT = 'observable-bayesian-bathroom-experiment-v2'
V3_EXPERIMENT = 'observable-bayesian-bathroom-experiment-v3'
V4_EXPERIMENT = 'observable-bayesian-floor-experiment-v4'
BEDROOM_DIMS = {'residual_bedroom_z': ('residual_bedroom',),
                'residual_bedroom_scale': (), 'sigma_by_bedroom': ('residual_bedroom',)}
LIMITATIONS = [*common.LIMITATIONS,
    'Replications use the exact fitted noise specification. In bedroom mode each observed row receives its bedroom-level scale from the same joint posterior draw; global sigma is not substituted.',
]


def verified_configuration(protocol, data, fit_directory):
    """Recompute declared graph settings against the exact source cohort."""
    version = protocol.get('version')
    if version == V2_EXPERIMENT:
        if any(name in protocol for name in ('graph_configuration', 'residual_scale',
                                            'building_prior_scale', 'unit_prior_scale')):
            raise ValueError('Legacy v2 fit cannot declare v3 noise or prior settings')
        # V2 mean/noise graph is frozen and checked by verify_implementation.
        return graph.graph_configuration(data, protocol['prior_multiplier'])
    if version not in (V3_EXPERIMENT,V4_EXPERIMENT):
        raise ValueError('Unsupported posterior experiment version')
    try:
        expected = graph.graph_configuration(data, protocol['prior_multiplier'],
            residual_scale=protocol['residual_scale'], building_prior_scale=protocol['building_prior_scale'],
            unit_prior_scale=protocol['unit_prior_scale'],
            residual_parameterization=protocol.get('residual_parameterization','noncentered'))
        saved = json.loads((Path(fit_directory)/'graph-configuration.json').read_text())
    except (KeyError, FileNotFoundError) as exc:
        raise ValueError('Missing explicit v3 graph configuration') from exc
    if canonical(protocol.get('graph_configuration')) != canonical(expected) or canonical(saved) != canonical(expected):
        raise ValueError('Graph configuration differs from protocol or source bedroom support')
    return expected


def verify_implementation(protocol):
    if protocol.get('version') in (V3_EXPERIMENT,V4_EXPERIMENT):
        required = {'bayesian_feature_graph_v3.py', 'bayesian_feature_experiment_v3.py'}
        if not required <= protocol['implementation_sha256'].keys():
            raise ValueError('Missing v3 graph/runner implementation bindings')
    if protocol.get('version') == V4_EXPERIMENT:
        if not {'bayesian_floor_increment_design.py','bayesian_feature_experiment_v4.py'} <= protocol['implementation_sha256'].keys():
            raise ValueError('Missing v4 floor design/runner implementation bindings')
    return common.verify_implementation(protocol)


def load_draws(path, protocol, design, configuration, per_chain=50):
    mode = configuration['residual_scale']
    if mode not in graph.RESIDUAL_SCALES or configuration['student_t_nu'] != 5.:
        raise ValueError('Unsupported residual noise configuration')
    variables = dict(common.VARIABLE_DIMS)
    if mode == 'bedroom':
        variables.update(BEDROOM_DIMS)
        if configuration.get('residual_bedroom_parameterization') == 'centered':
            variables['residual_bedroom_offset']=('residual_bedroom',)
    with xr.open_dataset(path, group='posterior', engine='h5netcdf') as posterior:
        if posterior.sizes.get('chain') != protocol['chains'] or posterior.sizes.get('draw') != protocol['draws']:
            raise ValueError('Posterior chain/draw dimensions differ from protocol')
        if mode == 'bedroom' and configuration.get('residual_bedroom_parameterization') != 'centered' and 'residual_bedroom_offset' in posterior:
            raise ValueError('Noncentered posterior contains centered offset draws')
        if mode == 'shared' and ((set(BEDROOM_DIMS)|{'residual_bedroom_offset'}) & set(posterior.data_vars) or 'residual_bedroom' in posterior.coords):
            raise ValueError('Shared residual fit contains bedroom-scale posterior variables')
        expected = {'feature': design.features, 'building': design.time.buildings,
                    'unit': design.time.unit_ids, 'trend_basis': list(range(design.time.time_matrix.shape[1])),
                    'season_basis': list(range(design.time.season_matrix.shape[1]))}
        if mode == 'bedroom':
            levels = configuration['residual_bedroom_levels']
            if len(levels) < 2:
                raise ValueError('Bedroom residual fit requires at least two declared levels')
            graph.bedroom_index(levels, levels)
            expected['residual_bedroom'] = levels
        for dimension, values in expected.items():
            if dimension not in posterior.coords or posterior[dimension].values.tolist() != list(values):
                raise ValueError('Posterior coordinate order differs from saved design: '+dimension)
        for name, dimensions in variables.items():
            if name not in posterior or posterior[name].dims != ('chain', 'draw', *dimensions):
                raise ValueError('Unexpected or missing posterior dimensions: '+name)
        chosen = common.select_draws(protocol['chains'], protocol['draws'], per_chain)
        samples = {name: [] for name in variables}
        selection = []
        for chain in range(protocol['chains']):
            positions = [draw for selected_chain, draw in chosen if selected_chain == chain]
            part = posterior[list(variables)].isel(chain=chain, draw=positions).load()
            for draw in positions:
                selection.append({'chain_index': chain, 'draw_index': draw,
                                  'chain_coordinate': posterior.chain.values[chain].item(),
                                  'draw_coordinate': posterior.draw.values[draw].item()})
            for name, dimensions in variables.items():
                samples[name].extend(np.asarray(part[name].transpose('draw', *dimensions).values).copy())
    samples = {name: np.stack(values) for name, values in samples.items()}
    if (any(not np.isfinite(value).all() for value in samples.values())
            or np.any(samples['sigma'] <= 0) or np.any(samples['sigma_unit'] < 0)):
        raise ValueError('Nonfinite draws or invalid residual/unit scales')
    if mode == 'bedroom':
        z, scale = samples['residual_bedroom_z'], samples['residual_bedroom_scale']
        expected_sigma = samples['sigma'][:, None]*np.exp(scale[:, None]*z)
        if (np.any(scale <= 0) or np.any(samples['sigma_by_bedroom'] <= 0)
                or not np.allclose(z.sum(axis=1), 0., rtol=0, atol=1e-10)
                or not np.allclose(samples['sigma_by_bedroom'], expected_sigma, rtol=1e-10, atol=0)):
            raise ValueError('Bedroom residual scales do not match their joint posterior parameterization')
        if configuration.get('residual_bedroom_parameterization') == 'centered':
            offset=samples['residual_bedroom_offset']
            if not np.allclose(offset,scale[:,None]*z,rtol=1e-10,atol=1e-12):
                raise ValueError('Centered residual offsets do not match scale times z')
    return samples, selection


def row_scales(samples, configuration, bedrooms):
    """Map each row to its noise scale; bedroom fits must never fall back."""
    mode = configuration['residual_scale']
    if mode == 'shared':
        if set(BEDROOM_DIMS) & samples.keys():
            raise ValueError('Shared noise cannot contain bedroom-scale draws')
        return np.broadcast_to(samples['sigma'][:, None], (len(samples['sigma']), len(bedrooms)))
    if mode != 'bedroom' or 'sigma_by_bedroom' not in samples:
        raise ValueError('Bedroom-specific residual scale draws are required')
    indices = graph.bedroom_index(bedrooms, configuration['residual_bedroom_levels'])
    sigmas = samples['sigma_by_bedroom']
    if sigmas.shape != (len(samples['sigma']), len(configuration['residual_bedroom_levels'])):
        raise ValueError('Bedroom residual scales have incompatible shape')
    return sigmas[:, indices]


def replicate_residuals(samples, configuration, bedrooms, seed):
    scales = row_scales(samples, configuration, bedrooms)
    if not np.isfinite(scales).all() or np.any(scales <= 0) or configuration['student_t_nu'] != 5.:
        raise ValueError('Invalid fitted observation scales or Student-t degrees of freedom')
    return np.random.default_rng(seed).standard_t(5., size=scales.shape)*scales


def run(experiment, dataset, output, *, per_chain=50, seed=20260919):
    experiment, dataset, output = map(Path, (experiment, dataset, output))
    check_paths = [Path(module.__file__) for module in (common, ordered_design, graph, report)] + [Path(__file__)]
    check_hashes = {path: digest(path) for path in check_paths}
    verified, manifests = report.build_report(experiment, dataset, top=1)
    protocol = json.loads((experiment/'protocol'/'protocol.json').read_text())
    if protocol['version'] == V4_EXPERIMENT:
        from . import bayesian_source_sensitivity as verification
        from threadpoolctl import threadpool_limits
        path = Path(verification.__file__)
        check_hashes[path] = digest(path)
        with threadpool_limits(limits=1,user_api='blas'):
            verification.verify_design(experiment,dataset,protocol,manifests)
    paths = verify_implementation(protocol)
    _, source = _verified_bundle(dataset, retain={'observations.jsonl'})
    data = pd.DataFrame(report.jsonl(source['observations.jsonl']))
    data['period'] = pd.to_datetime(data.period)
    data['square_feet'] = pd.to_numeric(data.square_feet, errors='coerce')
    configuration = verified_configuration(protocol, data, experiment/'fit')
    design = ordered_design.load_design(experiment/'fit', data, protocol)
    samples, selected = load_draws(experiment/'fit'/'posterior.nc', protocol, design, configuration, per_chain)
    mu = common.reconstruct_mu(samples, design, data)
    observed = np.log(data.asking_rent.to_numpy(dtype=float))[None, :]-mu
    replicated = replicate_residuals(samples, configuration, data.bedrooms, seed)
    accepted, omitted = common.slices(data)
    result = {'version': VERSION, 'purpose': 'conditional_in_sample_posterior_predictive_checks',
              'protocol_sha256': verified['protocol_sha256'], 'seed': seed, 'rng': 'numpy.default_rng/PCG64',
              'graph_configuration': configuration, 'experiment_version': protocol['version'],
              'noise_scale_source': 'sigma_by_bedroom indexed by observed bedrooms' if configuration['residual_scale'] == 'bedroom' else 'shared sigma',
              'design_loader': getattr(design,'version',ordered_design.VERSION),
              'design_loader_sha256': digest(Path(ordered_design.__file__)),
              'requested_draws_per_chain': per_chain, 'selected_draws': selected,
              'selection': 'Equal draw-index-bin midpoints per chain; chain-major order; posterior group only.',
              'thresholds_log_ratio': common.THRESHOLDS, 'minimum_slice_support': common.MIN_SUPPORT,
              'cohort': verified['cohort'], 'source_observations_sha256': verified['source_observations_sha256'],
              'bindings': {kind: digest(path/'complete.json') for kind, path in
                           [('fit', experiment/'fit'), ('protocol', experiment/'protocol'), ('source', dataset)]},
              'posterior_sha256': manifests['fit_manifest']['files']['posterior.nc'],
              'reconstruction_implementation_sha256': protocol['implementation_sha256'],
              'checks_implementation_sha256': {path.name: sha for path, sha in check_hashes.items()},
              'versions': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'xarray', 'h5netcdf', 'scipy')},
              'slices': [{**item, 'discrepancies': common.compare_residuals(observed[:, mask], replicated[:, mask])}
                         for item, mask in accepted], 'omitted_slices': omitted, 'limitations': LIMITATIONS,
              'main_model_changed': False}
    if any(digest(p) != protocol['implementation_sha256'][p.name] for p in paths):
        raise ValueError('Reconstruction implementation changed during checks')
    if any(digest(path) != sha for path, sha in check_hashes.items()):
        raise ValueError('Posterior check implementation changed during checks')
    markdown = common.markdown(result)+'\nResidual noise: '+result['noise_scale_source']+'.\n'+LIMITATIONS[-1]+'\n'
    snapshots = {Path(module.__file__).name: Path(module.__file__).read_text()
                 for module in (common, ordered_design, graph, report)}
    snapshots[Path(__file__).name] = Path(__file__).read_text()
    if protocol['version'] == V4_EXPERIMENT:
        snapshots[Path(verification.__file__).name] = Path(verification.__file__).read_text()
    publish_bundle(output, {'checks.json': canonical(result)+'\n', 'checks.md': markdown, **snapshots},
                   {'version': VERSION, 'protocol_sha256': verified['protocol_sha256']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draws-per-chain', type=int, default=50)
    parser.add_argument('--seed', type=int, default=20260919)
    args = parser.parse_args()
    result = run(args.experiment, args.dataset, args.output, per_chain=args.draws_per_chain, seed=args.seed)
    print(canonical({'slices': len(result['slices']), 'draws': len(result['selected_draws']), 'output': str(args.output)}))

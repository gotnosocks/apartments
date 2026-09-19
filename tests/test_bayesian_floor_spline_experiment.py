from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from models import bayesian_floor_spline_experiment as m
from tests.test_bayesian_feature_experiment_v3 import setup
from tests.test_bayesian_floor_increment_design import train
from tests.test_bayesian_floor_spline_design import spline_train


def configure(setup):
    args, _, _ = setup
    args.floor_prior_scale = .1
    args.maxdepth = 10
    frame, source = m.load_data(args.dataset)
    frame['listed_floor'] = [1., 2., 10., 52.]
    code = {path.name: m.digest(path) for path in m.implementation_paths()}
    configuration = m.graph.graph_configuration(frame, args.prior_multiplier, **m.graph_kwargs(args))
    return args, frame, source, code, configuration


def test_protocol_binds_spline_prior_support_and_sampler_settings(setup):
    args, frame, source, code, configuration = configure(setup)
    protocol = m.make_protocol(args, frame, source, code, configuration)
    assert protocol['version'] == m.VERSION
    assert protocol['feature_design_version'] == m.floor.VERSION
    assert protocol['floor_knots'] == [1., 5., 10., 20., 35., 52.]
    assert protocol['floor_reference'] == 2
    assert protocol['floor_prior_scale'] == .1
    assert protocol['floor_levels'] == [1., 2., 10., 52.]
    assert protocol['graph_configuration'] == configuration
    assert protocol['maxdepth'] == 10
    assert protocol['source_observations_sha256'] == source['files']['observations.jsonl']
    assert m.disk_protocol.verify_protocol(protocol)
    assert {'bayesian_floor_spline_design.py', 'bayesian_floor_spline_experiment.py'} <= code.keys()
    assert 'floor_increment_prior_scale' not in protocol
    args.floor_prior_scale = .05
    tighter = m.make_protocol(args, frame, source, code, configuration)
    assert tighter['floor_prior_scale'] == .05
    assert tighter['source_observations_sha256'] == protocol['source_observations_sha256']
    assert tighter['graph_configuration'] == protocol['graph_configuration']


def test_real_sampling_defaults_are_long_enough_for_diagnostics():
    args = m.argument_parser().parse_args(['--dataset', 'd', '--output', 'o'])
    assert (args.chains, args.tune, args.draws, args.target_accept, args.maxdepth) == (4, 4000, 6000, .93, 10)
    assert args.floor_prior_scale == .1
    assert args.adaptation == 'diag'
    m.validate_args(args)


@pytest.mark.parametrize('value', [0, -1, np.inf, np.nan, True])
def test_invalid_floor_prior_refuses_run_before_output(setup, value):
    args, *_ = configure(setup)
    args.floor_prior_scale = value
    with pytest.raises(ValueError, match='prior scale'):
        m.run(args)
    assert not args.output.exists()


@pytest.mark.parametrize('field', ['graph_validation', 'floor_block_graph_validation'])
def test_previous_increment_graph_proofs_cannot_certify_new_specification(setup, field):
    args, *_ = configure(setup)
    setattr(args, field, args.output.parent/'old-proof')
    with pytest.raises(ValueError, match='cannot validate a spline'):
        m.run(args)
    assert not args.output.exists()


def posterior_fixture(design):
    rng = np.random.default_rng(311)
    beta = rng.normal(0, .01, (4, 1200, len(design.features)))
    direction = design.contrast_vector(design.floor_levels[0], design.floor_levels[-1])
    first, second = np.flatnonzero(abs(direction) > 1e-10)[:2]
    beta[:, :, first] = rng.normal(0, .3, (4, 1200))
    beta[:, :, second] = (-direction[first]/direction[second])*beta[:, :, first] + rng.normal(.04, .002, (4, 1200))
    posterior = xr.Dataset({'beta': (('chain', 'draw', 'feature'), beta)}, coords={'feature': design.features})
    stats = xr.Dataset({
        'diverging': (('chain', 'draw'), np.zeros((4, 1200), dtype=bool)),
        'maxdepth_reached': (('chain', 'draw'), np.zeros((4, 1200), dtype=bool)),
        'energy': (('chain', 'draw'), rng.normal(size=(4, 1200))),
    })
    return beta, xr.DataTree.from_dict({'posterior': posterior, 'sample_stats': stats})


def test_joint_floor_contrasts_preserve_draw_covariance_and_direction(spline_train):
    design = m.floor.FeatureDesign(spline_train)
    beta, inference = posterior_fixture(design)
    result = m.floor_contrasts(inference, design)
    assert result['version'] == m.FLOOR_CONTRAST_VERSION
    assert result['draws'] == 4800
    assert result['diagnostics']['acceptable']
    for case in result['contrasts']:
        expected = beta @ design.contrast_vector(case['lower_floor'], case['upper_floor'])
        interval = np.quantile(expected, [.025, .5, .975])
        keys = ['lower_95', 'median', 'upper_95']
        np.testing.assert_allclose([case['log_effect'][key] for key in keys], interval)
        np.testing.assert_allclose([case['percent_effect'][key] for key in keys], 100*np.expm1(interval))
    full_range = result['contrasts'][-1]
    assert full_range['kind'] == 'observed_range'
    assert full_range['lower_floor'] == 1 and full_range['upper_floor'] == 52
    # This is deliberately highly correlated: adding marginal interval widths
    # would greatly overstate the uncertainty in the joint contrast.
    assert full_range['log_effect']['upper_95'] - full_range['log_effect']['lower_95'] < .2


def test_unmixed_floor_contrast_fails_gate(spline_train):
    design = m.floor.FeatureDesign(spline_train)
    _, inference = posterior_fixture(design)
    feature = design.features.index('listed_floor_spline_0')
    inference['posterior']['beta'][0, :, feature] += 5
    result = m.floor_contrasts(inference, design)
    assert not result['diagnostics']['acceptable']
    assert result['diagnostics']['max_rhat'] > 1.01


@pytest.mark.parametrize('fault', ['reordered', 'renamed', 'missing'])
def test_posterior_feature_coordinates_must_match_saved_design(spline_train, fault):
    design = m.floor.FeatureDesign(spline_train)
    _, inference = posterior_fixture(design)
    posterior = inference['posterior'].to_dataset()
    if fault == 'reordered':
        posterior = posterior.isel(feature=slice(None, None, -1))
    elif fault == 'renamed':
        names = deepcopy(design.features)
        names[-1] = 'unknown_feature'
        posterior = posterior.assign_coords(feature=names)
    else:
        posterior = posterior.isel(feature=slice(1, None))
    inference['posterior'] = posterior
    with pytest.raises(ValueError, match='coordinates'):
        m.floor_contrasts(inference, design)

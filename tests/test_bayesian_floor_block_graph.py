import numpy as np
import pytest
from models import bayesian_floor_block_graph as blocks
from models import bayesian_feature_graph_v3 as reference
from models import bayesian_floor_increment_design as floor
from models import bayesian_floor_elevator_design as elevator
from tests.test_bayesian_floor_elevator_design import data
from tests.test_bayesian_feature_graph_v3 import points


@pytest.mark.parametrize('mode', ['floor', 'pooled', 'separate'])
def test_exact_blocks_preserve_means_parameters_priors_density_gradient(mode):
    frame = data()
    design = floor.FeatureDesign(frame) if mode == 'floor' else elevator.FeatureDesign(frame, mode=mode)
    matrix = design.matrix(frame)
    parts = blocks.compress_blocks(matrix, design.features)
    reconstructed = np.empty_like(matrix)
    for _, columns, unique, inverse in parts:
        reconstructed[:, columns] = unique[inverse]
    np.testing.assert_array_equal(reconstructed, matrix)
    assert sorted(np.concatenate([p[1] for p in parts])) == list(range(matrix.shape[1]))
    beta = np.random.default_rng(41).normal(size=matrix.shape[1])
    mu = sum((unique @ beta[cols])[inv] for _, cols, unique, inv in parts)
    np.testing.assert_allclose(mu, matrix @ beta, rtol=1e-13, atol=1e-13)
    old = reference.build_model(frame, design, prior_multiplier=1.3)
    new = blocks.build_model(frame, design, prior_multiplier=1.3)
    assert old.coords == new.coords
    assert old.named_vars_to_dims == new.named_vars_to_dims
    assert old.graph_configuration == new.graph_configuration
    assert [rv.name for rv in old.free_RVs] == [rv.name for rv in new.free_RVs]
    assert [v.name for v in old.value_vars] == [v.name for v in new.value_vars]
    for key, value in old.initial_point().items():
        np.testing.assert_array_equal(value, new.initial_point()[key])
    functions = [(m.compile_logp(mode='FAST_COMPILE'), m.compile_dlogp(mode='FAST_COMPILE'),
                  m.compile_logp(vars=m.free_RVs, sum=False, mode='FAST_COMPILE')) for m in (old, new)]
    for point in points(old):
        np.testing.assert_allclose(functions[0][0](point), functions[1][0](point), rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(functions[0][1](point), functions[1][1](point), rtol=1e-11, atol=1e-9)
        for a, b in zip(functions[0][2](point), functions[1][2](point)):
            np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize('matrix,names', [([[1, 2]], ['listed_floor_gt_1']),
    ([[1, 2]], ['listed_floor_gt_1']*2), ([[np.nan]], ['listed_floor_gt_1']), ([[1]], ['other'])])
def test_invalid_partition_rejected(matrix, names):
    with pytest.raises(ValueError):
        blocks.compress_blocks(matrix, names)

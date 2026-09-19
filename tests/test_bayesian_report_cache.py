from types import SimpleNamespace
import numpy as np
import pytest
import xarray as xr
from models.bayesian_report_cache import UnitSamples, bounded_unit_samples, build_cache


def posterior():
    values = np.arange(2*65*1030, dtype=float).reshape(2, 65, 1030)/100
    return xr.Dataset({'unit_z': (('chain', 'draw', 'unit'), values)},
        coords={'chain': [0, 1], 'draw': np.arange(65), 'unit': ['u'+str(i) for i in range(1030)]})


def test_all_draws_order_scaling_repeated_indices_and_replay(tmp_path):
    p = posterior(); expected = p.unit_z.values.reshape(130, 1030)
    values, meta = build_cache(p, tmp_path, 'sourcehash')
    assert values.flags.f_contiguous and meta['maximum_source_block_bytes'] <= 8*1024*1024
    np.testing.assert_array_equal(values, expected)
    lazy = UnitSamples(values); scale = np.linspace(.1, .5, 130)
    scaled = scale[:, None]*lazy
    assert isinstance(scaled, UnitSamples)
    for index in [0, 1029, [7, 1, 7, 1029], slice(500, 520)]:
        np.testing.assert_array_equal(lazy[:, index], expected[:, index])
        np.testing.assert_array_equal(scaled[:, index], (scale[:, None]*expected)[:, index])
    values._mmap.close()
    replay, saved = build_cache(p, tmp_path, 'sourcehash')
    assert saved == meta
    replay._mmap.close()
    with pytest.raises(ValueError, match='identity'): build_cache(p, tmp_path, 'other')


def test_context_restores_helper_after_failure(tmp_path):
    original = lambda p, name: 'small-variable'
    base = SimpleNamespace(sample_values=original, posterior_dataset=lambda x: x)
    with pytest.raises(RuntimeError):
        with bounded_unit_samples(base, posterior(), tmp_path, 'hash'):
            assert base.sample_values(None, 'alpha') == 'small-variable'
            assert isinstance(base.sample_values(None, 'unit_z'), UnitSamples)
            raise RuntimeError()
    assert base.sample_values is original


def test_unsupported_matrix_operation_cannot_silently_materialize_all_units():
    x = UnitSamples(np.ones((10, 20)))
    with pytest.raises(TypeError): np.add(x, 1)
    with pytest.raises(ValueError): np.ones((10, 20))*x


def test_scientific_reports_are_byte_identical_with_disk_unit_access(tmp_path):
    from tests.test_bayesian_feature_model import train
    from models import bayesian_feature_experiment_v2 as reports
    frame = train.__wrapped__().copy()
    frame['audit_id'] = ['a'+str(i) for i in range(len(frame))]
    frame['source_listing_id'] = ['s'+str(i) for i in range(len(frame))]
    design = reports.feature.FeatureDesign(frame, 'full_half_balance')
    d = design.time; rng = np.random.default_rng(5721); shape = (4, 150)
    coords = {'feature': design.features, 'building': d.buildings, 'unit': d.unit_ids,
              'trend_basis': np.arange(d.time_matrix.shape[1]), 'season_basis': np.arange(d.season_matrix.shape[1])}
    variables = {name: (('chain', 'draw'), value+rng.normal(0, .01, shape)) for name, value in
                 [('alpha', 8.4), ('sigma_unit', .2), ('annual_drift', .03)]}
    for name, dim in [('beta', 'feature'), ('unit_z', 'unit'), ('building_effect', 'building'),
                      ('trend_coefficients', 'trend_basis'), ('season_coefficients', 'season_basis')]:
        variables[name] = (('chain', 'draw', dim), rng.normal(0, .03, (*shape, len(coords[dim]))))
    stats = xr.Dataset({'energy': (('chain', 'draw'), rng.normal(size=shape)),
        'diverging': (('chain', 'draw'), np.zeros(shape, dtype=bool)),
        'maxdepth_reached': (('chain', 'draw'), np.zeros(shape, dtype=bool))})
    inference = xr.DataTree.from_dict({'posterior': xr.Dataset(variables, coords=coords), 'sample_stats': stats})
    original = tmp_path/'original'; cached = tmp_path/'cached'; original.mkdir(); cached.mkdir()
    reports.write_reports(original, inference, design, frame, 'protocol')
    with bounded_unit_samples(reports.base, inference, tmp_path/'cache', 'source'):
        reports.write_reports(cached, inference, design, frame, 'protocol')
    assert {p.name for p in original.iterdir()} == {p.name for p in cached.iterdir()}
    for file in original.iterdir():
        assert file.read_bytes() == (cached/file.name).read_bytes(), file.name

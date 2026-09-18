"""Value effects must be distinguishable from amenity reporting patterns."""
import json

import numpy as np
import pandas as pd
import pytest

from models import amenity_ablation as ablation
from models import amenity_rent_model as model
from models import minimal_rent_model as baseline
from apartments.research_pipeline import publish_bundle


def sample():
    rows = []
    for year in (2017, 2018, 2019):
        for unit in range(30):
            rows.append(dict(unit_id=f'u{unit}', building=f'b{unit//2}',
                audit_id=f'{year}-{unit}', period=pd.Timestamp(year, 1, 1),
                bedrooms=1., bathrooms=1., square_feet=600.,
                asking_rent=3000.+100*(unit%3), laundry_type=('none','in_unit',None)[unit%3],
                physical_floor=unit%5+1, elevator=bool(unit%2)))
    data = pd.DataFrame(rows)
    data['log_rent'] = np.log(data.asking_rent)
    return data


def test_missingness_ignores_known_values_but_tracks_unknowns():
    data = sample()
    encoder = ablation.encoder_class('missingness')(data)
    rows = pd.concat([data.iloc[:1]]*3, ignore_index=True)
    rows['laundry_type'] = ['none', 'in_unit', None]
    encoded = encoder.matrix(rows).toarray()
    assert np.array_equal(encoded[0], encoded[1])
    assert not np.array_equal(encoded[0], encoded[2])
    full = ablation.encoder_class('full')(data)
    assert not np.array_equal(full.matrix(rows).toarray()[0], full.matrix(rows).toarray()[1])


def test_block_enables_only_its_values_and_all_missingness():
    encoder = ablation.encoder_class('laundry')(sample())
    mask = dict(zip(encoder.amenity_features, encoder.amenity_active_columns))
    assert mask['laundry_type=in_unit']
    assert not mask['physical_floor']
    assert mask['physical_floor.unknown']


def test_saved_mask_roundtrips(tmp_path):
    data = sample()
    fitted = baseline.fit(data, model.SETTINGS, iterations=12,
                          encoder_class=ablation.encoder_class('missingness'))
    publish_bundle(tmp_path, {'models.json':json.dumps({'amenities':{
        'encoder':fitted['encoder'].metadata(), 'beta':fitted['beta'].tolist(),
        'center':fitted['center']}}, sort_keys=True)}, {'version':ablation.VERSION})
    loaded = model.load_fit(tmp_path)
    assert np.allclose(baseline.predict(loaded, data), baseline.predict(fitted, data))
    assert loaded['encoder'].ablation_variant == 'missingness'


def test_single_known_category_cannot_reencode_missingness():
    data = sample()
    data['laundry_type'] = ['in_unit' if i%2 else None for i in range(len(data))]
    # Remove genuinely varying numeric values too, leaving only reporting signals.
    data['physical_floor'] = 1
    data['elevator'] = True
    full = ablation.encoder_class('full')(data, unit_effect=False)
    missing = ablation.encoder_class('missingness')(data, unit_effect=False)
    assert np.array_equal(full.matrix(data).toarray(), missing.matrix(data).toarray())
    fitted = [baseline.fit(data, model.SETTINGS, unit_effect=False, iterations=12,
                          encoder_class=ablation.encoder_class(v)) for v in ('full', 'missingness')]
    assert np.allclose(baseline.predict(fitted[0], data), baseline.predict(fitted[1], data))


def test_known_category_contrasts_center_on_training_and_zero_unknowns():
    data = sample()
    encoder = ablation.encoder_class('full')(data)
    start, _ = encoder.offsets['amenities']
    columns = [start+i for i, f in enumerate(encoder.amenity_features)
               if f.startswith('laundry_type=') and not f.endswith('__unknown__')]
    encoded = encoder.matrix(data).toarray()[:, columns]
    assert np.allclose(encoded.sum(axis=0), 0)
    assert np.allclose(encoded.sum(axis=1), 0)
    assert (encoded[data.laundry_type.isna()] == 0).all()


def test_crossed_splits_exclude_future_and_test_buildings():
    data = sample()
    for name, train, test in ablation.split_data(data, years=(), folds=range(5), cross_years=(2019,)):
        assert not set(train.building)&set(test.building)
        assert not set(train.unit_id)&set(test.unit_id)
        if name.startswith('year'):
            assert train.period.max() < test.period.min()
    assert sorted(ablation.building_fold(b) for b in data.building.unique()) == sorted(
        ablation.building_fold(b) for b in reversed(data.building.unique()))


def test_run_resume_and_protocol_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(model, 'load_analytical', lambda _: (sample(), {'fixture':True}, {}))
    kwargs = dict(years=(2019,), folds=(), unit_effect=False, min_rows=10)
    first = ablation.run(tmp_path/'input', tmp_path/'output', **kwargs)
    def forbidden(*args, **kwargs):
        raise AssertionError('Completed fits must not run again')
    monkeypatch.setattr(baseline, 'fit', forbidden)
    assert ablation.run(tmp_path/'input', tmp_path/'output', **kwargs) == first
    with pytest.raises(ValueError, match='Protocol changed'):
        ablation.run(tmp_path/'input', tmp_path/'output', **{**kwargs, 'unit_effect':True})


def test_pooled_building_analysis_covers_each_row_once(tmp_path, monkeypatch):
    from models.amenity_ablation_analysis import analyze
    data = sample()
    monkeypatch.setattr(model, 'load_analytical', lambda _: (data, {'fixture':True}, {}))
    ablation.run(tmp_path/'input', tmp_path/'experiment', years=(2019,), cross_years=(2019,),
                 unit_effect=False, min_rows=1)
    manifest = analyze(tmp_path/'experiment', tmp_path/'analysis')
    report = json.loads((tmp_path/'analysis'/'report.json').read_text())
    pooled = report['pooled_building_holdouts']
    assert pooled['rows'] == len(data)
    assert pooled['buildings'] == data.building.nunique()
    assert pooled['metrics']['full']['observations'] == len(data)
    assert pooled['comparisons']['full_minus_missingness']['resamples'] == 2000
    assert report['pooled_crossed_holdouts']['2019']['rows'] == 30
    assert analyze(tmp_path/'experiment', tmp_path/'analysis') == manifest

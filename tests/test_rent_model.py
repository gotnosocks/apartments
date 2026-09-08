"""Data-selection regressions; these tests never run the sampler."""
from pathlib import Path
import importlib.util

import pytest
pytest.importorskip('pymc')
from apartments.db import connect
from apartments.streeteasy import ingest_item

spec = importlib.util.spec_from_file_location('chelsea_model', Path(__file__).parents[1] / 'models/rent_model.py')
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def test_all_buildings_missing_covariates_and_furnished_unit_exclusion(tmp_path):
    path = tmp_path / 'model.duckdb'
    db = connect(path)
    for building, unit, furnished in [('new-building', '1203', False), ('another-new-building', 'PH', False), ('furnished-building', '2A', True)]:
        item = {'source':'streeteasy','building_slug':building,'source_listing_id':f'{building}/{unit}',
                'unit':unit,'address':'1 West 20th Street','captured_at':'2026-09-08T00:00:00Z',
                'home_features':['FURNISHED'] if furnished else [], 'attributes':{},
                'price_history':[{'date':'2010-01-01','base_rent':2000,'event':'Listed'},
                                 {'date':'2010-01-01','base_rent':2000,'event':'Active'},
                                 {'date':'2010-01-20','base_rent':4000,'event':'Changed'},
                                 {'date':'2026-01-01','base_rent':5000,'event':'Listed'}]}
        ingest_item(item,connection=db)
    db.close()
    data, periods = model.prepare_data(path)
    assert set(data.building_slug) == {'new-building','another-new-building'}
    assert data.floor_level.eq(-1).all()
    assert data.sqft_missing.eq(1).all()
    assert data.log_sqft_z.eq(0).all()
    assert data.period.min().year == 2010
    assert set(data.loc[data.period.dt.year.eq(2010),'asking_rent']) == {3000}
    assert data.attrs['coverage']['furnished_units_excluded'] == 1
    assert data[model.FEATURES].to_numpy(dtype=float).shape == (4,6)

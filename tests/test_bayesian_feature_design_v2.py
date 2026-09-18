"""Real roundtrip regression: sorted JSON metadata must not permute beta columns."""
import json

import numpy as np
import pandas as pd
import pytest

from models.bayesian_feature_model import FeatureDesign
from models.bayesian_feature_design_v2 import load_design


@pytest.fixture
def data():
    rng = np.random.default_rng(867)
    n=300
    full=rng.integers(1,5,n); half=rng.integers(0,3,n)
    return pd.DataFrame({'period':pd.date_range('2020-01-01',periods=36,freq='MS').take(np.arange(n)%36),
        'unit_id':['u'+str(i%40) for i in range(n)], 'building':['b'+str(i%5) for i in range(n)],
        'bedrooms':rng.integers(0,6,n).astype(float), 'bathrooms':full+half/2,
        'reported_full_bathrooms':full,'reported_half_bathrooms':half,
        'bathroom_count_evidence':[{'flags':[]} for _ in range(n)],
        'square_feet':rng.uniform(400,2400,n),'asking_rent':rng.uniform(2000,14000,n),
        'listed_floor':rng.integers(1,20,n), 'elevator':rng.choice([True,False,None],n),
        'laundry_type':rng.choice(['in_unit','in_building',None],n),
        'doorman_type':rng.choice(['full_time','part_time',None],n),
        'hvac_type':rng.choice(['central','window_units',None],n)})


@pytest.mark.parametrize('spec',['linear_total','incremental_total','full_half','full_half_balance'])
def test_sorted_serialization_roundtrip_preserves_every_named_column(data,tmp_path,spec):
    trained=FeatureDesign(data,spec)
    trained.save(tmp_path)
    unsafe=FeatureDesign.load(tmp_path)
    safe=load_design(tmp_path,data)
    assert unsafe.raw_features(data)[1] != trained.raw_features(data)[1]
    np.testing.assert_array_equal(safe.matrix(data), trained.matrix(data))
    assert safe.raw_features(data)[1] == trained.raw_features(data)[1]
    beta=np.arange(len(trained.features),dtype=float)/100
    np.testing.assert_array_equal(safe.matrix(data)@beta, trained.matrix(data)@beta)


def test_unexpected_saved_column_inventory_refused(data,tmp_path):
    trained=FeatureDesign(data);trained.save(tmp_path)
    path=tmp_path/'feature-design.json';meta=json.loads(path.read_text())
    meta['features'][0]='not_the_fitted_feature'
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='training feature order'):
        load_design(tmp_path,data)


def test_versioned_floor_loader_preserves_order_and_rejects_wrong_prior(data,tmp_path):
    from models import bayesian_floor_increment_design as floor
    design=floor.FeatureDesign(data);design.save(tmp_path)
    protocol={'version':'observable-bayesian-floor-experiment-v4',
              'feature_design_version':floor.VERSION,'floor_increment_prior_scale':.15}
    restored=load_design(tmp_path,data,protocol)
    np.testing.assert_array_equal(restored.matrix(data),design.matrix(data))
    protocol['floor_increment_prior_scale']=.05
    with pytest.raises(ValueError,match='prior'):load_design(tmp_path,data,protocol)

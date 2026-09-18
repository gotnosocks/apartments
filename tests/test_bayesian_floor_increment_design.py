import json

import numpy as np
import pandas as pd
import pytest

from models.bayesian_feature_model import FeatureDesign as Previous
from models.bayesian_floor_increment_design import FeatureDesign, listed_floor_values


@pytest.fixture
def train():
    rng=np.random.default_rng(494);n=400
    full=rng.integers(1,5,n);half=rng.integers(0,3,n)
    return pd.DataFrame({'period':pd.date_range('2020-01-01',periods=36,freq='MS').take(np.arange(n)%36),
        'unit_id':['u'+str(i%70) for i in range(n)],'building':['b'+str(i%8) for i in range(n)],
        'bedrooms':rng.integers(0,6,n).astype(float),'bathrooms':full+half/2,
        'reported_full_bathrooms':full,'reported_half_bathrooms':half,
        'bathroom_count_evidence':[{'flags':[]} for _ in range(n)],
        'square_feet':rng.uniform(400,2400,n),'asking_rent':rng.uniform(2000,14000,n),
        'listed_floor':rng.choice([-1.,0.,1.,3.,np.nan],n),
        'elevator':rng.choice([True,False,None],n),
        'laundry_type':rng.choice(['in_unit','in_building',None],n)})


def cases(train,floors):
    result=pd.concat([train.iloc[[0]]]*len(floors),ignore_index=True)
    result['listed_floor']=floors
    return result


def test_exact_increment_boundary_negative_ground_gaps_and_unknown(train):
    design=FeatureDesign(train)
    assert design.floor_levels==[-1.,0.,1.,3.]
    assert design.floor_thresholds==[-1.,0.,1.]
    matrix,names,_=design.raw_features(cases(train,[-1,0,1,3,None]))
    floor_names=['listed_floor_gt_-1','listed_floor_gt_0','listed_floor_gt_1','listed_floor.unknown']
    np.testing.assert_array_equal(matrix[:,[names.index(n) for n in floor_names]],
        [[0,0,0,0],[1,0,0,0],[1,1,0,0],[1,1,1,0],[0,0,0,1]])
    assert 'listed_floor' not in names and 'listed_floor' not in design.numeric
    assert not any('physical_floor' in name for name in design.features)
    gap=design.floor_support['adjacent_supported_contrasts'][-1]
    assert (gap['lower_supported_level'],gap['upper_supported_level'])==(1,3)
    assert gap['has_unobserved_integer_labels_between']
    beta=np.zeros(len(design.features));beta[[design.features.index(n) for n in floor_names[:-1]]]=[.1,-.05,.2]
    predictions=design.matrix(cases(train,[-1,0,1,3]))@beta
    np.testing.assert_allclose(np.diff(predictions),[.1,-.05,.2],atol=1e-14)


@pytest.mark.parametrize('spec',['linear_total','incremental_total','full_half','full_half_balance'])
def test_every_nonfloor_column_and_prior_exactly_unchanged(train,spec):
    previous=Previous(train,spec);design=FeatureDesign(train,spec)
    old,oldnames,oldscales=previous.raw_features(train)
    new,newnames,newscales=design.raw_features(train)
    for i,name in enumerate(oldnames):
        if name in ('listed_floor','listed_floor.unknown'):continue
        j=newnames.index(name)
        np.testing.assert_array_equal(old[:,i],new[:,j])
        assert oldscales[i]==newscales[j]
        if name in previous.features:
            np.testing.assert_array_equal(previous.matrix(train)[:,previous.features.index(name)],
                                          design.matrix(train)[:,design.features.index(name)])
    np.testing.assert_array_equal(previous.time.time_matrix,design.time.time_matrix)


def test_alias_and_physical_height_are_independent(train):
    data=train.copy();data['advertised_floor']=data.listed_floor;data['listed_floor']=None
    np.testing.assert_array_equal(listed_floor_values(data),listed_floor_values(train))
    data['floors_above_ground']=900  # Does not fill absent advertised values.
    np.testing.assert_array_equal(listed_floor_values(data),listed_floor_values(train))
    data.loc[0,'listed_floor']=0;data.loc[0,'advertised_floor']=3
    assert listed_floor_values(data)[0]==0


@pytest.mark.parametrize('floor',[-2,2,4,100])
def test_unobserved_floor_rejected_at_raw_and_public_transform(train,floor):
    design=FeatureDesign(train)
    with pytest.raises(ValueError,match='absent from fitted support'):design.matrix(cases(train,[floor]))
    with pytest.raises(ValueError,match='absent from fitted support'):design.raw_features(cases(train,[floor]))


def test_level_and_adjacent_endpoint_support(train):
    design=FeatureDesign(train)
    assert sum(v['rows'] for v in design.floor_support['levels'])==train.listed_floor.notna().sum()
    for item in design.floor_support['levels']:
        rows=train.loc[train.listed_floor.eq(item['level'])]
        assert item['units']==rows.unit_id.nunique() and item['buildings']==rows.building.nunique()
    for item in design.floor_support['adjacent_supported_contrasts']:
        lo=set(train.loc[train.listed_floor.eq(item['lower_supported_level']),'building'])
        hi=set(train.loc[train.listed_floor.eq(item['upper_supported_level']),'building'])
        assert item['shared_buildings']==len(lo&hi)


def test_explicit_column_order_roundtrip(train,tmp_path):
    design=FeatureDesign(train,floor_increment_prior_scale=.08);design.save(tmp_path)
    restored=FeatureDesign.load(tmp_path)
    assert restored.raw_feature_names==design.raw_feature_names
    np.testing.assert_array_equal(restored.matrix(train),design.matrix(train))
    np.testing.assert_array_equal(restored.prior_scales,design.prior_scales)
    assert restored.floor_support==design.floor_support
    assert restored.floor_policy['cumulative_extreme_log_prior_sd']==.08*np.sqrt(3)


@pytest.mark.parametrize('fault',['thresholds','features','numeric_order','category_order','raw_order','priors','active','version'])
def test_saved_order_and_encoding_tamper_rejected(train,tmp_path,fault):
    design=FeatureDesign(train);design.save(tmp_path)
    path=tmp_path/'feature-design.json';meta=json.loads(path.read_text())
    if fault=='thresholds':meta['floor_thresholds']=[-1.,1.]
    if fault=='features':meta['features']=meta['features'][::-1]
    if fault=='numeric_order':meta['numeric_order']=meta['numeric_order'][::-1]
    if fault=='category_order':meta['category_order']=meta['category_order'][::-1]
    if fault=='raw_order':meta['raw_feature_names']=meta['raw_feature_names'][::-1]
    if fault=='priors':meta['floor_increment_prior_scale']=.4
    if fault=='active':meta['active']=[int(v) for v in meta['active']]
    if fault=='version':meta['version']='unsupported'
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError):FeatureDesign.load(tmp_path)


@pytest.mark.parametrize('floor',[None,0,-1])
def test_all_unknown_or_single_supported_level_adds_no_fabricated_thresholds(train,floor):
    data=train.copy();data['listed_floor']=floor
    design=FeatureDesign(data)
    assert design.floor_thresholds==[]
    assert not any(name.startswith('listed_floor_gt_') for name in design.features)
    assert np.isfinite(design.matrix(data)).all()


@pytest.mark.parametrize('scale',[0,-1,float('nan'),float('inf'),True])
def test_invalid_increment_prior_rejected(train,scale):
    with pytest.raises(ValueError,match='prior scale'):FeatureDesign(train,floor_increment_prior_scale=scale)


def test_independently_observed_physical_floor_and_gap_columns_preserved(train):
    data=train.copy();rng=np.random.default_rng(723)
    data['physical_floor']=rng.choice([0.,1.,2.,4.,np.nan],len(data))
    old=Previous(data);new=FeatureDesign(data)
    oldmat,oldnames,_=old.raw_features(data);newmat,newnames,_=new.raw_features(data)
    for name in ('physical_floor','physical_floor.unknown','physical_floor_x_elevator',
                 'physical_floor_x_elevator.unknown','floor_label_gap','floor_label_gap.unknown'):
        np.testing.assert_array_equal(oldmat[:,oldnames.index(name)],newmat[:,newnames.index(name)])
    np.testing.assert_array_equal(listed_floor_values(data),listed_floor_values(train))

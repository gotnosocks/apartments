import importlib.util
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

spec=importlib.util.spec_from_file_location('minimal_rent_model',Path(__file__).parents[1]/'models/minimal_rent_model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_own_initial_event_dedup_uses_advertisement_attributes(tmp_path):
    (tmp_path/'complete.json').write_text(json.dumps({'unit_association_rule':'canonical-url-v1'}))
    listings=[]
    for sid,lid,beds in [(1,'1',1),(2,'1',1),(3,'2',3)]:
        listings.append({'snapshot_id':sid,'listing_id':lid,'bedrooms':beds,'bathrooms':1.,'square_feet':None,
                         'features_json':None,'pricing_json':'{}','raw_listing_json':'{}',
                         'collected_at':1789000000.,'listing_type':'rental'})
    # The latest unit advertisement repeats an old listing's history, but must
    # never lend its three-bedroom attributes to that older one-bedroom ad.
    events=[{'snapshot_id':sid,'event_listing_id':'1','event_date':'2020-01-02','price':2000.,'status':'ACTIVE','event_category':'rental'} for sid in [1,2,3]]
    events += [{'snapshot_id':3,'event_listing_id':'2','event_date':'2026-02-01','price':6000.,'status':'ACTIVE','event_category':'rental'},
               {'snapshot_id':1,'event_listing_id':'1','event_date':'2020-02-01','price':1900.,'status':'ACTIVE','event_category':'rental'}]
    members=[{'listing_id':lid,'unit_id':'u','canonical_unit_url':'https://streeteasy.com/building/a/1'} for lid in ['1','2']]
    for name,rows in [('listing_observations',listings),('event_mentions',events),('rental_unit_memberships',members)]:
        path=tmp_path/name;path.mkdir();pq.write_table(pa.Table.from_pylist(rows),path/'part.parquet')
    data=m.load_source(tmp_path).set_index('listing_id')
    assert len(data)==2
    assert data.loc['1','bedrooms']==1 and data.loc['1','asking_rent']==2000
    assert data.loc['2','bedrooms']==3 and data.loc['2','asking_rent']==6000
    assert data.loc['1','capture_count']==2 and not data.loc['1','price_conflict']


def fixture():
    rng=np.random.default_rng(12);n=240
    data=pd.DataFrame({'unit_id':['u'+str(i%12) for i in range(n)],
                       'building':['b'+str(i%3) for i in range(n)],
                       'period':pd.date_range('2020-01-01',periods=24,freq='MS').repeat(10),
                       'bedrooms':rng.integers(0,4,n).astype(float),'bathrooms':1.,
                       'square_feet':np.nan,'asking_rent':3000.})
    data['log_rent']=8.+.2*data.bedrooms+.01*np.arange(n)/10+rng.normal(0,.03,n)
    data['asking_rent']=np.exp(data.log_rent)
    return data


def test_train_only_encoding_unknown_units_and_sparse_fit(tmp_path):
    train=fixture();model=m.fit(train,{'building_penalty':10,'unit_penalty':8,'trend_penalty':100})
    test=train.iloc[:2].copy();test['unit_id']='unseen';test['building']='unknown';test['period']=pd.Timestamp('2025-06-01')
    assert np.isfinite(m.predict(model,test)).all()
    assert np.sqrt(np.mean((m.predict(model,train)-train.log_rent)**2))<.06
    enc=model['encoder']
    assert enc.size_default==700 and enc.size_medians=={}
    a,b=enc.offsets['unit'];x=enc.matrix(test)
    assert x[:,a:b].nnz==0
    a,b=enc.offsets['trend'];assert (x[:,b-1].toarray()==1).all()
    # Test-set sizes and prices cannot change training transformations.
    before=enc.metadata();test['square_feet']=1e9;test['asking_rent']=1e12
    enc.matrix(test)
    assert enc.metadata()==before


def test_model_round_trip_and_contemporaneous_baseline(tmp_path):
    train=fixture();train['listing_ids']='["1"]'
    model=m.fit(train,{'building_penalty':10,'unit_penalty':8,'trend_penalty':100})
    np.savez_compressed(tmp_path/'model.npz',beta=model['beta'],center=model['center'])
    (tmp_path/'encoder.json').write_text(json.dumps(model['encoder'].metadata()))
    restored=m.load_model(tmp_path)
    assert np.allclose(m.predict(model,train),m.predict(restored,train))
    scores,table=m.comparison(train,train,model,contemporaneous=True)
    expected=train.groupby(['period','bedrooms']).asking_rent.median()
    assert table.bedroom_baseline.iloc[0]==expected.loc[(train.period.iloc[0],train.bedrooms.iloc[0])]
    assert model['robust_objective_relative_change']<1e-5


def test_incremental_bedrooms_sum_adjacent_increments():
    data=fixture().iloc[:6].copy();data['bedrooms']=np.arange(6,dtype=float)
    enc=m.Encoder(data);matrix=enc.matrix(data)
    expected=np.array([[float(b>threshold) for threshold in range(5)] for b in range(6)])
    assert enc.features[1:6]==[f'bedrooms_gt_{n}' for n in range(5)]
    assert np.array_equal(matrix[:,1:6].toarray(),expected)
    beta=np.zeros(enc.n_parameters);increments=np.array([.20,.15,.12,.10,.08]);beta[1:6]=increments
    assert np.allclose(np.diff(matrix@beta),increments)
    assert enc.metadata()['bedroom_encoding']=='incremental'


def test_legacy_saved_categorical_model_keeps_original_predictions(tmp_path):
    data=fixture();enc=m.Encoder(data);enc.bedroom_encoding='categorical'
    enc.features[1:6]=[f'bedrooms_{n}' for n in range(1,6)]
    beta=np.zeros(enc.n_parameters);beta[1:6]=[.2,.35,.45,.5,.55]
    original=enc.matrix(data)@beta+8
    metadata=enc.metadata();metadata.pop('bedroom_encoding')
    (tmp_path/'encoder.json').write_text(json.dumps(metadata))
    np.savez_compressed(tmp_path/'model.npz',beta=beta,center=8.)
    assert np.allclose(m.predict(m.load_model(tmp_path),data),original)

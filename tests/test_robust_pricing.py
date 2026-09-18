"""Serving must reproduce the scientific fit without importing its dependencies."""
import json
import math

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from apartments import robust_pricing, pricing
from apartments.candidate_search import select_candidates, score_candidates, market_comparison
from apartments.cli import app
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle, digest
from models import amenity_ablation as ablation
from models import amenity_rent_model as amenities
from models import minimal_rent_model as baseline


@pytest.fixture
def fitted():
    rows=[]
    for period in pd.date_range('2017-01-01','2019-12-01',freq='MS'):
        for unit in range(12):
            rent=2800.+200*unit+20*(period.year-2017)
            rows.append(dict(unit_id=f'u{unit}',building=f'b{unit//3}',building_id=f'b{unit//3}',
                period=period,asking_rent=rent,log_rent=np.log(rent),bedrooms=unit%3,
                bathrooms=1.+.5*(unit%2),square_feet=None if unit%3==0 else 500.+50*unit,
                listed_floor=unit+1,physical_floor=unit,elevator=bool(unit%2),
                laundry_type=['in_unit','in_building',None][unit%3],
                pet_rules=['not_allowed','approval_required',None][unit%3],
                window_exposures={'south':bool(unit%2)}))
    train=pd.DataFrame(rows)
    fitted=baseline.fit(train,amenities.SETTINGS,iterations=20,encoder_class=ablation.encoder_class('full'))
    artifact={'version':robust_pricing.VERSION,'encoder':fitted['encoder'].metadata(),
              'coefficients':fitted['beta'].tolist(),'center':fitted['center'],
              'training':{'knowledge_cutoff':'2020-01-01T00:00:00Z',
                          'source_listing_ids':['listing-u0'],
                          'unit_buildings':{f'u{i}':f'b{i//3}' for i in range(12)}},
              'validation':{'max_serving_horizon_months':1}}
    return train,fitted,artifact


def bundle(root,artifact):
    publish_bundle(root,{'model.json':canonical(artifact)+'\n'},
                   {'model_version':robust_pricing.VERSION,'runtime_sha256':digest(robust_pricing.__file__),
                    'pricing_features_sha256':digest(pricing.__file__)})
    return root


def test_portable_parity_components_and_joint_floor_interaction(fitted):
    train,scientific,artifact=fitted
    portable=robust_pricing.RobustPricingModel(json.loads(canonical(artifact)))
    test=train.tail(12).copy();test['period']=pd.Timestamp('2020-01-01')
    test.loc[test.index[0],['unit_id','building','building_id']]=['new','new-b','new-b']
    test.loc[test.index[1],['unit_id','laundry_type']]=['new-2','unseen_laundry']
    expected=np.exp(baseline.predict(scientific,test))
    actual=[portable.predict(r,'2020-01') for r in test.to_dict('records')]
    np.testing.assert_allclose([r['predicted_rent'] for r in actual],expected,rtol=1e-12)
    assert actual[0]['familiarity']=='new_building'
    assert actual[0]['uncertainty']['status']=='unsupported_new_building'
    assert actual[0]['uncertainty']['interval'] is None
    assert actual[1]['familiarity']=='new_unit_seen_building'
    for row in actual:
        assert math.exp(math.fsum(row['log_components'].values()))==pytest.approx(row['predicted_rent'])
    record=test.iloc[2].to_dict();changes={'physical_floor':9,'elevator':True}
    contrast=portable.marginal_contributions(record,changes,'2020-01')
    pair=pd.DataFrame([record,{**record,**changes}]);scientific_pair=np.exp(baseline.predict(scientific,pair))
    assert contrast['dollar_change']==pytest.approx(scientific_pair[1]-scientific_pair[0],abs=1e-8)
    assert portable.marginal_contributions(record,{'laundry_type':'in_unit'},'2020-01')['status']=='unknown_attribute_contrast'
    with pytest.raises(ValueError,match='identity/date'):
        portable.marginal_contributions(record,{'building_id':'new'},'2020-01')


def capture(unit='u0',**changes):
    return dict(unit_id=unit,building_id='b0',rent=3000,bedrooms=1,bathrooms=1,
                source='streeteasy',source_listing_id='listing-'+unit,
                collected_at='2020-01-04T00:00:00Z',listing_status='ACTIVE',
                price_basis='gross_advertised_rent',capture_id='capture-'+unit,
                elevator=True,**changes)


def test_latest_inactive_conflicting_stale_and_future_captures():
    active=capture()
    inactive={**active,'collected_at':'2020-01-05','listing_status':'INACTIVE'}
    stale={**capture('stale'),'collected_at':'2019-12-01'}
    future={**capture('future'),'collected_at':'2020-01-07'}
    conflict=capture('conflict');other={**conflict,'rent':3500}
    good=capture('good')
    selected,rejected,stats=select_candidates([active,inactive,stale,future,conflict,other,good,good],
                                               as_of='2020-01-06',max_age_days=7)
    assert [r['unit_id'] for r in selected]==['good']
    assert stats['superseded_observations']==1 and stats['identical_latest_duplicates']==1
    assert stats['exclusion_counts']=={'conflicting_latest_capture':2,'latest_capture_not_confirmed_active':1,
                                       'not_known_at_cutoff':1,'stale_capture':1}
    # A later-knowledge observation cannot replace the earlier known snapshot.
    new={**active,'collected_at':'2020-01-05','known_at':'2020-01-08','listing_status':'INACTIVE'}
    selected,_,_=select_candidates([active,new],as_of='2020-01-06')
    assert selected[0]['unit_id']=='u0'
    selected,_,_=select_candidates([active,new],as_of='2020-01-09')
    assert not selected


def test_old_advertisement_does_not_supersede_active_episode_and_conflicts_precede_budget():
    active=capture()
    old={**active,'source_listing_id':'older-ad','collected_at':'2020-01-05','listing_status':'INACTIVE'}
    selected,_,_=select_candidates([active,old],as_of='2020-01-06')
    assert selected[0]['source_listing_id']=='listing-u0'
    duplicate={**active,'source_listing_id':'another-active-ad','collected_at':'2020-01-05'}
    selected,_,stats=select_candidates([active,old,duplicate],as_of='2020-01-06')
    assert len(selected)==1 and len(selected[0]['active_advertisement_evidence'])==2
    assert stats['compatible_active_advertisements_merged']==1
    expensive={**duplicate,'rent':4000}
    selected,_,stats=select_candidates([active,expensive],as_of='2020-01-06',budget=3200)
    assert not selected
    assert stats['exclusion_counts']=={'conflicting_active_advertisements':2}


def test_fresh_search_cli_keeps_preferences_separate_and_replays(tmp_path,fitted):
    _,_,artifact=fitted;model=bundle(tmp_path/'model',artifact)
    candidates=tmp_path/'candidates.jsonl';prefs=tmp_path/'prefs.json'
    records=[capture('u0'),{**capture('u1'),'rent':3100,'elevator':False},
             {**capture('u2'),'rent':3400,'elevator':True},
             {**capture('cold'),'building_id':'unseen','rent':2800,'elevator':None}]
    candidates.write_text(''.join(canonical(r)+'\n' for r in records));prefs.write_text('{"elevator":200}')
    output=tmp_path/'scores'
    args=[str(candidates),str(prefs),str(model),str(output),'--as-of','2020-01-06','--budget','3200']
    response=CliRunner().invoke(app,['score-apartments',*args])
    assert response.exit_code==0,response.output
    manifest=json.loads(response.output)
    assert score_candidates(candidates,prefs,output,model_bundle=model,as_of='2020-01-06',budget=3200)==manifest
    rankings=[json.loads(s) for s in (output/'rankings.jsonl').read_text().split('\n') if s]
    assert rankings[0]['record']['unit_id']=='u0'
    assert rankings[0]['pareto_efficient']
    assert rankings[0]['market_comparison']['status']=='estimated'
    assert rankings[0]['market_comparison']['same_advertisement_in_training'] is True
    assert rankings[0]['market_comparison']['independent_valuation'] is False
    assert rankings[-1]['eligible'] is False
    assert rankings[-1]['market_comparison']['uncertainty']['status']=='unsupported_new_building'
    assert manifest['selection']['exclusion_counts']=={'over_budget':1}
    assert manifest['selection']['frontier_units']==1
    assert not rankings[0]['availability']['current_availability_verified']
    changed=json.loads(canonical(artifact));changed['center']+=.3
    other=bundle(tmp_path/'other-model',changed)
    score_candidates(candidates,prefs,tmp_path/'other-scores',model_bundle=other,as_of='2020-01-06',budget=3200)
    other_rows=[json.loads(s) for s in (tmp_path/'other-scores'/'rankings.jsonl').read_text().split('\n') if s]
    assert [(r['monthly_surplus'],r['pareto_efficient']) for r in rankings]==[(r['monthly_surplus'],r['pareto_efficient']) for r in other_rows]
    assert rankings[0]['market_comparison']['predicted_rent']!=other_rows[0]['market_comparison']['predicted_rent']


def test_model_clock_horizon_tampering_and_missing_capture_clock(tmp_path,fitted):
    _,_,artifact=fitted;model=robust_pricing.RobustPricingModel(artifact)
    assert market_comparison(model,capture(),as_of='2019-12-31')['status']=='model_not_known_at_cutoff'
    assert market_comparison(model,capture(),as_of='2020-02-01')['status']=='model_outside_serving_horizon'
    assert market_comparison(model,{**capture(),'bedrooms':6},as_of='2020-01-06')['status']=='unsupported_candidate_attributes'
    assert market_comparison(model,{**capture(),'building_id':'wrong-building'},as_of='2020-01-06')['status']=='unsupported_candidate_attributes'
    malformed=capture();del malformed['collected_at'];malformed['observed_at']='2020-01-04'
    selected,rejected,_=select_candidates([malformed],as_of='2020-01-06')
    assert not selected and rejected[0]['reason']=='missing_or_invalid_collection_knowledge_clock'
    root=bundle(tmp_path/'model',artifact);(root/'model.json').write_text('{}\n')
    with pytest.raises(ValueError,match='integrity'):
        robust_pricing.RobustPricingModel.load(root)

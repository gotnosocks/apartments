"""Calibration must reserve buildings and respect the outcome clock."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from models import building_transfer_validation as transfer
from models import amenity_rent_model as amenities
from models import minimal_rent_model as baseline


def buildings():
    result={i:[] for i in range(5)}
    for i in range(100):
        name=f'building-{i}';fold=transfer.ablation.building_fold(name)
        if len(result[fold])<2:
            result[fold].append(name)
    assert all(len(v)==2 for v in result.values())
    return result


def sample():
    rows=[]
    for date in pd.date_range('2016-01-01','2019-12-01',freq='MS'):
        for fold,names in buildings().items():
            for index,name in enumerate(names):
                rent=3000.+200*fold+100*index+5*(date.year-2016)
                rows.append(dict(building=name,unit_id=name+'-unit',audit_id=f'{name}-{date.date()}',
                    period=date,asking_rent=rent,log_rent=np.log(rent),bedrooms=1.,bathrooms=1.,square_feet=600.,
                    laundry_type='in_unit' if index else 'in_building'))
    return pd.DataFrame(rows)


def test_all_dates_of_calibration_and_evaluation_buildings_are_reserved():
    data=sample();origin=pd.Timestamp('2019-01-01')
    for fold in range(5):
        train,cal,test=transfer.partition(data,origin,fold)
        assert train.period.max()<origin
        assert cal.period.eq(origin).all() and test.period.eq(origin).all()
        assert set(train.building).isdisjoint(cal.building)
        assert set(train.building).isdisjoint(test.building)
        assert set(cal.building).isdisjoint(test.building)
        changed=data.copy();changed.loc[changed.building.isin(test.building),'asking_rent']=1e9
        newtrain,newcal,_=transfer.partition(changed,origin,fold)
        pd.testing.assert_frame_equal(train,newtrain);pd.testing.assert_frame_equal(cal,newcal)


def history():
    names=buildings()[1];rows=[]
    for date in pd.date_range('2018-01-01','2019-06-01',freq='MS'):
        for i in range(100):
            # The high-volume building has zero error; the rare one has a large
            # systematic premium. Row calibration must not pretend these are
            # 100 independent buildings.
            rows.append(dict(building=names[i==99],period=str(date.date()),prediction=3000.,
                             asking_rent=3000.*np.exp(.7 if i==99 else 0)))
    return pd.DataFrame(rows)


def test_building_balanced_quantiles_and_strict_past_only_calibration():
    hist=history();origin=pd.Timestamp('2019-01-01');kwargs=dict(calibration_fold=1,min_buildings=2)
    rule=transfer.rules(hist,origin,**kwargs)
    assert rule['row_weighted']['quantiles']['95']==[0.,0.]
    assert rule['building_balanced']['quantiles']['95']==pytest.approx([0.,.7])
    assert rule['building_balanced']['rows']==1200 and rule['building_balanced']['months']==12
    changed=hist.copy();changed.loc[changed.period>='2019-01-01','asking_rent']=1e10
    assert transfer.rules(changed,origin,**kwargs)==rule
    assert rule['building_balanced']['end']=='2018-12-01'
    bad=hist.copy();bad.loc[0,'building']=buildings()[0][0]
    with pytest.raises(ValueError,match='reserved fold'):
        transfer.rules(bad,origin,**kwargs)
    unavailable=transfer.rules(hist,origin,calibration_fold=1,min_buildings=3)
    assert all(r['status']=='unavailable' for r in unavailable.values())
    with pytest.raises(ValueError,match='positive weights'):
        transfer.quantile([0,1],[0,1],[.5])


def test_interval_scoring_denominators_and_building_equal_weight():
    hist=history().iloc[:100].copy()
    hist['unit_id']=hist.building;hist['audit_id']=range(100)
    rule={p:{'status':'estimated','quantiles':{'80':[-.1,.1],'95':[-.1,.1]}} for p in transfer.POLICIES}
    table=transfer.add_bands(hist,rule)
    report=transfer.score(table)['intervals']['row_weighted']['95']
    assert report['coverage_percent']==99 and report['equal_building_coverage_percent']==50
    assert report['above_percent']==1 and report['buildings']==2
    unavailable=transfer.add_bands(hist,{p:{'status':'unavailable'} for p in transfer.POLICIES})
    report=transfer.score(unavailable)
    assert report['point']['observations']==100
    assert report['intervals']['row_weighted']['95']['unavailable_rows']==100


def test_resumable_real_fits_replayed_rules_and_binding_rejection(tmp_path,monkeypatch):
    data=sample()
    monkeypatch.setattr(amenities,'load_analytical',lambda _: (data,{'fixture':True},{}))
    kwargs=dict(start_year=2019,end_year=2019,folds=(0,),min_rows=1,min_buildings=1,min_months=1)
    root=tmp_path/'experiment'
    assert transfer.run(tmp_path,root,prepare_only=True,**kwargs)['fits']==120
    partial=transfer.run(tmp_path,root,max_new_months=2,**kwargs)
    assert partial['phase']=='paused_at_declared_limit' and partial['completed_months']==2
    result=transfer.run(tmp_path,root,**kwargs)
    assert result['completed_folds']==[0]
    report=json.loads((root/'fold-0/summary/report.json').read_text())
    assert report['pooled']['rows']==24 and len(report['months'])==12
    assert report['pooled']['intervals']['building_balanced']['95']['unavailable_rows']==0
    all_kwargs={**kwargs,'folds':tuple(range(5))}
    completed=transfer.run(tmp_path,root,**all_kwargs)
    summary=json.loads((root/'summary/report.json').read_text())
    assert summary['pooled']['rows']==120 and summary['pooled']['buildings']==10
    assert summary['natural_new_building']['rows']==0
    def forbidden(*args,**kwargs):
        raise AssertionError('Completed fits must not be repeated')
    monkeypatch.setattr(baseline,'fit',forbidden)
    assert transfer.run(tmp_path,root,**all_kwargs)==completed
    source=root/'fold-0/2018-01/fit';destination=root/'fold-0/2018-02/fit'
    shutil.rmtree(destination);shutil.copytree(source,destination)
    with pytest.raises(ValueError,match='membership or dependency'):
        transfer.run(tmp_path,root,**kwargs)


def test_protocol_support_threshold_changes_require_new_artifact(tmp_path,monkeypatch):
    monkeypatch.setattr(amenities,'load_analytical',lambda _: (sample(),{'fixture':True},{}))
    kwargs=dict(start_year=2019,end_year=2019,prepare_only=True)
    transfer.run(tmp_path,tmp_path/'run',**kwargs)
    with pytest.raises(ValueError,match='identity changed'):
        transfer.run(tmp_path,tmp_path/'run',min_buildings=31,**kwargs)

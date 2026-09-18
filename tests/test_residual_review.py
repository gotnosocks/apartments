"""Residuals guide source review without turning model errors into corrections."""
import math

import pytest

from models import residual_review as review


class Model:
    artifact={'training':{'current_capture_ids':['c']}}

    def predict(self,row,month):
        components={'center':math.log(3000),'building:b':.1,'unit:u':-.05,
                    'bedrooms_gt_0':.2,'amenity:laundry_type=in_unit':.03,
                    'amenity:window_exposures.north.unknown':-.01}
        return {'predicted_rent':math.exp(math.fsum(components.values())),
                'log_components':components,'warnings':[]}


def test_residual_sign_group_contributions_and_deliberate_training_inclusion():
    row=dict(audit_id='a',unit_id='u',building_id='b',source_listing_id='100',period='2026-09-01',
        asking_rent=5000,capture_id='c',analysis_price_basis='current_capture_gross_ask')
    result=review.residual(Model(),row)
    assert result['asking_minus_fitted']>0 and result['log_residual']>0
    assert math.exp(math.fsum(result['log_contributions_by_family'].values()))==pytest.approx(result['fitted_rent'])
    assert result['log_contributions_by_family']['missingness']==-.01
    assert result['current_capture_in_fit'] is True
    assert result['residual_type']=='in_sample_fitted_diagnostic'
    assert result['asking_vs_fitted_percent']==pytest.approx(100*(5000/result['fitted_rent']-1))


def test_review_tails_are_distinct_units_and_retain_all_current_rows():
    rows=[]
    for i,(unit,error,current) in enumerate([('u',2,False),('u',1.9,False),('v',1,False),
                                            ('w',-.9,False),('x',-.8,False),('y',.01,True)]):
        rows.append(dict(audit_id=str(i),unit_id=unit,log_residual=error,absolute_log_residual=abs(error),
                         current_capture=current))
    queue=review.review_queue(rows,top_units=2)
    assert {r['audit_id'] for r in queue}=={'0','2','3','4','5'}
    assert all(r['review_status']=='unreviewed' for r in queue)
    assert next(r for r in queue if r['audit_id']=='5')['selection_reasons']==['current_capture']
    with pytest.raises(ValueError,match='distinct units'):
        review.review_queue(rows,top_units=0)

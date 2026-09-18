"""Prior comparisons require identical source, contrasts and endpoint support."""
import copy
import pytest
from models import bayesian_category_sensitivity as m


def cases():
    interval={'median':2.,'lower_95':1.,'upper_95':3.,'probability_positive':.99}
    row={'id':'laundry:a->b','design_vector':[1.,-1.],'support_before':{'rows':10},
         'support_after':{'rows':20},'overlap':{'buildings':3},'status':'supported_converged',
         'diagnostics':{'acceptable':True,'max_rhat':1.001,'ess_bulk':800,'ess_tail':700},
         'log_effect':dict(interval),'percent_effect':dict(interval)}
    before={'version':m.contrasts.VERSION,'status':'all_supported_contrasts_converged',
            'source_observations_sha256':'source','design_features':['a','b'],'categories':[],
            'omitted':[],'highlight_ids':[],'implementation_sha256':{'code':'hash'},'contrasts':[row]}
    after=copy.deepcopy(before);after['contrasts'][0]['percent_effect']['median']=2.2
    ap={'source':'same','prior_multiplier':1.,'seed':1,'tune':1000}
    bp={'source':'same','prior_multiplier':.5,'seed':2,'tune':2000}
    return before,after,ap,bp


def test_independent_fit_median_shift_is_descriptive_not_paired_interval():
    result=m.compare(*cases());row=result['contrasts'][0]
    assert row['median_shift_percentage_points']==pytest.approx(.2)
    assert result['interval_sign_changes']==[]
    assert 'difference_interval' not in row and 'probability_change' not in row
    assert result['changed_protocol_settings']['prior_multiplier']=={'before':1.,'after':.5}


@pytest.mark.parametrize('mutation',['source','vector','support','overlap','model','diagnostics','code'])
def test_nonidentical_estimands_or_unaccepted_intervals_are_refused(mutation):
    a,b,ap,bp=cases()
    if mutation=='source':b['source_observations_sha256']='different'
    elif mutation=='vector':b['contrasts'][0]['design_vector']=[-1.,1.]
    elif mutation=='support':b['contrasts'][0]['support_after']['rows']+=1
    elif mutation=='overlap':b['contrasts'][0]['overlap']['buildings']+=1
    elif mutation=='model':bp['likelihood']='different'
    elif mutation=='diagnostics':b['contrasts'][0]['diagnostics']['ess_tail']=300
    else:b['implementation_sha256']['code']='different'
    with pytest.raises(ValueError):m.compare(a,b,ap,bp)

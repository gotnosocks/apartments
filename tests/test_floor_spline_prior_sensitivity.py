"""Prior reweighting is conditional sensitivity, with strict overlap gates."""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import norm

from models import floor_spline_prior_sensitivity as m


def test_density_ratio_exactly_changes_only_five_normal_priors():
    rng=np.random.default_rng(718)
    beta=rng.normal(0,.04,(4,500,5))
    for alt in (.05,.20):
        expected=(norm.logpdf(beta,scale=alt)-norm.logpdf(beta,scale=.1)).sum(axis=2)
        np.testing.assert_allclose(m.prior_log_ratios(beta,.1,alt),expected,rtol=1e-13,atol=1e-13)
    np.testing.assert_array_equal(m.prior_log_ratios(beta,.1,.1),np.zeros((4,500)))


@pytest.mark.parametrize('scale',[0,-1,np.nan,np.inf,True])
def test_bad_scales_rejected(scale):
    with pytest.raises(ValueError):m.prior_log_ratios(np.zeros((4,1000,5)),.1,scale)


def test_weight_normalization_and_diagnostics_preserve_chain_order():
    rng=np.random.default_rng(4012);beta=rng.normal(0,.025,(4,3000,5))
    ratios=m.prior_log_ratios(beta,.1,.05)
    weights,diagnostic=m.importance_weights(ratios,.8)
    assert diagnostic['acceptable']
    assert diagnostic['pareto_k']<.5
    assert weights.shape==(4,3000) and weights.sum()==pytest.approx(1.)
    assert diagnostic['raw']['chain_mass']==pytest.approx(weights.sum(axis=1))
    assert diagnostic['raw']['ess']==pytest.approx(1/np.square(weights).sum())
    assert diagnostic['raw']['ess_fraction']==pytest.approx(diagnostic['raw']['ess']/12000)
    assert diagnostic['raw']['ess_accounts_for_autocorrelation'] is False
    shifted,_=m.importance_weights(ratios+1000,.8)
    np.testing.assert_allclose(shifted,weights,rtol=2e-13,atol=1e-15)


def test_weight_concentration_and_low_reff_fail_closed():
    ratios=np.zeros((4,3000));ratios[0,0]=50
    _,diag=m.importance_weights(ratios,.9)
    assert not diag['acceptable']
    assert 'raw_weight_ess_below_1000' in diag['withholding_reasons']
    assert 'raw_maximum_weight_above_0.01' in diag['withholding_reasons']
    assert 'raw_chain_mass_imbalance' in diag['withholding_reasons']
    rng=np.random.default_rng(551)
    ratios=m.prior_log_ratios(rng.normal(0,.02,(4,3000,5)),.1,.05)
    _,diag=m.importance_weights(ratios,.001)
    assert not diag['acceptable']
    assert 'raw_reff_times_weight_ess_below_400' in diag['withholding_reasons']


def test_weighted_quantiles_are_empirical_not_resampled():
    value=m.weighted_interval([-100.,1.,2.,4.],[0.,.025,.925,.05])
    assert value=={'lower_95':1.,'median':2.,'upper_95':4.,'probability_positive':1.}
    with pytest.raises(ValueError):m.weighted_interval([1,2],[-1,2])


def test_reweighting_matches_analytic_gaussian_changed_prior():
    rng=np.random.default_rng(910)
    baseline=.1;likelihood_sd=.03;likelihood_mean=.035
    variance=1/(1/baseline**2+1/likelihood_sd**2)
    mean=variance*likelihood_mean/likelihood_sd**2
    beta=rng.normal(mean,np.sqrt(variance),(4,20000,5))
    for alt in (.05,.2):
        weights,diagnostic=m.importance_weights(m.prior_log_ratios(beta,baseline,alt),1.)
        assert diagnostic['acceptable']
        newvar=1/(1/alt**2+1/likelihood_sd**2);newmean=newvar*likelihood_mean/likelihood_sd**2
        interval=m.weighted_interval(beta[:,:,0],weights)
        expected=norm.ppf([.025,.5,.975],loc=newmean,scale=np.sqrt(newvar))
        np.testing.assert_allclose([interval[k] for k in ('lower_95','median','upper_95')],expected,atol=.001)


@pytest.fixture
def simple_case():
    features=['unrelated','listed_floor.unknown',*[f'listed_floor_spline_{i}' for i in range(5)]]
    def direction(low,high):
        return np.r_[0.,0.,np.array([1.,.4,-.3,.2,.1])*(high-low)/50]
    design=SimpleNamespace(version=m.contract.DESIGN,floor_prior_scale=.1,floor_levels=[1.,2.,10.,52.],
        features=features,prior_scales=np.array([.2,.2,*([.1]*5)]),floor_support={'test':True},contrast_vector=direction)
    beta=np.random.default_rng(4216).normal(0,.025,(4,3000,len(features)))
    return design,beta


def test_only_five_floor_priors_change_and_intervals_match_base_rules(simple_case):
    design,beta=simple_case
    result=m.calculate(design,beta)
    assert result['posterior_refitted'] is False and result['main_selection_changed'] is False
    assert all(a['diagnostics']['acceptable'] for a in result['alternatives'])
    changed=beta.copy();changed[:,:,:2]*=1e6
    other=m.calculate(design,changed)
    assert other==result
    assert result['changed_coefficients']==design.features[2:]
    for alternative in result['alternatives']:
        points=alternative['points']
        assert points[1]['status']=='deterministic_reference'
        assert points[1]['log_effect']['median']==0
        assert all(p['log_effect'] is not None for p in points)


def test_failed_weights_withhold_all_alternative_nonzero_intervals(simple_case,monkeypatch):
    design,beta=simple_case
    original=m.importance_weights
    def reject(values,reff):
        weights,diagnostic=original(values,reff)
        diagnostic.update(acceptable=False,withholding_reasons=['forced_test_failure'])
        return weights,diagnostic
    monkeypatch.setattr(m,'importance_weights',reject)
    result=m.calculate(design,beta)
    assert all(p['log_effect'] is not None for p in result['baseline_curve'])
    for alternative in result['alternatives']:
        assert alternative['status']=='withheld_requires_refit'
        for point in alternative['points']:
            if point['floor']==2.:continue
            assert point['log_effect'] is None and point['percent_effect'] is None
            assert point['median_log_shift_from_base'] is None
            assert point['median_percentage_point_shift_from_base'] is None


def test_failed_baseline_coefficients_refused(simple_case):
    design,beta=simple_case
    beta[0,:,2:]+=1.
    with pytest.raises(ValueError,match='coefficient diagnostics fail'):m.calculate(design,beta)


def test_psis_adapter_smooths_large_weights_not_their_inverse():
    rng=np.random.default_rng(55)
    # Weight concentration must remain in chain 0 after smoothing.
    ratios=rng.normal(0,.1,(4,3000));ratios[0]+=2.
    weights,diagnostic=m.importance_weights(ratios,1.)
    assert diagnostic['raw']['chain_mass'][0]>.70
    assert diagnostic['psis']['chain_mass'][0]>.70
    assert weights[0].sum()>.70
    assert not diagnostic['acceptable']
    assert 'psis_chain_mass_imbalance' in diagnostic['withholding_reasons']


def test_degenerate_psis_tail_withholds_instead_of_inventing_k():
    _,diagnostic=m.importance_weights(np.zeros((4,3000)),1.)
    assert diagnostic['raw']['ess']==pytest.approx(12000)
    assert not diagnostic['acceptable'] and diagnostic['pareto_k'] is None
    assert diagnostic['psis'] is None
    assert diagnostic['psis_error']=='All tail values are the same'

import numpy as np
import pytest
from scipy import sparse
from scipy.optimize import minimize

from models.amenity_solver_diagnostic import objective_gradient, refine, prediction_change


def test_stationarity_matches_independent_finite_difference_and_penalty():
    x = sparse.csr_matrix([[1., -2.], [1., .5], [1., 3.]])
    p = sparse.diags([.1, 2.])
    y, beta = np.array([-.5, .3, 1.2]), np.array([.07, .11])
    g = objective_gradient(x,p,y,beta)['negative_gradient']
    numerical = []
    for index in range(2):
        shift = np.eye(2)[index]*1e-6
        numerical.append((objective_gradient(x,p,y,beta+shift)['objective']-
                          objective_gradient(x,p,y,beta-shift)['objective'])/2e-6)
    assert -g == pytest.approx(numerical, abs=1e-9)


def test_tight_irls_matches_independent_convex_optimizer_and_does_all_steps():
    x = sparse.csr_matrix(np.column_stack([np.ones(12), np.linspace(-1,1,12)]))
    p = sparse.diags([.1, .3])
    y = .25 + .5*np.linspace(-1,1,12);y[-1] += 3.
    initial = np.zeros(2)
    beta, history = refine(x,p,y,initial,steps=30)
    reference = minimize(lambda b:objective_gradient(x,p,y,b)['objective'], initial,
                         jac=lambda b:-objective_gradient(x,p,y,b)['negative_gradient'],method='BFGS',
                         options={'gtol':1e-11})
    assert beta == pytest.approx(reference.x, abs=1e-7)
    assert len(history) == 30
    assert history[-1]['gradient_inf'] < 1e-7
    assert all(b['objective'] <= a['objective']+1e-10 for a,b in zip(history,history[1:]))
    assert np.array_equal(initial,np.zeros(2))


def test_tiny_rare_contrast_gradient_can_hide_behind_large_unchanged_loss():
    # Many outliers dominate aggregate loss, while a lightly observed column
    # still has a materially wrong coefficient. Objective-change gates alone
    # are not stationarity tests.
    x = sparse.csr_matrix(np.array([[0.,0.]]*100 + [[1.,0.],[0.,1.]]))
    p = sparse.diags([.01,.01])
    y = np.array([100.]*100 + [.05,-.05])
    before = objective_gradient(x,p,y,np.zeros(2))
    beta, history = refine(x,p,y,np.zeros(2),steps=3)
    after = objective_gradient(x,p,y,beta)
    assert (before['objective']-after['objective'])/before['objective'] < 2e-6
    assert abs(beta[1]-beta[0]) > .099
    assert after['gradient_inf'] < 1e-10
    assert len(history) == 3


def test_prediction_change_reports_log_percent_and_dollars_consistently():
    change = prediction_change(np.log([100.,200.]),np.log([110.,180.]))
    assert change['max_absolute_percent_change'] == pytest.approx(10.)
    assert change['max_absolute_dollar_change'] == pytest.approx(20.)
    assert change['mean_absolute_dollar_change'] == pytest.approx(15.)


def _implementation_fixture(tmp_path, version):
    from apartments.research_pipeline import digest, publish_bundle
    names = ['amenity_ablation.py', 'amenity_ablation_contrasts.py', 'amenity_rent_model.py',
             'minimal_rent_model.py', 'pricing.py', 'amenity_sensitivity.py']
    live = tmp_path/'live'; live.mkdir()
    contents = {name:f'original {name}\n' for name in names}
    paths = {}
    for name,content in contents.items():
        path=live/name;path.write_text(content);paths[name]=path
    expected = {name:digest(path) for name,path in paths.items()}
    root=tmp_path/'experiment';root.mkdir()
    protocol={'version':version,'implementation_sha256':expected}
    protocol_hash='p'*64
    if version.endswith('-v2'):
        publish_bundle(root/'implementation', contents, {'version':version,'protocol_sha256':protocol_hash})
    else:
        (root/'implementation').mkdir()
        for name,content in contents.items():(root/'implementation'/name).write_text(content)
    # A revised producer is never executed while replaying old saved encoders.
    paths['amenity_sensitivity.py'].write_text('new producer version\n')
    return root,protocol,protocol_hash,paths


@pytest.mark.parametrize('version',['amenity-shrinkage-sensitivity-v1','amenity-shrinkage-sensitivity-v2'])
def test_archived_producer_allows_replay_but_executed_core_must_match(tmp_path,version):
    from models.amenity_solver_diagnostic import _verify_implementation
    root,protocol,sha,paths=_implementation_fixture(tmp_path,version)
    verified=_verify_implementation(root,protocol,sha,current_paths=paths)
    assert verified['producer_snapshot']['executed'] is False
    assert 'amenity_sensitivity.py' not in verified['live_implementation_sha256']
    paths['amenity_rent_model.py'].write_text('changed executed encoder\n')
    with pytest.raises(ValueError,match='Executed fit implementation changed'):
        _verify_implementation(root,protocol,sha,current_paths=paths)


@pytest.mark.parametrize('version',['amenity-shrinkage-sensitivity-v1','amenity-shrinkage-sensitivity-v2'])
@pytest.mark.parametrize('damage',['missing','changed'])
def test_bad_or_missing_producer_snapshot_is_rejected(tmp_path,version,damage):
    from models.amenity_solver_diagnostic import _verify_implementation
    root,protocol,sha,paths=_implementation_fixture(tmp_path,version)
    path=root/'implementation'/'amenity_sensitivity.py'
    if damage=='missing':path.unlink()
    else:path.write_text('unbound producer\n')
    with pytest.raises(ValueError,match='snapshot|integrity'):
        _verify_implementation(root,protocol,sha,current_paths=paths)


def test_v2_snapshot_bundle_must_bind_protocol(tmp_path):
    from models.amenity_solver_diagnostic import _verify_implementation
    root,protocol,sha,paths=_implementation_fixture(tmp_path,'amenity-shrinkage-sensitivity-v2')
    with pytest.raises(ValueError,match='protocol mismatch'):
        _verify_implementation(root,protocol,'wrong-protocol',current_paths=paths)

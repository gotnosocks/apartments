from copy import deepcopy
import hashlib

import pytest

from models import recover_floor_report as m


ORIGINAL = "dims=('floor_contrast','feature')\ncoords={'floor_contrast':np.arange(len(pairs))}\njoint.isel(floor_contrast=i)"


def fixture():
    sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
    fixed=m.coordinate_fix(ORIGINAL)
    protocol={'version':'observable-bayesian-floor-experiment-v4',
              'implementation_sha256':{m.RUNNER:sha(ORIGINAL)}}
    products={k:'a'*64 for k in m.PRESERVED}
    code={m.RUNNER:sha(fixed),'recover_floor_report.py':'b'*64,'bayesian_feature_report.py':'c'*64}
    manifest={'files':{**products,**code,'pre-floor-summary.json':'d'*64}}
    recovery={'version':m.VERSION,'protocol_sha256':'ph','original_runner_sha256':sha(ORIGINAL),
              'implementation_sha256':code,'preserved_product_sha256':products,'original_summary_sha256':'d'*64}
    before={'status':'exploratory_converged','diagnostics':{'acceptable':True}}
    after={**before,'floor_diagnostics':{'acceptable':True}}
    return protocol,'ph',manifest,recovery,ORIGINAL,fixed,before,after


def test_exact_coordinate_fix_preserves_all_other_code_and_report_products():
    parts=fixture()
    assert m.verify_recovery(*parts)==parts[3]
    assert "dims=('contrast','feature')" in parts[5]


@pytest.mark.parametrize('fault',['math','original','posterior','diagnostics','runner','summary','status','missing_product'])
def test_recovery_refuses_changes_outside_naming_fix(fault):
    p,ph,fm,r,old,new,before,after=deepcopy(fixture())
    if fault=='math':new+='\nchanged_formula()'
    if fault=='original':r['original_runner_sha256']='bad'
    if fault=='posterior':fm['files']['posterior.nc']='different'
    if fault=='diagnostics':fm['files']['diagnostics.json']='different'
    if fault=='runner':fm['files'][m.RUNNER]='different'
    if fault=='summary':after['diagnostics']={'acceptable':False}
    if fault=='status':after['status']='published'
    if fault=='missing_product':r['preserved_product_sha256'].pop('residuals.jsonl')
    with pytest.raises(ValueError):m.verify_recovery(p,ph,fm,r,old,new,before,after)


def test_failed_new_floor_diagnostics_cannot_retain_accepted_status():
    parts=list(fixture());parts[-1]['floor_diagnostics']['acceptable']=False
    with pytest.raises(ValueError,match='status'):m.verify_recovery(*parts)
    parts[-1]['status']='diagnostic_only_do_not_interpret_intervals'
    m.verify_recovery(*parts)


def test_unexpected_or_repeated_original_code_refused():
    with pytest.raises(ValueError):m.coordinate_fix(ORIGINAL+ORIGINAL)
    with pytest.raises(ValueError):m.coordinate_fix('different implementation')

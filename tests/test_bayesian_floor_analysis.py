import hashlib
from pathlib import Path

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from apartments import bayesian_analysis as backend
from apartments.corrections import canonical
from models import bayesian_floor_increment_design as floor
from models import bayesian_source_sensitivity as verification
from tests.test_bayesian_feature_model import train
from tests.test_bayesian_source_sensitivity import design_archive, design_source, converted
from tests.test_bayesian_feature_report import publish_binary


@pytest.fixture
def floor_archive(tmp_path,train):
    rows=design_source(train)
    with threadpool_limits(limits=1,user_api='blas'):
        root,source,protocol,provenance=design_archive(tmp_path,rows)
        design=floor.FeatureDesign(converted(rows));design.save(root/'fit')
    protocol.update(version='observable-bayesian-floor-experiment-v4',feature_design_version=floor.VERSION,
                    floor_increment_prior_scale=.15, floor_levels=design.floor_levels,
                    floor_thresholds=design.floor_thresholds)
    code={name:(root/'protocol'/name).read_bytes() for name in protocol['implementation_sha256']}
    code[Path(floor.__file__).name]=Path(floor.__file__).read_bytes()
    protocol['implementation_sha256']={k:hashlib.sha256(v).hexdigest() for k,v in code.items()}
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    pm=publish_binary(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**code},
        {'version':protocol['version'],'protocol_sha256':ph})
    files={name:(root/'fit'/name).read_bytes() for name in verification.comparison.DESIGNS}
    fm=publish_binary(root/'fit',files,{'version':protocol['version'],'protocol_sha256':ph})
    return root,source,protocol,{'protocol_manifest':pm,'fit_manifest':fm},design,rows


def test_v4_reconstruction_exact_and_source_bound(floor_archive):
    root,source,protocol,provenance,*_=floor_archive
    with threadpool_limits(limits=1,user_api='blas'):
        result=verification.verify_design(root,source,protocol,provenance)
    assert result['verified']
    assert 'bayesian_floor_increment_design.py' in result['implementation_sha256']


def test_rehashed_wrong_prior_does_not_reconstruct(floor_archive):
    root,source,protocol,provenance,*_=floor_archive
    protocol['floor_increment_prior_scale']=.05
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
    old=provenance['protocol_manifest']
    files={name:(root/'protocol'/name).read_bytes() for name in old['files']}
    files['protocol.json']=canonical(protocol)+'\n'
    provenance['protocol_manifest']=publish_binary(root/'protocol',files,
        {'version':protocol['version'],'protocol_sha256':ph})
    provenance['fit_manifest']['protocol_sha256']=ph
    with threadpool_limits(limits=1,user_api='blas'),pytest.raises(ValueError,match='exact source reconstruction'):
        verification.verify_design(root,source,protocol,provenance)


def test_backend_floor_fields_and_source_values_keep_aliases(floor_archive):
    *_,design,rows=floor_archive
    analysis=backend.BayesianAnalysis()
    analysis.design=design
    analysis.fields=analysis._fields()
    assert analysis.fields['listed_floor']['observed_levels']==design.floor_levels
    row={**rows[0],'listed_floor':None,'advertised_floor':3}
    assert analysis._value(row,'listed_floor')==3
    assert not any('linear standardized floor' in warning for warning in analysis._warnings(row))
    assert any('gaps' in warning for warning in analysis._warnings(row))
    loaded=backend.load_design(floor_archive[0]/'fit',converted(rows),floor_archive[2])
    np.testing.assert_array_equal(loaded.matrix(converted(rows)),design.matrix(converted(rows)))

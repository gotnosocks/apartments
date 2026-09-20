from copy import deepcopy
import json
from pathlib import Path

import pytest

from models import direct_floor_fit_checks as checks


ARCHIVE = Path('data/model/chelsea-bayesian-commercial-scope-spline-disk-20260920/protocol')


@pytest.fixture
def protocols():
    path = ARCHIVE/'protocol.json'
    if not path.exists():
        pytest.skip('Archived reference protocol unavailable')
    reference = json.loads(path.read_text())
    candidate = deepcopy(reference)
    candidate.update(source_version=checks.projection.VERSION,
                     source_manifest_sha256='new source', source_observations_sha256='new rows')
    candidate['implementation_sha256']['direct_floor_projection.py'] = 'new contract'
    for name in checks.LOADER_CODE:
        candidate['implementation_sha256'][name] = 'reviewed loader change'
    return reference, candidate


def test_protocol_keeps_same_population_and_sampling(protocols):
    assert checks.check_protocols(*protocols) == sorted(checks.LOADER_CODE)


@pytest.mark.parametrize('field,value', [('rows', 1), ('units', 1), ('buildings', 1),
    ('current_rows', 1), ('draws', 50), ('tune', 50), ('seed', 1), ('floor_prior_scale', .5),
    ('floor_knots', [1, 3, 5]), ('floor_levels', [1, 2, 3]), ('unit_prior_scale', .5)])
def test_protocol_rejects_confounded_comparison(protocols, field, value):
    a, b = protocols
    b[field] = value
    with pytest.raises(ValueError):
        checks.check_protocols(a, b)


def test_changed_mathematics_rejected(protocols):
    a, b = protocols
    b['implementation_sha256']['bayesian_feature_model.py'] = 'changed'
    with pytest.raises(ValueError, match='Mathematical'):
        checks.check_protocols(a, b)


@pytest.mark.parametrize('name', sorted(checks.LOADER_CODE))
def test_actual_archived_to_current_loader_changes(name):
    if not (ARCHIVE/name).exists():
        pytest.skip('Archived reference loader unavailable')
    path = (Path('models') if name.startswith('bayesian') else Path('src/apartments'))/name
    before, after = (ARCHIVE/name).read_text(), path.read_text()
    assert checks.check_loader_change(before, after)
    with pytest.raises(ValueError):
        checks.check_loader_change(before, after+'\ndef unreviewed(): return 1\n')
    tampered = (after.replace('v2.pd.DataFrame(rows)', 'v2.pd.DataFrame(rows).fillna(0)')
                if name.startswith('bayesian') else after.replace('current, direct_floor_changes)', 'current, None)'))
    assert tampered != after
    with pytest.raises(ValueError):
        checks.check_loader_change(before, tampered)

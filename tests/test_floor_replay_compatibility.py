from pathlib import Path

import pytest

from models.floor_replay_compatibility import check_refactor


@pytest.mark.parametrize('name', ['floor_label_projection.py', 'expanded_floor_projection.py'])
def test_exact_archived_refactor_and_unrelated_changes(name):
    archive = Path('data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919/protocol')/name
    if not archive.exists():
        pytest.skip('Local archived fit unavailable')
    before = archive.read_text()
    after = (Path('src/apartments')/name).read_text()
    assert check_refactor(name, before, after)
    for altered in [after+'\ndef extra(): return 1\n',
                    after.replace('return deepcopy(_project_row_view', 'return list(_project_row_view'),
                    after.replace('result = dict(row)', 'result = row'),
                    after.replace("raise ValueError('Floor", "raise RuntimeError('Floor"),
                    after.replace("result['listed_floor'] = value", "result['listed_floor'] = value + 1")]:
        assert altered != after
        with pytest.raises(ValueError): check_refactor(name, before, altered)


def test_rejects_unknown_or_already_refactored_contract():
    with pytest.raises(ValueError): check_refactor('model.py', '', '')
    with pytest.raises(ValueError): check_refactor('floor_label_projection.py', 'def _project_row_view(): pass', '')

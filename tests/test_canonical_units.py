import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apartments.canonical_units import memberships, build_canonical_units
from apartments.unit_canonical import canonical_unit_id, ASSOCIATION_RULE


def capture(sid, lid, page='a/4c', **extra):
    return {'snapshot_id': sid, 'listing_id': lid,
            'canonical_unit_url': 'https://streeteasy.com/building/' + page if page else None,
            'listing_type': 'rental', **extra}


def test_url_only_ignores_labels_latest_history_and_attributes():
    rows = [capture(1, '1', unit_label='Studio', latest='99', bedrooms=0),
            capture(2, '2', unit_label=None, latest=None, bedrooms=3),
            capture(3, '1'), capture(4, '3', 'b/4c'), capture(5, '4', 'a/4d')]
    result = {r['listing_id']: r for r in memberships(rows)}
    assert result['1']['unit_id'] == result['2']['unit_id']
    assert len({r['unit_id'] for r in result.values()}) == 3
    assert result['1']['capture_count'] == 2
    assert memberships(list(reversed(rows))) == list(result.values())
    assert canonical_unit_id(rows[0]['canonical_unit_url']) == result['1']['unit_id']
    # Adding a later rental advertisement does not change the unit identity.
    assert memberships([capture(6, '999')])[0]['unit_id'] == result['1']['unit_id']


def test_conflicting_captures_never_bridge_distinct_units():
    result = memberships([capture(1, '1'), capture(2, '1', 'a/4d'),
                          capture(3, '2'), capture(4, '3', 'a/4d'),
                          capture(5, '4', 'b/1'), capture(6, '5', None)])
    assert {r['listing_id'] for r in result if r['unit_id']} == {'4'}
    assert all(r['reason'] for r in result if not r['unit_id'])
    with pytest.raises(ValueError):
        canonical_unit_id('https://streeteasy.com/rental/1')


def test_output_preserves_observations_and_joins_full_history(tmp_path):
    rows = [capture(1, '1'), capture(2, '2'), capture(3, '2'), capture(4, '3', 'b/4c'),
            capture(5, '4', listing_type='sale'), capture(6, None)]
    path = tmp_path / 'listing_observations' / 'part.parquet'
    path.parent.mkdir()
    pq.write_table(pa.Table.from_pylist(rows), path)
    before = path.read_bytes()
    summary = build_canonical_units(tmp_path)
    assert path.read_bytes() == before
    assert summary['rule'] == ASSOCIATION_RULE
    assert summary['counts'] == {'rental_units': 2, 'rental_unit_memberships': 3, 'rental_unit_observations': 5}
    assert summary['multi_listing_units'] == 1 and summary['listing_ids_in_multi_listing_units'] == 2
    assert summary['unresolved_captures'] == 1
    units = pq.read_table(tmp_path / 'rental_units').to_pylist()
    assert units[0]['listing_count'] == 2 and units[0]['capture_count'] == 3
    observations = pq.read_table(tmp_path / 'rental_unit_observations').to_pylist()
    unit = units[0]['unit_id']
    assert {r['snapshot_id'] for r in observations if r['unit_id'] == unit} == {1, 2, 3}
    assert build_canonical_units(tmp_path) == summary
    (tmp_path / 'complete.json').write_text('{}')
    with pytest.raises(ValueError, match='complete'):
        build_canonical_units(tmp_path)


def test_normal_finalizer_includes_canonical_associations(tmp_path):
    from .test_granular_export import test_preserves_fetches_snapshots_and_repeated_events
    from apartments.granular_export import finish
    test_preserves_fetches_snapshots_and_repeated_events(tmp_path)
    root = tmp_path / 'out'
    # The fixture opens a review service by supplying a dummy completion marker.
    (root / 'complete.json').unlink()
    result = finish(root)
    assert result['canonical_unit_association']['counts']['rental_units'] == 1
    assert result['canonical_unit_association']['counts']['rental_unit_observations'] == 2
    assert result['tables']['counts']['event_mentions'] == 4
    assert json.loads((root / 'complete.json').read_text())['unit_association_rule'] == ASSOCIATION_RULE
    with pytest.raises(ValueError, match='complete'):
        finish(root)

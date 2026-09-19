import pytest

from apartments.unit_canonical import canonical_unit_id
from models.discovery_identity_review import identity_evidence


def member(ad, url='https://streeteasy.com/building/demo/3d'):
    return {'listing_id': ad, 'unit_id': canonical_unit_id(url), 'canonical_unit_url': url,
            'status': 'associated', 'rule': 'canonical-url-v1'}


def listing(history, label='#3D'):
    return {'id': '100', 'propertyDetails': {'address': {'displayUnit': label}, 'bedroomCount': 4},
            'propertyHistory': history}


def history(ad, kind='rentalEventsOfInterest'):
    return {'listingId': ad, kind: [{'date': '2020-01-01', 'price': 1000}]}


TARGET = {'source_listing_id': '100', 'expected_building_path': '/building/demo'}


def test_rental_history_and_label_are_separate_corroboration():
    result = identity_evidence(TARGET, listing([history('10'), history('11')]), [member('10'), member('11')])
    assert result['status'] == 'unique_history_unit_candidate'
    assert result['history_and_label_agree']
    assert len(result['associated_history_memberships']) == 2
    assert len(result['history_unit_candidates']) == 1


def test_sale_history_and_label_only_cannot_become_rental_history_match():
    result = identity_evidence(TARGET, listing([history('10', 'saleEventsOfInterest')]), [member('10')])
    assert result['status'] == 'no_associated_history_unit'
    assert len(result['label_only_candidates']) == 1
    assert not result['history_and_label_agree']


def test_different_historical_units_remain_conflicted():
    result = identity_evidence(TARGET, listing([history('10'), history('11')]),
                               [member('10'), member('11', 'https://streeteasy.com/building/demo/4d')])
    assert result['status'] == 'multiple_history_units'
    assert not result['history_and_label_agree']


def test_history_building_conflict_not_overridden_by_label():
    result = identity_evidence(TARGET, listing([history('10')]),
                               [member('10', 'https://streeteasy.com/building/elsewhere/3d'), member('11')])
    assert result['status'] == 'history_building_conflict'
    assert len(result['label_only_candidates']) == 1
    assert not result['history_and_label_agree']


def test_missing_and_unresolved_history_remain_explicit():
    unresolved = {'listing_id': '10', 'status': 'unresolved', 'unit_id': None, 'canonical_unit_url': None}
    result = identity_evidence(TARGET, listing([history('10'), history('11')]), [unresolved])
    assert result['unresolved_history_listing_ids'] == ['10']
    assert result['unseen_history_listing_ids'] == ['11']


def test_wrong_advertisement_rejected():
    with pytest.raises(ValueError, match='Wrong advertisement'):
        identity_evidence(TARGET, {'id': '999'}, [])

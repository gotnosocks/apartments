from copy import deepcopy
import pytest
from models.current_source_audit import inspect

ROW = {'source_listing_id': '123', 'collected_at': '2026-09-18T12:00:00Z', 'asking_rent': 6950}


def payload():
    return {'id': '123', 'description': 'Monthly Rent: $7,750', 'pricing': {'price': 6950,
        'priceChanges': [{'changedAt': '2026-07-27T12:00:00Z', 'price': 7750},
                         {'changedAt': '2026-09-16T12:00:00Z', 'price': 6950}]}}


def test_earlier_description_price_is_evidence_not_a_correction():
    p = payload(); before = deepcopy(p)
    r = inspect(ROW, p)
    assert r['flags'] == ['description_rent_differs']
    assert r['description_rent_quotes'][0]['matches_earlier_price_before_verified_current_change']
    assert r['structured_price'] == 6950 and p == before


@pytest.mark.parametrize('change', ['future', 'conflict', 'missing'])
def test_no_unsupported_explanation_for_a_description_disagreement(change):
    p = payload()
    if change == 'future': p['pricing']['priceChanges'][-1]['changedAt'] = '2026-09-19T12:00:00Z'
    if change == 'conflict': p['pricing']['priceChanges'].append({'changedAt': '2026-09-16T12:00:00Z', 'price': 7000})
    if change == 'missing': p['pricing']['priceChanges'] = []
    assert not inspect(ROW, p)['description_rent_quotes'][0]['matches_earlier_price_before_verified_current_change']


def test_approval_clause_scope_does_not_hide_second_net_effective_claim():
    p = payload()
    p['description'] = ('Approval Standards: Where applicable, approvals are based on the gross rent, '
        'not the net effective rent. Advertised net effective rent is $6,000.')
    r = inspect(ROW, p)
    assert [f['approval_standards_scope'] for f in r['wording_findings']] == [True, False]


def test_wrong_advertisement_and_invalid_prices():
    p = payload(); p['id'] = 'other'
    with pytest.raises(ValueError, match='Wrong advertisement'): inspect(ROW, p)
    p['id'] = '123'; p['pricing']['priceChanges'][0]['price'] = True
    assert 'invalid_price_events' in inspect(ROW, p)['flags']

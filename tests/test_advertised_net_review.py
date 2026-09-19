from copy import deepcopy
import hashlib

import pytest

from apartments.rent_basis_measurement import measure
from docs.analysis.scripts import adjudicate_advertised_net_review as m
from tests.test_reviewed_cohort_quarantine import fixture, CLOCK


def case(ad='1694924', text='Net effective rent listed.', price=3000):
    rows, decisions, *_ = fixture()
    row = deepcopy(rows[0]); row['source_listing_id'] = ad
    captures, originals = [], []
    for initial in decisions[0]['evidence']:
        capture = {**deepcopy(initial), 'source_listing_id': ad, 'description': text,
            'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'measurement': measure(text, row['asking_rent'])}
        captures.append(capture)
        originals.append({'audit_id': row['audit_id'], 'capture_id': capture['capture_id'],
            'source_listing_id': ad, 'raw_listing_sha256': capture['raw_listing_sha256'],
            'initial_event_matches_analytical_target': True, 'pricing': {'price': price},
            'initial_active_events': [{'event_listing_id': ad, 'price': row['asking_rent'], 'status': 'ACTIVE'}]})
    return {'source_record': deepcopy(row), 'captures': captures, 'original_price_records': originals}, row


def test_matched_capture_price_is_evidence_without_inventing_a_net_quote():
    value, row = case()
    assert value['captures'][0]['measurement']['target_matches'] == []
    before = deepcopy(value)
    result = m.review_case(value, row, CLOCK)
    assert result['action'] == 'quarantine_unresolved_gross_price_basis'
    assert result['recommendation_only']
    assert all(r['captured_price_equals_historical_target'] for r in result['evidence'])
    assert value == before
    m.q.validate_decision(row, result, CLOCK)


@pytest.mark.parametrize('fault', ['later_price', 'missing_capture', 'duplicate_capture', 'typed_id',
    'raw_hash', 'own_event', 'own_ad', 'clock', 'negated', 'literal'])
def test_review_cannot_silently_weaken_capture_or_event_evidence(fault):
    value, row = case(); clock = CLOCK
    if fault == 'later_price': value['original_price_records'][0]['pricing']['price'] = 2800
    elif fault == 'missing_capture': value['original_price_records'].pop()
    elif fault == 'duplicate_capture': value['captures'].append(deepcopy(value['captures'][0]))
    elif fault == 'typed_id': value['original_price_records'][0]['capture_id'] = '0'
    elif fault == 'raw_hash': value['original_price_records'][0]['raw_listing_sha256'] = 'c'*64
    elif fault == 'own_event': value['original_price_records'][0]['initial_active_events'][0]['price'] = 2800
    elif fault == 'own_ad': value['original_price_records'][0]['source_listing_id'] = 'other'
    elif fault == 'clock': clock = '2020-01-01T00:00:00Z'
    elif fault == 'negated': value, row = case(text='Not net effective rent listed.')
    elif fault == 'literal': value['captures'][0]['description'] = 'Other text'
    with pytest.raises(ValueError): m.review_case(value, row, clock)


def test_explicit_gross_target_overrides_later_advertised_net_wording():
    value, row = case(ad='2079352', text='Net effective rent advertised. Gross rent $3,000.', price=2800)
    result = m.review_case(value, row, CLOCK)
    assert result['action'] == 'retain_explicit_gross_target'
    assert any('Gross rent $3,000' == s['literal'] for s in result['evidence'][0]['spans'])


def test_manual_board_approval_exception_is_specific_to_reviewed_ad():
    text = ('Net effective price advertised with one month free on a twelve month lease. Gross rent $3,000. '
            'Please note, this is a Co-op that requires board approval.')
    value, row = case(ad='2475341', text=text, price=2800)
    # Use the real reviewed quote's distance to put approval near only the gross
    # clause; the administrative hint is contextual, not a literal negation.
    assert not value['captures'][0]['measurement']['advertised_net_statements'][0]['administrative_context']
    assert value['captures'][0]['measurement']['amounts'][0]['administrative_context']
    assert m.review_case(value, row, CLOCK)['action'] == 'retain_explicit_gross_target'
    other, other_row = case(ad='2079352', text=text, price=2800)
    with pytest.raises(ValueError, match='administrative'): m.review_case(other, other_row, CLOCK)


def test_changed_price_without_target_quote_is_deferred_not_certified_gross():
    value, row = case(ad='2438307', price=2800)
    result = m.review_case(value, row, CLOCK)
    assert result['action'] == 'defer_event_specific_price_basis'
    assert all(not c['captured_price_equals_historical_target'] for c in result['evidence'])


def test_inconsistent_gross_amount_is_not_repaired_or_declared_verified_net():
    value, row = case(ad='2265090', text='Net effective price advertised. Gross rent $2,800.')
    result = m.review_case(value, row, CLOCK)
    assert result['action'] == 'quarantine_unresolved_gross_price_basis'
    assert 'amounts conflict' in result['reason']

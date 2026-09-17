import pytest

from apartments.review_ledger import GENESIS, ReviewConflict, ReviewLedgerError
from apartments.unit_identity import UnitIdentityLedger, expand_ids, identity_map, resolve_unit


def merge(ledger, ids, request_id):
    return ledger.write('merge', listing_ids=sorted(ids), review_revision=GENESIS,
        author='Ben', reason='Verified same home', request_id=request_id,
        expected_revision=ledger.revision(ledger.events()))


def undo(ledger, event, request_id):
    return ledger.write('undo', merge_id=event['id'], author='Ben', reason='Mistaken identity',
        request_id=request_id, expected_revision=ledger.revision(ledger.events()))


def test_persistent_identity_expansion_and_dependent_undo(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / 'identities.jsonl', 'dataset')
    first = merge(ledger, ['1', '2'], 'first')
    reopened = UnitIdentityLedger(ledger.path, 'dataset')
    assert resolve_unit('1', reopened.events()) == resolve_unit('2', reopened.events()) == first['unit_id']
    assert resolve_unit('3', reopened.events()) == 'streeteasy:rental:3'
    assert expand_ids(['1', '3'], reopened.events()) == ['1', '2', '3']
    with pytest.raises(ValueError, match='every listing'):
        merge(reopened, ['1', '3'], 'partial')
    second = merge(reopened, ['1', '2', '3'], 'second')
    assert second['unit_id'] == first['unit_id']
    with pytest.raises(ValueError, match='later merge'):
        undo(reopened, first, 'wrong-order')
    undo(reopened, second, 'undo-second')
    assert resolve_unit('3', reopened.events()) == 'streeteasy:rental:3'
    assert resolve_unit('2', reopened.events()) == first['unit_id']
    undo(reopened, first, 'undo-first')
    assert identity_map(reopened.events()) == {}


def test_identity_retry_conflict_and_integrity(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / 'identities.jsonl', 'dataset')
    args = dict(listing_ids=['1','2'], review_revision=GENESIS, author='Ben',
                reason='same home', request_id='one', expected_revision=GENESIS)
    saved = ledger.write('merge', **args)
    assert ledger.write('merge', **args) == saved
    assert len(ledger.events()) == 1
    with pytest.raises(ReviewConflict):
        ledger.write('merge', **{**args, 'reason': 'different'})
    with pytest.raises(ReviewConflict):
        ledger.write('merge', **{**args, 'request_id': 'two', 'listing_ids': ['3','4']})
    ledger.path.write_text(ledger.path.read_text().replace('same home', 'tampered'))
    with pytest.raises(ReviewLedgerError, match='hash chain'):
        ledger.events()


def test_merge_two_existing_units_and_restore(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / 'identities.jsonl', 'dataset')
    a = merge(ledger, ['1','2'], 'a')
    b = merge(ledger, ['3','4'], 'b')
    both = merge(ledger, ['1','2','3','4'], 'both')
    assert set(identity_map(ledger.events()).values()) == {a['unit_id']}
    undo(ledger, both, 'undo')
    assert identity_map(ledger.events()) == {'1':a['unit_id'], '2':a['unit_id'], '3':b['unit_id'], '4':b['unit_id']}

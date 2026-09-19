from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from apartments import corrections
from apartments.attribute_evidence import extract_attribute_evidence
from apartments.corrections import Overlay, canonical
from apartments.research_pipeline import digest, publish_bundle
from models.laundry_negation_revision import PATCH, assemble, hashed, run

WHEN = '2026-09-19T03:00:00+00:00'


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(corrections, 'now', lambda: datetime(2026, 9, 19, 3, tzinfo=timezone.utc))
    row = {'audit_id': 'a', 'unit_id': 'u', 'building': 'b', 'source_listing_id': '123',
        'capture_ids': [12, 13], 'laundry_type': 'in_building', 'asking_rent': 5000,
        'known_at': '2026-09-18T12:00:00+00:00',
        'analysis_price_basis': 'historical_initial_own_advertisement_ask'}
    text = "The building doesn't have on-site laundry."
    spans = extract_attribute_evidence({'description': text})['evidence']
    captures = [{
        'audit_id': 'a', 'unit_id': 'u', 'source_listing_id': '123', 'capture_id': cid,
        'body_sha256': str(cid)*32, 'raw_listing_sha256': str(cid)*32,
        'description': text, 'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'source_collected_at': '2026-09-10T12:00:00+00:00',
        'known_at': '2026-09-18T12:00:00+00:00', 'description_interpreted_at': None,
        'source_path': '/description'} for cid in (12, 13)]
    audit = [{**c, 'building': 'b', 'laundry_type': 'in_building',
        'replay_version': 'attribute-evidence-v4', 'replayed_laundry_type': None,
        'structured_in_unit_claim': False, 'structured_in_building_claim': False,
        'laundry_assertions': spans} for c in captures]
    ledger = tmp_path/'ledger.jsonl'
    edit = {'target': {'source': 'streeteasy', 'source_listing_id': '123', 'version_id': hashed(row)},
            'patch': PATCH, 'validity': {'all_time': True}}
    corrections.append(ledger, author='test reviewer', reason='Verified scoped denial.', edit=edit)
    return row, captures, audit, ledger


def apply(source, *, as_of=WHEN):
    row, captures, audit, ledger = source
    return assemble([row], {'a': captures}, audit, Overlay(ledger, as_of=as_of))


def test_exact_patch_preserves_source_clock_prices_and_original_category(source):
    row = deepcopy(source[0])
    revised, changes = apply(source)
    assert source[0] == row
    assert revised[0]['laundry_type'] is None
    assert {k: v for k, v in revised[0].items() if k not in ('laundry_type', 'attribute_review_history')} == {
        k: v for k, v in row.items() if k != 'laundry_type'}
    assert changes[0]['before_laundry_type'] == 'in_building'
    assert len(changes[0]['captures']) == 2
    assert changes[0]['recorded_at'] == WHEN
    assert revised[0]['attribute_review_history'] == changes


@pytest.mark.parametrize('fault', ['missing_capture', 'typed_capture', 'raw_hash',
    'positive_structured', 'wrong_literal', 'wrong_replay', 'missing_denial', 'duplicate_audit'])
def test_incomplete_or_conflicting_capture_evidence_is_rejected(source, fault):
    row, captures, audit, _ = source
    if fault == 'missing_capture': captures.pop()
    if fault == 'typed_capture': captures[0]['capture_id'] = '12'
    if fault == 'raw_hash': audit[0]['raw_listing_sha256'] = 'wrong'
    if fault == 'positive_structured': audit[0]['structured_in_unit_claim'] = True
    if fault == 'wrong_literal': audit[0]['laundry_assertions'][0]['literal'] = 'wrong'
    if fault == 'wrong_replay': audit[0]['replay_version'] = 'attribute-evidence-v3'
    if fault == 'missing_denial': audit[0]['laundry_assertions'] = []
    if fault == 'duplicate_audit': audit.append(deepcopy(audit[0]))
    with pytest.raises(ValueError): apply(source)


def test_changed_row_cannot_silently_drop_or_reuse_the_correction(source):
    source[0]['asking_rent'] = 5100
    with pytest.raises(ValueError, match='exact source row version'): apply(source)


def test_cutoff_before_correction_does_not_apply_later_knowledge(source):
    with pytest.raises(ValueError, match='active review correction'):
        apply(source, as_of='2026-09-18T23:00:00+00:00')


def test_source_knowledge_after_review_is_rejected(source):
    source[1][0]['known_at'] = '2026-09-20T00:00:00+00:00'
    source[2][0]['known_at'] = source[1][0]['known_at']
    with pytest.raises(ValueError, match='does not support'): apply(source)


def test_other_patch_fields_are_not_allowed(source, tmp_path):
    row, captures, audit, _ = source
    ledger = tmp_path/'other.jsonl'
    corrections.append(ledger, author='test', reason='Wrong scope', edit={
        'target': {'source': 'streeteasy', 'source_listing_id': '123', 'version_id': hashed(row)},
        'validity': {'all_time': True}, 'patch': [{'op': 'replace', 'path': '/asking_rent', 'value': 1}]})
    with pytest.raises(ValueError, match='bounded laundry patch'):
        assemble([row], {'a': captures}, audit, Overlay(ledger, as_of=WHEN))


def test_publication_and_idempotent_replay_with_real_ledger_and_description_binding(source, tmp_path):
    row, captures, audit, ledger = source
    dataset = tmp_path/'dataset'; descriptions = tmp_path/'descriptions'; source_audit = tmp_path/'audit'
    dm = publish_bundle(dataset, {'observations.jsonl': canonical(row)+'\n'}, {
        'version': 'reviewed-capture-refreshed-analysis-v1'})
    publish_bundle(descriptions, {'evidence.jsonl': ''.join(canonical(c)+'\n' for c in captures)}, {
        'version': 'refreshed-fitted-description-archive-v1',
        'dataset_manifest_sha256': digest(dataset/'complete.json'),
        'dataset_observations_sha256': dm['files']['observations.jsonl']})
    publish_bundle(source_audit, {'captures.jsonl': ''.join(canonical(c)+'\n' for c in audit)}, {
        'version': 'laundry-capture-source-audit-v1'})
    kwargs = dict(dataset=dataset, descriptions=descriptions, source_audit=source_audit,
                  ledger=ledger, as_of=WHEN, output=tmp_path/'revised')
    first = run(**kwargs)
    assert first['summary']['changed_rows'] == 1
    assert run(**kwargs) == first
    assert json.loads((dataset/'observations.jsonl').read_text()) == row
    visible = corrections.Overlay(kwargs['output']/'corrections.jsonl', as_of=WHEN)
    assert visible.manifest == first['overlay']

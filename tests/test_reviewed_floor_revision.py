from copy import deepcopy
from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from apartments import corrections
from apartments.corrections import Overlay, canonical
from apartments.research_pipeline import digest, publish_bundle
from models.bayesian_floor_increment_design import listed_floor_values
from models.reviewed_floor_revision import assemble, hashed, patch, run

WHEN = '2026-09-19T04:00:00+00:00'


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(corrections, 'now', lambda: datetime(2026, 9, 19, 4, tzinfo=timezone.utc))
    rows, reviews = [], []
    for key, decision in [('a', 'withhold_floor_due_to_scope'), ('b', 'retain_explicit_floor_claim')]:
        row = {'audit_id': key, 'unit_id': 'unit', 'building': 'building', 'source_listing_id': key,
            'capture_ids': [1 if key == 'a' else 2], 'advertised_floor': 3., 'listed_floor': None,
            'physical_floor': None, 'floors_above_ground': None, 'asking_rent': 5000,
            'known_at': '2026-09-18T12:00:00+00:00', 'analysis_price_basis': 'historical_initial_own_advertisement_ask'}
        text = 'Video of the third floor.' if key == 'a' else 'Apartment is on the third floor.'
        capture = {k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'known_at')}
        capture.update(capture_id=row['capture_ids'][0], description=text,
            body_sha256='b'*64, raw_listing_sha256='c'*64, description_sha256='d'*64,
            source_collected_at=row['known_at'], review_spans=[{'start': 0, 'end': len(text), 'literal': text}])
        review = {k: row[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id')}
        review.update(decision=decision, status='review_complete_recommendation_not_yet_projected',
            label_prefix_validated_as_floor=False, explicit_floor=3., interpreted_at='2026-09-19T03:00:00+00:00',
            proposed_analytical_floor=None if key == 'a' else 3., captures=[capture])
        rows.append(row); reviews.append(review)
    ledger = tmp_path/'ledger.jsonl'
    corrections.append(ledger, author='reviewer', reason='Media scope', edit={
        'target': {'source': 'streeteasy', 'source_listing_id': 'a', 'version_id': hashed(rows[0])},
        'validity': {'all_time': True}, 'patch': patch(3.)})
    return rows, deepcopy(rows), reviews, ledger


def apply(source):
    rows, originals, reviews, ledger = source
    return assemble(rows, originals, reviews, Overlay(ledger, as_of=WHEN))


def test_mask_changes_only_the_named_row_and_preserves_evidence_and_other_unit_history(source):
    original = deepcopy(source[0])
    revised, changes = apply(source)
    assert source[0] == original
    assert revised[1] == original[1]  # Same physical unit, separate source observation.
    assert revised[0]['advertised_floor'] is None
    assert {k: v for k, v in revised[0].items() if k not in ('advertised_floor', 'attribute_review_history')} == {
        k: v for k, v in original[0].items() if k != 'advertised_floor'}
    assert changes[0]['before_advertised_floor'] == 3.
    assert changes[0]['recorded_at'] == WHEN
    assert len(changes[0]['captures']) == 1
    before, after = listed_floor_values(pd.DataFrame(original)), listed_floor_values(pd.DataFrame(revised))
    assert before.tolist() == [3., 3.]
    assert pd.isna(after[0]) and after[1] == 3.


@pytest.mark.parametrize('fault', ['missing_capture', 'typed_capture', 'changed_row', 'changed_source',
    'missing_review', 'retained_mask', 'wrong_span', 'future_evidence', 'alternative_floor', 'duplicate_review'])
def test_unreviewed_or_stale_evidence_cannot_change_floors(source, fault):
    rows, originals, reviews, ledger = source
    if fault == 'missing_capture': reviews[0]['captures'] = []
    if fault == 'typed_capture': reviews[0]['captures'][0]['capture_id'] = '1'
    if fault == 'changed_row': rows[0]['asking_rent'] += 100
    if fault == 'changed_source': originals[0]['asking_rent'] += 100
    if fault == 'missing_review': reviews.pop(0)
    if fault == 'retained_mask': reviews[0]['decision'] = 'retain_explicit_floor_claim'
    if fault == 'wrong_span': reviews[0]['captures'][0]['review_spans'][0]['literal'] = 'Wrong'
    if fault == 'future_evidence': reviews[0]['captures'][0]['known_at'] = '2026-09-20T00:00:00+00:00'
    if fault == 'alternative_floor': rows[0]['listed_floor'] = originals[0]['listed_floor'] = 4.
    if fault == 'duplicate_review': reviews.append(deepcopy(reviews[0]))
    with pytest.raises(ValueError): apply(source)


def test_source_revision_does_not_reuse_old_ledger_even_when_review_row_matches(source):
    rows, originals, _, _ = source
    rows[0]['asking_rent'] = originals[0]['asking_rent'] = 5100
    with pytest.raises(ValueError, match='exact reviewed source version'): apply(source)


def test_publication_replay_and_cutoff_use_real_ledger(source, tmp_path):
    rows, originals, reviews, ledger = source
    parent, original, review = [tmp_path/name for name in ('parent', 'original', 'review')]
    publish_bundle(parent, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                   {'version': 'reviewed-laundry-negation-projection-v1'})
    publish_bundle(original, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in originals)},
                   {'version': 'reviewed-scope-composition-projection-v2'})
    publish_bundle(review, {'decisions.jsonl': ''.join(canonical(r)+'\n' for r in reviews)},
                   {'version': 'unit-label-floor-conflict-review-v1',
                    'source_manifest_sha256': digest(original/'complete.json'), 'summary': {'observations': 2}})
    kwargs = dict(dataset=parent, reviewed_source=original, review=review, ledger=ledger,
                  as_of=WHEN, output=tmp_path/'result')
    result = run(**kwargs)
    assert result['summary']['changed_rows'] == 1
    assert result['summary']['retained_reviewed_claims'] == 1
    assert run(**kwargs) == result
    with pytest.raises(ValueError, match='active correction'):
        run(**{**kwargs, 'as_of': '2026-09-19T03:30:00+00:00', 'output': tmp_path/'too-early'})
    assert not (tmp_path/'too-early').exists()

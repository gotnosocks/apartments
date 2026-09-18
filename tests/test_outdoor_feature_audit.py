import gzip
import hashlib
import json

import duckdb
import pandas as pd
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.outdoor_feature_audit import run, category


def test_cohort_audit_binds_sources_counts_rows_and_replays(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    source_files = {}
    raw = canonical({'description': 'Private balcony.', 'propertyDetails': {'features': {'privateOutdoorSpaceTypes': ['BALCONY']}}})
    for name, frame in {
        'listing_observations': pd.DataFrame([{'snapshot_id': 1, 'listing_id': '123',
            'canonical_unit_url': 'unit:1', 'raw_listing_json': raw, 'collected_at': 1789743600.0}]),
        'snapshots': pd.DataFrame([{'snapshot_id': 1, 'body_hash': 'historical-body'}])}.items():
        path = archive / name / 'part.parquet'
        path.parent.mkdir(parents=True)
        with duckdb.connect() as db:
            db.from_df(frame).write_parquet(str(path))
        source_files[str(path.relative_to(archive))] = digest(path)
    historical = tmp_path / 'historical'
    hm = publish_bundle(historical, {'source-files.json': canonical(source_files)}, {'version': 'fixture'})
    recovery = tmp_path / 'recovery'
    publish_bundle(recovery, {'accepted.jsonl': ''}, {'version': 'fixture'})
    refresh = tmp_path / 'refresh'
    fm = publish_bundle(refresh / 'snapshot', {'candidates.jsonl': ''}, {'version': 'fixture'})
    body = b'verified fresh body'
    sha = hashlib.sha256(body).hexdigest()
    path = refresh / 'archive/bodies' / sha[:2] / (sha + '.gz')
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(body))
    monkeypatch.setattr('models.outdoor_feature_audit.granular_parse.parse_listing',
        lambda body, url: ({'listing_id': '456', 'canonical_unit_url': 'unit:2',
                           'raw_listing_json': canonical({'description': 'Shared roof deck.', 'propertyDetails': {'amenities': {'sharedOutdoorSpaceTypes': ['ROOF_DECK']}}})}, None))
    common = {'building': 'building:1', 'period': '2026-09-01', 'known_at': '2026-09-18T16:00:00Z',
              'collected_at': '2026-09-18T15:00:00Z'}
    rows = [{**common, 'audit_id': 'old', 'source_listing_id': '123', 'canonical_unit_url': 'unit:1',
             'unit_id': 'unit:1', 'capture_ids': [1], 'analysis_price_basis': 'historical_initial_own_advertisement_ask'},
            {**common, 'audit_id': 'fresh', 'source_listing_id': '456', 'canonical_unit_url': 'unit:2',
             'unit_id': 'unit:2', 'capture_id': 'fresh:1', 'analysis_price_basis': 'current_capture_gross_ask',
             'refresh_provenance': {'body_sha256': sha, 'requested_url': 'source:456'}}]
    dataset = tmp_path / 'dataset'
    dm = publish_bundle(dataset, {'observations.jsonl': ''.join(canonical(r) + '\n' for r in rows)},
                        {'historical_manifest': hm, 'current_snapshot_manifest': fm})
    residuals = tmp_path / 'residuals'
    queue = {'audit_id': 'old', 'source_listing_id': '123', 'asking_rent': 5000, 'fitted_rent': 4000,
             'asking_vs_fitted_percent': 25, 'selection_reasons': ['large_positive'], 'current_capture': False}
    publish_bundle(residuals, {'review-queue.jsonl': canonical(queue) + '\n'}, {'dataset_manifest': dm})
    output = tmp_path / 'out'
    args = (dataset, archive, historical, recovery, refresh, output)
    result = run(*args)
    assert result['report']['rows'] == 2
    assert result['report']['captures']['resolved_text_captures'] == 2
    assert result['report']['support']['private']['known_rows'] == 1
    assert result['report']['support']['shared']['categories'] == {'ROOF_DECK': 1}
    assert run(*args) == result
    path.write_bytes(gzip.compress(b'changed body'))
    with pytest.raises(ValueError, match='body hash mismatch'):
        run(*args)


def test_category_union_keeps_positive_scope_changes_and_unknown_codes():
    def capture(types):
        return {'extraction': {'assertions': [
            {'attribute':'private_type','value':value} for value in types]}}
    assert category([], 'private')['category'] is None
    result=category([capture(['BALCONY']),capture(['BALCONY','TERRACE'])], 'private')
    assert result['category']=='BALCONY+TERRACE'
    assert result['reported_type_sets_changed'] is True
    assert category([capture(['BALCONY','UNKNOWN_CODE'])], 'private')['category'] is None
    assert category([capture(['BALCONY'])], 'shared')['category'] is None

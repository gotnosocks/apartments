"""Verified, literal description evidence for reviewed Bayesian source cohorts.

No model fitting, feature promotion, HTML rendering, or network operations.
"""
from __future__ import annotations

import hashlib
import json

from .corrections import canonical
from .pricing import _timestamp
from .research_pipeline import _verified_bundle, digest

_REVIEWED = 'reviewed-bathroom-counts-projection-v1'
_CLEANED = 'reviewed-scope-composition-projection-v2'
_REPORTED = 'reported-bathroom-counts-projection-v1'
_ANALYSIS = 'historical-plus-current-capture-analysis-v1'
_REFRESHED_REVIEW = 'reviewed-capture-refreshed-analysis-v1'
_REFRESHED_ARCHIVE = 'refreshed-fitted-description-archive-v1'


def _records(data):
    # Source literals may contain Unicode line separators; only LF separates JSONL.
    for line in data.decode().split('\n'):
        if line.strip():
            yield json.loads(line)


def _original_manifest(manifest):
    if manifest.get('version') not in {_REVIEWED, _CLEANED}:
        raise ValueError('A reviewed Bayesian source projection is required')
    if manifest['version'] == _CLEANED:
        parent = manifest.get('source_manifest')
        if (not isinstance(parent, dict) or parent.get('version') != _REVIEWED
                or hashlib.sha256((canonical(parent) + '\n').encode()).hexdigest()
                != manifest.get('source_manifest_sha256')):
            raise ValueError('Cleaned dataset source lineage or manifest hash differs')
        manifest = parent
    projection = manifest.get('projection_manifest')
    if not isinstance(projection, dict) or projection.get('version') != _REPORTED:
        raise ValueError('Reviewed bathroom projection lineage is missing')
    decision = manifest.get('decision_manifest', {})
    if 'projection_manifest' in decision and decision['projection_manifest'] != projection:
        raise ValueError('Review decisions bind a different projection')
    original = projection.get('dataset_manifest')
    if not isinstance(original, dict) or original.get('dataset_version') != _ANALYSIS:
        raise ValueError('Original reviewed analysis lineage is missing')
    return original


def load_evidence(dataset, evidence):
    """Return ``{audit_id: [literal capture dictionaries]}`` for surviving rows.

    Both bundles are hash-verified. An explicit projection lineage must reach
    the description archive's exact original dataset manifest. Removed audit IDs
    are filtered; surviving rows must match ad, unit, and typed capture identity.
    Source/recovery/knowledge clocks are validated before any mapping is returned.
    Missing descriptions remain None, never inferred absence of an amenity.
    """
    from .reviewed_cohort_quarantine import SIDECAR
    dataset_manifest, dataset_files = _verified_bundle(dataset, retain={'observations.jsonl', SIDECAR})
    evidence_manifest, evidence_files = _verified_bundle(evidence, retain={'evidence.jsonl'})
    refreshed = evidence_manifest.get('version') == _REFRESHED_ARCHIVE
    if refreshed:
        from .reviewed_source_lineage import manifest_hash, source_lineage
        original = source_lineage(dataset_manifest, list(_records(dataset_files['observations.jsonl'])),
            quarantined=list(_records(dataset_files[SIDECAR])) if SIDECAR in dataset_files else None)
        bound = (original.get('version') == _REFRESHED_REVIEW
                 and evidence_manifest.get('dataset_manifest_sha256') == manifest_hash(original)
                 and evidence_manifest.get('dataset_observations_sha256') == original['files'].get('observations.jsonl'))
    else:
        bound = (evidence_manifest.get('version') in {'fitted-description-archive-v1', 'cohort-outdoor-evidence-v1'}
                 and evidence_manifest.get('dataset_manifest') == _original_manifest(dataset_manifest))
    if not bound:
        raise ValueError('Description archive does not bind the dataset lineage')
    if 'observations.jsonl' not in dataset_files or 'evidence.jsonl' not in evidence_files:
        raise ValueError('Missing verified observation or evidence records')
    rows = {}
    for row in _records(dataset_files['observations.jsonl']):
        key = row.get('audit_id')
        if not isinstance(key, str) or not key or key in rows:
            raise ValueError('Missing or duplicate observation audit ID')
        if (not isinstance(row.get('unit_id'), str) or not row['unit_id']
                or isinstance(row.get('source_listing_id'), bool)
                or not isinstance(row.get('source_listing_id'), (str, int))
                or not str(row['source_listing_id']).isdigit()):
            raise ValueError('Missing or invalid observation ad/unit identity')
        allowed = row.get('capture_ids') or []
        if not isinstance(allowed, list):
            raise ValueError('Invalid observation capture membership')
        allowed = allowed + ([row['capture_id']] if row.get('capture_id') is not None else [])
        if any(isinstance(value, bool) or not isinstance(value, (str, int)) or value in ('', 0)
               for value in allowed if value is not None):
            raise ValueError('Invalid observation capture identity')
        # Typed comparison prevents True/1 and string/integer accidental aliases.
        membership = {(type(value).__name__, value) for value in allowed if value is not None}
        rows[key] = {'unit_id': row['unit_id'], 'source_listing_id': str(row['source_listing_id']),
                     'known_at': _timestamp(row['known_at']), 'capture_membership': membership}
    del dataset_files
    result = {key: [] for key in rows}
    seen = set()
    for capture in _records(evidence_files['evidence.jsonl']):
        key = capture.get('audit_id')
        row = rows.get(key)
        if row is None:
            continue  # Original descriptions for quarantined observations.
        capture_id = capture.get('capture_id')
        typed_id = (type(capture_id).__name__, capture_id)
        identity = (key, typed_id)
        if (capture.get('source_listing_id') != row['source_listing_id']
                or capture.get('unit_id') != row['unit_id']
                or typed_id not in row['capture_membership'] or identity in seen):
            raise ValueError('Description ad/unit/capture identity differs or is duplicated')
        if (refreshed or evidence_manifest['version'] == 'fitted-description-archive-v1') and capture.get('known_at') is None:
            raise ValueError('Description archive is missing its knowledge clock')
        source_at = _timestamp(capture['source_collected_at'])
        known_at = _timestamp(capture['known_at']) if capture.get('known_at') is not None else None
        recovered_at = _timestamp(capture['description_interpreted_at']) if capture.get('description_interpreted_at') else None
        if (source_at > row['known_at'] or (known_at is not None and (source_at > known_at or known_at > row['known_at']))
                or (recovered_at is not None and (recovered_at < source_at or recovered_at > row['known_at']
                                                  or (known_at is not None and recovered_at > known_at)))):
            raise ValueError('Description source/recovery/knowledge clock is inconsistent')
        seen.add(identity)
        text = capture.get('description')
        source_path = capture.get('source_path') or '/description'
        details = capture.get('property_details')
        if isinstance(details, dict) and isinstance(details.get('description'), str):
            text = details['description']
            source_path = '/propertyDetails/description'
        if text is not None and not isinstance(text, str):
            raise ValueError('Description must be literal text or unknown')
        expected = capture.get('description_sha256')
        if expected is not None and (not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != expected):
            raise ValueError('Description literal hash mismatch')
        result[key].append({**{field: capture.get(field) for field in (
            'audit_id', 'capture_id', 'source_listing_id', 'unit_id', 'source_collected_at',
            'description_interpreted_at', 'known_at', 'body_sha256', 'raw_listing_sha256',
            'description_sha256', 'description_source')}, 'description': text, 'source_path': source_path})
    if refreshed:
        for key, row in rows.items():
            if {(type(c['capture_id']).__name__, c['capture_id']) for c in result[key]} != row['capture_membership']:
                raise ValueError('Refreshed description archive has incomplete capture coverage')
    for captures in result.values():
        captures.sort(key=lambda capture: (_timestamp(capture['source_collected_at']), str(capture['capture_id'])))
    return result

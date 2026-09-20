import hashlib
import json

import pytest

from apartments import reviewed_lineage_cache as lineage, reviewed_source_lineage as source


def bundle():
    data = (json.dumps({'audit_id': 'a'}) + '\n').encode()
    return {'version': source.REFRESHED, 'files': {'observations.jsonl': hashlib.sha256(data).hexdigest()}}, {'observations.jsonl': data}


def test_verified_lineage_is_reused_and_returned_as_a_copy(monkeypatch):
    calls = []
    monkeypatch.setattr(lineage, '_VERIFIED', {})
    monkeypatch.setattr(source, 'source_lineage', lambda manifest, rows, **_: calls.append(rows) or {'version': 'root'})
    manifest, files = bundle()
    first = lineage.verified_bundle_lineage(manifest, files)
    first['version'] = 'mutated'
    assert lineage.verified_bundle_lineage(manifest, files) == {'version': 'root'}
    assert calls == [[{'audit_id': 'a'}]]


def test_verified_lineage_rejects_bytes_that_differ_from_manifest(monkeypatch):
    monkeypatch.setattr(lineage, '_VERIFIED', {})
    manifest, files = bundle()
    lineage.verified_bundle_lineage(manifest, files)
    with pytest.raises(ValueError, match='differs from its manifest'):
        lineage.verified_bundle_lineage(manifest, {'observations.jsonl': b'{"audit_id": "b"}\n'})

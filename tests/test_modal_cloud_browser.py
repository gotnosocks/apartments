import importlib.util
import json
from pathlib import Path

import pytest
from streeteasy_archive.store import ArchiveStore


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location('modal_cloud_browser', Path(__file__).parents[1]/'models/modal_cloud_browser.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_authority_preserves_original_and_browser_reads_cloud(module, tmp_path):
    from streeteasy_archive.cloud_state import publish_browser_checkpoint
    source = tmp_path/'snapshots/original'
    store = ArchiveStore(source)
    store.new_generation('backfill'); store.close()
    (source/'complete.json').write_text('{}')
    (tmp_path/'bodies').mkdir()
    pointer = module.initialize(tmp_path, 'original', 'chelsea')
    publish_browser_checkpoint(tmp_path/'crawls/chelsea',tmp_path)
    assert pointer['archive_path'] == 'crawls/chelsea'
    assert module.initialize(tmp_path, 'original', 'chelsea') == pointer
    result = module.respond(tmp_path, '/api/summary')
    assert result['status'] == 200
    summary = json.loads(result['body'])
    assert summary['storage_mode'] == 'cloud'
    assert summary['archive_path'] == 'crawls/chelsea'
    assert summary['local_copy_role'] == 'backup'
    assert summary['writer_running'] is False
    assert module.respond(tmp_path, '/')['status'] == 200
    assert (source/'archive.sqlite3').exists()
    with pytest.raises(ValueError): module.initialize(tmp_path,'original','different')


@pytest.mark.parametrize('path', ['https://example.com','//example.com','/../secret','/api/../secret','/other'])
def test_invalid_browser_requests(module,tmp_path,path):
    with pytest.raises(ValueError): module.respond(tmp_path,path)

import base64
from io import BytesIO

from PIL import Image
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import fetch_floorplan_assets as subject


def response(kind='WEBP'):
    stream = BytesIO()
    Image.new('RGB', (40, 30), 'white').save(stream, format=kind)
    return {'results': [{'status_code': 200, 'content': base64.b64encode(stream.getvalue()).decode()}]}


def references(tmp_path, url='https://photos.zillowstatic.com/fp/abc-full.webp'):
    row = {'source_listing_id': '123', 'audit_id': 'audit', 'capture_id': 'capture',
           'body_sha256': 'body', 'raw_listing_sha256': 'raw',
           'recommended_images': [{'asset_id': 'abc', 'image_url': url,
             'variant': 'full', 'explicit_floorplan_label': 'mediaType=floor_plan'}]}
    root = tmp_path/'references'
    publish_bundle(root, {'selected-comparisons.jsonl': canonical(row)+'\n'}, {'version': 'test'})
    return root


@pytest.mark.parametrize('kind', ['WEBP', 'JPEG', 'PNG'])
def test_supported_images_preserve_exact_bytes(kind):
    envelope = response(kind)
    body, metadata = subject.decode_response(envelope)
    assert body == base64.b64decode(envelope['results'][0]['content'])
    assert metadata['format'] == kind
    assert (metadata['width'], metadata['height']) == (40, 30)


@pytest.mark.parametrize('envelope', [
    {'results': []}, {'results': [{'status_code': 404, 'content': 'abc'}]},
    {'results': [{'status_code': 200, 'content': '<html>denied</html>'}]},
])
def test_failed_or_nonimage_results_rejected(envelope):
    with pytest.raises(ValueError):
        subject.decode_response(envelope)


def test_other_hosts_rejected(tmp_path):
    with pytest.raises(ValueError, match='archived floor-plan URL'):
        subject.targets(references(tmp_path, 'https://other.example/image'), ['123'])


def test_completed_replay_does_not_submit_again(tmp_path, monkeypatch):
    source = references(tmp_path)
    calls = []
    class Reply:
        status_code = 200
        def json(self): return response()
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Reply()
    monkeypatch.setattr(subject.requests, 'post', post)
    monkeypatch.setattr(subject, '_credentials', lambda: ('test', 'test'))
    output = tmp_path/'assets'
    subject.run(source, output, ['123'])
    subject.run(source, output, ['123'])
    assert len(calls) == 1
    assert calls[0]['json']['content_encoding'] == 'base64'
    assert calls[0]['allow_redirects'] is False
    assert (output/'assets/123/floorplan.webp').exists()


def test_uncertain_submission_never_automatically_retried(tmp_path, monkeypatch):
    source = references(tmp_path)
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('private request information')
    monkeypatch.setattr(subject.requests, 'post', post)
    monkeypatch.setattr(subject, '_credentials', lambda: ('test', 'test'))
    output = tmp_path/'assets'
    with pytest.raises(RuntimeError, match='TimeoutError'):
        subject.run(source, output, ['123'])
    with pytest.raises(RuntimeError, match='Prior submission'):
        subject.run(source, output, ['123'])
    assert len(calls) == 1
    assert 'private' not in (output/'assets/123/failure.json').read_text()

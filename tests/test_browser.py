"""Scope regression plus optional real Firefox loopback validation."""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from streeteasy_archive.store import ArchiveStore


def test_claim_building_boundary_and_resume(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    base = 'https://streeteasy.com/building/example'
    store.enqueue(generation, [
        {'url': base + '-other/1', 'kind': 'listing'},
        {'url': base + '/1', 'kind': 'listing'},
        {'url': base, 'kind': 'building'},
    ])
    first = store.claim(generation, url_prefix=base)
    assert first['url'] == base + '/1'
    store.record(generation, first['url'], 200, {}, b'detail')
    assert store.claim(generation, url_prefix=base)['url'] == base
    store.close()
    store = ArchiveStore(tmp_path)
    store.recover_inflight(generation)
    assert store.claim(generation, url_prefix=base)['url'] == base
    assert store.claim(generation, url_prefix=base) is None
    assert store.claim(generation)['url'] == base + '-other/1'
    store.close()


@pytest.mark.skipif(os.environ.get('ARCHIVE_TEST_FIREFOX') != '1', reason='opt-in installed Firefox loopback test')
def test_firefox_entity_conditional_and_redirect():
    from streeteasy_archive.browser import capture_main_document
    class Handler(BaseHTTPRequestHandler):
        seen = []
        body = '<html><body>entity\x00é€<img src="/image"></body></html>'.encode('utf-8')
        def do_GET(self):
            self.seen.append((self.path, self.headers.get('If-None-Match')))
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/forbidden')
            elif self.headers.get('If-None-Match') == '"v1"':
                self.send_response(304)
            else:
                self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('ETag', '"v1"')
            self.end_headers()
            if self.path == '/page' and not self.headers.get('If-None-Match'):
                self.wfile.write(self.body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        first = capture_main_document(base + '/page')
        assert first['status'] == 200
        assert first['body'] == Handler.body
        assert first['rendered_html']
        second = capture_main_document(base + '/page', {'If-None-Match': '"v1"'})
        assert second['status'] == 304 and second['body'] == b''
        redirect = capture_main_document(base + '/redirect')
        assert redirect['status'] == 302
        assert all(path not in ('/forbidden', '/image') for path, _ in Handler.seen)
    finally:
        server.shutdown()
        server.server_close()
